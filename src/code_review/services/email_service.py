from __future__ import annotations

import html
import logging
import os
from typing import Any

import resend

from code_review.config import get_settings

logger = logging.getLogger(__name__)


def _build_feedback_html(data: dict[str, Any]) -> str:
    category = html.escape(str(data.get("category", "General Feedback")))
    details = html.escape(str(data.get("details") or "No additional details provided."))
    user_name = html.escape(str(data.get("user_name", "Anonymous User")))
    user_email = html.escape(str(data.get("user_email", "unknown@user.com")))
    user_id = html.escape(str(data.get("user_id", "N/A")))
    conversation_id = html.escape(str(data.get("conversation_id", "N/A")))
    message_id = html.escape(str(data.get("message_id", "N/A")))
    conversation_title = html.escape(
        str(data.get("conversation_title") or "Untitled Conversation")
    )
    reported_response = html.escape(str(data.get("reported_response") or "No response captured."))
    created_at = html.escape(str(data.get("created_at", "Just now")))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Nexarion User Feedback</title>
</head>
<body style="margin: 0; padding: 24px; background-color: #0A0A0A; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #EDEDED; line-height: 1.5;">
  <div style="max-width: 640px; margin: 0 auto; background-color: #121212; border: 1px solid #262626; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 30px rgba(0,0,0,0.5);">
    
    <!-- Header -->
    <div style="padding: 20px 24px; border-bottom: 1px solid #262626; background: linear-gradient(180deg, #181818 0%, #121212 100%);">
      <div style="display: flex; align-items: center; justify-content: space-between;">
        <span style="font-size: 14px; font-weight: 700; letter-spacing: 0.05em; color: #FFFFFF; font-family: monospace;">NEXARION // USER FEEDBACK ALERT</span>
        <span style="background-color: #2E1A1A; border: 1px solid #5C2B2B; color: #F87171; font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 6px; font-family: monospace;">
          {category}
        </span>
      </div>
      <p style="margin: 8px 0 0 0; font-size: 13px; color: #A1A1AA;">
        A user submitted feedback on an AI response in conversation: <strong style="color: #EDEDED;">{conversation_title}</strong>
      </p>
    </div>

    <!-- Body -->
    <div style="padding: 24px;">
      
      <!-- Reporter details -->
      <div style="margin-bottom: 20px; background-color: #171717; border: 1px solid #262626; border-radius: 8px; padding: 14px 16px;">
        <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #71717A; font-family: monospace; margin-bottom: 6px;">Submitted By</div>
        <div style="font-size: 14px; font-weight: 500; color: #FFFFFF;">{user_name} <span style="color: #A1A1AA; font-weight: 400; font-size: 13px;">({user_email})</span></div>
        <div style="font-size: 11px; font-family: monospace; color: #52525B; margin-top: 4px;">User ID: {user_id} &bull; Time: {created_at}</div>
      </div>

      <!-- Feedback Details -->
      <div style="margin-bottom: 20px;">
        <div style="font-size: 12px; font-weight: 600; color: #D4D4D8; margin-bottom: 6px;">User Comment / Details:</div>
        <div style="background-color: #1C1917; border: 1px solid #442727; border-left: 3px solid #EF4444; border-radius: 6px; padding: 12px 14px; font-size: 13px; color: #F5F5F5;">
          {details}
        </div>
      </div>

      <!-- Reported AI Response Preview -->
      <div style="margin-bottom: 20px;">
        <div style="font-size: 12px; font-weight: 600; color: #D4D4D8; margin-bottom: 6px;">Reported AI Response:</div>
        <div style="max-height: 240px; overflow-y: auto; background-color: #0A0A0A; border: 1px solid #262626; border-radius: 6px; padding: 12px 14px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; line-height: 1.6; color: #D4D4D8; white-space: pre-wrap; word-break: break-word;">
{reported_response}
        </div>
      </div>

      <!-- Technical References -->
      <div style="background-color: #121212; border: 1px solid #222222; border-radius: 6px; padding: 10px 14px; font-size: 11px; font-family: monospace; color: #71717A;">
        <div>Conversation ID: <span style="color: #A1A1AA;">{conversation_id}</span></div>
        <div>Message ID: <span style="color: #A1A1AA;">{message_id}</span></div>
      </div>

    </div>

    <!-- Footer -->
    <div style="padding: 16px 24px; border-top: 1px solid #262626; background-color: #0E0E0E; text-align: center; font-size: 12px; color: #52525B;">
      Nexarion Intelligence &bull; Founder Feedback Monitor
    </div>

  </div>
</body>
</html>
"""


def _build_feedback_text(data: dict[str, Any]) -> str:
    category = data.get("category", "General Feedback")
    details = data.get("details") or "No additional details provided."
    user_name = data.get("user_name", "Anonymous User")
    user_email = data.get("user_email", "unknown@user.com")
    user_id = data.get("user_id", "N/A")
    conversation_id = data.get("conversation_id", "N/A")
    message_id = data.get("message_id", "N/A")
    conversation_title = data.get("conversation_title") or "Untitled Conversation"
    reported_response = data.get("reported_response") or "No response captured."
    created_at = data.get("created_at", "Just now")

    return f"""[NEXARION USER FEEDBACK ALERT]
=========================================
Category: {category}
Submitted By: {user_name} ({user_email})
User ID: {user_id}
Date/Time: {created_at}
Conversation: {conversation_title} (ID: {conversation_id})
Message ID: {message_id}

USER DETAILS:
-----------------------------------------
{details}

REPORTED AI RESPONSE:
-----------------------------------------
{reported_response}

=========================================
Delivered by Nexarion Founder Feedback Monitor
"""


def get_resolved_email_config() -> tuple[str, str, str]:
    """
    Resolve (api_key, admin_email, email_from) by checking process environment variables
    first, then falling back to Pydantic Settings (.env / defaults).
    """
    settings = get_settings()

    api_key = (os.environ.get("RESEND_API_KEY") or settings.resend_api_key or "").strip()
    admin_email = (
        os.environ.get("ADMIN_EMAIL") or settings.admin_email or "kaushalkr.585@gmail.com"
    ).strip()
    email_from = (
        os.environ.get("EMAIL_FROM") or settings.email_from or "Nexarion <onboarding@resend.dev>"
    ).strip()

    return api_key, admin_email, email_from


def send_feedback_notification(
    feedback_data: dict[str, Any],
) -> tuple[bool, str | None, str | None]:
    """
    Deliver user feedback alert email to the admin/founder via Resend.
    Returns (success, email_message_id, error_message).
    Never raises an uncaught exception.
    """
    api_key, admin_email, email_from = get_resolved_email_config()

    # 1. Validate environment configuration
    if not api_key:
        logger.warning(
            "[ENV_CONFIG_MISSING] RESEND_API_KEY is not set in environment or .env. Email dispatch skipped."
        )
        return False, None, "RESEND_API_KEY environment variable is missing"

    if not admin_email:
        logger.warning(
            "[ENV_CONFIG_MISSING] ADMIN_EMAIL is not set in environment or .env. Email dispatch skipped."
        )
        return False, None, "ADMIN_EMAIL environment variable is missing"

    category = str(feedback_data.get("category", "Feedback"))
    user_email = str(feedback_data.get("user_email", "User"))
    subject = f"[Nexarion Feedback] {category} reported by {user_email}"

    # Resend testing domain (onboarding@resend.dev) requires sending exclusively to
    # the verified account owner email address.
    recipients = [admin_email.lower()]

    html_content = _build_feedback_html(feedback_data)
    text_content = _build_feedback_text(feedback_data)

    logger.info(
        "[EMAIL_NOTIFICATION_ATTEMPT] Dispatching feedback email via Resend to %s from %s (category: '%s')",
        recipients,
        email_from,
        category,
    )

    try:
        resend.api_key = api_key
        params: resend.Emails.SendParams = {
            "from": email_from,
            "to": recipients,
            "subject": subject,
            "html": html_content,
            "text": text_content,
        }
        response = resend.Emails.send(params)

        message_id: str | None = None
        if isinstance(response, dict):
            message_id = response.get("id")
        elif hasattr(response, "id"):
            message_id = getattr(response, "id", None)

        if not message_id:
            logger.error(
                "[RESEND_FAILURE] Resend API did not return a confirmed email ID. Raw response: %s",
                response,
            )
            return False, None, "Resend did not return a confirmed message ID"

        logger.info(
            "[RESEND_SUCCESS] Email sent successfully via Resend. email_id=%s, recipient=%s",
            message_id,
            recipients,
        )
        return True, str(message_id), None

    except Exception as exc:
        err_msg = str(exc)
        # Sanitize error message to prevent leaking any potential API keys
        if api_key and api_key in err_msg:
            err_msg = err_msg.replace(api_key, "[REDACTED]")

        status_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        logger.error(
            "[RESEND_FAILURE] Failed to send email via Resend (status_code=%s): %s",
            status_code,
            err_msg,
        )
        return False, None, f"Resend error: {err_msg[:250]}"
