from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from code_review.db.models import UserRecord
from code_review.github.service import GitHubService
from code_review.web.auth import get_current_user
from code_review.web.schemas import PullRequestResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pull-requests", tags=["Pull Requests"])


def _parse_pr_datetime(dt_str: str | None) -> datetime:
    if not dt_str:
        return datetime.now(UTC)
    try:
        clean = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean)
    except Exception:
        return datetime.now(UTC)


@router.get("", response_model=list[PullRequestResponse])
def list_pull_requests(
    status_filter: str | None = Query(None, alias="status"),
    repository: str | None = Query(None),
    search: str | None = Query(None),
    user: UserRecord = Depends(get_current_user),
) -> list[PullRequestResponse]:
    if not user.github_connected or not user.github_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "GITHUB_NOT_CONNECTED: GitHub account is not connected. "
                "Please connect your GitHub account via Settings or the Pull Requests page."
            ),
        )

    service = GitHubService(user.github_token)
    try:
        repos = service.list_repositories()
    except Exception as exc:
        logger.error("Failed to list GitHub repositories for user %s: %s", user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error fetching repositories: {exc}",
        ) from exc

    target_repos = repos
    if repository and repository.lower() != "all":
        target_repos = [
            r
            for r in repos
            if r["full_name"].lower() == repository.lower()
            or r["name"].lower() == repository.lower()
        ]
        if not target_repos:
            return []

    all_prs: list[PullRequestResponse] = []
    for r in target_repos[:8]:
        owner = r["owner"]
        repo_name = r["name"]
        full_name = r.get("full_name") or f"{owner}/{repo_name}"
        try:
            raw_prs = service.list_pull_requests(owner, repo_name)
            for p in raw_prs:
                pr_item = PullRequestResponse(
                    id=f"{full_name}#{p['number']}",
                    repository_name=full_name,
                    pr_number=p["number"],
                    title=p["title"],
                    source_branch=p.get("head_branch") or "feature",
                    target_branch=p.get("base_branch") or "main",
                    author=p.get("author") or "Unknown",
                    status=p.get("state") or "open",
                    additions=0,
                    deletions=0,
                    changed_files=1,
                    created_at=_parse_pr_datetime(p.get("created_at")),
                )
                all_prs.append(pr_item)
        except Exception as pr_err:
            logger.warning("Could not list pull requests for %s: %s", full_name, pr_err)

    if status_filter and status_filter.lower() != "all":
        norm_status = status_filter.lower()
        all_prs = [pr for pr in all_prs if pr.status.lower() == norm_status]

    if search:
        st = search.lower()
        all_prs = [
            pr
            for pr in all_prs
            if st in pr.title.lower()
            or st in pr.repository_name.lower()
            or st in pr.author.lower()
            or st in pr.source_branch.lower()
            or st in pr.target_branch.lower()
        ]

    all_prs.sort(key=lambda pr: pr.created_at, reverse=True)
    return all_prs


@router.get("/{owner}/{repo}/{number}", response_model=PullRequestResponse)
def get_pull_request(
    owner: str,
    repo: str,
    number: int,
    user: UserRecord = Depends(get_current_user),
) -> PullRequestResponse:
    if not user.github_connected or not user.github_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GITHUB_NOT_CONNECTED: GitHub account is not connected.",
        )

    service = GitHubService(user.github_token)
    try:
        repos = service.list_repositories()
        repo_names = {r["full_name"].lower() for r in repos} | {r["name"].lower() for r in repos}
        target_name = f"{owner}/{repo}".lower()
        if target_name not in repo_names and repo.lower() not in repo_names:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this repository.",
            )

        diff_info = service.get_pull_request_diff(owner, repo, number)
        return PullRequestResponse(
            id=f"{owner}/{repo}#{number}",
            repository_name=f"{owner}/{repo}",
            pr_number=number,
            title=diff_info.get("title", f"PR #{number}"),
            source_branch="feature",
            target_branch="main",
            author=diff_info.get("author", "Developer"),
            status=diff_info.get("state", "open"),
            additions=diff_info.get("additions", 0),
            deletions=diff_info.get("deletions", 0),
            changed_files=diff_info.get("changed_files", 1),
            created_at=datetime.now(UTC),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to fetch PR %s/%s #%s: %s", owner, repo, number, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error: {exc}",
        ) from exc
