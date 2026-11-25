import hashlib
import logging
import secrets
import time
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from code_review.config import get_settings
from code_review.db.database import get_db
from code_review.db.models import (
    PasswordResetTokenRecord,
    SecurityAuditLogRecord,
    UserRecord,
)
from code_review.web.auth import (
    ALGORITHM,
    REAUTH_TOKEN_EXPIRE_SECONDS,
    _extract_raw_token,
    create_access_token,
    create_reauth_token,
    get_current_user,
    get_current_user_optional,
    hash_password,
    hash_subject_identifier,
    record_user_session,
    revoke_all_user_sessions,
    revoke_session_token,
    verify_password,
)
from code_review.web.password_policy import evaluate_password_strength
from code_review.web.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordStrengthCheckRequest,
    ReauthPasswordRequest,
    SignupRequest,
    UserResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

SESSION_COOKIE_NAME = "nexarion_session"
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 7
PASSWORD_RESET_TTL_MINUTES = 30


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


def _hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _dispatch_password_reset_token(user: UserRecord, raw_token: str) -> None:
    """Extensible email/notification hook for password reset tokens.

    Never logs plaintext passwords or raw tokens.
    """
    del user, raw_token


def _generate_oauth_state(
    origin: str | None = None,
    *,
    intent: str = "login",
    user_id: str | None = None,
) -> str:
    settings = get_settings()
    fallback_origin = (
        settings.frontend_url.rstrip("/") if settings.frontend_url else "http://localhost:8000"
    )
    target_origin = (origin or fallback_origin).rstrip("/")
    state_payload: dict[str, Any] = {
        "nonce": secrets.token_hex(16),
        "origin": target_origin,
        "intent": intent,
        "exp": int(time.time()) + 600,
    }
    if user_id:
        state_payload["user_id"] = user_id
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


def _raise_weak_password_error(password: str, *, name: str | None, email: str | None) -> None:
    evaluation = evaluate_password_strength(password, name=name, email=email)
    if not evaluation.acceptable:
        detail_msg = evaluation.warning or (
            evaluation.suggestions[0]
            if evaluation.suggestions
            else "Your password is too weak. Try using a longer password with unpredictable words."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail_msg,
        )


def perform_password_change(
    db: Session,
    *,
    user: UserRecord,
    current_password: str | None,
    new_password: str,
    response: Response,
) -> AuthResponse:
    """Validate current credentials + password strength, update hash, rotate sessions."""
    if user.hashed_password:
        if not current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is required to set a new password.",
            )
        if not verify_password(current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect.",
            )
        if verify_password(new_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must differ from your current password.",
            )

    _raise_weak_password_error(new_password, name=user.name, email=user.email)

    now_ts = int(time.time())
    now = datetime.fromtimestamp(now_ts, tz=UTC)
    user.hashed_password = hash_password(new_password)
    user.password_changed_at = now
    new_tv = revoke_all_user_sessions(db, user)

    db.add(
        SecurityAuditLogRecord(
            event_type="password_changed",
            subject_hash=hash_subject_identifier("audit", user.id),
            auth_provider=user.auth_provider,
            metadata_json={"had_prior_password": bool(current_password)},
        )
    )
    db.commit()
    db.refresh(user)

    token = create_access_token(
        {"sub": user.id, "email": user.email, "iat": now_ts},
        token_version=new_tv,
    )
    record_user_session(db, user=user, token=token, auth_method="password_change")
    _set_session_cookie(response, token)
    return AuthResponse(token=token, user=UserResponse.model_validate(user))


@router.post("/password-strength")
def check_password_strength(payload: PasswordStrengthCheckRequest) -> dict[str, Any]:
    evaluation = evaluate_password_strength(
        payload.password,
        name=payload.name,
        email=payload.email,
    )
    return evaluation.to_dict()


@router.post("/signup", response_model=AuthResponse)
def signup(
    payload: SignupRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    clean_name = payload.name.strip()
    clean_email = payload.email.lower().strip()

    _raise_weak_password_error(payload.password, name=clean_name, email=clean_email)

    existing = db.query(UserRecord).filter(UserRecord.email == clean_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    user = UserRecord(
        name=clean_name,
        email=clean_email,
        hashed_password=hash_password(payload.password),
        auth_provider="local",
        plan="",
        theme="dark",
        token_version=1,
        password_changed_at=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        {"sub": user.id, "email": user.email},
        token_version=user.token_version,
    )
    record_user_session(db, user=user, token=token, auth_method="local")
    _set_session_cookie(response, token)
    return AuthResponse(token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    user = db.query(UserRecord).filter(UserRecord.email == payload.email.lower().strip()).first()
    if (
        not user
        or not user.hashed_password
        or not verify_password(payload.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    tv = int(getattr(user, "token_version", 1) or 1)
    token = create_access_token({"sub": user.id, "email": user.email}, token_version=tv)
    record_user_session(db, user=user, token=token, auth_method="local")
    _set_session_cookie(response, token)
    return AuthResponse(token=token, user=UserResponse.model_validate(user))


@router.post("/change-password", response_model=AuthResponse)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    db: Session = Depends(get_db),
    user: UserRecord = Depends(get_current_user),
) -> AuthResponse:
    return perform_password_change(
        db,
        user=user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        response=response,
    )


@router.post("/password-reset/request")
def request_password_reset(
    payload: PasswordResetRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    clean_email = payload.email.lower().strip()
    user = db.query(UserRecord).filter(UserRecord.email == clean_email).first()

    if user:
        db.query(PasswordResetTokenRecord).filter(
            PasswordResetTokenRecord.user_id == user.id,
            PasswordResetTokenRecord.used_at.is_(None),
        ).delete(synchronize_session=False)

        raw_token = secrets.token_urlsafe(32)
        reset_rec = PasswordResetTokenRecord(
            user_id=user.id,
            token_hash=_hash_reset_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(minutes=PASSWORD_RESET_TTL_MINUTES),
        )
        db.add(reset_rec)
        db.commit()
        _dispatch_password_reset_token(user, raw_token)

    return {
        "message": (
            "If an account with that email exists, password reset instructions have been issued."
        ),
        "delivery_configured": False,
    }


@router.post("/password-reset/confirm")
def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    token_hash = _hash_reset_token(payload.token.strip())
    now = datetime.now(UTC)

    reset_rec = (
        db.query(PasswordResetTokenRecord)
        .filter(
            PasswordResetTokenRecord.token_hash == token_hash,
            PasswordResetTokenRecord.used_at.is_(None),
        )
        .first()
    )
    if not reset_rec:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token.",
        )

    exp = (
        reset_rec.expires_at.replace(tzinfo=UTC)
        if reset_rec.expires_at.tzinfo is None
        else reset_rec.expires_at
    )
    if exp < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token has expired. Please request a new one.",
        )

    user = db.query(UserRecord).filter(UserRecord.id == reset_rec.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account associated with this reset token no longer exists.",
        )

    _raise_weak_password_error(payload.new_password, name=user.name, email=user.email)

    user.hashed_password = hash_password(payload.new_password)
    user.password_changed_at = now
    reset_rec.used_at = now
    revoke_all_user_sessions(db, user)

    db.add(
        SecurityAuditLogRecord(
            event_type="password_reset",
            subject_hash=hash_subject_identifier("audit", user.id),
            auth_provider=user.auth_provider,
            metadata_json={},
        )
    )
    db.commit()
    _clear_session_cookie(response)
    return {"message": "Password reset successfully. Please sign in with your new password."}


@router.post("/sessions/revoke-all", response_model=AuthResponse)
def revoke_other_sessions(
    response: Response,
    db: Session = Depends(get_db),
    user: UserRecord = Depends(get_current_user),
) -> AuthResponse:
    new_tv = revoke_all_user_sessions(db, user)
    db.add(
        SecurityAuditLogRecord(
            event_type="sessions_revoked",
            subject_hash=hash_subject_identifier("audit", user.id),
            auth_provider=user.auth_provider,
            metadata_json={},
        )
    )
    db.commit()
    token = create_access_token({"sub": user.id, "email": user.email}, token_version=new_tv)
    record_user_session(db, user=user, token=token, auth_method="session_rotate")
    _set_session_cookie(response, token)
    return AuthResponse(token=token, user=UserResponse.model_validate(user))


@router.post("/reauth/password")
def reauthenticate_with_password(
    payload: ReauthPasswordRequest,
    user: UserRecord = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password. Please verify your current password to continue.",
        )
    reauth_token = create_reauth_token(user, purpose="account_delete", method="password")
    return {"reauth_token": reauth_token, "expires_in": REAUTH_TOKEN_EXPIRE_SECONDS}


@router.get("/me", response_model=UserResponse)
def get_current_profile(user: UserRecord = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    raw_token = _extract_raw_token(request)
    revoke_session_token(db, raw_token)
    _clear_session_cookie(response)
    return {"message": "Logged out successfully."}


@router.get("/google/url")
def get_google_auth_url(
    origin: str | None = Query(default=None),
    intent: str | None = Query(default=None),
    user: UserRecord | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    settings = get_settings()
    effective_intent = "reauth_delete" if intent == "reauth_delete" else "login"
    if effective_intent == "reauth_delete" and not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required before Google re-authentication.",
        )

    if not settings.google_client_id:
        return {
            "url": "",
            "configured": False,
            "message": "Google Client ID is not configured.",
        }

    state = _generate_oauth_state(
        origin,
        intent=effective_intent,
        user_id=user.id if (effective_intent == "reauth_delete" and user) else None,
    )

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "login consent select_account"
        if effective_intent == "reauth_delete"
        else "consent",
        "state": state,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return {"url": auth_url, "configured": True}


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
    intent = state_data.get("intent", "login") if state_data else "login"
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
        if intent == "reauth_delete":
            return RedirectResponse(url=f"{target_origin}/?view=settings&reauth_error={err_msg}")
        return RedirectResponse(url=f"{target_origin}/?auth_error={err_msg}")

    if not code:
        logger.warning("Google OAuth callback received without authorization code.")
        if intent == "reauth_delete":
            return RedirectResponse(
                url=f"{target_origin}/?view=settings&reauth_error=missing_authorization_code"
            )
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

    if intent == "reauth_delete":
        target_uid = state_data.get("user_id") if state_data else None
        target_user = (
            db.query(UserRecord).filter(UserRecord.id == target_uid).first()
            if target_uid
            else None
        )
        if not target_user:
            return RedirectResponse(
                url=f"{target_origin}/?view=settings&reauth_error=session_not_found",
                status_code=status.HTTP_302_FOUND,
            )
        id_matches = bool(target_user.google_id and target_user.google_id == google_id)
        email_matches = bool(
            not target_user.google_id
            and email_verified
            and target_user.email.lower() == email.lower().strip()
        )
        if not (id_matches or email_matches):
            return RedirectResponse(
                url=f"{target_origin}/?view=settings&reauth_error=google_account_mismatch",
                status_code=status.HTTP_302_FOUND,
            )
        reauth_token = create_reauth_token(target_user, purpose="account_delete", method="google")
        return RedirectResponse(
            url=f"{target_origin}/?view=settings&reauth_delete_token={reauth_token}",
            status_code=status.HTTP_302_FOUND,
        )

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
                token_version=1,
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

    tv = int(getattr(user, "token_version", 1) or 1)
    app_token = create_access_token({"sub": user.id, "email": user.email}, token_version=tv)
    record_user_session(db, user=user, token=app_token, auth_method="google")

    redirect_target = f"{target_origin}/?token={app_token}"
    response = RedirectResponse(url=redirect_target, status_code=status.HTTP_302_FOUND)
    _set_session_cookie(response, app_token)
    return response
