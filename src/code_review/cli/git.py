from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class GitError(RuntimeError):
        pass


def is_git_available() -> bool:
    return shutil.which("git") is not None


def is_git_repo(repo_path: Path | str | None = None) -> bool:
    if not is_git_available():
        return False

    cwd = Path(repo_path) if repo_path else Path.cwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (subprocess.SubprocessError, OSError) as exc:
        logger.debug("Error checking git repo status: %s", exc)
        return False


def get_git_diff(
    *,
    staged: bool = False,
    branch: str | None = None,
    repo_path: Path | str | None = None,
    timeout: int = 30,
) -> str:
    if not is_git_available():
        raise GitError("Git executable not found in system PATH.")

    cwd = Path(repo_path) if repo_path else Path.cwd()
    if not is_git_repo(cwd):
        raise GitError(f"Directory '{cwd}' is not inside a git repository.")

    cmd: list[str] = ["git", "diff"]

    if branch:
        cmd.extend([f"{branch}...HEAD"])
    elif staged:
        cmd.append("--cached")

    logger.debug("Executing git diff command: %s in %s", " ".join(cmd), cwd)
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"Git diff command timed out after {timeout}s: {' '.join(cmd)}") from exc
    except OSError as exc:
        raise GitError(f"Failed to execute git process: {exc}") from exc

    if result.returncode != 0:
        if branch:
            fallback_cmd = ["git", "diff", branch]
            logger.debug("Retrying with fallback command: %s", " ".join(fallback_cmd))
            try:
                fallback_res = subprocess.run(
                    fallback_cmd,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    check=False,
                )
                if fallback_res.returncode == 0:
                    return fallback_res.stdout
            except Exception:
                pass

        err_msg = result.stderr.strip() or f"Process exited with code {result.returncode}"
        raise GitError(f"Git diff failed: {err_msg}")
    return result.stdout
