from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from sqlalchemy.orm import Session

from code_review.db.models import UserRecord
from code_review.github.auth_resolver import ResolvedGitHubAuth, resolve_user_github_context
from code_review.github.tools import VALID_TOOL_NAMES

ChatMode = Literal["normal", "github"]
VALID_CHAT_MODES: frozenset[str] = frozenset({"normal", "github"})


class UserIntent(StrEnum):
    CASUAL_CHAT = "casual_chat"
    GENERAL_CODING = "general_coding"
    ANALYZE_PROVIDED_CODE = "analyze_provided_code"
    EDUCATIONAL_GITHUB = "educational_github"
    GITHUB_REPO_LIST = "github_repo_list"
    GITHUB_REPO_INSPECTION = "github_repo_inspection"
    GITHUB_PR_OPERATION = "github_pr_operation"


EXPLICIT_REPO_RE = re.compile(r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b")
GITHUB_URL_RE = re.compile(r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")
GITHUB_PR_URL_RE = re.compile(
    r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+",
    re.IGNORECASE,
)

CASUAL_GREETING_RE = re.compile(
    r"^\s*(?:hi|hello|hey|yo|sup|good morning|good afternoon|good evening|"
    r"how are you|how's it going|what's up|thanks|thank you|ok|okay|bye)"
    r"(?:[\s,!]+(?:there|nexarion|how are you|how's it going|what's up|man|bro|team))?[!.? ]*$",
    re.IGNORECASE,
)

REPO_LIST_PHRASES = (
    "list my repo",
    "list my github repo",
    "show my repo",
    "show my github repo",
    "what repositories",
    "which repositories",
    "my repositories",
    "list repositories",
)

_EDUCATIONAL_LEAD_RE = re.compile(
    r"^\s*(?:what\s+(?:is|are)|explain|how\s+(?:does|do|to|can\s+i|should\s+i)|"
    r"why\s+(?:does|do|is|use)|tell\s+me\s+about|describe\s+how|"
    r"difference\s+between|compare\s+.+\s+(?:vs|versus|and)\s+|"
    r"guide\s+to|tutorial\s+(?:on|for)|overview\s+of)\b",
    re.IGNORECASE,
)

_EDUCATIONAL_CONCEPT_RE = re.compile(
    r"\b(?:what\s+is\s+(?:a|an)\s+(?:pull\s+request|repo|repository|fork|commit|branch|"
    r"webhook|oauth|github\s+actions?|ci/cd)|"
    r"explain\s+(?:github\s+oauth|github\s+actions?|github\s+apps?|webhooks?|"
    r"pull\s+requests?|git\s+\w+|oauth|ci/cd))\b",
    re.IGNORECASE,
)

_PASTED_CODE_CUE_RE = re.compile(
    r"(?:```[\s\S]*```|"
    r"\b(?:(?:this|the|following|below|above|attached|pasted|provided)\s+){1,3}"
    r"(?:python|js|javascript|ts|typescript|java|c\+\+|cpp|go|rust|sql|bash|code|snippet|"
    r"function|class|method|script|diff|patch|error|traceback|log|file)\b)",
    re.IGNORECASE,
)

_FENCED_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)

_TARGETED_PR_ACTION_RE = re.compile(
    r"(?:\b(?:inspect|analyze|review|check|audit|show|fetch|list|summarize|examine)\b.{0,45}"
    r"\b(?:(?:my|our|the|open|latest|recent|active)\s+)?(?:github\s+)?(?:pull\s+requests?|prs?)\b"
    r"|\bpr\s*#\d+\b|\bpull\s+request\s*#\d+\b)",
    re.IGNORECASE,
)

_POSSESSIVE_REPO_RE = re.compile(
    r"\b(?:my|our)\s+(?:[A-Za-z0-9_.-]+\s+)?(?:github\s+)?(?:repos?|repository|repositories|codebase)\b",
    re.IGNORECASE,
)

_REPO_TARGET_VERB_RE = re.compile(
    r"\b(?:inspect|analyze|audit|review|scan|explore|examine|check|search|fetch|list|summarize)\b"
    r".{0,120}"
    r"\b(?:(?:my|our|this|the)\s+(?:[A-Za-z0-9_.-]+\s+)?(?:github\s+)?(?:repos?|repository|repositories|codebase)|"
    r"github\s+repos?(?:itory|itories)?)\b",
    re.IGNORECASE,
)

_REPO_SCOPE_PHRASE_RE = re.compile(
    r"\b(?:in|of|from|on|inside|across)\s+(?:(?:my|our|this|the)\s+)?"
    r"(?:(?:[A-Za-z0-9_.-]+\s+)?(?:github\s+)?(?:repos?|repository|codebase))\b",
    re.IGNORECASE,
)

_GITHUB_COMMITS_WORKFLOW_RE = re.compile(
    r"\b(?:inspect|analyze|review|check|show|fetch|list|summarize)\b.{0,45}"
    r"\b(?:my|our)\b.{0,30}\b(?:commits?|branches|issues?|workflow\s+runs?|github\s+actions?\s+runs?)\b",
    re.IGNORECASE,
)

_GITHUB_MODE_PROJECT_RE = re.compile(
    r"\b(?:inspect|analyze|audit|review|explore|examine)\s+(?:my|our)\s+(?:[A-Za-z0-9_.-]+\s+)?project\b",
    re.IGNORECASE,
)

_LOCKED_REPO_FOLLOWUP_CUES = (
    "file",
    "files",
    "directory",
    "folder",
    "branch",
    "commit",
    "commits",
    "pr",
    "pull request",
    "repo",
    "repository",
    "inspect",
    "audit",
    "vulnerabilit",
    "readme",
    "workflow",
    "entrypoint",
    "entry point",
)

# Tool scopes by intent so an explicit GitHub ask in Normal Mode never unlocks unrelated tools
REPO_LIST_SCOPED_TOOLS: frozenset[str] = frozenset(
    {"get_user_repositories", "search_repositories"}
)
PR_SCOPED_TOOLS: frozenset[str] = frozenset(
    {
        "get_user_repositories",
        "get_repository_details",
        "get_pull_requests",
        "get_pull_request_details",
        "get_pull_request_diff",
        "get_pull_request_files",
        "get_pull_request_reviews",
        "get_pull_request_comments",
    }
)
REPO_INSPECTION_SCOPED_TOOLS: frozenset[str] = frozenset(
    {
        "get_user_repositories",
        "explore_repository_overview",
        "get_repository_details",
        "get_repository_branches",
        "get_repository_tree",
        "get_repository_contents",
        "fetch_file",
        "fetch_files",
        "search_repository_code",
        "get_commit_history",
        "get_commit_details",
        "run_security_and_quality_agents",
    }
)
ALL_GITHUB_TOOLS: frozenset[str] = VALID_TOOL_NAMES


def extract_explicit_repo_slug(prompt: str) -> str | None:
    """Extract explicit `owner/repo` slug from a GitHub URL or owner/repo token in text."""
    url_match = GITHUB_URL_RE.search(prompt or "")
    if url_match:
        owner, repo = url_match.group(1), url_match.group(2)
        return f"{owner}/{repo.removesuffix('.git')}"
    for match in EXPLICIT_REPO_RE.finditer(prompt or ""):
        candidate = match.group(1)
        owner, repo = candidate.split("/", 1)
        if owner.lower() in (
            "src",
            "app",
            "api",
            "frontend",
            "backend",
            "tests",
            "docs",
            "http",
            "https",
            "application",
            "text",
            "usr",
            "var",
            "etc",
            "ci",
        ):
            continue
        if "." in repo and not repo.endswith((".js", ".py", ".ts", ".tsx", ".jsx", ".md", ".json")):
            return candidate
        if "-" in owner or "_" in owner or (repo and repo[0].isupper()):
            return candidate
    return None


def looks_like_casual_chitchat(prompt: str) -> bool:
    clean = (prompt or "").strip()
    if not clean:
        return True
    return bool(CASUAL_GREETING_RE.match(clean))


class ChatModeResolver:
    """Validates and resolves authoritative chat mode ('normal' | 'github')."""

    @staticmethod
    def normalize_mode(raw_mode: Any) -> ChatMode:
        if not isinstance(raw_mode, str):
            raise ValueError("Invalid chat mode: expected 'normal' or 'github'.")
        clean = raw_mode.strip().lower()
        if clean not in VALID_CHAT_MODES:
            raise ValueError("Invalid chat mode: must be either 'normal' or 'github'.")
        return clean  # type: ignore[return-value]

    @classmethod
    def resolve(
        cls,
        *,
        mode: Any = None,
        github_mode: bool | None = None,
    ) -> ChatMode:
        """
        Resolve mode deterministically for the incoming request:
        - Explicit `mode` is always authoritative and strictly validated.
        - Legacy `github_mode=True` is honored only when `mode` is omitted (`None`).
        - Missing mode always defaults strictly to `'normal'`, never `'github'`.
        """
        if mode is not None:
            return cls.normalize_mode(mode)
        if github_mode is True:
            return "github"
        return "normal"


class IntentClassifier:
    """Classifies user prompts carefully so educational/coding requests never trigger GitHub tools."""

    @staticmethod
    def classify(
        prompt: str,
        *,
        mode: ChatMode,
        diff_context: str | None = None,
        document_context: str | None = None,
        explicit_repo: str | None = None,
        has_locked_repo: bool = False,
    ) -> UserIntent:
        clean = (prompt or "").strip()
        lower = clean.lower()

        if looks_like_casual_chitchat(clean) and not explicit_repo:
            return UserIntent.CASUAL_CHAT

        # Explicit repo slug passed by UI selection or GitHub URL in prompt
        slug_in_prompt = extract_explicit_repo_slug(clean)
        if explicit_repo or GITHUB_URL_RE.search(clean) or slug_in_prompt:
            if GITHUB_PR_URL_RE.search(clean) or _TARGETED_PR_ACTION_RE.search(clean):
                return UserIntent.GITHUB_PR_OPERATION
            return UserIntent.GITHUB_REPO_INSPECTION

        # User wants to analyze an attached diff or uploaded document directly
        if diff_context and not _POSSESSIVE_REPO_RE.search(clean):
            return UserIntent.ANALYZE_PROVIDED_CODE

        # Inspect natural-language intent without letting string literals/comments inside pasted code blocks trigger GitHub
        prose_only = _FENCED_CODE_BLOCK_RE.sub(" ", clean).strip() or clean
        prose_lower = prose_only.lower()

        has_repo_list_ask = any(p in prose_lower for p in REPO_LIST_PHRASES)
        has_targeted_pr = bool(_TARGETED_PR_ACTION_RE.search(prose_only)) and not bool(
            re.search(r"\bwhat\s+is\s+a\s+pull\s+request\b", prose_lower)
        )
        has_explicit_repo_target = bool(
            _POSSESSIVE_REPO_RE.search(prose_only)
            or _REPO_TARGET_VERB_RE.search(prose_only)
            or _REPO_SCOPE_PHRASE_RE.search(prose_only)
            or _GITHUB_COMMITS_WORKFLOW_RE.search(prose_only)
        )

        # Inline/pasted code analysis without any repo target stays local to the pasted code
        if _PASTED_CODE_CUE_RE.search(clean) and not has_explicit_repo_target and not has_targeted_pr:
            return UserIntent.ANALYZE_PROVIDED_CODE

        if _EDUCATIONAL_CONCEPT_RE.search(prose_only) and not has_explicit_repo_target and not has_targeted_pr:
            return UserIntent.EDUCATIONAL_GITHUB

        if (
            _EDUCATIONAL_LEAD_RE.search(prose_only)
            and not has_explicit_repo_target
            and not has_targeted_pr
            and not has_repo_list_ask
        ):
            if any(term in prose_lower for term in ("github", "pull request", "oauth", "webhook", "actions")):
                return UserIntent.EDUCATIONAL_GITHUB
            return UserIntent.GENERAL_CODING

        if has_repo_list_ask:
            return UserIntent.GITHUB_REPO_LIST

        if has_targeted_pr:
            return UserIntent.GITHUB_PR_OPERATION

        if has_explicit_repo_target:
            return UserIntent.GITHUB_REPO_INSPECTION

        # Inside explicit GitHub Mode only, handle locked-repo follow-ups and repo-project asks
        if mode == "github":
            if _GITHUB_MODE_PROJECT_RE.search(prose_only):
                return UserIntent.GITHUB_REPO_INSPECTION
            if has_locked_repo and not _EDUCATIONAL_LEAD_RE.search(prose_only):
                if any(cue in prose_lower for cue in _LOCKED_REPO_FOLLOWUP_CUES):
                    if "pull request" in prose_lower or re.search(r"\bprs?\b", prose_lower):
                        return UserIntent.GITHUB_PR_OPERATION
                    return UserIntent.GITHUB_REPO_INSPECTION

        if document_context:
            return UserIntent.ANALYZE_PROVIDED_CODE

        if "github" in lower or "pull request" in lower:
            return UserIntent.EDUCATIONAL_GITHUB

        return UserIntent.GENERAL_CODING


@dataclass(frozen=True)
class GitHubGuardDecision:
    mode: ChatMode
    intent: UserIntent
    is_github_intent: bool
    use_github_orchestrator: bool
    allow_github_tools: bool
    allowed_tools: frozenset[str]
    persist_repo_context: bool
    auth_verified: bool
    auth_status: str
    denial_reason: str | None = None


class GitHubToolGuard:
    """
    Authoritative server-side policy guard controlling whether a chat turn may access
    GitHub orchestration and precisely which subset of read-only GitHub tools are permitted.
    """

    @staticmethod
    def scoped_tools_for_intent(intent: UserIntent, mode: ChatMode) -> frozenset[str]:
        if intent == UserIntent.GITHUB_REPO_LIST:
            return REPO_LIST_SCOPED_TOOLS
        if intent == UserIntent.GITHUB_PR_OPERATION:
            return PR_SCOPED_TOOLS if mode == "normal" else ALL_GITHUB_TOOLS
        if intent == UserIntent.GITHUB_REPO_INSPECTION:
            return REPO_INSPECTION_SCOPED_TOOLS if mode == "normal" else ALL_GITHUB_TOOLS
        return frozenset()

    @classmethod
    def authorize(
        cls,
        *,
        db: Session | None,
        user: UserRecord | None,
        mode: ChatMode,
        intent: UserIntent,
        prompt: str = "",
        explicit_repo: str | None = None,
    ) -> GitHubGuardDecision:
        github_intents = {
            UserIntent.GITHUB_REPO_LIST,
            UserIntent.GITHUB_PR_OPERATION,
            UserIntent.GITHUB_REPO_INSPECTION,
        }
        is_gh_intent = intent in github_intents

        # Non-GitHub intents NEVER unlock GitHub orchestration or tools in Normal Mode.
        # In GitHub Mode, ordinary coding/educational questions do not force GitHub inspection either.
        if not is_gh_intent:
            return GitHubGuardDecision(
                mode=mode,
                intent=intent,
                is_github_intent=False,
                use_github_orchestrator=False,
                allow_github_tools=False,
                allowed_tools=frozenset(),
                persist_repo_context=False,
                auth_verified=False,
                auth_status="not_required",
                denial_reason="GitHub tools are disabled for non-GitHub requests.",
            )

        # Verify GitHub authorization independently on the server for every GitHub operation
        resolved_auth: ResolvedGitHubAuth | None = (
            resolve_user_github_context(db, user) if db is not None else None
        )
        auth_connected = bool(user is not None and resolved_auth and resolved_auth.connected)
        auth_status = resolved_auth.connection_status if resolved_auth else "not_connected"

        # Determine whether request explicitly names a public repository URL/slug
        has_explicit_slug = bool(explicit_repo or extract_explicit_repo_slug(prompt))

        if mode == "normal":
            # In Normal Mode, explicit GitHub operations execute only through narrowly
            # scoped tools after independent authorization, without changing conversation mode.
            if not auth_connected:
                return GitHubGuardDecision(
                    mode=mode,
                    intent=intent,
                    is_github_intent=True,
                    use_github_orchestrator=True,
                    allow_github_tools=False,
                    allowed_tools=frozenset(),
                    persist_repo_context=False,
                    auth_verified=False,
                    auth_status=auth_status,
                    denial_reason="GitHub authentication is required before executing GitHub tools in Normal Mode.",
                )

            scoped = cls.scoped_tools_for_intent(intent, mode="normal")
            return GitHubGuardDecision(
                mode=mode,
                intent=intent,
                is_github_intent=True,
                use_github_orchestrator=True,
                allow_github_tools=True,
                allowed_tools=scoped,
                persist_repo_context=False,
                auth_verified=True,
                auth_status=auth_status,
            )

        # Explicit GitHub Mode
        if auth_connected or has_explicit_slug:
            return GitHubGuardDecision(
                mode="github",
                intent=intent,
                is_github_intent=True,
                use_github_orchestrator=True,
                allow_github_tools=True,
                allowed_tools=cls.scoped_tools_for_intent(intent, mode="github"),
                persist_repo_context=True,
                auth_verified=auth_connected,
                auth_status=auth_status,
            )

        # GitHub Mode enabled + GitHub intent, but user hasn't connected GitHub yet:
        # route into orchestrator solely to emit connect-GitHub guidance with ALL tools blocked.
        return GitHubGuardDecision(
            mode="github",
            intent=intent,
            is_github_intent=True,
            use_github_orchestrator=True,
            allow_github_tools=False,
            allowed_tools=frozenset(),
            persist_repo_context=True,
            auth_verified=False,
            auth_status=auth_status,
            denial_reason="GitHub account is not connected.",
        )


class ProgressMessageManager:
    """Produces mode-accurate status/progress messages matching the active execution path."""

    GITHUB_STATUS_KEYWORDS: tuple[str, ...] = (
        "github",
        "repository",
        "repositories",
        "pull request",
        "pr #",
    )

    @staticmethod
    def status_event(stage: str, detail: str) -> dict[str, str]:
        return {"stage": stage, "detail": detail}

    @classmethod
    def initial_normal_status(
        cls,
        intent: UserIntent,
        *,
        has_diff: bool = False,
        has_docs: bool = False,
    ) -> dict[str, str]:
        if has_diff or intent == UserIntent.ANALYZE_PROVIDED_CODE:
            return cls.status_event("analyzing", "Reviewing the provided code...")
        if has_docs:
            return cls.status_event("analyzing", "Analyzing attached documents...")
        if intent == UserIntent.GENERAL_CODING:
            return cls.status_event("analyzing", "Analyzing your question...")
        return cls.status_event("thinking", "Thinking...")

    @classmethod
    def initial_github_planning_status(cls, intent: UserIntent) -> dict[str, str]:
        if intent == UserIntent.GITHUB_PR_OPERATION:
            return cls.status_event("analyzing", "Planning pull request inspection...")
        if intent == UserIntent.GITHUB_REPO_LIST:
            return cls.status_event("discovering", "Discovering repositories...")
        return cls.status_event("analyzing", "Planning GitHub inspection...")

    @classmethod
    def for_github_tool(cls, tool_name: str, detail: str) -> dict[str, str]:
        stage_map = {
            "get_user_repositories": "discovering",
            "search_repositories": "discovering",
            "explore_repository_overview": "exploring",
            "get_repository_tree": "exploring",
            "run_security_and_quality_agents": "agents",
        }
        stage = stage_map.get(tool_name, "fetching")
        return cls.status_event(stage, detail)


@dataclass(frozen=True)
class ToolRoutePlan:
    mode: ChatMode
    intent: UserIntent
    guard: GitHubGuardDecision
    initial_status: dict[str, str]

    @property
    def use_github_orchestrator(self) -> bool:
        return self.guard.use_github_orchestrator

    @property
    def allow_github_tools(self) -> bool:
        return self.guard.allow_github_tools

    @property
    def allowed_tools(self) -> frozenset[str]:
        return self.guard.allowed_tools

    @property
    def persist_repo_context(self) -> bool:
        return self.guard.persist_repo_context


class ToolExecutionRouter:
    """Unified router resolving mode, prompt intent, GitHub authorization, and initial progress."""

    @staticmethod
    def plan_chat_request(
        *,
        prompt: str,
        requested_mode: Any = None,
        legacy_github_mode: bool | None = None,
        db: Session | None = None,
        user: UserRecord | None = None,
        diff_context: str | None = None,
        document_context: str | None = None,
        explicit_repo: str | None = None,
        has_locked_repo: bool = False,
    ) -> ToolRoutePlan:
        mode = ChatModeResolver.resolve(mode=requested_mode, github_mode=legacy_github_mode)
        # In Normal Mode, never treat a prior locked repo context as implicit GitHub intent
        effective_locked_repo = bool(has_locked_repo) if mode == "github" else False
        effective_explicit_repo = explicit_repo if (mode == "github" or explicit_repo) else None

        intent = IntentClassifier.classify(
            prompt,
            mode=mode,
            diff_context=diff_context,
            document_context=document_context,
            explicit_repo=effective_explicit_repo,
            has_locked_repo=effective_locked_repo,
        )

        guard = GitHubToolGuard.authorize(
            db=db,
            user=user,
            mode=mode,
            intent=intent,
            prompt=prompt,
            explicit_repo=effective_explicit_repo,
        )

        if guard.use_github_orchestrator and guard.allow_github_tools:
            initial_status = ProgressMessageManager.initial_github_planning_status(intent)
        else:
            initial_status = ProgressMessageManager.initial_normal_status(
                intent,
                has_diff=bool(diff_context),
                has_docs=bool(document_context),
            )

        return ToolRoutePlan(
            mode=mode,
            intent=intent,
            guard=guard,
            initial_status=initial_status,
        )
