from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
import urllib.parse
from pathlib import Path
from typing import Any

import httpx
import jwt

from code_review.config import get_settings
from code_review.github.cache import get_github_cache
from code_review.parsers.diff_parser import parse_diff

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
MAX_DIFF_BYTES = 500 * 1024
MAX_FILE_BYTES = 200 * 1024

IGNORED_PATH_SEGMENTS = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "dist",
        "build",
        "target",
        "vendor",
        ".next",
        ".nuxt",
        "coverage",
        "htmlcov",
    }
)

BINARY_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".bmp",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".7z",
        ".rar",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".pyc",
        ".pyo",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp3",
        ".mp4",
        ".wav",
        ".avi",
        ".mov",
        ".sqlite",
        ".db",
        ".bin",
        ".lockb",
    }
)

SENSITIVE_BASENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        ".env.staging",
        ".env.test",
        "id_rsa",
        "id_ed25519",
        "credentials.json",
        "service-account.json",
        "secrets.yaml",
        "secrets.yml",
        ".npmrc",
        ".pypirc",
        ".netrc",
    }
)

SENSITIVE_EXTENSIONS = frozenset({".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"})


class GitHubApiError(Exception):
    def __init__(self, message: str, status_code: int = 502, error_code: str = "GITHUB_ERROR"):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class GitHubAuthError(GitHubApiError):
    def __init__(self, message: str, error_code: str = "GITHUB_AUTH_ERROR"):
        super().__init__(message, status_code=401, error_code=error_code)


class GitHubAccessDeniedError(GitHubAuthError):
    def __init__(
        self,
        message: str = "GitHub repository access is denied without explicit authorization.",
        error_code: str = "GITHUB_ACCESS_DENIED",
    ):
        super().__init__(message, error_code=error_code)
        self.status_code = 403


class GitHubRateLimitError(GitHubApiError):
    def __init__(self, message: str = "GitHub API rate limit exceeded. Please try again shortly."):
        super().__init__(message, status_code=429, error_code="GITHUB_RATE_LIMIT")


class GitHubNotFoundError(GitHubApiError):
    def __init__(self, message: str = "GitHub resource not found or access is denied."):
        super().__init__(message, status_code=404, error_code="GITHUB_NOT_FOUND")


def is_ignored_repo_path(path: str) -> bool:
    norm = path.replace("\\", "/").strip("/")
    if not norm:
        return False
    parts = norm.split("/")
    if any(p in IGNORED_PATH_SEGMENTS for p in parts):
        return True
    basename = parts[-1].lower()
    if basename.endswith(".min.js") or basename.endswith(".min.css"):
        return True
    suffix = Path(basename).suffix.lower()
    if suffix in BINARY_EXTENSIONS:
        return True
    return False


def is_sensitive_repo_path(path: str) -> bool:
    norm = path.replace("\\", "/").strip("/")
    basename = norm.split("/")[-1].lower()
    if basename in SENSITIVE_BASENAMES:
        return True
    if basename.startswith(".env.") and basename != ".env.example":
        return True
    suffix = Path(basename).suffix.lower()
    if suffix in SENSITIVE_EXTENSIONS:
        return True
    if "secret" in basename and suffix in {".json", ".yaml", ".yml", ".toml", ".ini"}:
        return True
    return False


class GitHubService:
    def __init__(
        self,
        token: str | None = None,
        *,
        cache_scope: str | None = None,
        access_grant: Any | None = None,
        bound_user: Any | None = None,
        db: Any | None = None,
    ) -> None:
        self.settings = get_settings()
        self.token = token or self.settings.github_token or None
        self._access_grant = access_grant
        self._bound_user = bound_user
        self._db = db
        if cache_scope:
            self.cache_scope = cache_scope
        elif self.token:
            self.cache_scope = hashlib.sha256(self.token.encode("utf-8")).hexdigest()[:16]
        else:
            self.cache_scope = "public"
        self._cache = get_github_cache()

    def _authorize_operation(
        self,
        operation: str,
        *,
        owner: str | None = None,
        repo: str | None = None,
    ) -> None:
        from code_review.github.access_guard import GitHubAccessGuard

        GitHubAccessGuard.enforce_service_call(
            self,
            operation,
            owner=owner,
            repo=repo,
            db=self._db,
        )

    def get_auth_headers(self, custom_token: str | None = None) -> dict[str, str]:
        active_token = custom_token or self.token
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "NEXARION-Code-Review/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if active_token:
            headers["Authorization"] = f"Bearer {active_token}"
        return headers

    def _handle_http_error(self, resp: httpx.Response, context_msg: str = "") -> None:
        if resp.status_code < 400:
            return
        if resp.status_code == 401:
            raise GitHubAuthError(
                "GitHub authorization expired or was revoked. Please reconnect GitHub.",
                error_code="GITHUB_TOKEN_EXPIRED",
            )
        if resp.status_code == 403:
            remaining = resp.headers.get("X-RateLimit-Remaining", "")
            text_lower = (resp.text or "").lower()
            if remaining == "0" or "rate limit" in text_lower:
                raise GitHubRateLimitError(
                    "GitHub API rate limit reached. Wait a moment or connect your GitHub account."
                )
            raise GitHubAuthError(
                f"GitHub access forbidden{': ' + context_msg if context_msg else ''}. "
                "Check repository permissions.",
                error_code="GITHUB_FORBIDDEN",
            )
        if resp.status_code == 404:
            raise GitHubNotFoundError(
                f"GitHub resource not found or unauthorized"
                f"{' (' + context_msg + ')' if context_msg else ''}."
            )
        raise GitHubApiError(
            f"GitHub API error ({resp.status_code}){': ' + context_msg if context_msg else ''}",
            status_code=resp.status_code,
        )

    def _get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float = 20.0,
        context_msg: str = "",
    ) -> Any:
        req_headers = headers or self.get_auth_headers()
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(url, headers=req_headers, params=params)
                self._handle_http_error(resp, context_msg=context_msg)
                return resp.json()
        except GitHubApiError:
            raise
        except httpx.TimeoutException as exc:
            raise GitHubApiError(
                f"GitHub request timed out ({context_msg or url}).",
                status_code=504,
                error_code="GITHUB_TIMEOUT",
            ) from exc
        except Exception as exc:
            raise GitHubApiError(f"GitHub communication failure: {exc}") from exc

    # --- GitHub App & OAuth Authentication Helpers ---

    @staticmethod
    def _load_app_private_key(raw_key: str) -> str:
        val = (raw_key or "").strip()
        if not val:
            return ""
        if "BEGIN" in val and "PRIVATE KEY" in val:
            return val.replace("\\n", "\n")
        key_path = Path(val)
        if key_path.is_file():
            return key_path.read_text(encoding="utf-8")
        return val.replace("\\n", "\n")

    def is_github_app_configured(self) -> bool:
        return bool(
            (self.settings.github_app_id or "").strip()
            and (self.settings.github_app_private_key or "").strip()
            and (self.settings.github_app_slug or "").strip()
        )

    def create_app_jwt(self) -> str:
        app_id = (self.settings.github_app_id or "").strip()
        pem_key = self._load_app_private_key(self.settings.github_app_private_key)
        if not app_id or not pem_key:
            raise GitHubAuthError(
                "GitHub App credentials (GITHUB_APP_ID / GITHUB_APP_PRIVATE_KEY) not configured.",
                error_code="GITHUB_APP_NOT_CONFIGURED",
            )
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + 540,
            "iss": app_id,
        }
        try:
            return jwt.encode(payload, pem_key, algorithm="RS256")
        except Exception as exc:
            raise GitHubAuthError(
                f"Failed to sign GitHub App JWT: {exc}",
                error_code="GITHUB_APP_JWT_ERROR",
            ) from exc

    def get_app_install_url(self, state: str = "nexarion_app") -> str:
        slug = (self.settings.github_app_slug or "").strip()
        if not slug:
            return ""
        params = urllib.parse.urlencode({"state": state})
        return f"https://github.com/apps/{urllib.parse.quote(slug)}/installations/new?{params}"

    def get_installation_details(self, installation_id: str | int) -> dict[str, Any]:
        self._authorize_operation("get_installation_details")
        app_jwt = self.create_app_jwt()
        headers = self.get_auth_headers(app_jwt)
        return self._get_json(
            f"{GITHUB_API_BASE}/app/installations/{installation_id}",
            headers=headers,
            context_msg=f"installation {installation_id}",
        )

    def create_installation_access_token(self, installation_id: str | int) -> dict[str, Any]:
        self._authorize_operation("create_installation_access_token")
        app_jwt = self.create_app_jwt()
        headers = self.get_auth_headers(app_jwt)
        url = f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(url, headers=headers)
                self._handle_http_error(resp, context_msg=f"installation token {installation_id}")
                return resp.json()
        except GitHubApiError:
            raise
        except Exception as exc:
            raise GitHubAuthError(
                f"Failed to create GitHub App installation token: {exc}",
                error_code="GITHUB_INSTALLATION_TOKEN_ERROR",
            ) from exc

    def list_installation_repositories(
        self, token: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        self._authorize_operation("list_installation_repositories")
        headers = self.get_auth_headers(token)
        repos: list[dict[str, Any]] = []
        page = 1
        per_page = min(100, max(1, limit))
        while len(repos) < limit:
            data = self._get_json(
                f"{GITHUB_API_BASE}/installation/repositories",
                headers=headers,
                params={"per_page": per_page, "page": page},
                context_msg="installation repositories",
            )
            batch = data.get("repositories", []) if isinstance(data, dict) else []
            if not batch:
                break
            for r in batch:
                repos.append(self._normalize_repo(r))
                if len(repos) >= limit:
                    break
            if len(batch) < per_page:
                break
            page += 1
        return repos

    @staticmethod
    def _normalize_repo(r: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": r.get("id"),
            "name": r.get("name", ""),
            "full_name": r.get("full_name", ""),
            "owner": (r.get("owner") or {}).get("login", ""),
            "private": bool(r.get("private", False)),
            "html_url": r.get("html_url", ""),
            "default_branch": r.get("default_branch") or "main",
            "description": r.get("description") or "",
            "language": r.get("language") or "",
            "stargazers_count": r.get("stargazers_count", 0),
            "updated_at": r.get("updated_at"),
        }

    @staticmethod
    def verify_webhook_signature(
        payload_bytes: bytes,
        signature_header: str | None,
        secret: str,
    ) -> bool:
        if not secret:
            logger.warning(
                "GitHub webhook secret is not configured; skipping signature verification."
            )
            return True
        if not signature_header or not signature_header.startswith("sha256="):
            return False

        expected_hash = hmac.new(
            secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        received_hash = signature_header[7:].strip()
        return hmac.compare_digest(expected_hash, received_hash)

    def get_oauth_url(self, state: str = "nexarion_auth") -> str:
        if not self.settings.github_client_id:
            return ""
        params = {
            "client_id": self.settings.github_client_id,
            "redirect_uri": self.settings.github_redirect_uri,
            "scope": "repo,read:user",
            "state": state,
        }
        return f"https://github.com/login/oauth/authorize?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str) -> str:
        self._authorize_operation("exchange_code")
        url = "https://github.com/login/oauth/access_token"
        payload = {
            "client_id": self.settings.github_client_id,
            "client_secret": self.settings.github_client_secret,
            "code": code,
        }
        headers = {
            "Accept": "application/json",
            "User-Agent": "NEXARION-Code-Review/1.0",
        }
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            token = data.get("access_token")
            if not token:
                raise ValueError(
                    data.get("error_description") or "Failed to retrieve access token from GitHub."
                )
            return str(token)

    def get_user_profile(self, token: str | None = None) -> dict[str, Any]:
        self._authorize_operation("get_user_profile")
        headers = self.get_auth_headers(token)
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(f"{GITHUB_API_BASE}/user", headers=headers)
            resp.raise_for_status()
            return resp.json()

    def list_repositories(
        self, token: str | None = None, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        self._authorize_operation("list_repositories")
        active_token = token or self.token
        cache_key = self._cache.build_key(self.cache_scope, "list_repos", extra={"limit": limit})
        if not token:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        headers = self.get_auth_headers(token)
        # GitHub App installation tokens start with ghs_ and only work with /installation/repositories
        if active_token and active_token.startswith("ghs_"):
            result = self.list_installation_repositories(token=active_token, limit=limit)
            if not token:
                self._cache.set(cache_key, result, ttl=120.0)
            return result

        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                f"{GITHUB_API_BASE}/user/repos?sort=updated&per_page={min(100, limit)}",
                headers=headers,
            )
            if resp.status_code == 403:
                # Fallback for installation tokens without ghs_ prefix
                try:
                    result = self.list_installation_repositories(token=active_token, limit=limit)
                    if not token:
                        self._cache.set(cache_key, result, ttl=120.0)
                    return result
                except Exception:
                    pass
            if resp.status_code == 401:
                raise GitHubAuthError(f"GitHub 401 Unauthorized listing repositories: {resp.text}")
            if resp.status_code == 403:
                raise GitHubAuthError(f"GitHub 403 Forbidden listing repositories: {resp.text}")
            if resp.status_code == 404:
                raise GitHubNotFoundError("GitHub repositories not found: 404")
            resp.raise_for_status()
            repos = resp.json()
            result = [self._normalize_repo(r) for r in repos]
            if not token:
                self._cache.set(cache_key, result, ttl=120.0)
            return result

    def list_pull_requests(
        self, owner: str, repo: str, token: str | None = None
    ) -> list[dict[str, Any]]:
        self._authorize_operation("list_pull_requests", owner=owner, repo=repo)
        headers = self.get_auth_headers(token)
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls?state=all&per_page=30",
                headers=headers,
            )
            resp.raise_for_status()
            pulls = resp.json()
            results = []
            for pr in pulls:
                if pr.get("merged_at") is not None:
                    real_state = "merged"
                elif pr.get("state") == "closed":
                    real_state = "closed"
                else:
                    real_state = "open"

                results.append(
                    {
                        "number": pr["number"],
                        "title": pr["title"],
                        "state": real_state,
                        "raw_state": pr.get("state"),
                        "merged_at": pr.get("merged_at"),
                        "author": pr["user"]["login"] if pr.get("user") else "Unknown",
                        "html_url": pr["html_url"],
                        "created_at": pr.get("created_at"),
                        "updated_at": pr.get("updated_at"),
                        "head_branch": pr.get("head", {}).get("ref", "feature"),
                        "base_branch": pr.get("base", {}).get("ref", "main"),
                        "body": pr.get("body") or "",
                    }
                )
            return results

    def get_pull_request_diff(
        self, owner: str, repo: str, pull_number: int, token: str | None = None
    ) -> dict[str, Any]:
        self._authorize_operation("get_pull_request_diff", owner=owner, repo=repo)
        headers = self.get_auth_headers(token)

        with httpx.Client(timeout=25.0) as client:
            pr_resp = client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}",
                headers=headers,
            )
            pr_resp.raise_for_status()
            pr_data = pr_resp.json()

            diff_headers = headers.copy()
            diff_headers["Accept"] = "application/vnd.github.v3.diff"
            diff_resp = client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}",
                headers=diff_headers,
            )
            diff_resp.raise_for_status()
            diff_text = diff_resp.text

        if len(diff_text.encode("utf-8")) > MAX_DIFF_BYTES:
            raise ValueError(
                f"Pull request diff ({len(diff_text)} bytes) exceeds review limit (500KB). "
                "Please review smaller, focused PRs to ensure comprehensive analysis."
            )

        return {
            "owner": owner,
            "repo": repo,
            "number": pull_number,
            "title": pr_data.get("title", f"PR #{pull_number}"),
            "author": pr_data.get("user", {}).get("login", "Developer"),
            "state": pr_data.get("state", "open"),
            "head_sha": pr_data.get("head", {}).get("sha"),
            "base_sha": pr_data.get("base", {}).get("sha"),
            "additions": pr_data.get("additions", 0),
            "deletions": pr_data.get("deletions", 0),
            "changed_files": pr_data.get("changed_files", 1),
            "diff": diff_text,
        }

    def format_pr_review(
        self,
        findings: list[Any],
        owner: str,
        repo: str,
        pull_number: int,
        diff_text: str = "",
        duration_seconds: float = 0.0,
        commit_sha: str | None = None,
        dashboard_url: str | None = None,
    ) -> tuple[str, list[dict[str, Any]], str]:
        valid_diff_lines: dict[str, set[int]] = {}
        if diff_text:
            try:
                parsed_files = parse_diff(diff_text)
                for df in parsed_files:
                    lines_set = set()
                    for hunk in df.hunks:
                        for line in hunk.lines:
                            if line.target_line is not None:
                                lines_set.add(line.target_line)
                    clean_path = df.path.replace("\\", "/").lstrip("/")
                    valid_diff_lines[clean_path] = lines_set
            except Exception as exc:
                logger.warning("Could not parse diff for inline comment line mapping: %s", exc)

        inline_comments: list[dict[str, Any]] = []
        unmapped_findings: list[Any] = []

        severity_counts = {"CRITICAL": 0, "ERROR": 0, "WARNING": 0, "INFO": 0}
        agent_counts: dict[str, int] = {}
        has_critical = False

        for f in findings:
            sev = str(getattr(f, "severity", "INFO")).upper()
            if hasattr(getattr(f, "severity", None), "value"):
                sev = f.severity.value.upper()
            if sev not in severity_counts:
                severity_counts[sev] = 0
            severity_counts[sev] += 1

            if sev == "CRITICAL":
                has_critical = True

            ag_name = str(getattr(f, "agent", "agent"))
            if hasattr(getattr(f, "agent", None), "value"):
                ag_name = f.agent.value
            agent_counts[ag_name] = agent_counts.get(ag_name, 0) + 1

            raw_path = getattr(f, "file", "") or getattr(f, "file_path", "")
            f_file = str(raw_path).replace("\\", "/").lstrip("/")
            f_line = int(getattr(f, "line", 0) or getattr(f, "line_start", 0))
            raw_msg = (
                getattr(f, "message", "")
                or getattr(f, "description", "")
                or getattr(f, "title", "")
            )
            f_msg = str(raw_msg)
            f_fix = getattr(f, "suggestion", None) or getattr(f, "suggested_fix", None)
            f_rule = getattr(f, "rule_id", None)

            is_valid_line = False
            if f_file in valid_diff_lines and f_line in valid_diff_lines[f_file]:
                is_valid_line = True
            elif not valid_diff_lines and f_line > 0:
                is_valid_line = True

            if is_valid_line and f_line > 0:
                rule_tag = f" `[{f_rule}]`" if f_rule else ""
                comment_lines = [
                    f"**[{sev}]** {f_msg}{rule_tag}",
                    f"*Found by `{ag_name}` agent*",
                ]
                if f_fix and str(f_fix).strip():
                    comment_lines.append("")
                    comment_lines.append(f"```suggestion\n{f_fix.strip()}\n```")

                inline_comments.append(
                    {
                        "path": f_file,
                        "line": f_line,
                        "side": "RIGHT",
                        "body": "\n".join(comment_lines),
                    }
                )
            else:
                unmapped_findings.append(f)

        if has_critical:
            status_badge = "**Changes Requested**"
        elif (severity_counts["ERROR"] + severity_counts["WARNING"]) > 0:
            status_badge = "**Warnings Found**"
        else:
            status_badge = "**Review Passed**"

        commit_tag = f"`{commit_sha[:7]}`" if commit_sha else "latest"
        dash_link = (
            f"[Open in NEXARION]({dashboard_url})"
            if dashboard_url
            else "NEXARION Code Review System"
        )

        body_parts = [
            f"## NEXARION Multi-Agent Code Review — PR #{pull_number}",
            f"> Automated code quality and security review for commit {commit_tag}.",
            "",
            f"### Verdict: {status_badge}",
            "",
            "| Metric | Value |",
            "| :--- | :--- |",
            f"| **Total Findings** | **{len(findings)}** |",
            f"| **Critical Issues** | `{severity_counts['CRITICAL']}` |",
            f"| **Errors** | `{severity_counts['ERROR']}` |",
            f"| **Warnings** | `{severity_counts['WARNING']}` |",
            f"| **Informational** | `{severity_counts['INFO']}` |",
            f"| **Analysis Duration** | `{duration_seconds:.2f}s` |",
            "",
        ]

        if agent_counts:
            body_parts.append("### Agent Breakdown")
            body_parts.append("| Agent | Findings Detected |")
            body_parts.append("| :--- | :---: |")
            for ag, count in sorted(agent_counts.items(), key=lambda x: -x[1]):
                body_parts.append(f"| `{ag}` | {count} |")
            body_parts.append("")

        high_severity = [
            f
            for f in findings
            if str(getattr(f, "severity", "")).upper() in ("CRITICAL", "ERROR")
            or getattr(getattr(f, "severity", None), "value", "").upper() in ("CRITICAL", "ERROR")
        ]
        if high_severity:
            body_parts.append("### Urgent Action Required")
            for hf in high_severity[:5]:
                raw_s = getattr(hf, "severity", "")
                h_sev = getattr(raw_s, "value", str(raw_s)).upper()
                h_file = getattr(hf, "file", "") or getattr(hf, "file_path", "")
                h_line = getattr(hf, "line", 0) or getattr(hf, "line_start", 0)
                h_msg = getattr(hf, "message", "") or getattr(hf, "description", "")
                body_parts.append(f"- **[{h_sev}]** `{h_file}:{h_line}` — {h_msg}")
            if len(high_severity) > 5:
                body_parts.append(
                    f"- *...and {len(high_severity) - 5} more critical/error issues.*"
                )
            body_parts.append("")

        if unmapped_findings:
            body_parts.append("<details>")
            count_unmapped = len(unmapped_findings)
            body_parts.append(
                f"<summary><b>Structural Findings ({count_unmapped})</b></summary>\n"
            )
            for uf in unmapped_findings:
                raw_us = getattr(uf, "severity", "")
                u_sev = getattr(raw_us, "value", str(raw_us)).upper()
                u_file = getattr(uf, "file", "") or getattr(uf, "file_path", "")
                u_line = getattr(uf, "line", 0) or getattr(uf, "line_start", 0)
                u_msg = getattr(uf, "message", "") or getattr(uf, "description", "")
                u_fix = getattr(uf, "suggestion", None) or getattr(uf, "suggested_fix", None)
                body_parts.append(f"- **[{u_sev}]** `{u_file}:{u_line}`: {u_msg}")
                if u_fix:
                    body_parts.append(f"  *Suggestion: {u_fix}*")
            body_parts.append("\n</details>")
            body_parts.append("")

        body_parts.append("---")
        body_parts.append(
            f"<sub>Report generated by **{dash_link}** • Multi-Agent AI Code Review</sub>"
        )

        summary_markdown = "\n".join(body_parts)
        review_action = "REQUEST_CHANGES" if has_critical else "COMMENT"
        return summary_markdown, inline_comments, review_action

    def post_pull_request_review(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        body: str,
        event: str = "COMMENT",
        comments: list[dict[str, Any]] | None = None,
        commit_sha: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        self._authorize_operation("post_pull_request_review", owner=owner, repo=repo)
        headers = self.get_auth_headers(token)
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}/reviews"

        payload: dict[str, Any] = {
            "body": body,
            "event": event,
        }
        if commit_sha:
            payload["commit_id"] = commit_sha
        if comments:
            payload["comments"] = comments

        with httpx.Client(timeout=30.0) as client:
            try:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as err:
                if err.response.status_code == 422 and comments:
                    logger.warning(
                        "GitHub review submission returned 422 for %s/%s #%s. "
                        "Retrying with all findings compiled into review body.",
                        owner,
                        repo,
                        pull_number,
                    )
                    fallback_body = body + "\n\n### Inline Findings (Aggregated Fallback)\n"
                    for c in comments:
                        fallback_body += f"\n- `{c['path']}:{c.get('line', '?')}`: {c['body']}"
                    fallback_payload = {
                        "body": fallback_body,
                        "event": event,
                    }
                    if commit_sha:
                        fallback_payload["commit_id"] = commit_sha
                    retry_resp = client.post(url, json=fallback_payload, headers=headers)
                    retry_resp.raise_for_status()
                    return retry_resp.json()
                raise

    def create_commit_status(
        self,
        owner: str,
        repo: str,
        sha: str,
        state: str,
        description: str,
        context: str = "nexarion/multi-agent-review",
        target_url: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        self._authorize_operation("create_commit_status", owner=owner, repo=repo)
        headers = self.get_auth_headers(token)
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/statuses/{sha}"
        payload: dict[str, Any] = {
            "state": state,
            "description": description[:140],
            "context": context,
        }
        if target_url:
            payload["target_url"] = target_url

        with httpx.Client(timeout=20.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    def create_check_run(
        self,
        owner: str,
        repo: str,
        head_sha: str,
        name: str = "NEXARION Multi-Agent Review",
        status: str = "completed",
        conclusion: str = "success",
        title: str | None = None,
        summary: str | None = None,
        text: str | None = None,
        annotations: list[dict[str, Any]] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        self._authorize_operation("create_check_run", owner=owner, repo=repo)
        headers = self.get_auth_headers(token)
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/check-runs"
        payload: dict[str, Any] = {
            "name": name,
            "head_sha": head_sha,
            "status": status,
        }
        if status == "completed":
            payload["conclusion"] = conclusion

        output: dict[str, Any] = {}
        if title:
            output["title"] = title
        if summary:
            output["summary"] = summary
        if text:
            output["text"] = text
        if annotations:
            output["annotations"] = annotations[:50]

        if output:
            payload["output"] = output

        with httpx.Client(timeout=25.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    # --- Repository Discovery, Exploration, Commits, Issues & Actions ---

    def search_repositories(
        self, query: str, *, include_public: bool = False, limit: int = 20
    ) -> list[dict[str, Any]]:
        self._authorize_operation("search_repositories")
        q = (query or "").strip()
        matches: list[dict[str, Any]] = []
        seen_full: set[str] = set()

        if self.token:
            try:
                user_repos = self.list_repositories(limit=100)
                q_lower = q.lower()
                for r in user_repos:
                    haystack = (
                        f"{r.get('full_name', '')} {r.get('name', '')} {r.get('description', '')}"
                    ).lower()
                    if not q_lower or q_lower in haystack:
                        matches.append(r)
                        seen_full.add(r.get("full_name", "").lower())
            except Exception as exc:
                logger.warning("Failed searching user repositories: %s", exc)

        if include_public and q and len(matches) < limit:
            cache_key = self._cache.build_key(
                self.cache_scope, "search_public_repos", extra={"q": q, "limit": limit}
            )
            pub_items = self._cache.get(cache_key)
            if pub_items is None:
                data = self._get_json(
                    f"{GITHUB_API_BASE}/search/repositories",
                    params={"q": q, "per_page": min(20, limit)},
                    context_msg=f"search repositories '{q}'",
                )
                pub_items = [self._normalize_repo(r) for r in data.get("items", [])]
                self._cache.set(cache_key, pub_items, ttl=120.0)

            for r in pub_items:
                fn = r.get("full_name", "").lower()
                if fn not in seen_full:
                    matches.append(r)
                    seen_full.add(fn)
                    if len(matches) >= limit:
                        break

        return matches[:limit]

    def get_repository_details(self, owner: str, repo: str) -> dict[str, Any]:
        self._authorize_operation("get_repository_details", owner=owner, repo=repo)
        repo_slug = f"{owner}/{repo}"
        cache_key = self._cache.build_key(self.cache_scope, "repo_details", repo=repo_slug)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        data = self._get_json(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}",
            context_msg=repo_slug,
        )
        result = {
            **self._normalize_repo(data),
            "topics": data.get("topics") or [],
            "open_issues_count": data.get("open_issues_count", 0),
            "forks_count": data.get("forks_count", 0),
            "size_kb": data.get("size", 0),
            "visibility": data.get("visibility", "private" if data.get("private") else "public"),
            "pushed_at": data.get("pushed_at"),
        }
        self._cache.set(cache_key, result, ttl=180.0)
        return result

    def get_repository_branches(
        self, owner: str, repo: str, *, limit: int = 30
    ) -> list[dict[str, Any]]:
        self._authorize_operation("get_repository_branches", owner=owner, repo=repo)
        repo_slug = f"{owner}/{repo}"
        cache_key = self._cache.build_key(
            self.cache_scope, "repo_branches", repo=repo_slug, extra={"limit": limit}
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        data = self._get_json(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/branches",
            params={"per_page": min(100, max(1, limit))},
            context_msg=f"{repo_slug} branches",
        )
        branches = [
            {
                "name": b.get("name", ""),
                "sha": (b.get("commit") or {}).get("sha", ""),
                "protected": bool(b.get("protected", False)),
            }
            for b in (data if isinstance(data, list) else [])
        ]
        self._cache.set(cache_key, branches, ttl=120.0)
        return branches

    def get_repository_tree(
        self,
        owner: str,
        repo: str,
        ref: str | None = None,
        *,
        recursive: bool = True,
        max_entries: int = 500,
    ) -> dict[str, Any]:
        self._authorize_operation("get_repository_tree", owner=owner, repo=repo)
        repo_slug = f"{owner}/{repo}"
        target_ref = ref
        if not target_ref:
            details = self.get_repository_details(owner, repo)
            target_ref = details.get("default_branch") or "main"

        cache_key = self._cache.build_key(
            self.cache_scope,
            "repo_tree",
            repo=repo_slug,
            ref=target_ref,
            extra={"recursive": recursive, "max": max_entries},
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        params = {"recursive": "1"} if recursive else None
        try:
            data = self._get_json(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{urllib.parse.quote(target_ref, safe='')}",
                params=params,
                context_msg=f"{repo_slug}@{target_ref} tree",
            )
        except GitHubNotFoundError:
            # Empty repository has no git tree yet
            return {
                "repository": repo_slug,
                "ref": target_ref,
                "sha": None,
                "truncated": False,
                "empty": True,
                "entries": [],
            }

        raw_tree = data.get("tree", []) if isinstance(data, dict) else []
        filtered: list[dict[str, Any]] = []
        for item in raw_tree:
            item_path = item.get("path", "")
            if is_ignored_repo_path(item_path) or is_sensitive_repo_path(item_path):
                continue
            filtered.append(
                {
                    "path": item_path,
                    "type": item.get("type", "blob"),  # "blob" or "tree"
                    "size": item.get("size", 0),
                    "sha": item.get("sha", ""),
                }
            )
            if len(filtered) >= max_entries:
                break

        result = {
            "repository": repo_slug,
            "ref": target_ref,
            "sha": data.get("sha"),
            "truncated": bool(data.get("truncated", False)) or len(raw_tree) > max_entries,
            "empty": len(raw_tree) == 0,
            "total_unfiltered": len(raw_tree),
            "entries": filtered,
        }
        self._cache.set(cache_key, result, ttl=300.0)
        return result

    def get_repository_contents(
        self, owner: str, repo: str, path: str = "", ref: str | None = None
    ) -> list[dict[str, Any]] | dict[str, Any]:
        self._authorize_operation("get_repository_contents", owner=owner, repo=repo)
        repo_slug = f"{owner}/{repo}"
        clean_path = path.strip("/")
        if clean_path and is_sensitive_repo_path(clean_path):
            raise GitHubAuthError(
                f"Access to sensitive file '{clean_path}' is blocked by security policy.",
                error_code="SENSITIVE_FILE_BLOCKED",
            )

        cache_key = self._cache.build_key(
            self.cache_scope,
            "repo_contents",
            repo=repo_slug,
            ref=ref or "HEAD",
            extra={"path": clean_path},
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        quoted_path = urllib.parse.quote(clean_path, safe="/")
        url = (
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{quoted_path}"
            if clean_path
            else f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents"
        )
        params = {"ref": ref} if ref else None
        data = self._get_json(url, params=params, context_msg=f"{repo_slug}/{clean_path}")

        if isinstance(data, list):
            result = [
                {
                    "name": item.get("name", ""),
                    "path": item.get("path", ""),
                    "type": item.get("type", "file"),
                    "size": item.get("size", 0),
                    "sha": item.get("sha", ""),
                    "html_url": item.get("html_url", ""),
                }
                for item in data
                if not is_sensitive_repo_path(item.get("path", ""))
            ]
        else:
            result = {
                "name": data.get("name", ""),
                "path": data.get("path", ""),
                "type": data.get("type", "file"),
                "size": data.get("size", 0),
                "sha": data.get("sha", ""),
                "html_url": data.get("html_url", ""),
            }
        self._cache.set(cache_key, result, ttl=240.0)
        return result

    def fetch_file(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str | None = None,
        *,
        max_bytes: int = MAX_FILE_BYTES,
    ) -> dict[str, Any]:
        self._authorize_operation("fetch_file", owner=owner, repo=repo)
        clean_path = (path or "").replace("\\", "/").strip().strip("/")
        if not clean_path or clean_path in (".", ".."):
            raise GitHubApiError(
                "Invalid file path: 'path' cannot be empty. Use get_repository_tree or get_repository_contents to browse directories.",
                status_code=400,
                error_code="INVALID_FILE_PATH",
            )
        if is_sensitive_repo_path(clean_path):
            return {
                "path": clean_path,
                "blocked": True,
                "reason": "Sensitive credential/environment file excluded by security policy.",
                "content": "",
            }
        if is_ignored_repo_path(clean_path):
            return {
                "path": clean_path,
                "blocked": True,
                "reason": "Binary or ignored build/vendor file excluded.",
                "content": "",
            }

        repo_slug = f"{owner}/{repo}"
        cache_key = self._cache.build_key(
            self.cache_scope,
            "fetch_file",
            repo=repo_slug,
            ref=ref or "default",
            extra={"path": clean_path, "max_bytes": max_bytes},
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        quoted_path = urllib.parse.quote(clean_path, safe="/")
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{quoted_path}"
        params = {"ref": ref} if ref else None
        data = self._get_json(url, params=params, context_msg=f"{repo_slug}:{clean_path}")

        if isinstance(data, list):
            return {
                "path": clean_path,
                "is_directory": True,
                "entries": [i.get("path", "") for i in data],
                "content": "",
            }

        file_size = int(data.get("size", 0))
        if file_size > max_bytes * 2:
            return {
                "path": clean_path,
                "sha": data.get("sha", ""),
                "size": file_size,
                "html_url": data.get("html_url", ""),
                "truncated": True,
                "content": "",
                "reason": f"File too large ({file_size} bytes > {max_bytes * 2} bytes limit).",
            }

        raw_content = data.get("content", "")
        encoding = data.get("encoding", "")
        decoded_text = ""
        if encoding == "base64" and raw_content:
            try:
                raw_bytes = base64.b64decode(raw_content)
                if b"\x00" in raw_bytes[:1024]:
                    return {
                        "path": clean_path,
                        "blocked": True,
                        "reason": "Binary file excluded.",
                        "content": "",
                    }
                decoded_text = raw_bytes.decode("utf-8", errors="replace")
            except Exception as exc:
                raise GitHubApiError(f"Failed decoding file {clean_path}: {exc}") from exc
        elif data.get("download_url"):
            headers = self.get_auth_headers()
            with httpx.Client(timeout=20.0) as client:
                dl_resp = client.get(data["download_url"], headers=headers)
                self._handle_http_error(dl_resp, context_msg=clean_path)
                if b"\x00" in dl_resp.content[:1024]:
                    return {
                        "path": clean_path,
                        "blocked": True,
                        "reason": "Binary file excluded.",
                        "content": "",
                    }
                decoded_text = dl_resp.text

        was_truncated = False
        if len(decoded_text) > max_bytes:
            decoded_text = decoded_text[:max_bytes]
            was_truncated = True

        result = {
            "path": clean_path,
            "sha": data.get("sha", ""),
            "size": file_size,
            "html_url": data.get("html_url", ""),
            "line_count": decoded_text.count("\n") + (1 if decoded_text else 0),
            "truncated": was_truncated,
            "content": decoded_text,
        }
        self._cache.set(cache_key, result, ttl=300.0)
        return result

    def search_repository_code(
        self, owner: str, repo: str, query: str, *, limit: int = 15
    ) -> list[dict[str, Any]]:
        self._authorize_operation("search_repository_code", owner=owner, repo=repo)
        clean_q = (query or "").strip()
        if not clean_q:
            return []
        repo_slug = f"{owner}/{repo}"
        cache_key = self._cache.build_key(
            self.cache_scope,
            "search_code",
            repo=repo_slug,
            extra={"q": clean_q, "limit": limit},
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        headers = self.get_auth_headers()
        headers["Accept"] = "application/vnd.github.text-match+json"
        try:
            data = self._get_json(
                f"{GITHUB_API_BASE}/search/code",
                headers=headers,
                params={"q": f"{clean_q} repo:{repo_slug}", "per_page": min(30, limit)},
                context_msg=f"code search in {repo_slug}",
            )
            items = data.get("items", []) if isinstance(data, dict) else []
            results = [
                {
                    "path": item.get("path", ""),
                    "name": item.get("name", ""),
                    "sha": item.get("sha", ""),
                    "html_url": item.get("html_url", ""),
                    "matches": [
                        m.get("fragment", "")
                        for m in item.get("text_matches", [])[:3]
                        if m.get("fragment")
                    ],
                }
                for item in items
                if not is_sensitive_repo_path(item.get("path", ""))
                and not is_ignored_repo_path(item.get("path", ""))
            ]
            self._cache.set(cache_key, results, ttl=120.0)
            return results
        except GitHubApiError as exc:
            # Fallback to path search in tree when GitHub Code Search API is unindexed or restricted
            logger.debug("GitHub code search API fallback to tree match (%s)", exc)
            tree = self.get_repository_tree(owner, repo)
            q_lower = clean_q.lower()
            fallback = [
                {
                    "path": entry["path"],
                    "name": entry["path"].split("/")[-1],
                    "sha": entry.get("sha", ""),
                    "html_url": f"https://github.com/{repo_slug}/blob/{tree.get('ref', 'main')}/{entry['path']}",
                    "matches": [],
                }
                for entry in tree.get("entries", [])
                if entry.get("type") == "blob" and q_lower in entry.get("path", "").lower()
            ][:limit]
            return fallback

    def get_commit_history(
        self, owner: str, repo: str, branch: str | None = None, *, limit: int = 15
    ) -> list[dict[str, Any]]:
        self._authorize_operation("get_commit_history", owner=owner, repo=repo)
        repo_slug = f"{owner}/{repo}"
        cache_key = self._cache.build_key(
            self.cache_scope,
            "commits",
            repo=repo_slug,
            ref=branch or "default",
            extra={"limit": limit},
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        params: dict[str, Any] = {"per_page": min(50, max(1, limit))}
        if branch:
            params["sha"] = branch
        data = self._get_json(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits",
            params=params,
            context_msg=f"{repo_slug} commits",
        )
        commits = [
            {
                "sha": c.get("sha", ""),
                "short_sha": (c.get("sha") or "")[:7],
                "message": ((c.get("commit") or {}).get("message") or "").strip(),
                "author": ((c.get("commit") or {}).get("author") or {}).get("name")
                or ((c.get("author") or {}).get("login") or "Unknown"),
                "date": ((c.get("commit") or {}).get("author") or {}).get("date"),
                "html_url": c.get("html_url", ""),
            }
            for c in (data if isinstance(data, list) else [])
        ]
        self._cache.set(cache_key, commits, ttl=90.0)
        return commits

    def get_commit_details(self, owner: str, repo: str, sha: str) -> dict[str, Any]:
        self._authorize_operation("get_commit_details", owner=owner, repo=repo)
        repo_slug = f"{owner}/{repo}"
        cache_key = self._cache.build_key(
            self.cache_scope, "commit_detail", repo=repo_slug, ref=sha
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        data = self._get_json(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{urllib.parse.quote(sha, safe='')}",
            context_msg=f"{repo_slug} commit {sha[:7]}",
        )
        files = [
            {
                "filename": f.get("filename", ""),
                "status": f.get("status", ""),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "patch": (f.get("patch") or "")[:4000]
                if not is_sensitive_repo_path(f.get("filename", ""))
                else "[REDACTED SENSITIVE FILE]",
            }
            for f in data.get("files", [])[:40]
        ]
        result = {
            "sha": data.get("sha", ""),
            "message": ((data.get("commit") or {}).get("message") or "").strip(),
            "author": ((data.get("commit") or {}).get("author") or {}).get("name", "Unknown"),
            "date": ((data.get("commit") or {}).get("author") or {}).get("date"),
            "html_url": data.get("html_url", ""),
            "stats": data.get("stats", {}),
            "files": files,
        }
        self._cache.set(cache_key, result, ttl=300.0)
        return result

    def compare_commits(self, owner: str, repo: str, base: str, head: str) -> dict[str, Any]:
        self._authorize_operation("compare_commits", owner=owner, repo=repo)
        repo_slug = f"{owner}/{repo}"
        spec = f"{urllib.parse.quote(base, safe='')}...{urllib.parse.quote(head, safe='')}"
        cache_key = self._cache.build_key(
            self.cache_scope, "compare_commits", repo=repo_slug, ref=spec
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        data = self._get_json(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/compare/{spec}",
            context_msg=f"{repo_slug} compare {base}..{head}",
        )
        result = {
            "status": data.get("status", ""),
            "ahead_by": data.get("ahead_by", 0),
            "behind_by": data.get("behind_by", 0),
            "total_commits": data.get("total_commits", 0),
            "html_url": data.get("html_url", ""),
            "commits": [
                {
                    "sha": (c.get("sha") or "")[:7],
                    "message": ((c.get("commit") or {}).get("message") or "").splitlines()[0],
                    "author": ((c.get("commit") or {}).get("author") or {}).get("name", "Unknown"),
                }
                for c in data.get("commits", [])[:25]
            ],
            "files": [
                {
                    "filename": f.get("filename", ""),
                    "status": f.get("status", ""),
                    "additions": f.get("additions", 0),
                    "deletions": f.get("deletions", 0),
                    "patch": (f.get("patch") or "")[:3500]
                    if not is_sensitive_repo_path(f.get("filename", ""))
                    else "[REDACTED SENSITIVE FILE]",
                }
                for f in data.get("files", [])[:35]
            ],
        }
        self._cache.set(cache_key, result, ttl=180.0)
        return result

    def get_pull_request_details(self, owner: str, repo: str, pull_number: int) -> dict[str, Any]:
        self._authorize_operation("get_pull_request_details", owner=owner, repo=repo)
        data = self._get_json(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}",
            context_msg=f"{owner}/{repo}#{pull_number}",
        )
        return {
            "number": data.get("number"),
            "title": data.get("title", ""),
            "state": "merged" if data.get("merged_at") else data.get("state", "open"),
            "author": (data.get("user") or {}).get("login", "Unknown"),
            "body": (data.get("body") or "")[:6000],
            "head_branch": (data.get("head") or {}).get("ref", ""),
            "head_sha": (data.get("head") or {}).get("sha", ""),
            "base_branch": (data.get("base") or {}).get("ref", ""),
            "additions": data.get("additions", 0),
            "deletions": data.get("deletions", 0),
            "changed_files": data.get("changed_files", 0),
            "html_url": data.get("html_url", ""),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }

    def get_pull_request_files(
        self, owner: str, repo: str, pull_number: int
    ) -> list[dict[str, Any]]:
        self._authorize_operation("get_pull_request_files", owner=owner, repo=repo)
        data = self._get_json(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}/files",
            params={"per_page": 50},
            context_msg=f"{owner}/{repo}#{pull_number} files",
        )
        return [
            {
                "filename": f.get("filename", ""),
                "status": f.get("status", ""),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "patch": (f.get("patch") or "")[:4000]
                if not is_sensitive_repo_path(f.get("filename", ""))
                else "[REDACTED SENSITIVE FILE]",
            }
            for f in (data if isinstance(data, list) else [])
        ]

    def get_pull_request_reviews(
        self, owner: str, repo: str, pull_number: int
    ) -> list[dict[str, Any]]:
        self._authorize_operation("get_pull_request_reviews", owner=owner, repo=repo)
        data = self._get_json(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}/reviews",
            context_msg=f"{owner}/{repo}#{pull_number} reviews",
        )
        return [
            {
                "id": r.get("id"),
                "author": (r.get("user") or {}).get("login", "Unknown"),
                "state": r.get("state", ""),
                "body": (r.get("body") or "")[:2000],
                "submitted_at": r.get("submitted_at"),
            }
            for r in (data if isinstance(data, list) else [])
        ]

    def get_pull_request_comments(
        self, owner: str, repo: str, pull_number: int
    ) -> list[dict[str, Any]]:
        self._authorize_operation("get_pull_request_comments", owner=owner, repo=repo)
        data = self._get_json(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}/comments",
            params={"per_page": 40},
            context_msg=f"{owner}/{repo}#{pull_number} comments",
        )
        return [
            {
                "id": c.get("id"),
                "author": (c.get("user") or {}).get("login", "Unknown"),
                "path": c.get("path", ""),
                "line": c.get("line") or c.get("original_line"),
                "body": (c.get("body") or "")[:1500],
                "created_at": c.get("created_at"),
            }
            for c in (data if isinstance(data, list) else [])
        ]

    def get_repository_issues(
        self, owner: str, repo: str, *, state: str = "open", limit: int = 20
    ) -> list[dict[str, Any]]:
        self._authorize_operation("get_repository_issues", owner=owner, repo=repo)
        data = self._get_json(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues",
            params={"state": state, "per_page": min(50, max(1, limit))},
            context_msg=f"{owner}/{repo} issues",
        )
        issues: list[dict[str, Any]] = []
        for item in data if isinstance(data, list) else []:
            if "pull_request" in item:
                continue  # GitHub /issues returns PRs too; filter to true issues
            issues.append(
                {
                    "number": item.get("number"),
                    "title": item.get("title", ""),
                    "state": item.get("state", "open"),
                    "author": (item.get("user") or {}).get("login", "Unknown"),
                    "labels": [lb.get("name", "") for lb in item.get("labels", [])],
                    "comments": item.get("comments", 0),
                    "html_url": item.get("html_url", ""),
                    "created_at": item.get("created_at"),
                    "body": (item.get("body") or "")[:1000],
                }
            )
            if len(issues) >= limit:
                break
        return issues

    def search_issues(
        self, owner: str, repo: str, query: str, *, limit: int = 15
    ) -> list[dict[str, Any]]:
        self._authorize_operation("search_issues", owner=owner, repo=repo)
        clean_q = (query or "").strip()
        if not clean_q:
            return self.get_repository_issues(owner, repo, limit=limit)
        data = self._get_json(
            f"{GITHUB_API_BASE}/search/issues",
            params={"q": f"{clean_q} repo:{owner}/{repo} is:issue", "per_page": min(30, limit)},
            context_msg=f"{owner}/{repo} search issues",
        )
        return [
            {
                "number": item.get("number"),
                "title": item.get("title", ""),
                "state": item.get("state", "open"),
                "author": (item.get("user") or {}).get("login", "Unknown"),
                "html_url": item.get("html_url", ""),
                "created_at": item.get("created_at"),
            }
            for item in (data.get("items", []) if isinstance(data, dict) else [])
        ]

    def get_issue_details(self, owner: str, repo: str, issue_number: int) -> dict[str, Any]:
        self._authorize_operation("get_issue_details", owner=owner, repo=repo)
        issue = self._get_json(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}",
            context_msg=f"{owner}/{repo} issue #{issue_number}",
        )
        comments = self._get_json(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/comments",
            params={"per_page": 25},
            context_msg=f"{owner}/{repo} issue #{issue_number} comments",
        )
        return {
            "number": issue.get("number"),
            "title": issue.get("title", ""),
            "state": issue.get("state", "open"),
            "author": (issue.get("user") or {}).get("login", "Unknown"),
            "labels": [lb.get("name", "") for lb in issue.get("labels", [])],
            "body": (issue.get("body") or "")[:5000],
            "html_url": issue.get("html_url", ""),
            "comments": [
                {
                    "author": (c.get("user") or {}).get("login", "Unknown"),
                    "body": (c.get("body") or "")[:1500],
                    "created_at": c.get("created_at"),
                }
                for c in (comments if isinstance(comments, list) else [])
            ],
        }

    def get_workflow_runs(self, owner: str, repo: str, *, limit: int = 10) -> list[dict[str, Any]]:
        self._authorize_operation("get_workflow_runs", owner=owner, repo=repo)
        data = self._get_json(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/actions/runs",
            params={"per_page": min(30, max(1, limit))},
            context_msg=f"{owner}/{repo} workflow runs",
        )
        runs = data.get("workflow_runs", []) if isinstance(data, dict) else []
        return [
            {
                "id": r.get("id"),
                "name": r.get("name", ""),
                "status": r.get("status", ""),
                "conclusion": r.get("conclusion"),
                "head_branch": r.get("head_branch", ""),
                "head_sha": (r.get("head_sha") or "")[:7],
                "event": r.get("event", ""),
                "html_url": r.get("html_url", ""),
                "created_at": r.get("created_at"),
            }
            for r in runs[:limit]
        ]

    def get_check_runs(self, owner: str, repo: str, ref: str) -> list[dict[str, Any]]:
        self._authorize_operation("get_check_runs", owner=owner, repo=repo)
        data = self._get_json(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{urllib.parse.quote(ref, safe='')}/check-runs",
            params={"per_page": 30},
            context_msg=f"{owner}/{repo}@{ref} check-runs",
        )
        runs = data.get("check_runs", []) if isinstance(data, dict) else []
        return [
            {
                "id": r.get("id"),
                "name": r.get("name", ""),
                "status": r.get("status", ""),
                "conclusion": r.get("conclusion"),
                "html_url": r.get("html_url", ""),
                "output_title": (r.get("output") or {}).get("title"),
            }
            for r in runs
        ]
