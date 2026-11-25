from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from code_review.crypto import decrypt_secret, encrypt_secret
from code_review.db.database import get_engine
from code_review.db.models import Base, GitHubConnectionRecord, UserRecord
from code_review.github.service import GitHubAuthError, GitHubService

logger = logging.getLogger(__name__)
_GITHUB_TABLES_VERIFIED = False


def ensure_github_tables() -> None:
    """Create new GitHub integration tables if app lifespan hasn't run yet (e.g. TestClient)."""
    global _GITHUB_TABLES_VERIFIED
    if _GITHUB_TABLES_VERIFIED:
        return
    try:
        engine = get_engine()
        Base.metadata.create_all(
            bind=engine,
            tables=[
                Base.metadata.tables["github_connections"],
                Base.metadata.tables["conversation_repository_contexts"],
            ],
            checkfirst=True,
        )
        _GITHUB_TABLES_VERIFIED = True
    except Exception as exc:
        logger.debug("Could not auto-ensure GitHub tables: %s", exc)


@dataclass
class ResolvedGitHubAuth:
    user_id: str | None
    connected: bool
    auth_method: str  # "github_app" | "oauth" | "pat" | "none"
    username: str | None
    token: str | None
    installation_id: str | None
    connection_status: (
        str  # "connected" | "expired" | "revoked" | "disconnected" | "not_connected"
    )
    cache_scope: str


def _parse_iso_expiry(raw_iso: str | None) -> datetime | None:
    if not raw_iso:
        return None
    try:
        return datetime.fromisoformat(raw_iso.replace("Z", "+00:00"))
    except Exception:
        return None


def resolve_user_github_context(
    db: Session,
    user: UserRecord | None,
) -> ResolvedGitHubAuth:
    """
    Resolve active GitHub credentials for a user without leaking tokens to callers.
    Prefers GitHubConnectionRecord (GitHub App installation token with auto-renewal),
    and preserves full backward compatibility with legacy UserRecord.github_token.
    """
    if not user:
        return ResolvedGitHubAuth(
            user_id=None,
            connected=False,
            auth_method="none",
            username=None,
            token=None,
            installation_id=None,
            connection_status="not_connected",
            cache_scope="public",
        )

    try:
        ensure_github_tables()
        conn = (
            db.query(GitHubConnectionRecord)
            .filter(GitHubConnectionRecord.user_id == user.id)
            .order_by(GitHubConnectionRecord.updated_at.desc())
            .first()
        )
    except SQLAlchemyError as exc:
        logger.warning("GitHubConnectionRecord lookup failed (%s); falling back cleanly.", exc)
        db.rollback()
        conn = None

    if conn:
        if conn.connection_status in ("disconnected", "revoked"):
            return ResolvedGitHubAuth(
                user_id=user.id,
                connected=False,
                auth_method=conn.auth_method,
                username=conn.github_username,
                token=None,
                installation_id=conn.installation_id,
                connection_status=conn.connection_status,
                cache_scope=f"user:{user.id}",
            )

        # GitHub App installation access token flow with automatic renewal
        if conn.auth_method == "github_app" and conn.installation_id:
            now = datetime.now(UTC)
            token = decrypt_secret(conn.encrypted_access_token)
            expires_at = conn.token_expires_at
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)

            needs_refresh = not token or not expires_at or expires_at <= now + timedelta(minutes=2)
            if needs_refresh:
                svc = GitHubService()
                try:
                    token_data = svc.create_installation_access_token(conn.installation_id)
                    new_token = token_data.get("token")
                    if not new_token:
                        raise GitHubAuthError("GitHub App returned an empty installation token.")
                    new_expiry = _parse_iso_expiry(token_data.get("expires_at"))
                    conn.encrypted_access_token = encrypt_secret(new_token)
                    conn.token_expires_at = new_expiry
                    conn.permissions_json = token_data.get("permissions") or conn.permissions_json
                    conn.connection_status = "connected"
                    user.github_connected = True
                    user.github_token = new_token
                    if conn.github_username:
                        user.github_username = conn.github_username
                    db.commit()
                    token = new_token
                except GitHubAuthError as auth_err:
                    logger.warning(
                        "GitHub App installation %s renewal failed for user %s: %s",
                        conn.installation_id,
                        user.id,
                        auth_err,
                    )
                    conn.connection_status = (
                        "revoked" if auth_err.status_code in (401, 403, 404) else "expired"
                    )
                    user.github_connected = False
                    db.commit()
                    return ResolvedGitHubAuth(
                        user_id=user.id,
                        connected=False,
                        auth_method="github_app",
                        username=conn.github_username,
                        token=None,
                        installation_id=conn.installation_id,
                        connection_status=conn.connection_status,
                        cache_scope=f"user:{user.id}",
                    )
                except Exception as exc:
                    logger.error("Unexpected error renewing installation token: %s", exc)
                    if not token:
                        return ResolvedGitHubAuth(
                            user_id=user.id,
                            connected=False,
                            auth_method="github_app",
                            username=conn.github_username,
                            token=None,
                            installation_id=conn.installation_id,
                            connection_status="expired",
                            cache_scope=f"user:{user.id}",
                        )

            return ResolvedGitHubAuth(
                user_id=user.id,
                connected=True,
                auth_method="github_app",
                username=conn.github_username,
                token=token,
                installation_id=conn.installation_id,
                connection_status="connected",
                cache_scope=f"user:{user.id}",
            )

        # OAuth or PAT stored encrypted inside GitHubConnectionRecord
        decrypted = decrypt_secret(conn.encrypted_access_token)
        if decrypted:
            return ResolvedGitHubAuth(
                user_id=user.id,
                connected=True,
                auth_method=conn.auth_method,
                username=conn.github_username or user.github_username,
                token=decrypted,
                installation_id=conn.installation_id,
                connection_status="connected",
                cache_scope=f"user:{user.id}",
            )

    # Backward compatibility with legacy UserRecord.github_token
    if user.github_connected and user.github_token:
        legacy_token = decrypt_secret(user.github_token) or user.github_token
        return ResolvedGitHubAuth(
            user_id=user.id,
            connected=True,
            auth_method="pat",
            username=user.github_username,
            token=legacy_token,
            installation_id=None,
            connection_status="connected",
            cache_scope=f"user:{user.id}",
        )

    return ResolvedGitHubAuth(
        user_id=user.id,
        connected=False,
        auth_method="none",
        username=user.github_username,
        token=None,
        installation_id=None,
        connection_status="not_connected",
        cache_scope=f"user:{user.id}",
    )


def mark_connection_revoked_or_expired(
    db: Session, user: UserRecord | None, status_name: str = "revoked"
) -> None:
    if not user:
        return
    try:
        ensure_github_tables()
        conn = (
            db.query(GitHubConnectionRecord)
            .filter(GitHubConnectionRecord.user_id == user.id)
            .order_by(GitHubConnectionRecord.updated_at.desc())
            .first()
        )
    except SQLAlchemyError as exc:
        logger.warning("GitHubConnectionRecord lookup failed (%s); falling back cleanly.", exc)
        db.rollback()
        conn = None
    if conn:
        conn.connection_status = status_name
    user.github_connected = False
    db.commit()
