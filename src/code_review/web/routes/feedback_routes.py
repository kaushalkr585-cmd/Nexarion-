from __future__ import annotations

import hashlib
import logging
import math
import time
from collections import defaultdict
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from code_review.db.database import get_db
from code_review.db.models import ConversationRecord, FeedbackRecord, UserRecord, utc_now
from code_review.services.email_service import send_feedback_notification
from code_review.web.auth import get_current_admin_user, get_current_user
from code_review.web.schemas import (
    FEEDBACK_CATEGORIES,
    FeedbackCreateRequest,
    FeedbackListResponse,
    FeedbackResponse,
    FeedbackStatsResponse,
    FeedbackStatusUpdateRequest,
    FeedbackUserSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Feedback"])

# Simple in-memory sliding window rate limiter: user_id -> list of timestamps
_RATE_LIMIT_BUCKETS: dict[str, list[float]] = defaultdict(list)
_MAX_FEEDBACK_PER_WINDOW = 15
_WINDOW_SECONDS = 300  # 5 minutes


def _check_rate_limit(user_id: str) -> None:
    now = time.time()
    cutoff = now - _WINDOW_SECONDS
    timestamps = [t for t in _RATE_LIMIT_BUCKETS[user_id] if t > cutoff]
    if len(timestamps) >= _MAX_FEEDBACK_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many feedback submissions. Please wait a few minutes before submitting again.",
        )
    timestamps.append(now)
    _RATE_LIMIT_BUCKETS[user_id] = timestamps


def _build_feedback_response(record: FeedbackRecord) -> FeedbackResponse:
    user_summary: FeedbackUserSummary | None = None
    if record.user:
        user_summary = FeedbackUserSummary(
            id=record.user.id,
            name=record.user.name,
            email=record.user.email,
            avatar_url=record.user.avatar_url,
            role=record.user.role,
        )

    return FeedbackResponse(
        id=record.id,
        user_id=record.user_id,
        user=user_summary,
        conversation_id=record.conversation_id,
        message_id=record.message_id,
        conversation_ref=record.conversation_ref,
        message_ref=record.message_ref,
        conversation_title=record.conversation_title,
        category=record.category,
        details=record.details,
        reported_response=record.reported_response,
        status=record.status,
        email_notification_status=record.email_notification_status,
        email_error=record.email_error,
        email_message_id=record.email_message_id,
        email_sent_at=record.email_sent_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit user feedback on an AI response",
)
def submit_feedback(
    payload: FeedbackCreateRequest,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FeedbackResponse:
    # 1. Rate limiting
    _check_rate_limit(current_user.id)

    # 2. Category validation
    category_clean = payload.category.strip()
    if category_clean not in FEEDBACK_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid feedback category. Must be one of: {', '.join(FEEDBACK_CATEGORIES)}",
        )

    logger.info(
        "[FEEDBACK_RECEIVED] User %s (%s) submitted category='%s' conv_id='%s' msg_id='%s'",
        current_user.id,
        current_user.email,
        category_clean,
        payload.conversation_id,
        payload.message_id,
    )

    # 3. Deduplication key (sha256 of user_id, conversation_id, message_id, category)
    conv_id = (payload.conversation_id or "").strip() or None
    msg_id = (payload.message_id or "").strip() or None
    dedupe_key = hashlib.sha256(
        f"{current_user.id}:{conv_id}:{msg_id}:{category_clean}".encode()
    ).hexdigest()[:64]

    # Check if duplicate submitted recently (within last 60 seconds)
    recent_cutoff = utc_now() - timedelta(seconds=60)
    existing = db.scalar(
        select(FeedbackRecord)
        .options(selectinload(FeedbackRecord.user))
        .where(
            FeedbackRecord.dedupe_key == dedupe_key,
            FeedbackRecord.created_at >= recent_cutoff,
        )
    )
    if existing:
        logger.info(
            "Duplicate feedback submission detected for user %s within 60s, returning existing record %s",
            current_user.id,
            existing.id,
        )
        if payload.details and payload.details.strip():
            existing.details = payload.details.strip()
            db.commit()
            db.refresh(existing)
        return _build_feedback_response(existing)

    # 4. Safe conversation and message reference resolution
    valid_conv_id: str | None = None
    conv_title: str | None = None
    if conv_id:
        conversation = db.scalar(
            select(ConversationRecord).where(ConversationRecord.id == conv_id)
        )
        if conversation:
            valid_conv_id = conversation.id
            conv_title = conversation.title

    valid_msg_id: str | None = None
    if msg_id:
        from code_review.db.models import MessageRecord

        message_rec = db.scalar(select(MessageRecord).where(MessageRecord.id == msg_id))
        if message_rec:
            valid_msg_id = message_rec.id

    # 5. Persist FeedbackRecord
    record = FeedbackRecord(
        user_id=current_user.id,
        conversation_id=valid_conv_id,
        message_id=valid_msg_id,
        conversation_ref=conv_id or "direct",
        message_ref=msg_id or "direct",
        conversation_title=conv_title,
        category=category_clean,
        details=payload.details.strip() if payload.details else None,
        reported_response=payload.reported_response.strip(),
        status="new",
        email_notification_status="pending",
        dedupe_key=dedupe_key,
    )
    record.user = current_user

    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception as exc:
        db.rollback()
        logger.error("[FEEDBACK_SAVE_ERROR] Failed to persist feedback: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save feedback. Please try again.",
        )

    logger.info(
        "[FEEDBACK_SAVED] Feedback record %s persisted successfully (status=%s, email_status=%s)",
        record.id,
        record.status,
        record.email_notification_status,
    )

    # 6. Deliver email notification via Resend
    email_data = {
        "category": record.category,
        "details": record.details,
        "user_name": current_user.name,
        "user_email": current_user.email,
        "user_id": current_user.id,
        "conversation_id": record.conversation_ref,
        "conversation_title": record.conversation_title,
        "message_id": record.message_ref,
        "reported_response": record.reported_response,
        "created_at": record.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
    }

    try:
        success, email_msg_id, email_err = send_feedback_notification(email_data)
        if success:
            record.email_notification_status = "sent"
            record.email_message_id = email_msg_id
            record.email_sent_at = utc_now()
            logger.info(
                "[FEEDBACK_EMAIL_STATUS] Feedback %s email notification status updated to 'sent' (email_id=%s)",
                record.id,
                email_msg_id,
            )
        else:
            record.email_notification_status = "failed"
            record.email_error = (email_err or "Delivery failed")[:500]
            logger.warning(
                "[FEEDBACK_EMAIL_STATUS] Feedback %s email notification status updated to 'failed': %s",
                record.id,
                record.email_error,
            )

        db.commit()
        db.refresh(record)
    except Exception as exc:
        db.rollback()
        logger.error(
            "[FEEDBACK_EMAIL_UPDATE_ERROR] Error updating email status for record %s: %s",
            record.id,
            exc,
            exc_info=True,
        )

    return _build_feedback_response(record)


@router.get(
    "/admin/feedback",
    response_model=FeedbackListResponse,
    summary="List feedback reports (Admin only)",
)
def list_feedback_reports(
    current_admin: Annotated[UserRecord, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = Query(None),
    email_status: str | None = Query(None),
    search: str | None = Query(None),
) -> FeedbackListResponse:
    query = select(FeedbackRecord).options(selectinload(FeedbackRecord.user))

    # Filters
    if status_filter and status_filter.lower() != "all":
        query = query.where(FeedbackRecord.status == status_filter.lower())

    if category and category.lower() != "all":
        query = query.where(FeedbackRecord.category == category)

    if email_status and email_status.lower() != "all":
        query = query.where(FeedbackRecord.email_notification_status == email_status.lower())

    if search and search.strip():
        search_pattern = f"%{search.strip()}%"
        query = query.outerjoin(UserRecord, FeedbackRecord.user_id == UserRecord.id).where(
            or_(
                FeedbackRecord.details.ilike(search_pattern),
                FeedbackRecord.reported_response.ilike(search_pattern),
                FeedbackRecord.conversation_title.ilike(search_pattern),
                FeedbackRecord.conversation_ref.ilike(search_pattern),
                UserRecord.email.ilike(search_pattern),
                UserRecord.name.ilike(search_pattern),
            )
        )

    # Count total
    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = db.scalar(count_query) or 0

    # Pagination & Ordering
    offset = (page - 1) * limit
    items = db.scalars(
        query.order_by(FeedbackRecord.created_at.desc()).offset(offset).limit(limit)
    ).all()

    pages = max(1, math.ceil(total / limit)) if total > 0 else 1

    return FeedbackListResponse(
        items=[_build_feedback_response(item) for item in items],
        total=total,
        page=page,
        limit=limit,
        pages=pages,
    )


@router.get(
    "/admin/feedback/stats",
    response_model=FeedbackStatsResponse,
    summary="Get feedback overview counts and metrics (Admin only)",
)
def get_feedback_stats(
    current_admin: Annotated[UserRecord, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FeedbackStatsResponse:
    total = db.scalar(select(func.count(FeedbackRecord.id))) or 0
    new_count = (
        db.scalar(select(func.count(FeedbackRecord.id)).where(FeedbackRecord.status == "new")) or 0
    )
    reviewing_count = (
        db.scalar(
            select(func.count(FeedbackRecord.id)).where(FeedbackRecord.status == "reviewing")
        )
        or 0
    )
    resolved_count = (
        db.scalar(select(func.count(FeedbackRecord.id)).where(FeedbackRecord.status == "resolved"))
        or 0
    )
    failed_emails = (
        db.scalar(
            select(func.count(FeedbackRecord.id)).where(
                FeedbackRecord.email_notification_status == "failed"
            )
        )
        or 0
    )

    return FeedbackStatsResponse(
        total=total,
        new_count=new_count,
        reviewing_count=reviewing_count,
        resolved_count=resolved_count,
        failed_emails=failed_emails,
    )


@router.get(
    "/admin/feedback/{feedback_id}",
    response_model=FeedbackResponse,
    summary="Get single feedback report detail (Admin only)",
)
def get_feedback_detail(
    feedback_id: str,
    current_admin: Annotated[UserRecord, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FeedbackResponse:
    record = db.scalar(
        select(FeedbackRecord)
        .options(selectinload(FeedbackRecord.user))
        .where(FeedbackRecord.id == feedback_id)
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback report '{feedback_id}' not found",
        )

    return _build_feedback_response(record)


@router.patch(
    "/admin/feedback/{feedback_id}/status",
    response_model=FeedbackResponse,
    summary="Update feedback resolution status (Admin only)",
)
def update_feedback_status(
    feedback_id: str,
    payload: FeedbackStatusUpdateRequest,
    current_admin: Annotated[UserRecord, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FeedbackResponse:
    record = db.scalar(
        select(FeedbackRecord)
        .options(selectinload(FeedbackRecord.user))
        .where(FeedbackRecord.id == feedback_id)
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback report '{feedback_id}' not found",
        )

    record.status = payload.status
    record.updated_at = utc_now()

    db.commit()
    db.refresh(record)

    return _build_feedback_response(record)
