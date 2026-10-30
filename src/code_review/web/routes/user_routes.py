import logging
import uuid
from pathlib import Path

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from code_review.config import get_settings
from code_review.db.database import get_db
from code_review.db.models import UserRecord
from code_review.web.auth import get_current_user
from code_review.web.schemas import UserResponse, UserUpdateRequest

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


@router.delete("/account")
def delete_account(
    db: Session = Depends(get_db),
    user: UserRecord = Depends(get_current_user),
) -> dict[str, str]:
    user_id = user.id
    db.delete(user)
    db.commit()
    logger.info("Deleted account for user %s", user_id)
    return {"message": "Account successfully deleted."}
