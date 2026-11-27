"""Centralized deny-by-default server-side GitHub access guard and audit logging."""

from __future__ import annotations

import contextlib
import contextvars
import logging
import re
import threading
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Sensitive token patterns redacted from all audit log messages
_SECRET_TOKEN_RE = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,}|Bearer\s+[A-Za-z0-9._\-]{8,})",
    re.IGNORECASE,
)

# Maps each high-level LLM tool name to the exact underlying GitHubService operations it may invoke.
TOOL_SERVICE_OPERATIONS: dict[str, frozenset[str]] = {
    "get_user_repositories": frozenset({"list_repositories", "list_installation_repositories"}),
    "search_repositories": frozenset(
        {"search_repositories", "list_repositories", "list_installation_repositories"}
    ),
    "explore_repository_overview": frozenset(
        {"get_repository_details", "get_commit_history", "get_repository_tree", "fetch_file"}
    ),
    "get_repository_details": frozenset({"get_repository_details"}),
    "get_repository_branches": frozenset({"get_repository_branches"}),
    "get_repository_tree": frozenset({"get_repository_tree"}),
    "get_repository_contents": frozenset({"get_repository_contents"}),
    "fetch_file": frozenset({"fetch_file"}),
    "fetch_files": frozenset({"fetch_file"}),
    "search_repository_code": frozenset({"search_repository_code"}),
    "get_commit_history": frozenset({"get_commit_history"}),
    "get_commit_details": frozenset({"get_commit_details"}),
    "compare_commits": frozenset({"compare_commits"}),
    "get_pull_requests": frozenset({"list_pull_requests"}),
    "get_pull_request_details": frozenset({"get_pull_request_details"}),
    "get_pull_request_diff": frozenset({"get_pull_request_diff"}),
    "get_pull_request_files": frozenset({"get_pull_request_files"}),
    "get_pull_request_reviews": frozenset({"get_pull_request_reviews"}),
    "get_pull_request_comments": frozenset({"get_pull_request_comments"}),
    "get_repository_issues": frozenset({"get_repository_issues"}),
    "search_issues": frozenset({"search_issues"}),
    "get_issue_details": frozenset({"get_issue_details"}),
    "get_workflow_runs": frozenset({"get_workflow_runs"}),
    "get_check_runs": frozenset({"get_check_runs"}),
    "run_security_and_quality_agents": frozenset(
        {"get_repository_details", "get_repository_tree", "fetch_file"}
    ),
}

AUTH_HANDSHAKE_OPERATIONS: frozenset[str] = frozenset(
    {
        "exchange_code",
        "get_user_profile",
        "create_installation_access_token",
        "get_installation_details",
        "create_app_jwt",
    }
)

WEBHOOK_PR_OPERATIONS: frozenset[str] = frozenset(
    {
        "get_pull_request_diff",
        "create_commit_status",
        "post_pull_request_review",
    }
)

REST_PULL_REQUEST_LIST_OPERATIONS: frozenset[str] = frozenset(
    {"list_repositories", "list_installation_repositories", "list_pull_requests"}
)

REST_PULL_REQUEST_DETAIL_OPERATIONS: frozenset[str] = frozenset(
    {"list_repositories", "list_installation_repositories", "get_pull_request_diff"}
)

REST_PR_REVIEW_OPERATIONS: frozenset[str] = frozenset(
    {"get_pull_request_diff", "post_pull_request_review"}
)


def expand_tools_to_service_ops(tool_names: Iterable[str]) -> frozenset[str]:
    """Expand high-level registered tool names to their strictly required GitHubService operations."""
    ops: set[str] = set()
    for name in tool_names:
        ops.update(TOOL_SERVICE_OPERATIONS.get(str(name).strip(), ()))
    return frozenset(ops)


def sanitize_audit_text(text: str | None, *, max_len: int = 480) -> str:
    """Strip any credential-like token patterns before writing logs or DB audit records."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    cleaned = _SECRET_TOKEN_RE.sub("[REDACTED_CREDENTIAL]", raw)
    if len(cleaned) > max_len:
        return cleaned[:max_len] + "..."
    return cleaned


@dataclass(frozen=True)
class GitHubAccessGrant:
    """Short-lived, operation-scoped authorization ticket issued only by GitHubAccessGuard."""

    grant_id: str
    user_id: str | None
    conversation_id: str | None
    mode: str  # "normal" | "github" | "rest_explicit" | "auth" | "webhook"
    intent: str
    operation_scope: str
    allowed_operations: frozenset[str]
    repository: str | None = None
    auth_verified: bool = False
    allow_unauthenticated_public_repo: bool = False
    disconnect_epoch: int = 0
    reason: str = ""


_ACTIVE_GITHUB_GRANT: contextvars.ContextVar[GitHubAccessGrant | None] = contextvars.ContextVar(
    "nexarion_active_github_grant", default=None
)

# Tracks immediate per-user disconnect/revocation events in memory alongside DB state
_USER_DISCONNECT_EPOCHS: dict[str, int] = {}
_EPOCH_LOCK = threading.Lock()


def get_active_grant() -> GitHubAccessGrant | None:
    return _ACTIVE_GITHUB_GRANT.get()


@contextlib.contextmanager
def grant_scope(grant: GitHubAccessGrant | None) -> Iterator[None]:
    token = _ACTIVE_GITHUB_GRANT.set(grant)
    try:
        yield
    finally:
        try:
            _ACTIVE_GITHUB_GRANT.reset(token)
        except ValueError:
            # Streaming sync generators run across AnyIO threadpool contexts; clear locally instead of raising.
            _ACTIVE_GITHUB_GRANT.set(None)


def get_user_disconnect_epoch(user_id: str | None) -> int:
    if not user_id:
        return 0
    with _EPOCH_LOCK:
        return _USER_DISCONNECT_EPOCHS.get(user_id, 0)


def bump_user_disconnect_epoch(user_id: str | None) -> int:
    if not user_id:
        return 0
    with _EPOCH_LOCK:
        next_epoch = _USER_DISCONNECT_EPOCHS.get(user_id, 0) + 1
        _USER_DISCONNECT_EPOCHS[user_id] = next_epoch
        return next_epoch


def record_github_access_audit(
    *,
    user_id: str | None,
    conversation_id: str | None,
    mode: str,
    intent: str,
    operation: str,
    decision: str,
    reason: str,
    repository: str | None = None,
    db: Session | None = None,
) -> None:
    """Persist and emit a sanitized audit entry for every GitHub authorization decision."""
    safe_reason = sanitize_audit_text(reason, max_len=480)
    safe_repo = sanitize_audit_text(repository, max_len=240) if repository else None
    safe_op = sanitize_audit_text(operation, max_len=78) or "unknown"
    safe_mode = sanitize_audit_text(mode, max_len=20) or "normal"
    safe_intent = sanitize_audit_text(intent, max_len=64)
    norm_decision = "ALLOW" if decision == "ALLOW" else "DENY"
    timestamp_iso = datetime.now(UTC).isoformat()

    log_fn = logger.info if norm_decision == "ALLOW" else logger.warning
    log_fn(
        "[GITHUB_AUDIT] decision=%s user_id=%s conversation_id=%s mode=%s intent=%s operation=%s repository=%s timestamp=%s reason=%s",
        norm_decision,
        user_id or "anonymous",
        conversation_id or "none",
        safe_mode,
        safe_intent or "none",
        safe_op,
        safe_repo or "none",
        timestamp_iso,
        safe_reason,
    )

    try:
        from code_review.db.database import get_engine
        from code_review.db.models import GitHubAccessAuditRecord

        record = GitHubAccessAuditRecord(
            user_id=user_id,
            conversation_id=conversation_id,
            chat_mode=safe_mode,
            intent=safe_intent,
            operation=safe_op,
            repository=safe_repo,
            decision=norm_decision,
            reason=safe_reason,
            created_at=datetime.now(UTC),
        )
        # Always write audit logs in an isolated short session so caller rollbacks never erase audit trails
        engine = db.get_bind() if db is not None else get_engine()
        with Session(engine) as audit_session:
            audit_session.add(record)
            audit_session.commit()
    except Exception as exc:
        logger.debug("GitHub audit DB persistence skipped/deferred: %s", exc)


class GitHubAccessGuard:
    """
    Centralized server-side deny-by-default authorization authority for ALL GitHub operations:
    chat tool orchestration, REST endpoints, background workers, and GitHubService HTTP calls.
    """

    @staticmethod
    def _deny(message: str) -> Any:
        from code_review.github.service import GitHubAccessDeniedError

        return GitHubAccessDeniedError(message)

    @classmethod
    def authorize_chat_turn(
        cls,
        *,
        db: Session | None,
        user: Any | None,
        conversation_id: str | None,
        mode: str,
        intent: str,
        is_github_intent: bool,
        allow_tools: bool,
        allowed_tools: frozenset[str],
        explicit_repo: str | None = None,
        auth_connected: bool = False,
        auth_status: str = "not_connected",
        operation: str = "chat_github_orchestration",
        reason: str = "",
        audit_when_non_github: bool = False,
    ) -> GitHubAccessGrant | None:
        user_id = getattr(user, "id", None) if user is not None else None
        norm_repo = explicit_repo.strip() if explicit_repo and "/" in explicit_repo else None

        if not is_github_intent or not allow_tools:
            deny_reason = reason or (
                "Explicit GitHub intent is absent; repository access denied by default."
                if not is_github_intent
                else f"GitHub tools denied in mode '{mode}' (auth_status={auth_status})."
            )
            if audit_when_non_github or is_github_intent:
                record_github_access_audit(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    mode=mode,
                    intent=intent,
                    operation=operation,
                    repository=norm_repo,
                    decision="DENY",
                    reason=deny_reason,
                    db=db,
                )
            return None

        # Verify user authentication and explicit grant when connected
        if not auth_connected:
            has_public_slug = bool(norm_repo) and mode == "github"
            if not has_public_slug:
                record_github_access_audit(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    mode=mode,
                    intent=intent,
                    operation=operation,
                    repository=norm_repo,
                    decision="DENY",
                    reason=f"GitHub account not connected or authorization revoked (status={auth_status}).",
                    db=db,
                )
                return None

        allowed_ops = set(expand_tools_to_service_ops(allowed_tools))
        # Chat orchestrator may resolve active repository before entering tool loop
        if auth_connected and ("get_user_repositories" in allowed_tools or allowed_ops):
            allowed_ops.update({"list_repositories", "list_installation_repositories"})
        if norm_repo or "explore_repository_overview" in allowed_tools:
            allowed_ops.add("get_repository_details")

        allow_reason = reason or (
            f"Authorized explicit intent '{intent}' in chat mode '{mode}'."
        )
        grant = GitHubAccessGrant(
            grant_id=uuid.uuid4().hex,
            user_id=user_id,
            conversation_id=conversation_id,
            mode=mode,
            intent=intent,
            operation_scope=f"chat:{mode}:{intent}",
            allowed_operations=frozenset(allowed_ops),
            repository=norm_repo,
            auth_verified=auth_connected,
            allow_unauthenticated_public_repo=(not auth_connected and bool(norm_repo) and mode == "github"),
            disconnect_epoch=get_user_disconnect_epoch(user_id),
            reason=allow_reason,
        )
        record_github_access_audit(
            user_id=user_id,
            conversation_id=conversation_id,
            mode=mode,
            intent=intent,
            operation=operation,
            repository=norm_repo,
            decision="ALLOW",
            reason=allow_reason,
            db=db,
        )
        return grant

    @classmethod
    def authorize_explicit_rest_operation(
        cls,
        *,
        db: Session | None,
        user: Any | None,
        operation: str,
        allowed_operations: Iterable[str],
        repository: str | None = None,
        conversation_id: str | None = None,
        require_connected: bool = True,
        reason: str = "",
    ) -> GitHubAccessGrant:
        from code_review.github.auth_resolver import resolve_user_github_context

        user_id = getattr(user, "id", None) if user is not None else None
        auth_connected = False
        auth_status = "not_connected"

        if user is not None and db is not None:
            resolved = resolve_user_github_context(db, user)
            auth_connected = resolved.connected and bool(resolved.token)
            auth_status = resolved.connection_status
        elif user is not None:
            auth_connected = bool(
                getattr(user, "github_connected", False) and getattr(user, "github_token", None)
            )
            auth_status = "connected" if auth_connected else "not_connected"

        if require_connected and (not user_id or not auth_connected):
            deny_msg = (
                f"Denied REST GitHub operation '{operation}': user GitHub account is not connected "
                f"(status={auth_status})."
            )
            record_github_access_audit(
                user_id=user_id,
                conversation_id=conversation_id,
                mode="rest_explicit",
                intent="explicit_rest_action",
                operation=operation,
                repository=repository,
                decision="DENY",
                reason=deny_msg,
                db=db,
            )
            raise cls._deny(deny_msg)

        ops = frozenset(allowed_operations) | {operation}
        allow_reason = reason or f"User-initiated REST action '{operation}'."
        grant = GitHubAccessGrant(
            grant_id=uuid.uuid4().hex,
            user_id=user_id,
            conversation_id=conversation_id,
            mode="rest_explicit",
            intent="explicit_rest_action",
            operation_scope=f"rest:{operation}",
            allowed_operations=ops,
            repository=repository,
            auth_verified=auth_connected,
            allow_unauthenticated_public_repo=(not require_connected and not auth_connected),
            disconnect_epoch=get_user_disconnect_epoch(user_id),
            reason=allow_reason,
        )
        record_github_access_audit(
            user_id=user_id,
            conversation_id=conversation_id,
            mode="rest_explicit",
            intent="explicit_rest_action",
            operation=operation,
            repository=repository,
            decision="ALLOW",
            reason=allow_reason,
            db=db,
        )
        return grant

    @classmethod
    def authorize_auth_flow(
        cls,
        *,
        user: Any | None = None,
        operation: str,
        reason: str = "Explicit GitHub authentication flow.",
        db: Session | None = None,
    ) -> GitHubAccessGrant:
        user_id = getattr(user, "id", None) if user is not None else None
        grant = GitHubAccessGrant(
            grant_id=uuid.uuid4().hex,
            user_id=user_id,
            conversation_id=None,
            mode="auth",
            intent="github_authentication",
            operation_scope="auth_flow",
            allowed_operations=AUTH_HANDSHAKE_OPERATIONS,
            repository=None,
            auth_verified=True,
            disconnect_epoch=get_user_disconnect_epoch(user_id),
            reason=reason,
        )
        record_github_access_audit(
            user_id=user_id,
            conversation_id=None,
            mode="auth",
            intent="github_authentication",
            operation=operation,
            repository=None,
            decision="ALLOW",
            reason=reason,
            db=db,
        )
        return grant

    @classmethod
    def authorize_webhook(
        cls,
        *,
        owner: str,
        repo: str,
        delivery_id: str | None = None,
        db: Session | None = None,
    ) -> GitHubAccessGrant:
        repo_full = f"{owner}/{repo}".strip("/")
        reason = f"Signed GitHub pull_request webhook review (delivery={delivery_id or 'none'})."
        grant = GitHubAccessGrant(
            grant_id=uuid.uuid4().hex,
            user_id=None,
            conversation_id=None,
            mode="webhook",
            intent="webhook_pr_review",
            operation_scope="webhook",
            allowed_operations=WEBHOOK_PR_OPERATIONS,
            repository=repo_full,
            auth_verified=True,
            reason=reason,
        )
        record_github_access_audit(
            user_id=None,
            conversation_id=None,
            mode="webhook",
            intent="webhook_pr_review",
            operation="webhook_pr_review",
            repository=repo_full,
            decision="ALLOW",
            reason=reason,
            db=db,
        )
        return grant

    @classmethod
    def enforce_service_call(
        cls,
        service: Any,
        operation: str,
        *,
        owner: str | None = None,
        repo: str | None = None,
        grant: GitHubAccessGrant | None = None,
        db: Session | None = None,
    ) -> GitHubAccessGrant:
        """
        Enforced on EVERY GitHubService operation and repository agent inspection BEFORE
        performing any HTTP call or cache read. Rejects with GitHubAccessDeniedError by default.
        """
        target_repo = f"{owner}/{repo}".strip("/") if owner and repo else None
        active_grant = grant or getattr(service, "_access_grant", None) or get_active_grant()

        if active_grant is None:
            deny_reason = (
                f"Blocked unauthorized GitHub operation '{operation}': "
                "no active centralized authorization grant (deny-by-default)."
            )
            record_github_access_audit(
                user_id=None,
                conversation_id=None,
                mode="unknown",
                intent="unsolicited",
                operation=operation,
                repository=target_repo,
                decision="DENY",
                reason=deny_reason,
                db=db,
            )
            raise cls._deny(deny_reason)

        # Reject immediately if user disconnected/revoked GitHub after grant creation
        if (
            active_grant.user_id
            and active_grant.mode not in ("auth", "webhook")
            and not active_grant.allow_unauthenticated_public_repo
        ):
            live_epoch = get_user_disconnect_epoch(active_grant.user_id)
            if live_epoch != active_grant.disconnect_epoch:
                deny_reason = (
                    f"Blocked GitHub operation '{operation}': user disconnected or revoked GitHub."
                )
                record_github_access_audit(
                    user_id=active_grant.user_id,
                    conversation_id=active_grant.conversation_id,
                    mode=active_grant.mode,
                    intent=active_grant.intent,
                    operation=operation,
                    repository=target_repo or active_grant.repository,
                    decision="DENY",
                    reason=deny_reason,
                    db=db,
                )
                raise cls._deny(deny_reason)

            # Double-check DB connection flag when a Session is available
            if db is not None:
                from code_review.github.auth_resolver import resolve_user_github_context

                user_obj = getattr(service, "_bound_user", None)
                if user_obj is not None:
                    live_auth = resolve_user_github_context(db, user_obj)
                    if not live_auth.connected:
                        deny_reason = (
                            f"Blocked GitHub operation '{operation}': GitHub connection is inactive "
                            f"(status={live_auth.connection_status})."
                        )
                        record_github_access_audit(
                            user_id=active_grant.user_id,
                            conversation_id=active_grant.conversation_id,
                            mode=active_grant.mode,
                            intent=active_grant.intent,
                            operation=operation,
                            repository=target_repo or active_grant.repository,
                            decision="DENY",
                            reason=deny_reason,
                            db=db,
                        )
                        raise cls._deny(deny_reason)

        if operation not in active_grant.allowed_operations:
            deny_reason = (
                f"Blocked GitHub operation '{operation}': not permitted under scope "
                f"'{active_grant.operation_scope}' in mode '{active_grant.mode}'."
            )
            record_github_access_audit(
                user_id=active_grant.user_id,
                conversation_id=active_grant.conversation_id,
                mode=active_grant.mode,
                intent=active_grant.intent,
                operation=operation,
                repository=target_repo or active_grant.repository,
                decision="DENY",
                reason=deny_reason,
                db=db,
            )
            raise cls._deny(deny_reason)

        if active_grant.repository and target_repo:
            if active_grant.repository.lower() != target_repo.lower():
                deny_reason = (
                    f"Blocked GitHub operation '{operation}' on '{target_repo}': "
                    f"authorized scope is restricted to '{active_grant.repository}'."
                )
                record_github_access_audit(
                    user_id=active_grant.user_id,
                    conversation_id=active_grant.conversation_id,
                    mode=active_grant.mode,
                    intent=active_grant.intent,
                    operation=operation,
                    repository=target_repo,
                    decision="DENY",
                    reason=deny_reason,
                    db=db,
                )
                raise cls._deny(deny_reason)

        record_github_access_audit(
            user_id=active_grant.user_id,
            conversation_id=active_grant.conversation_id,
            mode=active_grant.mode,
            intent=active_grant.intent,
            operation=operation,
            repository=target_repo or active_grant.repository,
            decision="ALLOW",
            reason=active_grant.reason or f"Allowed under grant {active_grant.operation_scope}.",
            db=db,
        )
        return active_grant
