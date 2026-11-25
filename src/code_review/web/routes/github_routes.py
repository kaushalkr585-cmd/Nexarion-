from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

import jwt
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from code_review.agents.registry import get_persisted_enabled_agent_ids
from code_review.config import get_settings
from code_review.db.database import get_db, get_session_factory
from code_review.db.models import (
    ConversationRecord,
    ConversationRepositoryContextRecord,
    FindingRecord,
    GitHubConnectionRecord,
    ReviewRecord,
    UserRecord,
)
from code_review.github.auth_resolver import ensure_github_tables, resolve_user_github_context
from code_review.github.cache import get_github_cache
from code_review.github.service import GitHubApiError, GitHubAuthError, GitHubService
from code_review.orchestrator import ReviewOrchestrator
from code_review.web.auth import (
    ALGORITHM,
    create_reauth_token,
    get_current_user,
    get_current_user_optional,
)
from code_review.web.crypto import encrypt_secret
from code_review.web.schemas import FindingResponse, ReviewDetailResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/github", tags=["GitHub Integration"])

_PROCESSED_DELIVERIES: dict[str, float] = {}
DELIVERY_TTL_SECONDS = 3600.0
_REVIEW_JOBS: dict[str, dict[str, Any]] = {}
_REVIEW_JOBS_LOCK = threading.Lock()


def _is_duplicate_delivery(delivery_id: str | None) -> bool:
    if not delivery_id:
        return False
    now = time.time()
    expired = [k for k, ts in _PROCESSED_DELIVERIES.items() if now - ts > DELIVERY_TTL_SECONDS]
    for k in expired:
        _PROCESSED_DELIVERIES.pop(k, None)

    if delivery_id in _PROCESSED_DELIVERIES:
        return True
    _PROCESSED_DELIVERIES[delivery_id] = now
    return False


class GitHubConnectRequest(BaseModel):
    token: str = Field(..., min_length=10, description="GitHub Personal Access Token")


class GitHubStatusResponse(BaseModel):
    connected: bool
    username: str | None = None
    configured: bool
    auth_type: str = "oauth"
    auth_method: str = "none"
    connection_status: str = "not_connected"
    app_configured: bool = False
    installation_id: str | None = None


class ConversationRepoContextRequest(BaseModel):
    repository_full_name: str = Field(..., min_length=3, max_length=255)
    repository_id: str | None = None
    default_branch: str = "main"
    selected_branch: str | None = None


class ConversationRepoContextResponse(BaseModel):
    conversation_id: str
    repository_full_name: str
    repository_id: str | None = None
    default_branch: str = "main"
    selected_branch: str = "main"
    last_inspected_commit: str | None = None


class PostReviewRequest(BaseModel):
    review_id: str | None = None
    commit_sha: str | None = None
    event: str = "COMMENT"


class PostReviewResponse(BaseModel):
    status: str
    github_review_id: int | None = None
    review_url: str | None = None
    total_findings: int = 0
    inline_comments_posted: int = 0
    verdict: str


def process_github_webhook_pr_review(
    owner: str,
    repo: str,
    pull_number: int,
    pr_title: str,
    head_sha: str | None,
    author: str,
) -> None:
    settings = get_settings()
    session_factory = get_session_factory()
    db = session_factory()
    service = GitHubService(token=settings.github_token or None)

    try:
        repo_name = f"{owner}/{repo}"
        pr_id = f"#{pull_number}"
        logger.info(
            "Starting background webhook review for %s %s (SHA: %s)",
            repo_name,
            pr_id,
            head_sha,
        )

        if settings.github_set_commit_status and head_sha:
            try:
                service.create_commit_status(
                    owner=owner,
                    repo=repo,
                    sha=head_sha,
                    state="pending",
                    description="NEXARION: Multi-agent code review in progress...",
                    target_url=settings.github_dashboard_url or None,
                )
            except Exception as e:
                logger.warning("Failed to set pending commit status on GitHub: %s", e)

        diff_info = service.get_pull_request_diff(owner, repo, pull_number)
        diff_text = diff_info["diff"]
        diff_head_sha = head_sha or diff_info.get("head_sha")

        start_time = time.perf_counter()
        provider = "llm" if settings.llm_provider in ("nvidia", "llm") else settings.llm_provider
        model_name = settings.nvidia_model if provider == "llm" else settings.ollama_model
        enabled_agent_ids = get_persisted_enabled_agent_ids(db)
        orchestrator = ReviewOrchestrator(
            enabled_agent_ids=enabled_agent_ids,
            include_semantic="semantic" in enabled_agent_ids,
            include_llm=bool({"documentation", "test", "llm"} & enabled_agent_ids),
            llm_provider=provider,
            parallel=True,
        )
        result = orchestrator.review_diff(diff_text)
        duration = round(time.perf_counter() - start_time, 2)
        agents_used = [str(getattr(a, "name", "agent")) for a in orchestrator.agents]

        review = ReviewRecord(
            user_id=None,
            repository_name=repo_name,
            pr_identifier=pr_id,
            title=f"GitHub PR #{pull_number}: {pr_title}",
            diff_content=diff_text,
            provider=provider,
            model_name=model_name,
            agents_used=agents_used,
            finding_count=result.total_findings,
            has_critical=result.has_critical,
            duration_seconds=duration,
        )
        db.add(review)
        db.flush()

        for f in result.findings:
            db.add(
                FindingRecord(
                    review_id=review.id,
                    agent=f.agent.value,
                    title=f.message[:120],
                    description=f.message,
                    severity=f.severity.value.upper(),
                    category=f.category.value.upper(),
                    file_path=f.file,
                    line_start=f.line,
                    line_end=f.line,
                    suggested_fix=f.suggestion,
                    rule_id=f.rule_id,
                    evidence=f.file,
                )
            )
        db.commit()

        summary_md, inline_comments, verdict_action = service.format_pr_review(
            findings=result.findings,
            owner=owner,
            repo=repo,
            pull_number=pull_number,
            diff_text=diff_text,
            duration_seconds=duration,
            commit_sha=diff_head_sha,
            dashboard_url=settings.github_dashboard_url or None,
        )

        if settings.github_post_review_comments:
            try:
                service.post_pull_request_review(
                    owner=owner,
                    repo=repo,
                    pull_number=pull_number,
                    body=summary_md,
                    event=verdict_action,
                    comments=inline_comments,
                    commit_sha=diff_head_sha,
                )
                logger.info("Successfully posted review to GitHub PR %s %s", repo_name, pr_id)
            except Exception as e:
                logger.error("Failed to post PR review to GitHub: %s", e)

        if settings.github_set_commit_status and diff_head_sha:
            final_state = "failure" if result.has_critical else "success"
            desc = (
                f"NEXARION: {result.total_findings} findings (Critical issues found!)"
                if result.has_critical
                else f"NEXARION: Passed with {result.total_findings} findings."
            )
            try:
                service.create_commit_status(
                    owner=owner,
                    repo=repo,
                    sha=diff_head_sha,
                    state=final_state,
                    description=desc,
                    target_url=settings.github_dashboard_url or None,
                )
            except Exception as e:
                logger.warning("Failed to update final commit status on GitHub: %s", e)

    except Exception as exc:
        logger.exception(
            "Error processing webhook PR review for %s/%s #%s: %s",
            owner,
            repo,
            pull_number,
            exc,
        )
        if settings.github_set_commit_status and head_sha:
            try:
                service.create_commit_status(
                    owner=owner,
                    repo=repo,
                    sha=head_sha,
                    state="error",
                    description=f"NEXARION: Review failed ({exc})",
                    target_url=settings.github_dashboard_url or None,
                )
            except Exception:
                pass
    finally:
        db.close()


@router.post("/webhook")
async def handle_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str | None = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
    x_github_delivery: str | None = Header(None, alias="X-GitHub-Delivery"),
) -> dict[str, Any]:
    settings = get_settings()
    raw_body = await request.body()

    if settings.github_webhook_secret:
        if not GitHubService.verify_webhook_signature(
            raw_body, x_hub_signature_256, settings.github_webhook_secret
        ):
            logger.warning("Rejected webhook: invalid HMAC signature.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature.",
            )

    if _is_duplicate_delivery(x_github_delivery):
        logger.info("Ignoring duplicate webhook delivery: %s", x_github_delivery)
        return {
            "status": "ignored",
            "reason": "duplicate_delivery",
            "delivery": x_github_delivery,
        }

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {exc}",
        ) from exc

    event = (x_github_event or "").lower()

    if event == "ping":
        zen = payload.get("zen", "Keep it logically awesome.")
        hook_id = payload.get("hook_id")
        logger.info("Received GitHub ping webhook (Hook ID: %s): %s", hook_id, zen)
        return {
            "status": "pong",
            "zen": zen,
            "hook_id": hook_id,
            "delivery": x_github_delivery,
        }

    if event == "pull_request":
        action = payload.get("action")
        if action not in ("opened", "synchronize", "reopened"):
            return {
                "status": "ignored",
                "action": action,
                "message": f"PR action '{action}' does not trigger an automated review.",
            }

        repo_data = payload.get("repository", {})
        pr_data = payload.get("pull_request", {})
        owner = repo_data.get("owner", {}).get("login", "")
        repo_name = repo_data.get("name", "")
        pr_number = pr_data.get("number")
        pr_title = pr_data.get("title", f"PR #{pr_number}")
        head_sha = pr_data.get("head", {}).get("sha")
        author = pr_data.get("user", {}).get("login", "Developer")

        if not owner or not repo_name or not pr_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required repository or pull request details in payload.",
            )

        if settings.github_auto_review:
            background_tasks.add_task(
                process_github_webhook_pr_review,
                owner=owner,
                repo=repo_name,
                pull_number=pr_number,
                pr_title=pr_title,
                head_sha=head_sha,
                author=author,
            )

        return {
            "status": "accepted",
            "delivery": x_github_delivery,
            "repository": f"{owner}/{repo_name}",
            "pull_request": pr_number,
            "head_sha": head_sha,
            "action": action,
            "message": "PR review dispatched for background processing.",
        }

    if event == "installation":
        action = payload.get("action", "")
        installation_id = str((payload.get("installation") or {}).get("id") or "")
        if installation_id and action in ("deleted", "suspend"):
            session_factory = get_session_factory()
            with session_factory() as wh_db:
                conns = (
                    wh_db.query(GitHubConnectionRecord)
                    .filter(GitHubConnectionRecord.installation_id == installation_id)
                    .all()
                )
                for conn in conns:
                    conn.connection_status = "revoked" if action == "deleted" else "expired"
                    conn.encrypted_access_token = None
                    user_rec = (
                        wh_db.query(UserRecord).filter(UserRecord.id == conn.user_id).first()
                    )
                    if user_rec:
                        user_rec.github_connected = False
                        user_rec.github_token = None
                wh_db.commit()
            get_github_cache().clear()
        return {
            "status": "processed",
            "event": "installation",
            "action": action,
            "installation_id": installation_id,
        }

    if event == "installation_repositories":
        get_github_cache().clear()
        return {
            "status": "processed",
            "event": "installation_repositories",
            "action": payload.get("action", ""),
        }

    return {
        "status": "ignored",
        "event": event,
        "message": f"Webhook event '{event}' is not monitored.",
    }


def _generate_github_state(
    user_id: str | None = None,
    origin: str | None = None,
    *,
    intent: str = "connect",
) -> str:
    settings = get_settings()
    fallback_origin = (
        settings.frontend_url.rstrip("/") if settings.frontend_url else "http://localhost:5173"
    )
    target_origin = (origin or fallback_origin).rstrip("/")
    payload = {
        "nonce": secrets.token_hex(16),
        "user_id": user_id,
        "origin": target_origin,
        "intent": intent,
        "exp": int(time.time()) + 600,
    }
    return jwt.encode(payload, settings.session_secret, algorithm=ALGORITHM)


def _decode_github_state(state: str | None) -> dict[str, Any] | None:
    if not state:
        return None
    settings = get_settings()
    try:
        return jwt.decode(state, settings.session_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        logger.warning("Invalid GitHub state parameter: %s", exc)
        return None


def _upsert_github_connection(
    db: Session,
    *,
    user: UserRecord,
    auth_method: str,
    username: str | None,
    access_token: str | None,
    account_id: str | None = None,
    installation_id: str | None = None,
    token_expires_at: datetime | None = None,
    permissions: dict[str, Any] | None = None,
) -> GitHubConnectionRecord:
    ensure_github_tables()
    conn = (
        db.query(GitHubConnectionRecord)
        .filter(GitHubConnectionRecord.user_id == user.id)
        .order_by(GitHubConnectionRecord.updated_at.desc())
        .first()
    )
    if not conn:
        conn = GitHubConnectionRecord(user_id=user.id)
        db.add(conn)

    conn.auth_method = auth_method
    conn.github_account_id = account_id
    conn.github_username = username
    conn.installation_id = installation_id
    conn.encrypted_access_token = encrypt_secret(access_token) if access_token else None
    conn.token_expires_at = token_expires_at
    if permissions is not None:
        conn.permissions_json = permissions
    conn.connection_status = "connected"

    # Maintain backward compatibility with legacy UserRecord fields used by existing PR review routes
    user.github_connected = True
    user.github_username = username
    user.github_token = encrypt_secret(access_token) if access_token else user.github_token
    db.commit()
    db.refresh(conn)
    get_github_cache().invalidate_scope(f"user:{user.id}")
    return conn


@router.get("/status", response_model=GitHubStatusResponse)
def get_github_status(
    db: Session = Depends(get_db),
    user: UserRecord | None = Depends(get_current_user_optional),
) -> GitHubStatusResponse:
    settings = get_settings()
    svc = GitHubService()
    has_oauth_config = bool(settings.github_client_id and settings.github_client_secret)
    app_configured = svc.is_github_app_configured()

    resolved = resolve_user_github_context(db, user)
    if not resolved.connected:
        return GitHubStatusResponse(
            connected=False,
            username=resolved.username,
            configured=has_oauth_config or app_configured,
            auth_type="github_app"
            if app_configured
            else ("oauth" if has_oauth_config else "token"),
            auth_method=resolved.auth_method,
            connection_status=resolved.connection_status,
            app_configured=app_configured,
            installation_id=resolved.installation_id,
        )

    return GitHubStatusResponse(
        connected=True,
        username=resolved.username,
        configured=has_oauth_config or app_configured,
        auth_type="github_app"
        if resolved.auth_method == "github_app"
        else ("oauth" if has_oauth_config else "token"),
        auth_method=resolved.auth_method,
        connection_status=resolved.connection_status,
        app_configured=app_configured,
        installation_id=resolved.installation_id,
    )


@router.get("/app/install-url")
def get_github_app_install_url(
    origin: str | None = Query(default=None),
    user: UserRecord | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    svc = GitHubService()
    if not svc.is_github_app_configured():
        return {
            "url": "",
            "configured": False,
            "message": "GitHub App is not configured in environment (GITHUB_APP_ID / SLUG / KEY).",
        }
    state = _generate_github_state(user_id=user.id if user else None, origin=origin)
    return {
        "url": svc.get_app_install_url(state=state),
        "configured": True,
    }


@router.get("/app/callback")
def github_app_callback(
    installation_id: str | None = Query(default=None),
    setup_action: str | None = Query(default=None),
    state: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: UserRecord | None = Depends(get_current_user_optional),
) -> RedirectResponse:
    settings = get_settings()
    state_data = _decode_github_state(state)
    target_origin = (
        state_data.get("origin")
        if state_data and "origin" in state_data
        else (
            settings.frontend_url.rstrip("/") if settings.frontend_url else "http://localhost:5173"
        )
    )

    if not installation_id or not state_data:
        return RedirectResponse(url=f"{target_origin}/?github=error&reason=invalid_state")

    target_user = current_user
    if not target_user and state_data.get("user_id"):
        target_user = db.query(UserRecord).filter(UserRecord.id == state_data["user_id"]).first()

    if not target_user:
        return RedirectResponse(url=f"{target_origin}/?github=error&reason=auth_required")

    if current_user and state_data.get("user_id") and state_data["user_id"] != current_user.id:
        logger.warning(
            "GitHub App callback state user mismatch: %s vs %s",
            state_data.get("user_id"),
            current_user.id,
        )
        return RedirectResponse(url=f"{target_origin}/?github=error&reason=state_mismatch")

    svc = GitHubService()
    try:
        token_data = svc.create_installation_access_token(installation_id)
        access_token = token_data.get("token")
        if not access_token:
            raise GitHubAuthError("Empty installation token returned by GitHub.")

        expires_raw = token_data.get("expires_at")
        expires_dt = (
            datetime.fromisoformat(expires_raw.replace("Z", "+00:00")) if expires_raw else None
        )
        install_details = svc.get_installation_details(installation_id)
        account = install_details.get("account") or {}
        username = account.get("login") or "github_app_user"
        account_id = str(account.get("id") or "")

        _upsert_github_connection(
            db,
            user=target_user,
            auth_method="github_app",
            username=username,
            access_token=access_token,
            account_id=account_id,
            installation_id=str(installation_id),
            token_expires_at=expires_dt,
            permissions=token_data.get("permissions") or {},
        )
        logger.info(
            "Connected GitHub App installation %s (%s) for user %s (action=%s)",
            installation_id,
            username,
            target_user.id,
            setup_action,
        )
        return RedirectResponse(url=f"{target_origin}/?github=connected")
    except Exception as exc:
        logger.error("GitHub App callback failed: %s", exc)
        return RedirectResponse(url=f"{target_origin}/?github=error")


@router.get("/auth-url")
def get_github_auth_url(
    origin: str | None = Query(default=None),
    user: UserRecord | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.github_client_id:
        return {
            "url": "",
            "configured": False,
            "message": (
                "GitHub OAuth is not configured on the server. "
                "GITHUB_CLIENT_ID is missing in .env. "
                "Please connect using a Personal Access Token on the right, or configure GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET."
            ),
        }
    service = GitHubService()
    state = _generate_github_state(user_id=user.id if user else None, origin=origin)
    url = service.get_oauth_url(state=state)
    return {
        "url": url,
        "configured": bool(url),
        "message": None if url else "GitHub Client ID is not configured.",
    }


@router.get("/reauth-url")
def get_github_reauth_url(
    origin: str | None = Query(default=None),
    user: UserRecord = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.github_connected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No GitHub account is connected to re-authenticate.",
        )
    settings = get_settings()
    if not settings.github_client_id:
        return {
            "url": "",
            "configured": False,
            "message": "GitHub OAuth is not configured on the server.",
        }
    service = GitHubService()
    state = _generate_github_state(
        user_id=user.id,
        origin=origin,
        intent="reauth_delete",
    )
    url = service.get_oauth_url(state=state)
    return {
        "url": url,
        "configured": bool(url),
    }


@router.get("/callback")
def github_callback(
    code: str = Query(...),
    state: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: UserRecord | None = Depends(get_current_user_optional),
) -> RedirectResponse:
    settings = get_settings()
    service = GitHubService()
    state_data = _decode_github_state(state)
    intent = state_data.get("intent", "connect") if state_data else "connect"
    target_origin = (
        state_data.get("origin")
        if state_data and "origin" in state_data
        else (
            settings.frontend_url.rstrip("/") if settings.frontend_url else "http://localhost:5173"
        )
    )
    target_user = user
    if not target_user and state_data and state_data.get("user_id"):
        target_user = db.query(UserRecord).filter(UserRecord.id == state_data["user_id"]).first()

    if state and not state_data:
        logger.warning("Rejected GitHub OAuth callback due to invalid state parameter.")
        if intent == "reauth_delete":
            return RedirectResponse(
                url=f"{target_origin}/?view=settings&reauth_error=invalid_state"
            )
        return RedirectResponse(url=f"{target_origin}/?github=error&reason=invalid_state")

    try:
        access_token = service.exchange_code(code)
        gh_profile = service.get_user_profile(access_token)
        username = gh_profile.get("login", "github_user")
        account_id = str(gh_profile.get("id") or "")

        if intent == "reauth_delete":
            if not target_user:
                return RedirectResponse(
                    url=f"{target_origin}/?view=settings&reauth_error=auth_required"
                )
            conn = (
                db.query(GitHubConnectionRecord)
                .filter(GitHubConnectionRecord.user_id == target_user.id)
                .order_by(GitHubConnectionRecord.updated_at.desc())
                .first()
            )
            expected_id = str(conn.github_account_id) if (conn and conn.github_account_id) else ""
            expected_login = (
                conn.github_username
                if (conn and conn.github_username)
                else (target_user.github_username or "")
            ).lower()
            id_ok = bool(expected_id and account_id and expected_id == account_id)
            login_ok = bool(expected_login and username and expected_login == username.lower())
            if not (id_ok or login_ok):
                return RedirectResponse(
                    url=f"{target_origin}/?view=settings&reauth_error=github_account_mismatch",
                    status_code=status.HTTP_302_FOUND,
                )
            reauth_token = create_reauth_token(
                target_user, purpose="account_delete", method="github"
            )
            return RedirectResponse(
                url=f"{target_origin}/?view=settings&reauth_delete_token={reauth_token}",
                status_code=status.HTTP_302_FOUND,
            )

        if target_user:
            _upsert_github_connection(
                db,
                user=target_user,
                auth_method="oauth",
                username=username,
                access_token=access_token,
                account_id=account_id,
            )
            logger.info(
                "Successfully connected GitHub OAuth %s for user %s", username, target_user.id
            )

        return RedirectResponse(url=f"{target_origin}/?github=connected")
    except Exception as exc:
        logger.error("GitHub OAuth callback failed: %s", exc)
        if intent == "reauth_delete":
            return RedirectResponse(
                url=f"{target_origin}/?view=settings&reauth_error=github_reauth_failed"
            )
        return RedirectResponse(url=f"{target_origin}/?github=error")


@router.post("/connect", response_model=GitHubStatusResponse)
def connect_github_token(
    payload: GitHubConnectRequest,
    db: Session = Depends(get_db),
    user: UserRecord | None = Depends(get_current_user_optional),
) -> GitHubStatusResponse:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to connect GitHub.",
        )

    service = GitHubService()
    try:
        clean_token = payload.token.strip()
        gh_profile = service.get_user_profile(clean_token)
        username = gh_profile.get("login", "developer")
        account_id = str(gh_profile.get("id") or "")

        _upsert_github_connection(
            db,
            user=user,
            auth_method="pat",
            username=username,
            access_token=clean_token,
            account_id=account_id,
        )

        logger.info("Connected GitHub token for user %s (%s)", user.id, username)
        return GitHubStatusResponse(
            connected=True,
            username=username,
            configured=True,
            auth_type="token",
            auth_method="pat",
            connection_status="connected",
            app_configured=service.is_github_app_configured(),
        )
    except Exception as exc:
        logger.error("Failed to validate GitHub token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid GitHub token or connection failed: {exc}",
        ) from exc


@router.post("/disconnect", response_model=GitHubStatusResponse)
def disconnect_github(
    db: Session = Depends(get_db),
    user: UserRecord | None = Depends(get_current_user_optional),
) -> GitHubStatusResponse:
    svc = GitHubService()
    if user:
        ensure_github_tables()
        conns = (
            db.query(GitHubConnectionRecord)
            .filter(GitHubConnectionRecord.user_id == user.id)
            .all()
        )
        for conn in conns:
            conn.connection_status = "disconnected"
            conn.encrypted_access_token = None
            conn.encrypted_refresh_token = None
        user.github_connected = False
        user.github_token = None
        user.github_username = None
        db.commit()
        get_github_cache().invalidate_scope(f"user:{user.id}")
        logger.info("Disconnected GitHub account for user %s", user.id)

    return GitHubStatusResponse(
        connected=False,
        username=None,
        configured=svc.is_github_app_configured(),
        auth_type="oauth",
        auth_method="none",
        connection_status="disconnected",
        app_configured=svc.is_github_app_configured(),
    )


def _get_active_token(user: UserRecord | None, db: Session | None = None) -> str:
    if db is not None and user is not None:
        resolved = resolve_user_github_context(db, user)
        if not resolved.connected or not resolved.token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "GitHub is not connected or authorization expired. "
                    "Please connect your GitHub account."
                ),
            )
        return resolved.token

    if not user or not user.github_connected or not user.github_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "GitHub is not connected. Please connect your GitHub account via "
                "Settings or the Pull Requests page."
            ),
        )
    from code_review.web.crypto import decrypt_secret

    return decrypt_secret(user.github_token) or user.github_token


@router.get("/repos", response_model=list[dict[str, Any]])
def list_repositories(
    db: Session = Depends(get_db),
    user: UserRecord = Depends(get_current_user),
) -> list[dict[str, Any]]:
    resolved = resolve_user_github_context(db, user)
    if not resolved.connected or not resolved.token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub is not connected. Please connect your GitHub account.",
        )
    service = GitHubService(resolved.token, cache_scope=resolved.cache_scope)
    try:
        return service.list_repositories()
    except GitHubAuthError as exc:
        logger.warning("GitHub auth error listing repos for user %s: %s", user.id, exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to list GitHub repositories: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error fetching repositories: {exc}",
        ) from exc


@router.get("/repos/{owner}/{repo}/pulls", response_model=list[dict[str, Any]])
def list_pull_requests(
    owner: str,
    repo: str,
    db: Session = Depends(get_db),
    user: UserRecord = Depends(get_current_user),
) -> list[dict[str, Any]]:
    token = _get_active_token(user, db)
    service = GitHubService(token, cache_scope=f"user:{user.id}")
    try:
        return service.list_pull_requests(owner, repo)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to list GitHub pull requests for %s/%s: %s", owner, repo, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error fetching pull requests: {exc}",
        ) from exc


@router.get("/repos/{owner}/{repo}/pulls/{number}/diff")
def get_pull_request_diff(
    owner: str,
    repo: str,
    number: int,
    db: Session = Depends(get_db),
    user: UserRecord = Depends(get_current_user),
) -> dict[str, Any]:
    token = _get_active_token(user, db)
    service = GitHubService(token, cache_scope=f"user:{user.id}")
    try:
        return service.get_pull_request_diff(owner, repo, number)
    except HTTPException:
        raise
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err)
        ) from val_err
    except Exception as exc:
        logger.error("Failed to get diff for %s/%s PR #%s: %s", owner, repo, number, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error fetching pull request diff: {exc}",
        ) from exc


def _run_user_pr_review_job(
    job_id: str,
    user_id: str,
    token: str,
    owner: str,
    repo: str,
    number: int,
    pr_title: str,
    diff_text: str,
    head_sha: str | None,
    post_to_github: bool,
) -> None:
    session_factory = get_session_factory()
    db = session_factory()
    repo_name = f"{owner}/{repo}"
    pr_identifier = f"#{number}"

    def on_agent_progress(agent_name: str, agent_status: str) -> None:
        with _REVIEW_JOBS_LOCK:
            job = _REVIEW_JOBS.get(job_id)
            if job is not None:
                job["agents"][agent_name] = agent_status
                job["completed_agents"] = sum(
                    value in ("completed", "failed") for value in job["agents"].values()
                )

    try:
        settings = get_settings()
        provider = "llm" if settings.llm_provider in ("nvidia", "llm") else settings.llm_provider
        model_name = settings.nvidia_model if provider == "llm" else settings.ollama_model
        start_time = time.perf_counter()
        enabled_agent_ids = get_persisted_enabled_agent_ids(db)
        orchestrator = ReviewOrchestrator(
            enabled_agent_ids=enabled_agent_ids,
            include_semantic="semantic" in enabled_agent_ids,
            include_llm=bool({"documentation", "test", "llm"} & enabled_agent_ids),
            llm_provider=provider,
            parallel=True,
            progress_callback=on_agent_progress,
        )
        with _REVIEW_JOBS_LOCK:
            job = _REVIEW_JOBS.get(job_id)
            if job is not None:
                job["agents"] = {agent.name: "queued" for agent in orchestrator.agents}
                job["total_agents"] = len(orchestrator.agents)
                job["status"] = "running"

        result = orchestrator.review_diff(diff_text)
        duration = round(time.perf_counter() - start_time, 2)
        review = ReviewRecord(
            user_id=user_id,
            repository_name=repo_name,
            pr_identifier=pr_identifier,
            title=f"GitHub PR #{number}: {pr_title}",
            diff_content=diff_text,
            provider=provider,
            model_name=model_name,
            agents_used=[agent.name for agent in orchestrator.agents],
            finding_count=result.total_findings,
            has_critical=result.has_critical,
            duration_seconds=duration,
        )
        db.add(review)
        db.flush()

        created_findings: list[FindingRecord] = []
        for finding in result.findings:
            record = FindingRecord(
                review_id=review.id,
                agent=finding.agent.value,
                title=finding.message[:120],
                description=finding.message,
                severity=finding.severity.value.upper(),
                category=finding.category.value.upper(),
                file_path=finding.file,
                line_start=finding.line,
                line_end=finding.line,
                suggested_fix=finding.suggestion,
                rule_id=finding.rule_id,
                evidence=finding.file,
            )
            db.add(record)
            created_findings.append(record)
        db.commit()
        db.refresh(review)

        response = ReviewDetailResponse(
            id=review.id,
            repository_name=review.repository_name,
            pr_identifier=review.pr_identifier,
            title=review.title,
            provider=review.provider,
            model_name=review.model_name,
            agents_used=review.agents_used,
            finding_count=review.finding_count,
            has_critical=review.has_critical,
            duration_seconds=review.duration_seconds,
            created_at=review.created_at,
            diff_content=review.diff_content,
            findings=[FindingResponse.model_validate(item) for item in created_findings],
        )

        if post_to_github:
            try:
                service = GitHubService(token)
                summary_md, inline_comments, verdict_action = service.format_pr_review(
                    findings=result.findings,
                    owner=owner,
                    repo=repo,
                    pull_number=number,
                    diff_text=diff_text,
                    duration_seconds=duration,
                    commit_sha=head_sha,
                    dashboard_url=settings.github_dashboard_url or None,
                )
                service.post_pull_request_review(
                    owner=owner,
                    repo=repo,
                    pull_number=number,
                    body=summary_md,
                    event=verdict_action,
                    comments=inline_comments,
                    commit_sha=head_sha,
                )
            except Exception as exc:
                logger.warning("Could not auto-post review to GitHub PR: %s", exc)

        with _REVIEW_JOBS_LOCK:
            job = _REVIEW_JOBS.get(job_id)
            if job is not None:
                job["status"] = "completed"
                job["review"] = response.model_dump(mode="json")
        logger.info("Completed multi-agent review for GitHub PR %s %s", repo_name, pr_identifier)
    except Exception as exc:
        logger.exception("Review job failed for PR %s %s", repo_name, pr_identifier)
        db.rollback()
        with _REVIEW_JOBS_LOCK:
            job = _REVIEW_JOBS.get(job_id)
            if job is not None:
                job["status"] = "failed"
                job["error"] = str(exc)
    finally:
        db.close()


@router.post("/repos/{owner}/{repo}/pulls/{number}/review")
def review_pull_request(
    owner: str,
    repo: str,
    number: int,
    background_tasks: BackgroundTasks,
    post_to_github: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: UserRecord = Depends(get_current_user),
) -> dict[str, str]:
    token = _get_active_token(user, db)
    user_id = user.id
    service = GitHubService(token, cache_scope=f"user:{user.id}")

    try:
        diff_info = service.get_pull_request_diff(owner, repo, number)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err)
        ) from val_err
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch GitHub PR diff: {exc}",
        ) from exc

    diff_text = diff_info["diff"]
    pr_title = diff_info["title"]
    head_sha = diff_info.get("head_sha")
    job_id = str(uuid4())
    with _REVIEW_JOBS_LOCK:
        expired_jobs = [
            existing_id
            for existing_id, existing_job in _REVIEW_JOBS.items()
            if existing_job.get("status") in ("completed", "failed")
            and time.monotonic() - existing_job.get("created_at", 0) > 3600
        ]
        for existing_id in expired_jobs:
            _REVIEW_JOBS.pop(existing_id, None)
        _REVIEW_JOBS[job_id] = {
            "user_id": user_id,
            "created_at": time.monotonic(),
            "status": "queued",
            "agents": {},
            "completed_agents": 0,
            "total_agents": 0,
        }
    background_tasks.add_task(
        _run_user_pr_review_job,
        job_id,
        user_id,
        token,
        owner,
        repo,
        number,
        pr_title,
        diff_text,
        head_sha,
        post_to_github,
    )
    return {"job_id": job_id, "diff": diff_text, "title": f"PR #{number}: {pr_title}"}


@router.get("/review-jobs/{job_id}")
def get_review_job_status(
    job_id: str,
    user: UserRecord = Depends(get_current_user),
) -> dict[str, Any]:
    with _REVIEW_JOBS_LOCK:
        job = _REVIEW_JOBS.get(job_id)
        if job is None or job.get("user_id") != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review job not found",
            )
        return {key: value for key, value in job.items() if key not in {"user_id", "created_at"}}


@router.post(
    "/repos/{owner}/{repo}/pulls/{number}/post-review",
    response_model=PostReviewResponse,
)
def publish_review_to_github(
    owner: str,
    repo: str,
    number: int,
    payload: PostReviewRequest,
    db: Session = Depends(get_db),
    user: UserRecord = Depends(get_current_user),
) -> PostReviewResponse:
    token = _get_active_token(user, db)
    service = GitHubService(token, cache_scope=f"user:{user.id}")
    settings = get_settings()

    review: ReviewRecord | None = None
    if payload.review_id:
        review = (
            db.query(ReviewRecord)
            .filter(ReviewRecord.id == payload.review_id, ReviewRecord.user_id == user.id)
            .first()
        )
        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Specified review not found or unauthorized.",
            )

    if not review:
        try:
            diff_info = service.get_pull_request_diff(owner, repo, number)
            diff_text = diff_info["diff"]
            head_sha = payload.commit_sha or diff_info.get("head_sha")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to fetch PR diff: {exc}",
            ) from exc

        orchestrator = ReviewOrchestrator(
            include_semantic=True,
            include_llm=True,
            parallel=True,
        )
        result = orchestrator.review_diff(diff_text)
        summary_md, inline_comments, verdict_action = service.format_pr_review(
            findings=result.findings,
            owner=owner,
            repo=repo,
            pull_number=number,
            diff_text=diff_text,
            duration_seconds=result.review_time_ms / 1000.0,
            commit_sha=head_sha,
            dashboard_url=settings.github_dashboard_url or None,
        )
        findings_count = len(result.findings)
    else:
        diff_text = review.diff_content
        head_sha = payload.commit_sha
        summary_md, inline_comments, verdict_action = service.format_pr_review(
            findings=review.findings,
            owner=owner,
            repo=repo,
            pull_number=number,
            diff_text=diff_text,
            duration_seconds=review.duration_seconds,
            commit_sha=head_sha,
            dashboard_url=settings.github_dashboard_url or None,
        )
        findings_count = len(review.findings)

    try:
        gh_resp = service.post_pull_request_review(
            owner=owner,
            repo=repo,
            pull_number=number,
            body=summary_md,
            event=payload.event or verdict_action,
            comments=inline_comments,
            commit_sha=head_sha,
        )
        return PostReviewResponse(
            status="published",
            github_review_id=gh_resp.get("id"),
            review_url=gh_resp.get("html_url"),
            total_findings=findings_count,
            inline_comments_posted=len(inline_comments),
            verdict=payload.event or verdict_action,
        )
    except Exception as exc:
        logger.error("Failed to post PR review to GitHub: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to publish review to GitHub PR: {exc}",
        ) from exc


@router.get(
    "/context/{conversation_id}",
    response_model=ConversationRepoContextResponse | None,
)
def get_conversation_repo_context(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: UserRecord | None = Depends(get_current_user_optional),
) -> ConversationRepoContextResponse | None:
    conv_q = db.query(ConversationRecord).filter(ConversationRecord.id == conversation_id)
    if user:
        conv_q = conv_q.filter(ConversationRecord.user_id == user.id)
    else:
        conv_q = conv_q.filter(ConversationRecord.user_id.is_(None))
    if not conv_q.first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        )

    ensure_github_tables()
    ctx = (
        db.query(ConversationRepositoryContextRecord)
        .filter(ConversationRepositoryContextRecord.conversation_id == conversation_id)
        .first()
    )
    if not ctx:
        return None
    return ConversationRepoContextResponse(
        conversation_id=ctx.conversation_id,
        repository_full_name=ctx.repository_full_name,
        repository_id=ctx.repository_id,
        default_branch=ctx.default_branch,
        selected_branch=ctx.selected_branch,
        last_inspected_commit=ctx.last_inspected_commit,
    )


@router.post(
    "/context/{conversation_id}",
    response_model=ConversationRepoContextResponse,
)
def set_conversation_repo_context(
    conversation_id: str,
    payload: ConversationRepoContextRequest,
    db: Session = Depends(get_db),
    user: UserRecord | None = Depends(get_current_user_optional),
) -> ConversationRepoContextResponse:
    conv_q = db.query(ConversationRecord).filter(ConversationRecord.id == conversation_id)
    if user:
        conv_q = conv_q.filter(ConversationRecord.user_id == user.id)
    else:
        conv_q = conv_q.filter(ConversationRecord.user_id.is_(None))
    if not conv_q.first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        )

    if "/" not in payload.repository_full_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="repository_full_name must be in 'owner/repo' format.",
        )

    owner, repo = payload.repository_full_name.split("/", 1)
    resolved = resolve_user_github_context(db, user)
    svc = GitHubService(
        resolved.token if resolved.connected else None, cache_scope=resolved.cache_scope
    )
    try:
        details = svc.get_repository_details(owner, repo)
    except GitHubApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    ctx = (
        db.query(ConversationRepositoryContextRecord)
        .filter(ConversationRepositoryContextRecord.conversation_id == conversation_id)
        .first()
    )
    if not ctx:
        ctx = ConversationRepositoryContextRecord(
            conversation_id=conversation_id,
            user_id=user.id if user else None,
        )
        db.add(ctx)

    ctx.repository_full_name = details.get("full_name") or payload.repository_full_name
    ctx.repository_id = str(details.get("id") or payload.repository_id or "")
    ctx.default_branch = details.get("default_branch") or payload.default_branch
    ctx.selected_branch = payload.selected_branch or ctx.default_branch
    db.commit()
    db.refresh(ctx)

    return ConversationRepoContextResponse(
        conversation_id=ctx.conversation_id,
        repository_full_name=ctx.repository_full_name,
        repository_id=ctx.repository_id,
        default_branch=ctx.default_branch,
        selected_branch=ctx.selected_branch,
        last_inspected_commit=ctx.last_inspected_commit,
    )
