from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from code_review.config import get_settings

logger = logging.getLogger(__name__)

ENCRYPTED_PREFIX = "enc:v1:"


def _get_fernet() -> Fernet:
    settings = get_settings()
    explicit_key = (settings.github_credential_encryption_key or "").strip()
    if explicit_key:
        try:
            return Fernet(explicit_key.encode("utf-8"))
        except Exception as exc:
            logger.warning(
                "Invalid GITHUB_CREDENTIAL_ENCRYPTION_KEY format (%s); falling back to derived key.",
                exc,
            )

    secret = (settings.session_secret or "nexarion_session_secret_dev_key").encode("utf-8")
    digest = hashlib.sha256(b"nexarion-github-cred-v1:" + secret).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith(ENCRYPTED_PREFIX))


def encrypt_secret(plaintext: str | None) -> str | None:
    """Encrypt a sensitive credential string for storage at rest."""
    if not plaintext:
        return None
    if is_encrypted(plaintext):
        return plaintext
    fernet = _get_fernet()
    token = fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return f"{ENCRYPTED_PREFIX}{token}"


def decrypt_secret(ciphertext: str | None) -> str | None:
    """Decrypt a stored credential string; handles legacy plaintext gracefully."""
    if not ciphertext:
        return None
    if not is_encrypted(ciphertext):
        # Legacy plaintext credential stored prior to encryption migration
        return ciphertext
    payload = ciphertext[len(ENCRYPTED_PREFIX) :]
    fernet = _get_fernet()
    try:
        return fernet.decrypt(payload.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.error("Failed to decrypt stored credential (InvalidToken).")
        return None
