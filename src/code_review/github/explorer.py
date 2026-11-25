from __future__ import annotations

import concurrent.futures
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

from code_review.agents.ast_agent import ASTAgent
from code_review.agents.bandit_agent import BanditAgent
from code_review.agents.base import BaseAgent
from code_review.agents.ruff_agent import RuffAgent
from code_review.agents.semantic_agent import SemanticAgent
from code_review.github.service import GitHubApiError, GitHubService, is_sensitive_repo_path
from code_review.models.enums import AgentType, Category, Severity
from code_review.models.finding import Finding
from code_review.orchestrator import ReviewOrchestrator
from code_review.parsers.diff_parser import DiffFile, DiffHunk, DiffLine, LineType

logger = logging.getLogger(__name__)

MANIFEST_FILENAMES = (
    "README.md",
    "readme.md",
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "frontend/package.json",
    "Dockerfile",
    "docker-compose.yml",
    "compose.yaml",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
)

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "auth": (
        "auth",
        "jwt",
        "token",
        "login",
        "session",
        "oauth",
        "security",
        "crypto",
        "password",
    ),
    "database": (
        "db",
        "database",
        "model",
        "schema",
        "migration",
        "alembic",
        "sql",
        "postgres",
        "mongo",
    ),
    "frontend": ("App.tsx", "Sidebar", "Workspace", "components/", "pages/", "api.ts", "routes"),
    "backend": ("app.py", "main.py", "server", "routes/", "router", "controller", "api/"),
    "security": ("auth", "crypto", "github", "webhook", "security", "sanitize", "config"),
    "ci": (".github/workflows", "Dockerfile", "docker-compose", "render.yaml", "Makefile"),
}


def detect_tech_stack(
    tree_entries: list[dict[str, Any]],
    manifests: dict[str, str],
) -> list[str]:
    """Detect real repository stack strictly from tree extensions and manifest contents."""
    detected: list[str] = []
    seen: set[str] = set()

    def add_tech(name: str) -> None:
        if name not in seen:
            seen.add(name)
            detected.append(name)

    paths = [e.get("path", "") for e in tree_entries if e.get("type") == "blob"]
    exts = {Path(p).suffix.lower() for p in paths}
    lower_paths = {p.lower() for p in paths}

    if ".py" in exts or "pyproject.toml" in lower_paths or "requirements.txt" in lower_paths:
        add_tech("Python")
    if ".ts" in exts or ".tsx" in exts:
        add_tech("TypeScript")
    if ".js" in exts or ".jsx" in exts:
        add_tech("JavaScript")
    if ".go" in exts or "go.mod" in lower_paths:
        add_tech("Go")
    if ".rs" in exts or "cargo.toml" in lower_paths:
        add_tech("Rust")
    if ".java" in exts or "pom.xml" in lower_paths or "build.gradle" in lower_paths:
        add_tech("Java")
    if (
        "dockerfile" in lower_paths
        or "docker-compose.yml" in lower_paths
        or "compose.yaml" in lower_paths
    ):
        add_tech("Docker")

    py_manifest = (
        manifests.get("pyproject.toml", "") + "\n" + manifests.get("requirements.txt", "")
    ).lower()
    if "fastapi" in py_manifest:
        add_tech("FastAPI")
    if "flask" in py_manifest:
        add_tech("Flask")
    if "django" in py_manifest:
        add_tech("Django")
    if "sqlalchemy" in py_manifest:
        add_tech("SQLAlchemy")
    if "psycopg" in py_manifest or "postgresql" in py_manifest:
        add_tech("PostgreSQL")
    if "pymongo" in py_manifest or "motor" in py_manifest:
        add_tech("MongoDB")
    if "redis" in py_manifest:
        add_tech("Redis")

    pkg_text = "\n".join(
        val for path, val in manifests.items() if path.lower().endswith("package.json")
    ).lower()
    if '"react"' in pkg_text:
        add_tech("React")
    if '"next"' in pkg_text:
        add_tech("Next.js")
    if '"express"' in pkg_text:
        add_tech("Express")
    if '"vite"' in pkg_text:
        add_tech("Vite")
    if '"tailwindcss"' in pkg_text:
        add_tech("Tailwind CSS")
    if '"mongoose"' in pkg_text or '"mongodb"' in pkg_text:
        add_tech("MongoDB")
    if pkg_text.strip() and "Node.js" not in seen:
        add_tech("Node.js")

    compose_text = (
        manifests.get("docker-compose.yml", "") + "\n" + manifests.get("compose.yaml", "")
    ).lower()
    if "postgres" in compose_text:
        add_tech("PostgreSQL")
    if "redis" in compose_text:
        add_tech("Redis")
    if "mongo" in compose_text:
        add_tech("MongoDB")

    return detected


_WEB_SECURITY_RULES: list[tuple[str, Severity, re.Pattern[str], str, str]] = [
    (
        "SEC-JS001",
        Severity.ERROR,
        re.compile(r"dangerouslySetInnerHTML"),
        "Use of React 'dangerouslySetInnerHTML' can lead to Cross-Site Scripting (XSS).",
        "Sanitize HTML with DOMPurify before rendering or render structured JSX elements instead.",
    ),
    (
        "SEC-JS002",
        Severity.ERROR,
        re.compile(r"\.(?:innerHTML|outerHTML)\s*=|document\.write\s*\("),
        "Direct DOM HTML injection sink detected (innerHTML/outerHTML/document.write).",
        "Use textContent/innerText or a safe sanitizer such as DOMPurify.",
    ),
    (
        "SEC-JS003",
        Severity.CRITICAL,
        re.compile(r"\b(?:eval|new\s+Function)\s*\("),
        "Dynamic code execution via eval() or new Function() creates severe code injection risk.",
        "Remove eval()/new Function() and use safe JSON parsing or explicit dispatch logic.",
    ),
    (
        "SEC-JS004",
        Severity.ERROR,
        re.compile(r"(?:child_process|execSync?\s*\(|shell\s*:\s*true)"),
        "Shell/command execution primitive detected; unvalidated inputs can enable command injection.",
        "Avoid shell execution or validate arguments strictly using execFile/spawn without shell=true.",
    ),
    (
        "SEC-JS005",
        Severity.CRITICAL,
        re.compile(
            r"(?:jwt\.sign\([^,]+,\s*['\"][^'\"]{4,}['\"]"
            r"|process\.env\.[A-Z0-9_]+(?:SECRET|KEY|PASSWORD|TOKEN)[A-Z0-9_]*\s*\|\|\s*['\"][^'\"]{3,}['\"]"
            r"|(?:JWT_SECRET|API_KEY|SECRET_KEY|DB_PASSWORD)\s*[:=]\s*['\"][^'\"]{6,}['\"])",
            re.IGNORECASE,
        ),
        "Hardcoded secret, credential, or hardcoded fallback secret detected in source code.",
        "Require secrets exclusively from environment variables/secret manager and fail fast if unset.",
    ),
    (
        "SEC-JS006",
        Severity.WARNING,
        re.compile(
            r"origin\s*:\s*(?:['\"]\*['\"]|true)|Access-Control-Allow-Origin['\"]?\s*[:=,]\s*['\"]\*['\"]"
        ),
        "Overly permissive CORS origin configuration detected ('*' or origin: true).",
        "Restrict CORS allowed origins to an explicit allowlist of trusted frontend domains.",
    ),
    (
        "SEC-JS007",
        Severity.WARNING,
        re.compile(r"(?:httpOnly\s*:\s*false|secure\s*:\s*false)"),
        "Session/auth cookie security flag explicitly disabled (httpOnly: false or secure: false).",
        "Set httpOnly: true, sameSite: 'lax'/'strict', and secure: true in production.",
    ),
    (
        "SEC-JS008",
        Severity.ERROR,
        re.compile(
            r"\.(?:find|findOne|findOneAndUpdate|findOneAndDelete|updateOne|deleteOne)\(\s*req\.(?:body|query|params)\b"
        ),
        "Unvalidated Express request object passed directly into database query (NoSQL injection risk).",
        "Whitelist and validate query fields explicitly (e.g. Zod/Joi) before passing to Mongoose/MongoDB.",
    ),
    (
        "SEC-JS009",
        Severity.ERROR,
        re.compile(r"res\.redirect\(\s*req\.(?:query|body|params)\b"),
        "Unvalidated user-controlled input passed to res.redirect() (Open Redirect risk).",
        "Validate redirect targets against an allowlist of safe relative paths or trusted hosts.",
    ),
    (
        "SEC-JS010",
        Severity.INFO,
        re.compile(r"target\s*=\s*['\"]_blank['\"](?![^\n>]*noopener)"),
        "External link uses target='_blank' without rel='noopener noreferrer'.",
        "Add rel='noopener noreferrer' alongside target='_blank' to mitigate reverse tabnabbing.",
    ),
    (
        "SEC-JS011",
        Severity.WARNING,
        re.compile(
            r"['\"]http://(?!(?:localhost|127\.0\.0\.1|0\.0\.0\.0|www\.w3\.org|schemas\.))[^'\"\s]+['\"]"
        ),
        "Cleartext http:// URL detected in source code.",
        "Use HTTPS endpoints to prevent man-in-the-middle interception.",
    ),
]


def scan_web_and_node_security(files_map: dict[str, str]) -> list[Finding]:
    """Deterministic multi-language static security scan for JS/TS/React/Node/HTML/manifests."""
    findings: list[Finding] = []
    web_exts = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".html"}

    for rel_path, content in files_map.items():
        if not content:
            continue
        suffix = Path(rel_path).suffix.lower()
        basename = Path(rel_path).name.lower()
        lines = content.splitlines()

        if suffix in web_exts:
            for line_no, line in enumerate(lines, start=1):
                stripped = line.strip()
                if not stripped or stripped.startswith(("//", "/*", "*")):
                    continue
                for rule_id, severity, pattern, message, suggestion in _WEB_SECURITY_RULES:
                    if pattern.search(line):
                        findings.append(
                            Finding(
                                file=rel_path,
                                line=line_no,
                                severity=severity,
                                category=Category.SECURITY,
                                agent=AgentType.BANDIT,
                                message=message,
                                suggestion=suggestion,
                                rule_id=rule_id,
                            )
                        )

            # Express entrypoints missing helmet security headers
            if "express()" in content and "helmet" not in content.lower():
                exp_line = next(
                    (idx for idx, ln in enumerate(lines, start=1) if "express()" in ln),
                    1,
                )
                findings.append(
                    Finding(
                        file=rel_path,
                        line=exp_line,
                        severity=Severity.WARNING,
                        category=Category.SECURITY,
                        agent=AgentType.BANDIT,
                        message="Express server initialized without 'helmet' security headers middleware.",
                        suggestion="Install and enable app.use(helmet()) to set CSP, HSTS, X-Frame-Options, and other security headers.",
                        rule_id="SEC-EXP001",
                    )
                )

            if (
                "express()" in content
                and "ratelimit" not in content.lower()
                and "rate-limit" not in content.lower()
            ):
                exp_line = next(
                    (idx for idx, ln in enumerate(lines, start=1) if "express()" in ln),
                    1,
                )
                findings.append(
                    Finding(
                        file=rel_path,
                        line=exp_line,
                        severity=Severity.WARNING,
                        category=Category.SECURITY,
                        agent=AgentType.BANDIT,
                        message="Express application lacks rate-limiting middleware (e.g. express-rate-limit) for brute-force/DoS protection.",
                        suggestion="Apply rate limiting (especially on /auth, /login, and mutation routes) with express-rate-limit.",
                        rule_id="SEC-EXP002",
                    )
                )

        if basename == "package.json":
            for line_no, line in enumerate(lines, start=1):
                if '"emailjs-com"' in line:
                    findings.append(
                        Finding(
                            file=rel_path,
                            line=line_no,
                            severity=Severity.WARNING,
                            category=Category.SECURITY,
                            agent=AgentType.BANDIT,
                            message="Deprecated package 'emailjs-com' listed in dependencies (superseded by '@emailjs/browser').",
                            suggestion="Remove 'emailjs-com' and use only maintained '@emailjs/browser'.",
                            rule_id="SEC-PKG001",
                        )
                    )

    return findings


def build_synthetic_diff_files(files_map: dict[str, str]) -> list[DiffFile]:
    """Convert raw fetched repository files into DiffFile models for existing agents."""
    diff_files: list[DiffFile] = []
    for rel_path, content in files_map.items():
        if not content or not content.strip():
            continue
        raw_lines = content.splitlines()
        diff_lines = tuple(
            DiffLine(
                line_type=LineType.ADDED,
                content=line,
                source_line=None,
                target_line=idx,
            )
            for idx, line in enumerate(raw_lines, start=1)
        )
        hunk = DiffHunk(
            source_start=0,
            source_length=0,
            target_start=1,
            target_length=len(diff_lines),
            lines=diff_lines,
        )
        diff_files.append(
            DiffFile(
                source_file="/dev/null",
                target_file=f"b/{rel_path.lstrip('/')}",
                hunks=(hunk,),
            )
        )
    return diff_files


class RepositoryExplorer:
    """Bounded, secure repository overview, tech-stack detection, and agent bridge."""

    def __init__(self, service: GitHubService) -> None:
        self.service = service

    def explore_overview(
        self,
        owner: str,
        repo: str,
        *,
        ref: str | None = None,
    ) -> dict[str, Any]:
        details = self.service.get_repository_details(owner, repo)
        branch = ref or details.get("default_branch") or "main"
        commits = []
        try:
            commits = self.service.get_commit_history(owner, repo, branch=branch, limit=5)
        except GitHubApiError:
            commits = []
        head_sha = commits[0]["sha"] if commits else None

        tree = self.service.get_repository_tree(owner, repo, ref=branch, max_entries=350)
        entries = tree.get("entries", [])
        blob_paths = [e["path"] for e in entries if e.get("type") == "blob"]

        # Identify manifests in root and common subpackages (monorepos / client+server)
        manifest_basenames = {
            "readme.md",
            "pyproject.toml",
            "requirements.txt",
            "package.json",
            "dockerfile",
            "docker-compose.yml",
            "compose.yaml",
            "go.mod",
            "cargo.toml",
            "pom.xml",
            "build.gradle",
        }
        target_manifests = [p for p in MANIFEST_FILENAMES if p in blob_paths]
        for p in blob_paths:
            if p in target_manifests:
                continue
            if p.count("/") <= 1 and Path(p).name.lower() in manifest_basenames:
                target_manifests.append(p)
        if not any(p.lower() == "readme.md" for p in target_manifests):
            for p in blob_paths:
                if "/" not in p and p.lower().startswith("readme"):
                    target_manifests.append(p)
                    break

        manifests: dict[str, str] = {}
        if target_manifests:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                future_map = {
                    pool.submit(
                        self.service.fetch_file, owner, repo, path, branch, max_bytes=25_000
                    ): path
                    for path in target_manifests[:8]
                }
                for fut in concurrent.futures.as_completed(future_map):
                    path = future_map[fut]
                    try:
                        file_res = fut.result()
                        if not file_res.get("blocked") and file_res.get("content"):
                            manifests[path] = file_res["content"][:12_000]
                    except Exception as exc:
                        logger.debug("Skipping manifest %s: %s", path, exc)

        stack = detect_tech_stack(entries, manifests)

        # Top-level directories and entry-point candidates
        top_dirs = sorted({p.split("/")[0] for p in blob_paths if "/" in p})
        root_files = sorted([p for p in blob_paths if "/" not in p])
        entry_candidates = [
            p
            for p in blob_paths
            if Path(p).name
            in (
                "app.py",
                "main.py",
                "server.py",
                "server.ts",
                "server.js",
                "app.ts",
                "app.js",
                "index.ts",
                "index.tsx",
                "App.tsx",
                "App.jsx",
                "main.tsx",
                "main.jsx",
                "main.go",
                "main.rs",
            )
        ][:15]

        return {
            "repository": details.get("full_name") or f"{owner}/{repo}",
            "html_url": details.get("html_url"),
            "visibility": details.get("visibility"),
            "description": details.get("description"),
            "branch": branch,
            "head_sha": head_sha,
            "empty": tree.get("empty", False),
            "tech_stack": stack,
            "top_directories": top_dirs[:30],
            "root_files": root_files[:40],
            "entry_points": entry_candidates,
            "total_indexed_files": len(blob_paths),
            "tree_truncated": tree.get("truncated", False),
            "recent_commits": commits[:5],
            "manifests": {k: v[:4000] for k, v in manifests.items()},
        }

    def fetch_files_concurrently(
        self,
        owner: str,
        repo: str,
        paths: list[str],
        *,
        ref: str | None = None,
        max_files: int = 8,
        max_bytes_per_file: int = 40_000,
    ) -> dict[str, dict[str, Any]]:
        clean_paths = [
            p.replace("\\", "/").strip("/") for p in paths if p and not is_sensitive_repo_path(p)
        ][:max_files]

        results: dict[str, dict[str, Any]] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            future_map = {
                pool.submit(
                    self.service.fetch_file,
                    owner,
                    repo,
                    p,
                    ref,
                    max_bytes=max_bytes_per_file,
                ): p
                for p in clean_paths
            }
            for fut in concurrent.futures.as_completed(future_map):
                p = future_map[fut]
                try:
                    results[p] = fut.result()
                except Exception as exc:
                    results[p] = {"path": p, "error": str(exc), "content": ""}
        return results

    def run_agents_on_files(
        self,
        owner: str,
        repo: str,
        paths: list[str],
        *,
        ref: str | None = None,
        agent_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Fetch target source files safely into an isolated temporary workspace and run
        existing ReviewOrchestrator static/semantic agents against them.
        """
        fetched = self.fetch_files_concurrently(
            owner, repo, paths, ref=ref, max_files=12, max_bytes_per_file=80_000
        )
        source_map = {
            p: info["content"]
            for p, info in fetched.items()
            if info.get("content") and not info.get("blocked")
        }
        if not source_map:
            return {
                "repository": f"{owner}/{repo}",
                "ref": ref or "default",
                "files_analyzed": [],
                "total_findings": 0,
                "findings": [],
                "note": "No analyzable text files were retrieved from the requested paths.",
            }

        requested = {
            a.lower().strip()
            for a in (agent_ids or ["security", "quality", "performance", "semantic"])
        }

        with tempfile.TemporaryDirectory(prefix="nexarion_repo_scan_") as tmp_dir:
            root_path = Path(tmp_dir).resolve()
            safe_sources: dict[str, str] = {}
            for rel_path, content in source_map.items():
                dest = (root_path / rel_path).resolve()
                # Strict path traversal guard
                if root_path not in dest.parents and dest != root_path:
                    logger.warning("Skipping unsafe repo path outside workspace: %s", rel_path)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
                safe_sources[rel_path] = content

            agents: list[BaseAgent] = []
            if requested & {"security", "bandit"}:
                agents.append(BanditAgent(repo_root=root_path))
            if requested & {"quality", "ruff"}:
                agents.append(RuffAgent(repo_root=root_path))
            if requested & {"performance", "ast"}:
                agents.append(ASTAgent(repo_root=root_path))
            if requested & {"semantic", "cross_file"}:
                agents.append(SemanticAgent(repo_root=root_path))

            if not agents:
                agents = [
                    BanditAgent(repo_root=root_path),
                    RuffAgent(repo_root=root_path),
                    ASTAgent(repo_root=root_path),
                ]

            diff_files = build_synthetic_diff_files(safe_sources)
            orchestrator = ReviewOrchestrator(
                agents=agents,
                parallel=True,
                deduplicate=True,
                use_cache=False,
            )
            review_res = orchestrator.review_files(diff_files)

            combined_findings = list(review_res.findings)
            if requested & {"security", "bandit"}:
                combined_findings.extend(scan_web_and_node_security(safe_sources))

            # Deduplicate combined findings by (file, line, rule_id)
            dedup_map: dict[tuple[str, int, str | None], Finding] = {}
            for f in combined_findings:
                key = (f.file, f.line, f.rule_id or f.message)
                if key not in dedup_map:
                    dedup_map[key] = f
            final_findings = list(dedup_map.values())

            file_lines_cache = {p: txt.splitlines() for p, txt in safe_sources.items()}
            target_ref = ref or "HEAD"
            findings_out: list[dict[str, Any]] = []
            for f in final_findings[:50]:
                src_lines = file_lines_cache.get(f.file, [])
                evidence = (
                    src_lines[f.line - 1].strip()[:240] if 1 <= f.line <= len(src_lines) else ""
                )
                findings_out.append(
                    {
                        "agent": f.agent.value,
                        "severity": f.severity.value.upper(),
                        "category": f.category.value.upper(),
                        "file": f.file,
                        "line": f.line,
                        "rule_id": f.rule_id,
                        "message": f.message,
                        "evidence": evidence,
                        "suggestion": f.suggestion,
                        "github_url": f"https://github.com/{owner}/{repo}/blob/{target_ref}/{f.file}#L{f.line}",
                    }
                )
            has_crit = any(
                f.severity in (Severity.CRITICAL, Severity.ERROR) for f in final_findings
            )
            agents_ran = [a.name for a in agents]
            if requested & {"security", "bandit"} and any(
                Path(p).suffix.lower() in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".html"}
                or Path(p).name.lower() == "package.json"
                for p in safe_sources
            ):
                agents_ran.append("WebSecurityScanner")
            return {
                "repository": f"{owner}/{repo}",
                "ref": target_ref,
                "agents_executed": agents_ran,
                "files_analyzed": list(safe_sources.keys()),
                "total_findings": len(final_findings),
                "has_critical": has_crit,
                "review_time_ms": review_res.review_time_ms,
                "findings": findings_out,
                "truncated": len(final_findings) > 50,
            }
