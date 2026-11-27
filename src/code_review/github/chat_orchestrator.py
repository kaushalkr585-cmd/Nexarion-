from __future__ import annotations

import concurrent.futures
import json
import logging
import re
from collections.abc import Iterator
from difflib import SequenceMatcher
from typing import Any

import httpx
from sqlalchemy.orm import Session

from code_review.db.models import ConversationRepositoryContextRecord, UserRecord
from code_review.github.auth_resolver import (
    ResolvedGitHubAuth,
    ensure_github_tables,
    mark_connection_revoked_or_expired,
    resolve_user_github_context,
)
from code_review.github.explorer import RepositoryExplorer
from code_review.github.mode_router import (
    ChatMode,
    GitHubGuardDecision,
    GitHubToolGuard,
    IntentClassifier,
    ProgressMessageManager,
    UserIntent,
    extract_explicit_repo_slug,
    looks_like_casual_chitchat,
)
from code_review.github.service import GitHubApiError, GitHubAuthError, GitHubService
from code_review.github.tools import GITHUB_TOOL_DEFINITIONS, GitHubToolRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8

EXPLICIT_REPO_RE = re.compile(r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b")
GITHUB_URL_RE = re.compile(r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")


def looks_like_github_intent(
    prompt: str,
    has_locked_repo: bool = False,
    mode: ChatMode = "github",
) -> bool:
    intent = IntentClassifier.classify(
        prompt,
        mode=mode,
        has_locked_repo=has_locked_repo if mode == "github" else False,
    )
    return intent in {
        UserIntent.GITHUB_REPO_LIST,
        UserIntent.GITHUB_PR_OPERATION,
        UserIntent.GITHUB_REPO_INSPECTION,
    }


def _extract_explicit_repo_slug(prompt: str) -> str | None:
    return extract_explicit_repo_slug(prompt)


GENERIC_REPO_TERMS = {
    "html",
    "css",
    "js",
    "javascript",
    "react",
    "website",
    "web",
    "app",
    "project",
    "code",
    "repo",
    "repository",
    "node",
    "nodejs",
    "express",
    "tailwind",
    "test",
    "demo",
    "mongodb",
    "frontend",
    "backend",
}

INSPECTION_PATTERNS = re.compile(
    r"\b(inspect|analyze|audit|review|overview|architecture|explore|examine|deep dive)\b",
    re.IGNORECASE,
)
REPO_NOUNS = re.compile(
    r"\b(repo|repository|project|codebase|application)\b",
    re.IGNORECASE,
)


def is_full_repo_inspection_intent(prompt: str) -> bool:
    if not prompt:
        return False
    clean = prompt.strip()
    has_verb = bool(INSPECTION_PATTERNS.search(clean))
    has_noun = bool(REPO_NOUNS.search(clean))
    if has_verb and has_noun:
        return True
    lower = clean.lower()
    return any(
        phrase in lower
        for phrase in (
            "inspect my",
            "review my",
            "analyze my",
            "audit my",
            "explain the architecture of my repository",
            "explain my project",
            "project architecture",
        )
    )


_TOOL_CALL_JSON_LINE_RE = re.compile(
    r'^\s*(?:```json\s*)?\{\s*"(?:tool|tool_calls|function|name)"\s*:',
    re.IGNORECASE,
)
_TOOL_RESULT_MARKER_RE = re.compile(r"^\s*\[Tool\s+[^\]]*result\]\s*:", re.IGNORECASE)
_XML_TOOL_TAG_RE = re.compile(r"</?tool_call\b", re.IGNORECASE)

SYNTHESIS_SYSTEM_PROMPT = (
    "You are Nexarion, a Senior AI Software Architect and Security Engineer created by Kaushal.\n"
    "Tool data collection is COMPLETE. No tool-calling API is active in this response phase.\n\n"
    "STRICT RESPONSE RULES:\n"
    '1. NEVER output raw JSON tool calls (such as `{"tool": ...}`, `{"tool_calls": ...}`, `github_get_file_content`, or `<tool_call>`).\n'
    "2. NEVER output `[Tool ... result]:` markers, internal tool schemas, or raw GitHub API dictionaries.\n"
    "3. Synthesize a clear, grounded, publication-grade Markdown engineering report directly from the verified tool results provided.\n"
    "4. Cite only verified file paths, line numbers, code evidence, commit SHAs, and findings actually present in the supplied repository data.\n"
    "5. If specific requested files were not fetched or failed validation, explicitly mention which files were inspected and which were not, rather than guessing or claiming unverified results.\n"
    "6. Never expose internal LLM model names or inference providers unless explicitly asked, and omit decorative emojis from formal security/engineering audit findings and error reports."
)


def is_raw_tool_leakage(text: str) -> bool:
    """Detect whether LLM output contains unformatted tool-call JSON or raw API payloads."""
    s = (text or "").strip()
    if not s:
        return False

    # Check whole-string single JSON dict/list payloads
    if s.startswith("{") and s.endswith("}"):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict) and any(
                k in parsed
                for k in (
                    "tool",
                    "tool_calls",
                    "arguments",
                    "path",
                    "sha",
                    "html_url",
                    "line_count",
                    "truncated",
                    "size",
                    "content",
                    "entries",
                    "files_analyzed",
                    "agents_executed",
                )
            ):
                return True
        except Exception:
            pass
    # Check if text is a raw JSON list of commit/file objects
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                if any(
                    k in parsed[0] for k in ("tool", "name", "sha", "commit", "path", "full_name")
                ):
                    return True
        except Exception:
            pass
    # Check if wrapped in ```json code fences containing raw tool dictionary keys

    if s.startswith("```json") and s.endswith("```"):
        if any(
            k in s
            for k in (
                '"tool":',
                '"tool_calls":',
                '"arguments":',
                '"path":',
                '"line_count":',
                '"html_url":',
                '"truncated":',
                '"files_analyzed":',
            )
        ):
            return True

    # Check multi-line JSONL / embedded tool-call instructions anywhere in text
    if "github_get_file_content" in s or _XML_TOOL_TAG_RE.search(s):
        return True
    for line in s.splitlines():
        ls = line.strip()
        if not ls:
            continue
        if _TOOL_CALL_JSON_LINE_RE.match(ls) or _TOOL_RESULT_MARKER_RE.match(ls):
            return True
        if ls.startswith("{") and '"arguments"' in ls and ('"tool"' in ls or '"name"' in ls):
            return True

    return False


def _strip_poisoned_memory_from_prompt(base_prompt: str) -> str:
    """Remove historical memory blocks from system prompt inside active GitHub tool orchestration."""
    marker = "--- RELEVANT HISTORICAL MEMORY"
    if marker in base_prompt:
        return base_prompt.split(marker, 1)[0].rstrip()
    return base_prompt


def _filter_stream_tool_leakage(
    raw_iter: Iterator[str],
    state: dict[str, bool],
) -> Iterator[str]:
    """
    Buffer line prefixes during streaming so partial or complete JSON tool-call lines
    or [Tool result] markers are never emitted to the SSE token stream.
    """
    buf = ""
    in_tool_json_fence = False

    def _is_suspect_prefix(chunk_str: str) -> bool:
        stripped = chunk_str.lstrip()
        if not stripped:
            return False
        return (
            stripped.startswith("{")
            or stripped.startswith("[Tool")
            or stripped.startswith("<tool_call")
            or stripped.startswith("```json")
            or "github_get_file_content" in stripped
        )

    def _is_tool_line(line: str) -> bool:
        ls = line.strip()
        if not ls:
            return False
        if "github_get_file_content" in ls:
            return True
        if _TOOL_CALL_JSON_LINE_RE.match(ls) or _TOOL_RESULT_MARKER_RE.match(ls):
            return True
        if _XML_TOOL_TAG_RE.search(ls):
            return True
        if ls.startswith("{") and ('"tool"' in ls or '"tool_calls"' in ls) and '"arguments"' in ls:
            return True
        return False

    for piece in raw_iter:
        if not piece:
            continue
        buf += piece

        while "\n" in buf:
            line, rest = buf.split("\n", 1)
            buf = rest
            line_with_nl = line + "\n"
            ls = line.strip()

            if ls.startswith("```json"):
                # Peek: wait if inside tool fence; buffer until closing fence
                in_tool_json_fence = True
                state["fence_buf"] = state.get("fence_buf", "") + line_with_nl  # type: ignore[assignment]
                continue
            if in_tool_json_fence:
                fence_buf = str(state.get("fence_buf", "")) + line_with_nl
                state["fence_buf"] = fence_buf  # type: ignore[assignment]
                if ls == "```":
                    in_tool_json_fence = False
                    state["fence_buf"] = ""  # type: ignore[assignment]
                    if is_raw_tool_leakage(fence_buf):
                        state["leaked"] = True
                        continue
                    state["emitted"] = True
                    yield fence_buf
                continue

            if _is_tool_line(line):
                state["leaked"] = True
                continue
            if state.get("leaked") and (ls.startswith('{"path"') or ls == ""):
                continue

            state["emitted"] = True
            yield line_with_nl

        # Stream normal non-JSON prose smoothly without waiting for newline
        if not in_tool_json_fence and len(buf) >= 24 and not _is_suspect_prefix(buf):
            state["emitted"] = True
            yield buf
            buf = ""

    # Flush remaining tail buffer
    if in_tool_json_fence:
        fence_buf = str(state.get("fence_buf", "")) + buf
        if not is_raw_tool_leakage(fence_buf) and fence_buf.strip():
            state["emitted"] = True
            yield fence_buf
        else:
            state["leaked"] = True
    elif buf:
        if _is_tool_line(buf) or is_raw_tool_leakage(buf):
            state["leaked"] = True
        else:
            state["emitted"] = True
            yield buf


def _format_tool_evidence_for_synthesis(
    tool_messages: list[dict[str, Any]],
    *,
    max_total_chars: int = 38_000,
) -> tuple[str, list[str]]:
    """
    Build structured, intact evidence blocks from completed tool outputs without
    slicing JSON payloads mid-object.
    Returns (formatted_evidence_markdown, list_of_inspected_file_paths).
    """
    overviews: list[str] = []
    trees: list[str] = []
    agent_reports: list[str] = []
    file_blocks: dict[str, str] = {}
    other_results: list[str] = []

    for msg in tool_messages:
        if msg.get("role") != "tool":
            continue
        tname = str(msg.get("name") or "")
        raw_content = str(msg.get("content") or "")
        try:
            data = json.loads(raw_content)
        except Exception:
            data = None

        if not isinstance(data, (dict, list)):
            other_results.append(f"### Tool `{tname}`\n{raw_content[:3000]}")
            continue

        if isinstance(data, dict) and data.get("error"):
            other_results.append(f"### Tool `{tname}` Error\n{data.get('error')}")
            continue

        if tname == "explore_repository_overview" and isinstance(data, dict):
            summary_obj = {
                k: data.get(k)
                for k in (
                    "repository",
                    "html_url",
                    "branch",
                    "head_sha",
                    "visibility",
                    "description",
                    "tech_stack",
                    "top_directories",
                    "root_files",
                    "entry_points",
                    "recent_commits",
                )
                if k in data
            }
            overviews.append(
                f"### Repository Overview\n```json\n{json.dumps(summary_obj, indent=2)[:4500]}\n```"
            )
            for mpath, mcontent in (data.get("manifests") or {}).items():
                if isinstance(mcontent, str) and mcontent.strip():
                    file_blocks[mpath] = f"#### File: `{mpath}`\n```\n{mcontent[:3500]}\n```"
        elif tname == "get_repository_tree" and isinstance(data, dict):
            paths = [
                e.get("path", "")
                for e in (data.get("entries") or [])
                if e.get("type") == "blob" and e.get("path")
            ]
            trees.append(
                f"### Repository Files ({len(paths)} indexed blobs, ref `{data.get('ref')}`, sha `{data.get('sha')}`)\n"
                + "\n".join(f"- `{p}`" for p in paths[:150])
            )
        elif tname == "run_security_and_quality_agents" and isinstance(data, dict):
            agent_reports.append(
                "### Multi-Agent Security & Quality Scan Results\n"
                f"- Agents Executed: {data.get('agents_executed')}\n"
                f"- Files Analyzed: {data.get('files_analyzed')}\n"
                f"- Total Findings: {data.get('total_findings')}\n"
                f"```json\n{json.dumps(data.get('findings') or [], indent=2)[:10_000]}\n```"
            )
        elif tname == "fetch_file" and isinstance(data, dict) and data.get("path"):
            p = str(data["path"])
            if not data.get("blocked") and data.get("content"):
                clean_code = str(data["content"])
                file_blocks[p] = (
                    f"#### File: `{p}` (URL: {data.get('html_url', '')}, lines: {data.get('line_count', '?')})\n"
                    f"```\n{clean_code[:4500]}\n```"
                )
        elif tname == "fetch_files" and isinstance(data, dict):
            for fobj in data.get("files") or []:
                if isinstance(fobj, dict) and fobj.get("path") and fobj.get("content"):
                    p = str(fobj["path"])
                    file_blocks[p] = (
                        f"#### File: `{p}` (URL: {fobj.get('html_url', '')}, lines: {fobj.get('line_count', '?')})\n"
                        f"```\n{str(fobj['content'])[:4000]}\n```"
                    )
        else:
            other_results.append(
                f"### Tool `{tname}`\n{json.dumps(data, ensure_ascii=False, indent=2)[:3500]}"
            )

    sections: list[str] = []
    sections.extend(overviews)
    sections.extend(agent_reports)
    sections.extend(trees)

    # Prioritize auth/security/config/server/route files first when packing source excerpts
    priority_terms = (
        "auth",
        "middleware",
        "security",
        "server",
        "route",
        "controller",
        "config",
        "db",
        "package.json",
        "contact",
        "api",
    )
    sorted_paths = sorted(
        file_blocks.keys(),
        key=lambda p: (0 if any(t in p.lower() for t in priority_terms) else 1, p),
    )
    if sorted_paths:
        sections.append("### Retrieved Source & Configuration Files")
        for sp in sorted_paths:
            candidate = "\n\n".join(sections + [file_blocks[sp]])
            if len(candidate) > max_total_chars - 2500:
                break
            sections.append(file_blocks[sp])

    for extra in other_results:
        candidate = "\n\n".join(sections + [extra])
        if len(candidate) > max_total_chars:
            break
        sections.append(extra)

    return "\n\n".join(sections)[:max_total_chars], sorted_paths


def _synthesize_raw_tool_output(
    llm_client: Any,
    raw_content: str,
    user_prompt: str,
    repo_name: str,
    base_system_prompt: str,
) -> Iterator[dict[str, Any]]:
    """Synthesize raw tool output into high-quality engineering markdown."""
    synthesis_prompt = (
        f"You are Nexarion, an elite AI code architect.\n"
        f"The user asked: {user_prompt}\n"
        f"Repository: {repo_name}\n\n"
        f"Below is repository data retrieved from GitHub tools:\n"
        f"{raw_content[:20_000]}\n\n"
        f"Instructions:\n"
        f"1. Synthesize this data into a clear, professional, human-readable markdown response.\n"
        f"2. DO NOT output raw JSON dictionaries, tool schemas, or internal metadata.\n"
        f"3. Highlight key insights, file paths, code snippets, and line references where appropriate.\n"
        f"4. Format any code in properly syntax-highlighted markdown blocks.\n"
        f"Synthesize this verified data into a clear, human-readable Markdown report."
    )
    payload = [
        {"role": "system", "content": base_system_prompt},
        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
        {"role": "user", "content": synthesis_prompt},
    ]
    stream_iter = (
        llm_client.stream_chat(payload)
        if hasattr(llm_client, "stream_chat")
        else iter([llm_client.chat(payload, json_format=False)])
    )
    stream_state: dict[str, bool] = {}
    for chunk in _filter_stream_tool_leakage(stream_iter, stream_state):
        if chunk:
            yield {"type": "token", "chunk": chunk}


def _match_repositories_to_prompt(
    prompt: str, repos: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """
    Match user prompt against accessible repositories with strict priority
    given to exact matches and discriminating keywords over generic shared tokens.
    """
    if not repos:
        return None, []
    if len(repos) == 1:
        return repos[0], []

    prompt_lower = prompt.lower()
    clean_prompt = re.sub(r"[^a-z0-9]+", "", prompt_lower)
    prompt_norm = re.sub(r"[^a-z0-9]+", " ", prompt_lower)
    tokens = {t for t in prompt_norm.split() if len(t) >= 2}

    scored: list[tuple[int, dict[str, Any]]] = []
    for r in repos:
        name = (r.get("name") or "").lower()
        full_name = (r.get("full_name") or "").lower()
        clean_name = re.sub(r"[^a-z0-9]+", "", name)
        clean_full = re.sub(r"[^a-z0-9]+", "", full_name)
        score = 0

        # 1. Exact full_name match (highest priority)
        if full_name:
            if full_name == prompt_lower.strip():
                score += 100_000
            elif full_name in prompt_lower:
                score += 50_000
            elif clean_full and clean_full in clean_prompt:
                score += 40_000

        # 2. Exact repo name match
        if name:
            if name == prompt_lower.strip():
                score += 80_000
            elif name in prompt_lower:
                score += 30_000
            elif clean_name and clean_name in clean_prompt:
                score += 25_000

        # 3. Dissect repository parts into distinctive vs generic
        name_parts = [p for p in re.split(r"[^a-z0-9]+", name) if len(p) >= 2]
        for part in name_parts:
            if part in tokens:
                if part not in GENERIC_REPO_TERMS:
                    score += 200  # Discriminating keyword (e.g. 'ecommerce', 'portfolio')
                else:
                    score += 10  # Common generic tech keyword (e.g. 'react', 'html', 'css')

        # 4. High-threshold fuzzy tolerance for typos on distinctive repo names (e.g. 'Thumbify' -> 'Thumblify')
        if score == 0 and clean_name and len(clean_name) >= 5:
            best_ratio = 0.0
            for tok in tokens:
                clean_tok = re.sub(r"[^a-z0-9]+", "", tok)
                if len(clean_tok) < 5 or clean_tok in GENERIC_REPO_TERMS:
                    continue
                ratio = SequenceMatcher(None, clean_name, clean_tok).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
            if best_ratio >= 0.80:
                score += int(1500 * best_ratio)

        if score > 0:
            scored.append((score, r))

    if not scored:
        return None, repos[:8]

    scored.sort(key=lambda item: -item[0])
    top_score = scored[0][0]

    # If top match is overwhelmingly decisive (exact slug or name matched, >= 10,000 pts)
    if top_score >= 10_000:
        return scored[0][1], []

    # If top candidate is decisively ahead of the runner-up
    if len(scored) > 1:
        runner_up_score = scored[1][0]
        if top_score >= runner_up_score * 1.5:
            return scored[0][1], []
    else:
        return scored[0][1], []

    # Ambiguous
    top_matches = [item[1] for item in scored if item[0] >= top_score * 0.8]
    return None, top_matches[:8]


class GitHubChatOrchestrator:
    """
    Orchestrates ChatGPT-style conversational GitHub assistance using
    LLM tool calling, RepositoryExplorer, and existing ReviewOrchestrator agents.
    Yields structured event dicts:
      - {"type": "status", "stage": str, "detail": str}
      - {"type": "repo_select", "candidates": list[dict], "message": str}
      - {"type": "token", "chunk": str}
      - {"type": "meta", "repository": str, "branch": str, "commit_sha": str | None}
    """

    def __init__(
        self,
        db: Session,
        user: UserRecord | None,
        conversation_id: str,
        llm_client: Any,
        base_system_prompt: str,
        *,
        chat_mode: ChatMode = "github",
        allowed_tools: frozenset[str] | None = None,
        persist_repo_context: bool = True,
        guard_decision: GitHubGuardDecision | None = None,
    ) -> None:
        self.db = db
        self.user = user
        self.conversation_id = conversation_id
        self.llm_client = llm_client
        self.base_system_prompt = base_system_prompt
        self.chat_mode: ChatMode = chat_mode
        self.allowed_tools = allowed_tools
        self.persist_repo_context = persist_repo_context
        self.guard_decision = guard_decision

    def _get_locked_repo_context(self) -> ConversationRepositoryContextRecord | None:
        try:
            ensure_github_tables()
            return (
                self.db.query(ConversationRepositoryContextRecord)
                .filter(
                    ConversationRepositoryContextRecord.conversation_id == self.conversation_id
                )
                .first()
            )
        except Exception as exc:
            logger.debug("Could not read conversation repo context: %s", exc)
            return None

    def _save_repo_context(
        self,
        *,
        full_name: str,
        repo_id: str | None = None,
        default_branch: str = "main",
        selected_branch: str | None = None,
        commit_sha: str | None = None,
    ) -> None:
        try:
            ensure_github_tables()
            ctx = (
                self.db.query(ConversationRepositoryContextRecord)
                .filter(
                    ConversationRepositoryContextRecord.conversation_id == self.conversation_id
                )
                .first()
            )
            if not ctx:
                ctx = ConversationRepositoryContextRecord(
                    conversation_id=self.conversation_id,
                    user_id=self.user.id if self.user else None,
                )
                self.db.add(ctx)
            ctx.repository_full_name = full_name
            if repo_id is not None:
                ctx.repository_id = str(repo_id)
            ctx.default_branch = default_branch or ctx.default_branch or "main"
            ctx.selected_branch = selected_branch or ctx.default_branch
            if commit_sha:
                ctx.last_inspected_commit = commit_sha
            self.db.commit()
        except Exception as exc:
            logger.warning("Failed persisting conversation repo context: %s", exc)
            self.db.rollback()

    def run_stream(
        self,
        *,
        prompt: str,
        history: list[dict[str, str]],
        explicit_repo: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        auth: ResolvedGitHubAuth = resolve_user_github_context(self.db, self.user)
        # Never inherit a prior locked repo context unless actively operating in GitHub mode
        locked_ctx = self._get_locked_repo_context() if self.chat_mode == "github" else None

        # Evaluate authoritative mode + intent + authorization guard
        guard = self.guard_decision
        if guard is None:
            classified_intent = IntentClassifier.classify(
                prompt,
                mode=self.chat_mode,
                explicit_repo=explicit_repo,
                has_locked_repo=bool(locked_ctx),
            )
            guard = GitHubToolGuard.authorize(
                db=self.db,
                user=self.user,
                mode=self.chat_mode,
                intent=classified_intent,
                prompt=prompt,
                explicit_repo=explicit_repo,
            )

        # 1. Non-GitHub intents (chitchat, educational GitHub questions, general coding, pasted code)
        # must respond normally without touching GitHub APIs or emitting GitHub status messages.
        if not guard.use_github_orchestrator:
            yield {
                "type": "status",
                **ProgressMessageManager.initial_normal_status(guard.intent),
            }
            chat_payload = [{"role": "system", "content": self.base_system_prompt}] + history[-8:]
            stream_iter = (
                self.llm_client.stream_chat(chat_payload)
                if hasattr(self.llm_client, "stream_chat")
                else iter([self.llm_client.chat(chat_payload, json_format=False)])
            )
            for chunk in stream_iter:
                if chunk:
                    yield {"type": "token", "chunk": chunk}
            return

        from code_review.github.access_guard import GitHubAccessGuard, grant_scope

        prompt_repo_slug = explicit_repo or _extract_explicit_repo_slug(prompt)
        effective_allowed_tools = (
            self.allowed_tools if self.allowed_tools is not None else guard.allowed_tools
        )
        turn_grant = GitHubAccessGuard.authorize_chat_turn(
            db=self.db,
            user=self.user,
            conversation_id=self.conversation_id,
            mode=self.chat_mode,
            intent=guard.intent.value,
            is_github_intent=guard.is_github_intent,
            allow_tools=guard.allow_github_tools,
            allowed_tools=effective_allowed_tools,
            explicit_repo=prompt_repo_slug,
            auth_connected=auth.connected,
            auth_status=auth.connection_status,
            operation="chat_github_orchestration",
            reason=guard.denial_reason or f"Chat turn ({self.chat_mode}/{guard.intent.value})",
        )

        # 2. If GitHub tools are blocked (e.g., user has not connected GitHub), emit clear auth guidance cleanly
        if not guard.allow_github_tools or turn_grant is None:
            if auth.connection_status in ("expired", "revoked"):
                msg = (
                    "Your GitHub authorization has expired or was revoked. "
                    "Please reconnect your GitHub account using the **Connect GitHub** button "
                    "above or in **Settings** so I can inspect your repositories."
                )
            elif not self.user:
                msg = (
                    "Please sign in and connect your GitHub account to inspect private or personal "
                    "repositories. You can also ask about a specific public repository URL "
                    "(for example, `https://github.com/owner/repo`)."
                )
            else:
                msg = (
                    "GitHub is not connected yet for your account. Click **Connect GitHub** "
                    "to authorize repository access, and I'll be able to inspect your code, "
                    "commits, pull requests, and issues directly in this chat."
                )
            yield {"type": "token", "chunk": msg}
            return

        should_persist_repo_context = self.persist_repo_context and guard.persist_repo_context

        # 3. Resolve GitHubService and active repository under explicit turn grant scope
        gh_service = GitHubService(
            auth.token,
            cache_scope=auth.cache_scope,
            access_grant=turn_grant,
            bound_user=self.user,
            db=self.db,
        )
        with grant_scope(turn_grant):
            yield from self._run_authorized_github_flow(
                gh_service=gh_service,
                auth=auth,
                guard=guard,
                locked_ctx=locked_ctx,
                prompt=prompt,
                history=history,
                prompt_repo_slug=prompt_repo_slug,
                effective_allowed_tools=effective_allowed_tools,
                should_persist_repo_context=should_persist_repo_context,
            )

    def _run_authorized_github_flow(
        self,
        *,
        gh_service: GitHubService,
        auth: ResolvedGitHubAuth,
        guard: GitHubGuardDecision,
        locked_ctx: ConversationRepositoryContextRecord | None,
        prompt: str,
        history: list[dict[str, str]],
        prompt_repo_slug: str | None,
        effective_allowed_tools: frozenset[str],
        should_persist_repo_context: bool,
    ) -> Iterator[dict[str, Any]]:
        active_repo_full: str | None = None
        active_branch: str | None = None

        yield {"type": "status", "stage": "connecting", "detail": "Connecting to GitHub..."}

        if prompt_repo_slug and "/" in prompt_repo_slug:
            owner_p, repo_p = prompt_repo_slug.split("/", 1)
            try:
                details = gh_service.get_repository_details(owner_p, repo_p)
                active_repo_full = details.get("full_name") or prompt_repo_slug
                active_branch = details.get("default_branch") or "main"
                if should_persist_repo_context:
                    self._save_repo_context(
                        full_name=active_repo_full,
                        repo_id=str(details.get("id") or ""),
                        default_branch=active_branch,
                        selected_branch=active_branch,
                    )
            except (GitHubAuthError, httpx.HTTPStatusError) as auth_err:
                mark_connection_revoked_or_expired(self.db, self.user, "revoked")
                yield {
                    "type": "token",
                    "chunk": (
                        "Your GitHub authorization has expired or was revoked. "
                        "Please reconnect your GitHub account using the **Connect GitHub** button "
                        "above or in **Settings** so I can inspect your repositories."
                    ),
                }
                return
            except GitHubApiError as api_err:
                yield {
                    "type": "token",
                    "chunk": f"Could not access repository `{prompt_repo_slug}`: {api_err}",
                }
                return
            except Exception as unk_err:
                yield {
                    "type": "token",
                    "chunk": f"Could not access repository `{prompt_repo_slug}`: {unk_err}",
                }
                return
        elif auth.connected:
            yield {
                "type": "status",
                "stage": "discovering",
                "detail": "Discovering repositories...",
            }
            try:
                repos = gh_service.list_repositories(limit=50)
            except (GitHubAuthError, httpx.HTTPStatusError) as auth_err:
                mark_connection_revoked_or_expired(self.db, self.user, "revoked")
                yield {
                    "type": "token",
                    "chunk": (
                        "Your GitHub authorization has expired or was revoked. "
                        "Please reconnect your GitHub account using the **Connect GitHub** button "
                        "above or in **Settings** so I can inspect your repositories."
                    ),
                }
                return
            except GitHubApiError as api_err:
                yield {
                    "type": "token",
                    "chunk": f"Failed to discover your GitHub repositories: {api_err}",
                }
                return
            except Exception as unk_err:
                yield {
                    "type": "token",
                    "chunk": f"Failed to discover your GitHub repositories: {unk_err}",
                }
                return

            if not repos:
                yield {
                    "type": "token",
                    "chunk": (
                        "I connected to your GitHub account, but no repositories were accessible under "
                        "the current authorization. Please grant repository access in GitHub Settings."
                    ),
                }
                return

            is_listing_repos = guard.intent == UserIntent.GITHUB_REPO_LIST or any(
                phrase in prompt.lower()
                for phrase in (
                    "list my repo",
                    "show my repo",
                    "what repositories",
                    "which repositories",
                    "my repos",
                )
            )

            # Match repositories against the current prompt with priority over old conversation context
            matched_repo, ambiguous = (
                _match_repositories_to_prompt(prompt, repos)
                if not is_listing_repos
                else (None, [])
            )

            if matched_repo:
                active_repo_full = matched_repo["full_name"]
                active_branch = matched_repo.get("default_branch") or "main"
                if should_persist_repo_context:
                    self._save_repo_context(
                        full_name=active_repo_full,
                        repo_id=str(matched_repo.get("id") or ""),
                        default_branch=active_branch,
                        selected_branch=active_branch,
                    )
            elif locked_ctx and locked_ctx.repository_full_name and not is_listing_repos:
                # Prompt did not name another repo, maintain active conversation context
                active_repo_full = locked_ctx.repository_full_name
                active_branch = locked_ctx.selected_branch or locked_ctx.default_branch
            elif ambiguous and not is_listing_repos:
                yield {
                    "type": "repo_select",
                    "candidates": ambiguous,
                    "message": "Multiple repositories match or are available. Select the repository you want me to inspect:",
                }
                lines = [
                    "I found multiple repositories in your connected GitHub account. Which one should I inspect?\n"
                ]
                for r in ambiguous[:8]:
                    vis = "Private" if r.get("private") else "Public"
                    desc = f" — {r['description']}" if r.get("description") else ""
                    lines.append(
                        f"- **{r['full_name']}** ({vis}, branch `{r.get('default_branch', 'main')}`){desc}"
                    )
                yield {"type": "token", "chunk": "\n".join(lines)}
                return

        # 4. Check for Dedicated Full Repository Inspection Intent
        default_owner, default_repo = (
            active_repo_full.split("/", 1)
            if active_repo_full and "/" in active_repo_full
            else (None, None)
        )

        full_inspection_required_tools = {
            "explore_repository_overview",
            "get_repository_tree",
            "run_security_and_quality_agents",
        }
        if (
            is_full_repo_inspection_intent(prompt)
            and guard.intent == UserIntent.GITHUB_REPO_INSPECTION
            and full_inspection_required_tools.issubset(effective_allowed_tools)
            and default_owner
            and default_repo
        ):
            yield from self._run_full_repository_inspection(
                gh_service=gh_service,
                owner=default_owner,
                repo=default_repo,
                branch=active_branch or "main",
                user_prompt=prompt,
                persist_repo_context=should_persist_repo_context,
            )
            return

        # 5. Run LLM-driven Tool Orchestration Loop for interactive queries
        progress_queue: list[tuple[str, str]] = []

        def on_tool_progress(stage: str, detail: str) -> None:
            progress_queue.append((stage, detail))

        registry = GitHubToolRegistry(
            gh_service,
            default_owner=default_owner,
            default_repo=default_repo,
            default_ref=active_branch,
            allowed_tools=effective_allowed_tools,
            progress_callback=on_tool_progress,
        )
        scoped_tool_definitions = [
            td
            for td in GITHUB_TOOL_DEFINITIONS
            if td.get("function", {}).get("name") in effective_allowed_tools
        ]

        repo_context_note = (
            f"ACTIVE REPOSITORY CONTEXT:\n"
            f"- Repository: {active_repo_full}\n"
            f"- Branch: {active_branch or 'main'}\n"
            if active_repo_full
            else "NO SPECIFIC REPOSITORY LOCKED YET. Use `get_user_repositories` or `search_repositories` if needed.\n"
        )

        clean_base_prompt = _strip_poisoned_memory_from_prompt(self.base_system_prompt)
        gh_system_prompt = (
            f"{clean_base_prompt}\n\n"
            "=== GITHUB INTEGRATION MODE (READ-ONLY TOOL ORCHESTRATION) ===\n"
            f"{repo_context_note}"
            "INSTRUCTIONS:\n"
            "1. Use the provided GitHub tools to fetch real evidence from the repository before answering.\n"
            "2. For architecture or structure queries, inspect directory layout and key entry points.\n"
            "3. For security audits or bug inspections, run security and quality analyzers on relevant source files.\n"
            "4. NEVER invent file paths, line numbers, commit SHAs, or code not present in tool outputs.\n"
            "5. In your final response, provide a clean, human-readable markdown response with file paths and clickable GitHub links (`https://github.com/owner/repo/blob/branch/path#Lline`).\n"
            "6. NEVER output raw JSON dictionaries, API payloads, or internal tool schemas.\n"
            "REGISTERED TOOLS WORKFLOW:\n"
            "1. Use ONLY the registered function tools provided via the tool-calling API (e.g. `explore_repository_overview`, `get_repository_tree`, `fetch_files`, `fetch_file`, `run_security_and_quality_agents`). Never invent tool names such as `github_get_file_content`.\n"
            "2. Start by checking the repository structure (`explore_repository_overview` or `get_repository_tree`) so you have real non-empty file paths.\n"
            '3. NEVER call `fetch_file` with an empty path (`""`). Use `fetch_files` (concurrently fetches up to 10 paths in one call) to inspect key source/config files (auth, routes, controllers, middleware, DB, server entry points, manifests).\n'
            '4. For security audits or code quality checks, pass key file paths to `run_security_and_quality_agents` with `agents=["security"]` (supports Python, JS, JSX, TS, TSX, HTML, and manifests) in addition to reviewing fetched file contents.\n'
            "5. Once sufficient files and findings are collected (usually 2–4 tool rounds), stop calling tools and write your final grounded Markdown report.\n"
            '6. NEVER output raw JSON tool calls (`{"tool": ...}`), tool schemas, or unverified file paths/line numbers.\n'
        )

        sanitized_history = [
            {"role": m["role"], "content": m["content"]}
            for m in history[-8:]
            if not (
                m.get("role") == "assistant" and is_raw_tool_leakage(str(m.get("content", "")))
            )
        ]
        if not sanitized_history and history:
            sanitized_history = [{"role": "user", "content": prompt}]
        tool_messages: list[dict[str, Any]] = [
            {"role": "system", "content": gh_system_prompt}
        ] + sanitized_history

        final_content = ""
        used_tools = False
        text_tool_retried = False

        for _round in range(MAX_TOOL_ROUNDS):
            if _round == 0 and scoped_tool_definitions:
                yield {
                    "type": "status",
                    **ProgressMessageManager.initial_github_planning_status(guard.intent),
                }

            if hasattr(self.llm_client, "chat_with_tools") and scoped_tool_definitions:
                try:
                    resp = self.llm_client.chat_with_tools(
                        tool_messages,
                        tools=scoped_tool_definitions,
                    )
                except Exception as tool_call_err:
                    logger.warning(
                        "Native tool calling failed (%s); falling back to direct chat",
                        tool_call_err,
                    )
                    text = self.llm_client.chat(tool_messages, json_format=False)
                    resp = {"content": text, "tool_calls": []}
            else:
                text = self.llm_client.chat(tool_messages, json_format=False)
                resp = {"content": text, "tool_calls": []}

            tool_calls = resp.get("tool_calls") or []
            if not tool_calls:
                final_content = (resp.get("content") or "").strip()
                candidate_text = (resp.get("content") or "").strip()
                if candidate_text and is_raw_tool_leakage(candidate_text):
                    logger.warning(
                        "Intercepted unexecuted plaintext tool-call/raw payload at round %d (used_tools=%s).",
                        _round,
                        used_tools,
                    )
                    if not used_tools and not text_tool_retried:
                        # Do NOT execute untrusted text as tool calls; ask the model to invoke registered function tools properly
                        text_tool_retried = True
                        tool_messages.append(
                            {
                                "role": "assistant",
                                "content": "I will invoke the registered GitHub tools via function calling.",
                            }
                        )
                        tool_messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "You emitted JSON text instead of invoking the native tool-calling API. "
                                    "Never write JSON tool calls in assistant text. Use the registered function tools "
                                    "(start with `explore_repository_overview` or `get_repository_tree`, then `fetch_files` and `run_security_and_quality_agents`)."
                                ),
                            }
                        )
                        continue
                    # Otherwise discard leaked text so synthesis handles grounded output cleanly
                    final_content = ""
                    break

                final_content = candidate_text
                break

            used_tools = True
            assistant_turn: dict[str, Any] = {
                "role": "assistant",
                "content": "",
            }
            if resp.get("raw_tool_calls"):
                assistant_turn["tool_calls"] = resp["raw_tool_calls"]
            else:
                assistant_turn["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": (
                                tc["arguments"]
                                if isinstance(tc["arguments"], str)
                                else json.dumps(tc["arguments"])
                            ),
                        },
                    }
                    for tc in tool_calls
                ]
            tool_messages.append(assistant_turn)

            # Execute tool calls (concurrently with bounded workers when multiple independent calls returned)
            progress_queue.clear()
            if len(tool_calls) > 1:
                tool_outputs: list[str] = [""] * len(tool_calls)
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=min(4, len(tool_calls))
                ) as pool:
                    fut_idx = {
                        pool.submit(
                            registry.execute,
                            tc["name"],
                            tc.get("arguments"),
                        ): idx
                        for idx, tc in enumerate(tool_calls)
                    }
                    for fut in concurrent.futures.as_completed(fut_idx):
                        idx = fut_idx[fut]
                        try:
                            tool_outputs[idx] = fut.result()
                        except Exception as exc:
                            tool_outputs[idx] = json.dumps({"error": str(exc)})
                for stg, dtl in progress_queue:
                    yield {"type": "status", "stage": stg, "detail": dtl}
                for tc, tool_output in zip(tool_calls, tool_outputs, strict=True):
                    tool_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "name": tc["name"],
                            "content": tool_output,
                        }
                    )
            else:
                tc = tool_calls[0]
                tool_name = tc["name"]
                tool_args = tc.get("arguments")
                tool_output = registry.execute(tool_name, tool_args)
                for stg, dtl in progress_queue:
                    yield {"type": "status", "stage": stg, "detail": dtl}

                tool_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": tool_name,
                        "content": tool_output,
                    }
                )

        if active_repo_full and registry.last_commit_sha:
            self._save_repo_context(
                full_name=active_repo_full,
                default_branch=active_branch or "main",
                selected_branch=active_branch or "main",
                commit_sha=registry.last_commit_sha,
            )

        if active_repo_full:
            yield {
                "type": "meta",
                "repository": active_repo_full,
                "branch": active_branch or "main",
                "commit_sha": registry.last_commit_sha,
            }

        # Stream the final answer — guard against any raw tool output leakage
        if final_content:
            if is_raw_tool_leakage(final_content):
                yield {
                    "type": "status",
                    "stage": "finalizing",
                    "detail": "Formatting repository response...",
                }
                yield from _synthesize_raw_tool_output(
                    self.llm_client,
                    final_content,
                    prompt,
                    active_repo_full or "",
                    clean_base_prompt,
                )
            else:
                words = re.findall(r"\S+\s*", final_content)
                for idx in range(0, len(words), 4):
                    yield {"type": "token", "chunk": "".join(words[idx : idx + 4])}
        elif used_tools:
            yield from self._synthesize_after_tools(
                tool_messages=tool_messages,
                user_prompt=prompt,
                active_repo_full=active_repo_full or "",
                active_branch=active_branch or "main",
                inspected_files=sorted(registry.inspected_files),
            )
        else:
            yield {
                "type": "token",
                "chunk": (
                    "I could not execute repository analysis tools for this request because the model "
                    "did not issue valid tool calls. Please retry or check your repository selection."
                ),
            }

    def _synthesize_after_tools(
        self,
        *,
        tool_messages: list[dict[str, Any]],
        user_prompt: str,
        active_repo_full: str,
        active_branch: str,
        inspected_files: list[str],
    ) -> Iterator[dict[str, Any]]:
        yield {
            "type": "status",
            "stage": "finalizing",
            "detail": "Synthesizing grounded repository analysis...",
        }

        evidence_block, packed_paths = _format_tool_evidence_for_synthesis(tool_messages)
        all_inspected = sorted(set(inspected_files) | set(packed_paths))

        is_security_req = any(
            kw in user_prompt.lower()
            for kw in ("security", "vulnerabilit", "audit", "xss", "injection", "secret", "auth")
        )
        if is_security_req and not all_inspected and "Multi-Agent Security" not in evidence_block:
            yield {
                "type": "token",
                "chunk": (
                    f"Unable to complete a security review of `{active_repo_full or 'repository'}` because "
                    "no source or configuration files could be retrieved from GitHub. "
                    "Verify repository access and permissions, then retry."
                ),
            }
            return

        synth_user_msg = (
            f"USER REQUEST: {user_prompt}\n"
            f"REPOSITORY: {active_repo_full or 'Unknown'} (branch `{active_branch}`)\n"
            f"FILES ACTUALLY RETRIEVED & ANALYZED ({len(all_inspected)}): {', '.join(all_inspected[:30])}\n\n"
            f"VERIFIED TOOL RESULTS:\n{evidence_block}\n\n"
            "Write a clear, well-structured Markdown report answering the user's request strictly from the verified evidence above. "
            "Include severity, exact file paths, line numbers, code evidence, and remediation recommendations where findings exist. "
            "Do NOT output any raw JSON tool-call objects or request additional tools."
        )
        synth_payload = [
            {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
            {"role": "user", "content": synth_user_msg},
        ]

        stream_iter = (
            self.llm_client.stream_chat(synth_payload)
            if hasattr(self.llm_client, "stream_chat")
            else iter([self.llm_client.chat(synth_payload, json_format=False)])
        )
        stream_state: dict[str, bool] = {}
        for chunk in _filter_stream_tool_leakage(stream_iter, stream_state):
            if chunk:
                yield {"type": "token", "chunk": chunk}

        if not stream_state.get("emitted"):
            # Safe fallback if stream yielded only filtered/leaked tool blocks
            fallback_text = (
                f"### Repository Analysis: `{active_repo_full}` (`{active_branch}`)\n\n"
                f"Inspected **{len(all_inspected)}** file(s): "
                + ", ".join(f"`{p}`" for p in all_inspected[:20])
                + ".\n\nPlease retry if you need a fuller breakdown."
            )
            yield {"type": "token", "chunk": fallback_text}

    def _run_full_repository_inspection(
        self,
        gh_service: GitHubService,
        owner: str,
        repo: str,
        branch: str,
        user_prompt: str,
        persist_repo_context: bool = True,
    ) -> Iterator[dict[str, Any]]:
        repo_full = f"{owner}/{repo}"
        explorer = RepositoryExplorer(gh_service)

        # 1. Structure & Overview
        yield {
            "type": "status",
            "stage": "exploring",
            "detail": f"Inspecting repository structure, commits, and manifests for {repo_full}...",
        }
        try:
            overview = explorer.explore_overview(owner, repo, ref=branch)
        except Exception as exc:
            logger.warning("Failed overview exploration for %s: %s", repo_full, exc)
            overview = {"repository": repo_full, "branch": branch}

        head_sha = overview.get("head_sha")
        tech_stack = overview.get("tech_stack", [])
        manifests = overview.get("manifests", {})
        entry_points = overview.get("entry_points", [])
        top_dirs = overview.get("top_directories", [])
        root_files = overview.get("root_files", [])

        tree_paths: list[str] = []
        try:
            tree = gh_service.get_repository_tree(owner, repo, ref=branch, recursive=True)
            tree_paths = [
                e["path"] for e in (tree.get("entries") or []) if e.get("type") == "blob"
            ]
        except Exception:
            tree_paths = []

        if head_sha and persist_repo_context:
            self._save_repo_context(
                full_name=repo_full,
                default_branch=branch,
                selected_branch=branch,
                commit_sha=head_sha,
            )

        # Emit meta event immediately so UI shows authoritative repository and commit
        yield {
            "type": "meta",
            "repository": repo_full,
            "branch": branch,
            "commit_sha": head_sha,
        }

        # 2. Multi-Agent Analysis
        stack_desc = ", ".join(tech_stack) if tech_stack else "General"
        yield {
            "type": "status",
            "stage": "analyzing",
            "detail": f"Detected stack ({stack_desc}). Running Security, AST, and Quality agents on codebase...",
        }

        candidate_paths: list[str] = []
        for m in (
            "package.json",
            "requirements.txt",
            "pyproject.toml",
            "Dockerfile",
            "docker-compose.yml",
        ):
            if (m in root_files or m in manifests) and m not in candidate_paths:
                candidate_paths.append(m)
        for m in manifests:
            if m not in candidate_paths:
                candidate_paths.append(m)
        for ep in entry_points:
            if ep not in candidate_paths:
                candidate_paths.append(ep)

        priority_terms = (
            "auth",
            "middleware",
            "security",
            "server",
            "route",
            "controller",
            "config",
            "db",
            "contact",
        )
        for tp in tree_paths:
            if tp in candidate_paths:
                continue
            if tp.endswith((".py", ".js", ".jsx", ".ts", ".tsx")) and any(
                t in tp.lower() for t in priority_terms
            ):
                candidate_paths.append(tp)

        if len(candidate_paths) < 8:
            for tp in tree_paths or root_files:
                if (
                    tp.endswith((".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs"))
                    and tp not in candidate_paths
                ):
                    candidate_paths.append(tp)

        agent_report: dict[str, Any] = {}
        try:
            agent_report = explorer.run_agents_on_files(
                owner,
                repo,
                paths=candidate_paths[:12],
                ref=branch,
            )
        except Exception as exc:
            logger.warning("Agent scan exception during inspection of %s: %s", repo_full, exc)
            agent_report = {"total_findings": 0, "findings": []}

        # 3. Report Synthesis
        yield {
            "type": "status",
            "stage": "finalizing",
            "detail": "Synthesizing authoritative engineering report...",
        }

        findings_summary = agent_report.get("findings", [])[:20]

        synthesis_prompt = (
            f"You are Nexarion, an elite AI Software Architect and Staff-Level Systems Engineer.\n"
            f"Generate a comprehensive, authoritative inspection report for repository `{repo_full}` based strictly on the verified factual evidence below.\n\n"
            f"USER REQUEST: {user_prompt}\n\n"
            f"VERIFIED REPOSITORY METADATA:\n"
            f"- Repository: {repo_full}\n"
            f"- HTML URL: {overview.get('html_url') or f'https://github.com/{repo_full}'}\n"
            f"- Default/Active Branch: {branch}\n"
            f"- Head Commit SHA: {head_sha or 'N/A'}\n"
            f"- Visibility: {overview.get('visibility', 'public')}\n"
            f"- Description: {overview.get('description') or 'No description provided'}\n"
            f"- Detected Tech Stack: {', '.join(tech_stack) if tech_stack else 'General'}\n"
            f"- Top Directories: {', '.join(top_dirs[:20])}\n"
            f"- Root Files: {', '.join(root_files[:25])}\n"
            f"- Key Entry Points: {', '.join(entry_points[:10])}\n"
            f"- Total Files Indexed: {overview.get('total_indexed_files', 0)}\n\n"
            f"DEPENDENCY MANIFEST SNIPPETS:\n"
            f"{json.dumps({k: v[:1200] for k, v in manifests.items()}, indent=2)}\n\n"
            f"MULTI-AGENT CODE REVIEW FINDINGS ({agent_report.get('total_findings', 0)} total findings across {agent_report.get('files_analyzed', [])}):\n"
            f"{json.dumps(findings_summary, indent=2)}\n\n"
            f"MANDATORY REPORT STRUCTURE:\n"
            f"You MUST format your entire response in clear, publication-grade GitHub Flavored Markdown using these exact 6 sections:\n\n"
            f"# Repository Inspection: {repo_full}\n\n"
            f"## A. Repository Overview\n"
            f"Present repository name, active branch, latest commit SHA ({head_sha or 'N/A'}), visibility, high-level purpose, and repository health overview.\n\n"
            f"## B. Project Architecture\n"
            f"Explain the structural layout, entry points, module separation (frontend, backend, shared services), and overall control flow.\n\n"
            f"## C. Technology Stack\n"
            f"Break down languages, core frameworks, runtime environments, libraries, and build/configuration tooling.\n\n"
            f"## D. Key Findings & Code Review\n"
            f"Synthesize the findings across 5 concrete areas:\n"
            f"1. **Security & Authentication** (credentials, tokens, sanitize inputs, vulnerabilities)\n"
            f"2. **Code Quality & Maintainability** (typing, modularity, patterns, dead code)\n"
            f"3. **Performance & Resource Efficiency** (blocking I/O, queries, bundles)\n"
            f"4. **Architecture & Modularity** (separation of concerns, coupling, structure)\n"
            f"5. **Documentation & Dependencies** (package versions, setup guides, README coverage)\n"
            f"For each finding, provide clear context and a clickable GitHub link (`https://github.com/{owner}/{repo}/blob/{branch}/path#Lline`).\n\n"
            f"## E. Overall Assessment\n"
            f"Provide a frank, professional engineering appraisal of production-readiness, architecture quality, and maintainability.\n\n"
            f"## F. Recommended Next Steps\n"
            f"Provide an actionable, prioritized roadmap (Immediate Fixes / Short-term Improvements / Long-term Architectural Goals).\n\n"
            f"STRICT RULES:\n"
            f"- NEVER output raw JSON tool calls, dictionaries, or tool metadata.\n"
            f"- Ground every single claim in the verified facts and manifests above."
        )

        payload = [
            {"role": "system", "content": self.base_system_prompt},
            {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
            {"role": "user", "content": synthesis_prompt},
        ]

        stream_iter = (
            self.llm_client.stream_chat(payload)
            if hasattr(self.llm_client, "stream_chat")
            else iter([self.llm_client.chat(payload, json_format=False)])
        )
        stream_state: dict[str, bool] = {}
        for chunk in _filter_stream_tool_leakage(stream_iter, stream_state):
            if chunk:
                yield {"type": "token", "chunk": chunk}
