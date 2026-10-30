from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from code_review.config import get_settings
from code_review.db.database import get_db
from code_review.db.models import UserRecord

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security_bearer = HTTPBearer(auto_error=False)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.session_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.session_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        logger.debug("Failed to decode token: %s", exc)
        return None


def get_current_user_optional(
    request: Request,
    auth: HTTPAuthorizationCredentials | None = Security(security_bearer),
    db: Session = Depends(get_db),
) -> UserRecord | None:
    token: str | None = None
    if auth and auth.credentials:
        token = auth.credentials
    elif request and request.cookies.get("nexarion_session"):
        token = request.cookies.get("nexarion_session")

    if token:
        payload = decode_access_token(token)
        if payload and "sub" in payload:
            user = db.query(UserRecord).filter(UserRecord.id == payload["sub"]).first()
            if user:
                return user
    return None


def get_current_user(
    request: Request,
    auth: HTTPAuthorizationCredentials | None = Security(security_bearer),
    db: Session = Depends(get_db),
) -> UserRecord:
    user = get_current_user_optional(request, auth, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
