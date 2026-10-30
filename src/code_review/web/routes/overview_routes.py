from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session, load_only

from code_review.db.database import get_db
from code_review.db.models import AgentConfigRecord, ReviewRecord, UserRecord
from code_review.github.service import GitHubService
from code_review.web.auth import get_current_user
from code_review.web.schemas import OverviewMetricsResponse, ReviewSummaryResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/overview", tags=["Overview"])


@router.get("/metrics", response_model=OverviewMetricsResponse)
def get_overview_metrics(
    db: Session = Depends(get_db),
    user: UserRecord = Depends(get_current_user),
) -> OverviewMetricsResponse:
    total_reviews, total_findings, critical_findings = (
        db.query(
            func.count(ReviewRecord.id),
            func.coalesce(func.sum(ReviewRecord.finding_count), 0),
            func.coalesce(
                func.sum(case((ReviewRecord.has_critical.is_(True), 1), else_=0)),
                0,
            ),
        )
        .filter(ReviewRecord.user_id == user.id)
        .one()
    )

    active_agents_count = (
        db.query(AgentConfigRecord).filter(AgentConfigRecord.is_enabled.is_(True)).count()
    )
    total_agents_count = db.query(AgentConfigRecord).count()

    is_github_connected = bool(user.github_connected and user.github_token)
    pull_requests_count: int | None = None
    open_pull_requests_count: int | None = None

    if is_github_connected:
        try:
            service = GitHubService(user.github_token)
            repos = service.list_repositories()
            total_prs = 0
            open_prs = 0
            for r in repos[:6]:
                try:
                    prs = service.list_pull_requests(r["owner"], r["name"])
                    total_prs += len(prs)
                    open_prs += sum(1 for p in prs if p.get("state") == "open")
                except Exception as pr_err:
                    logger.debug("Failed to list PRs for %s/%s: %s", r["owner"], r["name"], pr_err)
            pull_requests_count = total_prs
            open_pull_requests_count = open_prs
        except Exception as gh_err:
            logger.warning(
                "Could not calculate PR metrics from GitHub for user %s: %s", user.id, gh_err
            )
            pull_requests_count = None
            open_pull_requests_count = None

    recent_reviews = [
        ReviewSummaryResponse.model_validate(review)
        for review in (
            db.query(ReviewRecord)
            .options(
                load_only(
                    ReviewRecord.id,
                    ReviewRecord.repository_name,
                    ReviewRecord.pr_identifier,
                    ReviewRecord.title,
                    ReviewRecord.provider,
                    ReviewRecord.model_name,
                    ReviewRecord.agents_used,
                    ReviewRecord.finding_count,
                    ReviewRecord.has_critical,
                    ReviewRecord.duration_seconds,
                    ReviewRecord.created_at,
                )
            )
            .filter(ReviewRecord.user_id == user.id)
            .order_by(ReviewRecord.created_at.desc())
            .limit(4)
            .all()
        )
    ]

    return OverviewMetricsResponse(
        total_reviews=total_reviews,
        total_findings=total_findings,
        critical_findings=critical_findings,
        pull_requests_count=pull_requests_count,
        open_pull_requests_count=open_pull_requests_count,
        active_agents_count=active_agents_count,
        total_agents_count=total_agents_count,
        github_connected=is_github_connected,
        recent_reviews=recent_reviews,
    )
