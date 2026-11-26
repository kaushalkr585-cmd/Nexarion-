from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from code_review.config import get_settings
from code_review.db.database import get_db
from code_review.db.models import RevokedSubjectRecord, UserRecord, UserSessionRecord

logger = logging.getLogger(__name__)

security_bearer = HTTPBearer(auto_error=False)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7
REAUTH_TOKEN_EXPIRE_SECONDS = 300
_BSHA256_PREFIX = "bsha256$"


def hash_subject_identifier(namespace: str, user_id: str) -> str:
    return hashlib.sha256(f"{namespace}:{user_id}".encode()).hexdigest()


def _prehash_password(password: str) -> bytes:
    """SHA-256 + base64 pre-hash so bcrypt cleanly supports arbitrary passphrase lengths >72 bytes."""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    prehashed = _prehash_password(password)
    hashed = bcrypt.hashpw(prehashed, bcrypt.gensalt(rounds=12)).decode("utf-8")
    return f"{_BSHA256_PREFIX}{hashed}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False
    try:
        if hashed_password.startswith(_BSHA256_PREFIX):
            raw_bcrypt = hashed_password[len(_BSHA256_PREFIX) :].encode("utf-8")
            return bcrypt.checkpw(_prehash_password(plain_password), raw_bcrypt)
        pwd_bytes = plain_password.encode("utf-8")[:72]
        return bcrypt.checkpw(pwd_bytes, hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
    *,
    token_version: int = 1,
    jti: str | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode = data.copy()
    to_encode.setdefault("jti", jti or uuid.uuid4().hex)
    to_encode.setdefault("iat", int(now.timestamp()))
    to_encode.setdefault("tv", int(token_version or 1))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.session_secret, algorithm=ALGORITHM)


def create_reauth_token(
    user: UserRecord,
    *,
    purpose: str = "account_delete",
    method: str = "oauth",
) -> str:
    return create_access_token(
        {
            "sub": user.id,
            "purpose": purpose,
            "reauth_method": method,
            "tv": int(getattr(user, "token_version", 1) or 1),
        },
        expires_delta=timedelta(seconds=REAUTH_TOKEN_EXPIRE_SECONDS),
        token_version=int(getattr(user, "token_version", 1) or 1),
    )


def verify_reauth_token(
    token: str,
    user: UserRecord,
    *,
    expected_purpose: str = "account_delete",
) -> bool:
    payload = decode_access_token(token)
    if not payload:
        return False
    if payload.get("sub") != user.id:
        return False
    if payload.get("purpose") != expected_purpose:
        return False
    token_tv = payload.get("tv")
    user_tv = int(getattr(user, "token_version", 1) or 1)
    if token_tv is not None and int(token_tv) != user_tv:
        return False
    return True


def decode_access_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.session_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        logger.debug("Failed to decode token: %s", exc)
        return None


def record_user_session(
    db: Session,
    *,
    user: UserRecord,
    token: str,
    auth_method: str = "local",
) -> None:
    payload = decode_access_token(token)
    if not payload or not payload.get("jti"):
        return
    exp_ts = payload.get("exp")
    expires_at = (
        datetime.fromtimestamp(float(exp_ts), tz=UTC)
        if exp_ts
        else (datetime.now(UTC) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    )
    jti = str(payload["jti"])
    existing = db.query(UserSessionRecord).filter(UserSessionRecord.id == jti).first()
    if existing:
        return
    db.add(
        UserSessionRecord(
            id=jti,
            user_id=user.id,
            auth_method=auth_method,
            is_revoked=False,
            expires_at=expires_at,
        )
    )
    db.commit()


def revoke_session_token(db: Session, token: str | None) -> None:
    if not token:
        return
    payload = decode_access_token(token)
    if not payload or not payload.get("jti"):
        return
    jti = str(payload["jti"])
    rec = db.query(UserSessionRecord).filter(UserSessionRecord.id == jti).first()
    if rec:
        rec.is_revoked = True
        rec.revoked_at = datetime.now(UTC)
        db.commit()
        return

    user_id = payload.get("sub")
    if user_id and db.query(UserRecord.id).filter(UserRecord.id == user_id).first():
        exp_ts = payload.get("exp")
        expires_at = (
            datetime.fromtimestamp(float(exp_ts), tz=UTC)
            if exp_ts
            else (datetime.now(UTC) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
        )
        db.add(
            UserSessionRecord(
                id=jti,
                user_id=str(user_id),
                auth_method="revoked",
                is_revoked=True,
                revoked_at=datetime.now(UTC),
                expires_at=expires_at,
            )
        )
        db.commit()


def revoke_all_user_sessions(db: Session, user: UserRecord) -> int:
    user.token_version = int(getattr(user, "token_version", 1) or 1) + 1
    now = datetime.now(UTC)
    db.query(UserSessionRecord).filter(
        UserSessionRecord.user_id == user.id,
        UserSessionRecord.is_revoked.is_(False),
    ).update({"is_revoked": True, "revoked_at": now}, synchronize_session=False)
    db.commit()
    return user.token_version


def _extract_raw_token(
    request: Request,
    auth: HTTPAuthorizationCredentials | None = None,
) -> str | None:
    if auth and auth.credentials:
        return auth.credentials
    if request and request.cookies.get("nexarion_session"):
        return request.cookies.get("nexarion_session")
    return None


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _is_subject_revoked(db: Session, user_id: str, payload: dict[str, Any]) -> bool:
    subject_hash = hash_subject_identifier("deleted", user_id)
    now = datetime.now(UTC)
    revoked = (
        db.query(RevokedSubjectRecord)
        .filter(RevokedSubjectRecord.subject_hash == subject_hash)
        .first()
    )
    if not revoked:
        return False
    if revoked.expires_at and _as_utc(revoked.expires_at) < now:
        return False
    iat = payload.get("iat")
    if iat is None:
        return True
    revoked_before_ts = int(_as_utc(revoked.revoked_before).timestamp())
    return int(iat) <= revoked_before_ts + 1


def _resolve_authenticated_user(
    request: Request,
    auth: HTTPAuthorizationCredentials | None,
    db: Session,
    *,
    reject_invalidated_session: bool = False,
) -> UserRecord | None:
    token = _extract_raw_token(request, auth)
    if not token:
        return None

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None

    if payload.get("purpose"):
        return None

    sub = str(payload["sub"])
    if _is_subject_revoked(db, sub, payload):
        if reject_invalidated_session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This account has been deleted and the session is no longer valid.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return None

    jti = payload.get("jti")
    if jti:
        session_rec = db.query(UserSessionRecord).filter(UserSessionRecord.id == str(jti)).first()
        if session_rec and session_rec.is_revoked:
            if reject_invalidated_session:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session has been revoked. Please sign in again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None

    user = db.query(UserRecord).filter(UserRecord.id == sub).first()
    if not user:
        return None

    token_tv = payload.get("tv")
    user_tv = int(getattr(user, "token_version", 1) or 1)
    if token_tv is not None and int(token_tv) != user_tv:
        if reject_invalidated_session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session is no longer valid. Please sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return None

    pwd_changed = getattr(user, "password_changed_at", None)
    if pwd_changed is not None:
        iat = payload.get("iat")
        changed_ts = int(_as_utc(pwd_changed).timestamp())
        if iat is not None and int(iat) < changed_ts:
            if reject_invalidated_session:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session expired after password update. Please sign in again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None

    return user


def get_current_user_optional(
    request: Request,
    auth: HTTPAuthorizationCredentials | None = Security(security_bearer),
    db: Session = Depends(get_db),
) -> UserRecord | None:
    token = _extract_raw_token(request, auth)
    if token:
        payload = decode_access_token(token)
        if payload and "sub" in payload:
            if _is_subject_revoked(db, str(payload["sub"]), payload):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="This account has been deleted and the session is no longer valid.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            jti = payload.get("jti")
            if jti:
                session_rec = (
                    db.query(UserSessionRecord).filter(UserSessionRecord.id == str(jti)).first()
                )
                if session_rec and session_rec.is_revoked:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Session has been revoked. Please sign in again.",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
    return _resolve_authenticated_user(request, auth, db, reject_invalidated_session=False)


def get_current_user(
    request: Request,
    auth: HTTPAuthorizationCredentials | None = Security(security_bearer),
    db: Session = Depends(get_db),
) -> UserRecord:
    user = _resolve_authenticated_user(request, auth, db, reject_invalidated_session=True)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    sync_user_admin_role(db, user)
    return user


def get_configured_admin_emails() -> set[str]:
    """Return lowercased admin email allowlist from env/settings."""
    settings = get_settings()
    raw_values = [
        os.environ.get("ADMIN_EMAIL", "") or settings.admin_email,
        os.environ.get("ADMIN_EMAILS", "") or settings.admin_emails,
    ]
    emails: set[str] = set()
    for raw in raw_values:
        if not raw:
            continue
        for part in str(raw).split(","):
            clean = part.strip().lower()
            if clean and "@" in clean:
                emails.add(clean)
    return emails


def sync_user_admin_role(db: Session, user: UserRecord, *, commit: bool = True) -> UserRecord:
    """Server-side promotion when verified account matches configured ADMIN_EMAIL allowlist."""
    allowlist = get_configured_admin_emails()
    if not allowlist:
        return user
    clean_email = (user.email or "").strip().lower()
    if clean_email in allowlist and bool(user.email_verified) and user.role != "admin":
        user.role = "admin"
        if commit:
            db.commit()
            db.refresh(user)
    return user


def is_admin_user(user: UserRecord | None) -> bool:
    """Authoritative backend check for administrator privileges (never reads client input)."""
    if not user:
        return False
    if (getattr(user, "role", "user") or "user").strip().lower() == "admin":
        return True
    allowlist = get_configured_admin_emails()
    clean_email = (user.email or "").strip().lower()
    return bool(clean_email and clean_email in allowlist and bool(user.email_verified))


def get_current_admin_user(
    user: UserRecord = Depends(get_current_user),
) -> UserRecord:
    """FastAPI dependency enforcing administrator access with HTTP 403 for ordinary users."""
    if not is_admin_user(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator authorization required.",
        )
    return user


def seconds_since_epoch() -> int:
    return int(time.time())
