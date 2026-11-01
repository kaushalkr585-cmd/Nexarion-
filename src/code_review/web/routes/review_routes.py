from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload, load_only

from code_review.agents.registry import get_persisted_enabled_agent_ids
from code_review.config import get_settings
from code_review.db.database import get_db
from code_review.db.models import AgentConfigRecord, FindingRecord, ReviewRecord, UserRecord
from code_review.orchestrator import ReviewOrchestrator
from code_review.web.auth import get_current_user_optional
from code_review.web.schemas import (
    FindingResponse,
    ReviewCreateRequest,
    ReviewDetailResponse,
    ReviewSummaryResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.post("", response_model=ReviewDetailResponse)
def create_review(
    payload: ReviewCreateRequest,
    db: Session = Depends(get_db),
    user: UserRecord | None = Depends(get_current_user_optional),
) -> ReviewDetailResponse:
    settings = get_settings()
    raw_provider = (payload.provider or settings.llm_provider).lower().strip()
    if raw_provider in ("nvidia", "llm"):
        provider = "llm"
        model_name = settings.nvidia_model
    elif raw_provider == "ollama":
        provider = "ollama"
        model_name = settings.ollama_model
    else:
        provider = "llm"
        model_name = settings.nvidia_model

    start_time = time.perf_counter()

    persisted_configs = db.query(AgentConfigRecord).all()
    if persisted_configs:
        persisted_enabled = {c.agent_id.lower().strip() for c in persisted_configs if c.is_enabled}
    else:
        persisted_enabled = get_persisted_enabled_agent_ids(db)

    # Backend validation: enforce that disabled agents can NEVER be executed,
    # even if requested by an outdated client payload
    if payload.agents is not None:
        requested = {a.lower().strip() for a in payload.agents}
        effective_enabled = persisted_enabled & requested
    else:
        effective_enabled = persisted_enabled

    include_llm = payload.include_llm and bool(
        {"documentation", "test", "llm"} & effective_enabled
    )
    include_semantic = "semantic" in effective_enabled

    orchestrator = ReviewOrchestrator(
        enabled_agent_ids=effective_enabled,
        include_semantic=include_semantic,
        include_llm=include_llm,
        llm_provider=provider,
        parallel=True,
    )

    try:
        result = orchestrator.review_diff(payload.diff_text)
    except Exception as exc:
        logger.error("Review orchestration failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Review execution failed: {exc}",
        ) from exc

    duration = round(time.perf_counter() - start_time, 2)
    agents_used = [str(getattr(a, "name", "agent")) for a in orchestrator.agents]

    review = ReviewRecord(
        user_id=user.id if user else None,
        repository_name=payload.repository_name,
        pr_identifier=payload.pr_identifier,
        title=payload.title,
        diff_content=payload.diff_text,
        provider=provider,
        model_name=model_name,
        agents_used=agents_used,
        finding_count=result.total_findings,
        has_critical=result.has_critical,
        duration_seconds=duration,
    )
    db.add(review)
    db.flush()

    created_findings: list[FindingRecord] = []
    for f in result.findings:
        finding_record = FindingRecord(
            review_id=review.id,
            agent=f.agent.value,
            title=f.message[:120],
            description=f.message,
            severity=f.severity.value.upper(),
            category=f.category.value.upper(),
            file_path=f.file,
            line_start=f.line,
            line_end=f.line,
            suggested_fix=f.suggestion,
            rule_id=f.rule_id,
            evidence=f.file,
        )
        db.add(finding_record)
        created_findings.append(finding_record)

    db.commit()
    db.refresh(review)

    return ReviewDetailResponse(
        id=review.id,
        repository_name=review.repository_name,
        pr_identifier=review.pr_identifier,
        title=review.title,
        provider="llm" if str(review.provider).lower() in ("nvidia", "llm") else review.provider,
        model_name=review.model_name,
        agents_used=review.agents_used,
        finding_count=review.finding_count,
        has_critical=review.has_critical,
        duration_seconds=review.duration_seconds,
        created_at=review.created_at,
        diff_content=review.diff_content,
        findings=[FindingResponse.model_validate(f) for f in created_findings],
    )


@router.get("", response_model=list[ReviewSummaryResponse])
def list_reviews(
    search: str | None = Query(None),
    repository: str | None = Query(None),
    agent: str | None = Query(None),
    db: Session = Depends(get_db),
    user: UserRecord | None = Depends(get_current_user_optional),
) -> list[ReviewSummaryResponse]:
    if not user:
        return []

    query = (
        db.query(ReviewRecord)
        .options(
            load_only(
                ReviewRecord.id,
                ReviewRecord.user_id,
                ReviewRecord.repository_name,
                ReviewRecord.pr_identifier,
                ReviewRecord.title,
                ReviewRecord.provider,
                ReviewRecord.model_name,
                ReviewRecord.agents_used,
                ReviewRecord.finding_count,
                ReviewRecord.has_critical,
                ReviewRecord.duration_seconds,
                ReviewRecord.created_at,
            )
        )
        .filter(ReviewRecord.user_id == user.id)
        .order_by(ReviewRecord.created_at.desc())
    )

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            ReviewRecord.title.ilike(search_term) | ReviewRecord.repository_name.ilike(search_term)
        )

    if repository and repository.lower() != "all":
        query = query.filter(ReviewRecord.repository_name == repository)

    reviews = query.limit(50).all()
    summaries = []
    for r in reviews:
        summary = ReviewSummaryResponse.model_validate(r)
        if str(summary.provider).lower() in ("nvidia", "llm"):
            summary.provider = "llm"
        summaries.append(summary)
    return summaries


@router.get("/{review_id}", response_model=ReviewDetailResponse)
def get_review(
    review_id: str,
    db: Session = Depends(get_db),
    user: UserRecord | None = Depends(get_current_user_optional),
) -> ReviewDetailResponse:
    query = (
        db.query(ReviewRecord)
        .options(joinedload(ReviewRecord.findings))
        .filter(ReviewRecord.id == review_id)
    )
    if user:
        query = query.filter(ReviewRecord.user_id == user.id)
    else:
        query = query.filter(ReviewRecord.user_id.is_(None))

    review = query.first()
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review '{review_id}' not found.",
        )

    return ReviewDetailResponse(
        id=review.id,
        repository_name=review.repository_name,
        pr_identifier=review.pr_identifier,
        title=review.title,
        provider="llm" if str(review.provider).lower() in ("nvidia", "llm") else review.provider,
        model_name=review.model_name,
        agents_used=review.agents_used,
        finding_count=review.finding_count,
        has_critical=review.has_critical,
        duration_seconds=review.duration_seconds,
        created_at=review.created_at,
        diff_content=review.diff_content,
        findings=[FindingResponse.model_validate(f) for f in review.findings],
    )


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(
    review_id: str,
    db: Session = Depends(get_db),
    user: UserRecord | None = Depends(get_current_user_optional),
) -> None:
    query = db.query(ReviewRecord).filter(ReviewRecord.id == review_id)
    if user:
        query = query.filter(ReviewRecord.user_id == user.id)
    else:
        query = query.filter(ReviewRecord.user_id.is_(None))

    review = query.first()
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review '{review_id}' not found.",
        )

    db.query(FindingRecord).filter(FindingRecord.review_id == review.id).delete(
        synchronize_session=False
    )
    db.delete(review)
    db.commit()
    logger.info(
        "Successfully deleted review %s and its findings for user %s",
        review_id,
        user.id if user else "guest",
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_reviews(
    db: Session = Depends(get_db),
    user: UserRecord | None = Depends(get_current_user_optional),
) -> None:
    if user:
        user_reviews = db.query(ReviewRecord).filter(ReviewRecord.user_id == user.id).all()
        review_ids = [r.id for r in user_reviews]
        if review_ids:
            db.query(FindingRecord).filter(FindingRecord.review_id.in_(review_ids)).delete(
                synchronize_session=False
            )
            db.query(ReviewRecord).filter(ReviewRecord.user_id == user.id).delete(
                synchronize_session=False
            )
            db.commit()
        logger.info("Cleared %d reviews for user %s", len(review_ids), user.id)
    else:
        anon_reviews = db.query(ReviewRecord).filter(ReviewRecord.user_id.is_(None)).all()
        review_ids = [r.id for r in anon_reviews]
        if review_ids:
            db.query(FindingRecord).filter(FindingRecord.review_id.in_(review_ids)).delete(
                synchronize_session=False
            )
            db.query(ReviewRecord).filter(ReviewRecord.user_id.is_(None)).delete(
                synchronize_session=False
            )
            db.commit()
        logger.info("Cleared %d anonymous reviews", len(review_ids))
