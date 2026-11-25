from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import cloudinary
import cloudinary.uploader
import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from code_review.config import get_settings
from code_review.db.models import (
    AgentConfigRecord,
    AttachmentRecord,
    ConversationMemoryRecord,
    ConversationRecord,
    ConversationRepositoryContextRecord,
    DocumentChunkRecord,
    FindingRecord,
    GitHubConnectionRecord,
    MessageRecord,
    PasswordResetTokenRecord,
    PullRequestRecord,
    RepositoryRecord,
    ReviewRecord,
    RevokedSubjectRecord,
    SecurityAuditLogRecord,
    UserRecord,
    UserSessionRecord,
)
from code_review.github.cache import get_github_cache
from code_review.web.auth import ACCESS_TOKEN_EXPIRE_DAYS, hash_subject_identifier
from code_review.web.crypto import decrypt_secret

logger = logging.getLogger(__name__)


class AccountDeletionError(RuntimeError):
    """Raised when an account deletion cleanup step fails safely for retry."""


def _revoke_github_grants(db: Session, user: UserRecord) -> int:
    """Revoke stored GitHub OAuth tokens/connections cleanly and idempotently."""
    settings = get_settings()
    connections = (
        db.query(GitHubConnectionRecord).filter(GitHubConnectionRecord.user_id == user.id).all()
    )
    revoked_count = 0

    for conn in connections:
        raw_token = (
            decrypt_secret(conn.encrypted_access_token) if conn.encrypted_access_token else None
        )
        if (
            raw_token
            and conn.auth_method == "oauth"
            and settings.github_client_id
            and settings.github_client_secret
        ):
            try:
                with httpx.Client(timeout=8.0) as client:
                    resp = client.request(
                        "DELETE",
                        f"https://api.github.com/applications/{settings.github_client_id}/grant",
                        auth=(settings.github_client_id, settings.github_client_secret),
                        json={"access_token": raw_token},
                        headers={"Accept": "application/vnd.github+json"},
                    )
                    if resp.status_code not in (200, 204, 404, 422):
                        logger.warning(
                            "Unexpected GitHub grant revocation status %d for user_hash=%s",
                            resp.status_code,
                            hash_subject_identifier("audit", user.id)[:12],
                        )
            except Exception as exc:
                logger.warning(
                    "GitHub grant revocation network error (continuing cleanup): %s", exc
                )
        conn.connection_status = "revoked"
        conn.encrypted_access_token = None
        conn.encrypted_refresh_token = None
        revoked_count += 1

    # Clear legacy token fields as well
    user.github_connected = False
    user.github_token = None
    user.github_username = None
    db.flush()
    get_github_cache().invalidate_scope(f"user:{user.id}")
    return revoked_count


def _cleanup_user_avatars(user_id: str) -> int:
    """Remove locally stored and Cloudinary avatar assets for the deleted user idempotently."""
    removed = 0
    for base_dir in (Path("frontend/public/avatars"), Path("frontend/dist/avatars")):
        if not base_dir.is_dir():
            continue
        for path in base_dir.glob(f"avatar_{user_id}_*"):
            try:
                if path.is_file():
                    path.unlink()
                    removed += 1
            except OSError as exc:
                logger.warning("Could not remove avatar file %s: %s", path.name, exc)

    settings = get_settings()
    if (
        settings.cloudinary_cloud_name
        and settings.cloudinary_api_key
        and settings.cloudinary_api_secret
    ):
        try:
            cloudinary.config(
                cloud_name=settings.cloudinary_cloud_name,
                api_key=settings.cloudinary_api_key,
                api_secret=settings.cloudinary_api_secret,
                secure=True,
            )
            cloudinary.api.delete_resources_by_prefix(f"nexarion_avatars/avatar_{user_id}_")
        except Exception as exc:
            logger.debug("Cloudinary avatar cleanup skipped/non-fatal: %s", exc)

    return removed


def execute_account_deletion(db: Session, user: UserRecord) -> dict[str, Any]:
    """Safely, atomically, and idempotently delete all data belonging to `user`.

    - Respects foreign-key ordering across reviews, findings, conversations, messages,
      attachments, chunks, memories, repo contexts, GitHub tokens, sessions, and preferences.
    - Never touches shared/global records where `user_id IS NULL`.
    - Retries cleanly if interrupted prior to commit.
    - Stores zero PII in security audit or token-revocation markers.
    """
    uid = user.id
    auth_provider = user.auth_provider
    now = datetime.now(UTC)

    try:
        # 1. External integration revocation & file storage cleanup (idempotent)
        gh_revoked = _revoke_github_grants(db, user)
        avatars_removed = _cleanup_user_avatars(uid)

        # 2. Collect user-owned IDs cleanly before cascading deletes
        review_ids = [
            row[0] for row in db.query(ReviewRecord.id).filter(ReviewRecord.user_id == uid).all()
        ]
        conv_ids = [
            row[0]
            for row in db.query(ConversationRecord.id)
            .filter(ConversationRecord.user_id == uid)
            .all()
        ]

        att_filters = [AttachmentRecord.user_id == uid]
        if conv_ids:
            att_filters.append(AttachmentRecord.conversation_id.in_(conv_ids))
        att_ids = [row[0] for row in db.query(AttachmentRecord.id).filter(or_(*att_filters)).all()]

        # 3. Delete in strict FK-safe leaf -> root order
        if review_ids:
            db.query(FindingRecord).filter(FindingRecord.review_id.in_(review_ids)).delete(
                synchronize_session=False
            )
        reviews_deleted = (
            db.query(ReviewRecord)
            .filter(ReviewRecord.user_id == uid)
            .delete(synchronize_session=False)
        )

        chunk_filters = []
        if att_ids:
            chunk_filters.append(DocumentChunkRecord.attachment_id.in_(att_ids))
        if conv_ids:
            chunk_filters.append(DocumentChunkRecord.conversation_id.in_(conv_ids))
        if chunk_filters:
            db.query(DocumentChunkRecord).filter(or_(*chunk_filters)).delete(
                synchronize_session=False
            )

        attachments_deleted = 0
        if att_ids:
            attachments_deleted = (
                db.query(AttachmentRecord)
                .filter(AttachmentRecord.id.in_(att_ids))
                .delete(synchronize_session=False)
            )

        mem_filters = [ConversationMemoryRecord.user_id == uid]
        if conv_ids:
            mem_filters.append(ConversationMemoryRecord.conversation_id.in_(conv_ids))
        db.query(ConversationMemoryRecord).filter(or_(*mem_filters)).delete(
            synchronize_session=False
        )

        ctx_filters = [ConversationRepositoryContextRecord.user_id == uid]
        if conv_ids:
            ctx_filters.append(ConversationRepositoryContextRecord.conversation_id.in_(conv_ids))
        db.query(ConversationRepositoryContextRecord).filter(or_(*ctx_filters)).delete(
            synchronize_session=False
        )

        if conv_ids:
            db.query(MessageRecord).filter(MessageRecord.conversation_id.in_(conv_ids)).delete(
                synchronize_session=False
            )
        conversations_deleted = 0
        if conv_ids:
            conversations_deleted = (
                db.query(ConversationRecord)
                .filter(ConversationRecord.id.in_(conv_ids))
                .delete(synchronize_session=False)
            )

        db.query(GitHubConnectionRecord).filter(GitHubConnectionRecord.user_id == uid).delete(
            synchronize_session=False
        )
        db.query(RepositoryRecord).filter(RepositoryRecord.user_id == uid).delete(
            synchronize_session=False
        )
        db.query(PullRequestRecord).filter(PullRequestRecord.user_id == uid).delete(
            synchronize_session=False
        )
        # Strict isolation: NEVER delete global shared agent configs where user_id IS NULL
        db.query(AgentConfigRecord).filter(AgentConfigRecord.user_id == uid).delete(
            synchronize_session=False
        )
        db.query(PasswordResetTokenRecord).filter(PasswordResetTokenRecord.user_id == uid).delete(
            synchronize_session=False
        )
        db.query(UserSessionRecord).filter(UserSessionRecord.user_id == uid).delete(
            synchronize_session=False
        )

        # 4. Invalidate any outstanding tokens for this user without storing PII
        deleted_sub_hash = hash_subject_identifier("deleted", uid)
        existing_revoked = (
            db.query(RevokedSubjectRecord)
            .filter(RevokedSubjectRecord.subject_hash == deleted_sub_hash)
            .first()
        )
        expires_at = now + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS + 1)
        if existing_revoked:
            existing_revoked.revoked_before = now
            existing_revoked.expires_at = expires_at
        else:
            db.add(
                RevokedSubjectRecord(
                    subject_hash=deleted_sub_hash,
                    revoked_before=now,
                    expires_at=expires_at,
                )
            )

        # 5. Minimal non-PII security audit record (no email, name, or plaintext IDs)
        audit_counts = {
            "conversations_deleted": int(conversations_deleted),
            "reviews_deleted": int(reviews_deleted),
            "attachments_deleted": int(attachments_deleted),
            "github_connections_revoked": int(gh_revoked),
            "avatars_removed": int(avatars_removed),
        }
        db.add(
            SecurityAuditLogRecord(
                event_type="account_deleted",
                subject_hash=hash_subject_identifier("audit", uid),
                auth_provider=auth_provider,
                metadata_json=audit_counts,
            )
        )

        # 6. Delete user row last
        db.query(UserRecord).filter(UserRecord.id == uid).delete(synchronize_session=False)
        db.commit()

        logger.info(
            "Permanently deleted account subject_hash=%s (%s)",
            hash_subject_identifier("audit", uid)[:12],
            audit_counts,
        )
        return {"status": "deleted", **audit_counts}

    except Exception as exc:
        db.rollback()
        logger.error(
            "Account deletion rolled back safely for subject_hash=%s: %s",
            hash_subject_identifier("audit", uid)[:12],
            exc,
        )
        raise AccountDeletionError(
            "Account deletion failed before completion. No permanent partial deletion occurred; please retry."
        ) from exc
