import logging
import uuid
from pathlib import Path
from typing import Any

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Body, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from code_review.config import get_settings
from code_review.db.database import get_db
from code_review.db.models import GitHubConnectionRecord, UserRecord
from code_review.github.service import GitHubService
from code_review.web.account_deletion import AccountDeletionError, execute_account_deletion
from code_review.web.auth import get_current_user, verify_password, verify_reauth_token
from code_review.web.routes.auth_routes import SESSION_COOKIE_NAME, perform_password_change
from code_review.web.schemas import (
    AccountDeletionRequest,
    AuthResponse,
    ChangePasswordRequest,
    UserResponse,
    UserUpdateRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["User Profile"])

ALLOWED_MIME_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
}
MAX_FILE_SIZE = 5 * 1024 * 1024


@router.get("/profile", response_model=UserResponse)
@router.get("/me", response_model=UserResponse)
def get_profile(user: UserRecord = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)


@router.put("/profile", response_model=UserResponse)
@router.put("/me", response_model=UserResponse)
def update_profile(
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    user: UserRecord = Depends(get_current_user),
) -> UserResponse:
    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.theme is not None:
        user.theme = payload.theme.strip()
    if payload.email is not None:
        new_email = payload.email.lower().strip()
        if new_email != user.email:
            existing = (
                db.query(UserRecord)
                .filter(UserRecord.email == new_email, UserRecord.id != user.id)
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this email address already exists.",
                )
            user.email = new_email

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile. Please try again.",
        )
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/me/password", response_model=AuthResponse)
def update_user_password(
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


@router.post("/avatar", response_model=UserResponse)
@router.post("/me/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: UserRecord = Depends(get_current_user),
) -> UserResponse:
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a valid PNG, JPEG, or WebP image.",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds maximum permitted limit (5MB).",
        )

    settings = get_settings()
    secure_url: str | None = None

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
            unique_suffix = uuid.uuid4().hex[:8]
            upload_result = cloudinary.uploader.upload(
                content,
                folder="nexarion_avatars",
                public_id=f"avatar_{user.id}_{unique_suffix}",
                overwrite=True,
                transformation=[{"width": 256, "height": 256, "crop": "fill", "gravity": "face"}],
            )
            secure_url = upload_result.get("secure_url") or upload_result.get("url")
        except Exception as exc:
            logger.warning("Cloudinary upload failed, falling back to local storage: %s", exc)

    if not secure_url:
        ext = ALLOWED_MIME_TYPES.get(content_type, "png")
        file_name = f"avatar_{user.id}_{uuid.uuid4().hex[:8]}.{ext}"

        avatars_dir = Path("frontend/public/avatars")
        avatars_dir.mkdir(parents=True, exist_ok=True)
        local_path = avatars_dir / file_name
        local_path.write_bytes(content)

        dist_avatars = Path("frontend/dist/avatars")
        if dist_avatars.parent.is_dir():
            dist_avatars.mkdir(parents=True, exist_ok=True)
            (dist_avatars / file_name).write_bytes(content)

        secure_url = f"/avatars/{file_name}"

    user.avatar_url = secure_url
    db.commit()
    db.refresh(user)
    logger.info("Successfully updated avatar for user %s: %s", user.id, secure_url)
    return UserResponse.model_validate(user)


def _verify_deletion_reauth(
    db: Session,
    user: UserRecord,
    payload: AccountDeletionRequest,
) -> None:
    if payload.reauth_token:
        if not verify_reauth_token(payload.reauth_token, user, expected_purpose="account_delete"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Re-authentication token is invalid or expired. Please verify your identity again.",
            )
        return

    if payload.password:
        if not user.hashed_password or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password. Re-authentication failed.",
            )
        return

    if payload.github_pat:
        pat = payload.github_pat.strip()
        if not user.github_connected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="GitHub is not connected to this account.",
            )
        try:
            from code_review.github.access_guard import GitHubAccessGuard

            auth_grant = GitHubAccessGuard.authorize_auth_flow(
                user=user,
                operation="get_user_profile",
                reason="Verify user-entered GitHub PAT during account deletion reauth.",
                db=db,
            )
            profile = GitHubService(
                access_grant=auth_grant, bound_user=user, db=db
            ).get_user_profile(pat)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="GitHub token verification failed.",
            ) from exc
        login_name = str(profile.get("login") or "").lower()
        account_id = str(profile.get("id") or "")
        conn = (
            db.query(GitHubConnectionRecord)
            .filter(GitHubConnectionRecord.user_id == user.id)
            .order_by(GitHubConnectionRecord.updated_at.desc())
            .first()
        )
        expected_id = str(conn.github_account_id) if (conn and conn.github_account_id) else ""
        expected_login = (
            conn.github_username
            if (conn and conn.github_username)
            else (user.github_username or "")
        ).lower()
        id_ok = bool(expected_id and account_id and expected_id == account_id)
        login_ok = bool(expected_login and login_name and expected_login == login_name)
        if not (id_ok or login_ok):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Provided GitHub token does not match the connected GitHub account.",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Re-authentication is required before permanently deleting your account.",
    )


@router.delete("/account")
@router.delete("/me")
def delete_account(
    response: Response,
    payload: AccountDeletionRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    user: UserRecord = Depends(get_current_user),
) -> dict[str, Any]:
    if not payload or payload.confirmation_text.strip() != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must type DELETE to confirm permanent account deletion.",
        )

    _verify_deletion_reauth(db, user, payload)

    try:
        summary = execute_account_deletion(db, user)
    except AccountDeletionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {
        "status": "deleted",
        "message": "Your Nexarion account and associated personal data have been permanently deleted.",
        "summary": summary,
    }
