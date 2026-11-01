from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any
from uuid import uuid4

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
from code_review.db.models import FindingRecord, ReviewRecord, UserRecord
from code_review.github.service import GitHubService
from code_review.orchestrator import ReviewOrchestrator
from code_review.web.auth import get_current_user, get_current_user_optional
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

    return {
        "status": "ignored",
        "event": event,
        "message": f"Webhook event '{event}' is not monitored.",
    }


@router.get("/status", response_model=GitHubStatusResponse)
def get_github_status(
    user: UserRecord | None = Depends(get_current_user_optional),
) -> GitHubStatusResponse:
    settings = get_settings()
    has_oauth_config = bool(settings.github_client_id and settings.github_client_secret)

    if not user or not user.github_connected or not user.github_token:
        return GitHubStatusResponse(
            connected=False,
            username=None,
            configured=has_oauth_config,
            auth_type="oauth" if has_oauth_config else "token",
        )

    return GitHubStatusResponse(
        connected=True,
        username=user.github_username,
        configured=has_oauth_config,
        auth_type="oauth" if has_oauth_config else "token",
    )


@router.get("/auth-url")
def get_github_auth_url() -> dict[str, str]:
    service = GitHubService()
    url = service.get_oauth_url()
    return {"url": url}


@router.get("/callback")
def github_callback(
    code: str = Query(...),
    db: Session = Depends(get_db),
    user: UserRecord | None = Depends(get_current_user_optional),
) -> RedirectResponse:
    settings = get_settings()
    service = GitHubService()
    try:
        access_token = service.exchange_code(code)
        gh_profile = service.get_user_profile(access_token)
        username = gh_profile.get("login", "github_user")

        if user:
            user.github_connected = True
            user.github_token = access_token
            user.github_username = username
            db.commit()
            logger.info("Successfully connected GitHub account %s for user %s", username, user.id)

        redirect_target = f"{settings.frontend_url}/?github=connected"
        return RedirectResponse(url=redirect_target)
    except Exception as exc:
        logger.error("GitHub OAuth callback failed: %s", exc)
        redirect_target = f"{settings.frontend_url}/?github=error"
        return RedirectResponse(url=redirect_target)


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
        gh_profile = service.get_user_profile(payload.token.strip())
        username = gh_profile.get("login", "developer")

        user.github_connected = True
        user.github_token = payload.token.strip()
        user.github_username = username
        db.commit()
        db.refresh(user)

        logger.info("Connected GitHub token for user %s (%s)", user.id, username)
        return GitHubStatusResponse(
            connected=True,
            username=username,
            configured=True,
            auth_type="token",
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
    if user:
        user.github_connected = False
        user.github_token = None
        user.github_username = None
        db.commit()
        logger.info("Disconnected GitHub account for user %s", user.id)

    return GitHubStatusResponse(
        connected=False,
        username=None,
        configured=False,
        auth_type="oauth",
    )


def _get_active_token(user: UserRecord | None) -> str:
    if not user or not user.github_connected or not user.github_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "GitHub is not connected. Please connect your GitHub account via "
                "Settings or the Pull Requests page."
            ),
        )
    return user.github_token


@router.get("/repos", response_model=list[dict[str, Any]])
def list_repositories(
    user: UserRecord = Depends(get_current_user),
) -> list[dict[str, Any]]:
    token = _get_active_token(user)
    service = GitHubService(token)
    try:
        return service.list_repositories()
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
    user: UserRecord = Depends(get_current_user),
) -> list[dict[str, Any]]:
    token = _get_active_token(user)
    service = GitHubService(token)
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
    user: UserRecord = Depends(get_current_user),
) -> dict[str, Any]:
    token = _get_active_token(user)
    service = GitHubService(token)
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
    user: UserRecord = Depends(get_current_user),
) -> dict[str, str]:
    token = _get_active_token(user)
    user_id = user.id
    service = GitHubService(token)

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
        return {
            key: value
            for key, value in job.items()
            if key not in {"user_id", "created_at"}
        }


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
    token = _get_active_token(user)
    service = GitHubService(token)
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
