from __future__ import annotations

import hashlib
import hmac
import logging
import urllib.parse
from typing import Any

import httpx

from code_review.config import get_settings
from code_review.parsers.diff_parser import parse_diff

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
MAX_DIFF_BYTES = 500 * 1024


class GitHubService:
    def __init__(self, token: str | None = None) -> None:
        self.settings = get_settings()
        self.token = token or self.settings.github_token or None

    def get_auth_headers(self, custom_token: str | None = None) -> dict[str, str]:
        active_token = custom_token or self.token
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "NEXARION-Code-Review/1.0",
        }
        if active_token:
            headers["Authorization"] = f"Bearer {active_token}"
        return headers

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
        headers = self.get_auth_headers(token)
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(f"{GITHUB_API_BASE}/user", headers=headers)
            resp.raise_for_status()
            return resp.json()

    def list_repositories(self, token: str | None = None) -> list[dict[str, Any]]:
        headers = self.get_auth_headers(token)
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                f"{GITHUB_API_BASE}/user/repos?sort=updated&per_page=50",
                headers=headers,
            )
            resp.raise_for_status()
            repos = resp.json()
            return [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "full_name": r["full_name"],
                    "owner": r["owner"]["login"],
                    "private": r["private"],
                    "html_url": r["html_url"],
                    "default_branch": r.get("default_branch", "main"),
                    "description": r.get("description") or "",
                    "updated_at": r.get("updated_at"),
                }
                for r in repos
            ]

    def list_pull_requests(
        self, owner: str, repo: str, token: str | None = None
    ) -> list[dict[str, Any]]:
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
