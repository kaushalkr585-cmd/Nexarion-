import logging
import secrets
import time
import urllib.parse
from typing import Any

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from code_review.config import get_settings
from code_review.db.database import get_db
from code_review.db.models import UserRecord
from code_review.web.auth import (
    ALGORITHM,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from code_review.web.schemas import AuthResponse, LoginRequest, SignupRequest, UserResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

SESSION_COOKIE_NAME = "nexarion_session"
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 7


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )


def _generate_oauth_state(origin: str | None = None) -> str:
    settings = get_settings()
    fallback_origin = (
        settings.frontend_url.rstrip("/") if settings.frontend_url else "http://localhost:8000"
    )
    target_origin = (origin or fallback_origin).rstrip("/")
    state_payload = {
        "nonce": secrets.token_hex(16),
        "origin": target_origin,
        "exp": int(time.time()) + 600,
    }
    return jwt.encode(state_payload, settings.session_secret, algorithm=ALGORITHM)


def _decode_oauth_state(state: str | None) -> dict[str, Any] | None:
    if not state:
        return None
    settings = get_settings()
    try:
        return jwt.decode(state, settings.session_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        logger.warning("Invalid OAuth state parameter: %s", exc)
        return None


@router.post("/signup", response_model=AuthResponse)
def signup(
    payload: SignupRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    existing = db.query(UserRecord).filter(UserRecord.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    user = UserRecord(
        name=payload.name.strip(),
        email=payload.email.lower().strip(),
        hashed_password=hash_password(payload.password),
        auth_provider="local",
        plan="",
        theme="dark",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.id, "email": user.email})
    _set_session_cookie(response, token)
    return AuthResponse(token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    user = db.query(UserRecord).filter(UserRecord.email == payload.email.lower()).first()
    if (
        not user
        or not user.hashed_password
        or not verify_password(payload.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_access_token({"sub": user.id, "email": user.email})
    _set_session_cookie(response, token)
    return AuthResponse(token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
def get_current_profile(user: UserRecord = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    _clear_session_cookie(response)
    return {"message": "Logged out successfully."}


@router.get("/google/url")
def get_google_auth_url(origin: str | None = Query(default=None)) -> dict[str, str]:
    settings = get_settings()
    if not settings.google_client_id:
        return {
            "url": "",
            "message": "Google Client ID is not configured.",
        }

    state = _generate_oauth_state(origin)

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return {"url": auth_url}


@router.get("/google/callback")
def google_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()

    state_data = _decode_oauth_state(state)
    target_origin = (
        state_data.get("origin")
        if state_data and "origin" in state_data
        else (
            settings.frontend_url.rstrip("/") if settings.frontend_url else "http://localhost:8000"
        )
    )

    if error:
        logger.warning("Google OAuth returned error: %s (%s)", error, error_description)
        err_msg = urllib.parse.quote(error_description or error)
        return RedirectResponse(url=f"{target_origin}/?auth_error={err_msg}")

    if not code:
        logger.warning("Google OAuth callback received without authorization code.")
        return RedirectResponse(url=f"{target_origin}/?auth_error=missing_authorization_code")

    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            token_resp = client.post(token_url, data=token_data)
    except Exception as exc:
        logger.error("Network exception connecting to Google token endpoint: %s", exc)
        return RedirectResponse(url=f"{target_origin}/?auth_error=google_connection_failed")

    if token_resp.status_code != 200:
        logger.error(
            "Google token exchange failed (status %d): %s",
            token_resp.status_code,
            token_resp.text,
        )
        return RedirectResponse(url=f"{target_origin}/?auth_error=token_exchange_failed")

    token_json = token_resp.json()
    access_token = token_json.get("access_token")
    if not access_token:
        logger.error("No access_token found in Google token response: %s", token_json)
        return RedirectResponse(url=f"{target_origin}/?auth_error=missing_access_token")

    try:
        with httpx.Client(timeout=10.0) as client:
            userinfo_resp = client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except Exception as exc:
        logger.error("Network exception fetching Google userinfo: %s", exc)
        return RedirectResponse(url=f"{target_origin}/?auth_error=userinfo_fetch_failed")

    if userinfo_resp.status_code != 200:
        logger.error(
            "Google userinfo fetch failed (status %d): %s",
            userinfo_resp.status_code,
            userinfo_resp.text,
        )
        return RedirectResponse(url=f"{target_origin}/?auth_error=userinfo_failed")

    userinfo = userinfo_resp.json()
    google_id = userinfo.get("sub")
    email = userinfo.get("email")
    email_verified = userinfo.get("email_verified", False)
    name = userinfo.get("name") or (email.split("@")[0] if email else "Developer")
    picture = userinfo.get("picture")

    if not google_id or not email:
        logger.error("Incomplete identity data returned by Google: %s", userinfo)
        return RedirectResponse(url=f"{target_origin}/?auth_error=incomplete_identity")

    user = db.query(UserRecord).filter(UserRecord.google_id == google_id).first()

    if not user:
        user = db.query(UserRecord).filter(UserRecord.email == email.lower().strip()).first()
        if user:
            if email_verified:
                user.google_id = google_id
                user.google_email = email.lower().strip()
                if not user.avatar_url and picture:
                    user.avatar_url = picture
                if not user.email_verified:
                    user.email_verified = True
                db.commit()
                db.refresh(user)
                logger.info(
                    "Linked verified Google identity %s to user %s (%s)",
                    google_id,
                    user.id,
                    user.email,
                )
            else:
                logger.warning("Unverified Google email %s refused for account linking.", email)
                return RedirectResponse(url=f"{target_origin}/?auth_error=unverified_google_email")
        else:
            user = UserRecord(
                email=email.lower().strip(),
                name=name.strip(),
                google_id=google_id,
                google_email=email.lower().strip(),
                avatar_url=picture,
                auth_provider="google",
                email_verified=bool(email_verified),
                plan="",
                theme="dark",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info("Created new user via Google OAuth: %s (%s)", user.id, user.email)
    else:
        if picture and not user.avatar_url:
            user.avatar_url = picture
        if name and user.name in ("Developer", ""):
            user.name = name.strip()
        db.commit()
        db.refresh(user)
        logger.info("Authenticated existing Google user: %s (%s)", user.id, user.email)

    app_token = create_access_token({"sub": user.id, "email": user.email})

    redirect_target = f"{target_origin}/?token={app_token}"
    response = RedirectResponse(url=redirect_target, status_code=status.HTTP_302_FOUND)
    _set_session_cookie(response, app_token)
    return response
