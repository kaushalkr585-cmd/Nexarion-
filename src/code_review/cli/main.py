from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TextIO

from rich.console import Console

from code_review import __version__
from code_review.agents.ast_agent import ASTAgent
from code_review.agents.bandit_agent import BanditAgent
from code_review.agents.base import BaseAgent
from code_review.agents.llm_agent import LLMAgent
from code_review.agents.ruff_agent import RuffAgent
from code_review.agents.semantic_agent import SemanticAgent
from code_review.cache import DiskCache
from code_review.cli.formatter import render_json, render_markdown, render_table
from code_review.cli.git import GitError, get_git_diff, is_git_repo
from code_review.models.enums import Severity, severity_rank
from code_review.orchestrator import ReviewOrchestrator, default_agents

logger = logging.getLogger("code_review.cli")

AGENT_MAP: dict[str, type[BaseAgent]] = {
    "ast": ASTAgent,
    "ruff": RuffAgent,
    "bandit": BanditAgent,
    "llm": LLMAgent,
    "semantic": SemanticAgent,
    "cross_file": SemanticAgent,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="code-review",
        description="Multi-Agent AI Code Review System — Specialist reviewers for Git diffs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  code-review                             # Review uncommitted git changes\n"
            "  code-review --staged                    # Review staged git changes\n"
            "  code-review --branch main               # Review diff against main branch\n"
            "  git diff | code-review                  # Review diff piped from stdin\n"
            "  code-review changes.diff                # Review a saved diff file\n"
            "  code-review --fail-on error             # Exit code 1 if ERROR or CRITICAL found\n"
            "  code-review --format json -o out.json   # Export JSON report to file\n"
            "  code-review --llm                       # Include local LLM reviewer\n"
        ),
    )

    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Path to unified diff file, or '-' for stdin. Omit to review git working tree.",
    )

    git_group = parser.add_argument_group("Git Options")
    git_group.add_argument(
        "--staged",
        "--cached",
        action="store_true",
        dest="staged",
        help="Review staged git changes (git diff --cached).",
    )
    git_group.add_argument(
        "--branch",
        type=str,
        default=None,
        metavar="BRANCH",
        help="Review git diff against specified branch (e.g. 'main', 'master').",
    )

    agent_group = parser.add_argument_group("Review & Agent Options")
    agent_group.add_argument(
        "--semantic",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable or disable the semantic cross-file agent (default: False).",
    )
    agent_group.add_argument(
        "--llm",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable or disable the local LLM agent (default: False).",
    )
    agent_group.add_argument(
        "--agents",
        type=str,
        default=None,
        metavar="AGENTS",
        help=(
            "Comma-separated agents to run: ast, ruff, bandit, semantic, llm "
            "(default: all deterministic)."
        ),
    )
    agent_group.add_argument(
        "--min-severity",
        type=str,
        choices=["info", "warning", "error", "critical"],
        default=None,
        help="Filter findings by minimum severity threshold.",
    )
    agent_group.add_argument(
        "--fail-on",
        type=str,
        choices=["info", "warning", "error", "critical"],
        default=None,
        help="Exit with code 1 if any finding reaches or exceeds this severity.",
    )
    agent_group.add_argument(
        "--parallel",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Execute review agents concurrently in parallel (default: True).",
    )

    cache_group = parser.add_argument_group("Caching & Performance Options")
    cache_group.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass review result cache and force re-evaluation.",
    )
    cache_group.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".cache/code_review"),
        metavar="DIR",
        help="Directory to store persistent review cache (default: .cache/code_review).",
    )
    cache_group.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear all cached review results from cache directory and exit.",
    )
    cache_group.add_argument(
        "--semantic-cache",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use AST semantic hashing to ignore cosmetic changes (default: True).",
    )

    output_group = parser.add_argument_group("Output Options")
    output_group.add_argument(
        "-f",
        "--format",
        choices=["table", "json", "markdown"],
        default="table",
        help="Output display format (default: 'table').",
    )
    output_group.add_argument(
        "-o",
        "--output-file",
        type=Path,
        default=None,
        metavar="PATH",
        help="Save review results to the specified file path.",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging to stderr.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    return parser


def resolve_agents(
    agents_arg: str | None,
    include_llm: bool,
    include_semantic: bool = False,
) -> list[BaseAgent]:
    if agents_arg is None:
        return default_agents(include_semantic=include_semantic, include_llm=include_llm)

    selected_names = [name.strip().lower() for name in agents_arg.split(",") if name.strip()]
    if not selected_names:
        raise ValueError("No valid agents specified in --agents flag.")

    active_agents: list[BaseAgent] = []
    for name in selected_names:
        agent_cls = AGENT_MAP.get(name)
        if agent_cls is None:
            valid = ", ".join(AGENT_MAP.keys())
            raise ValueError(f"Unknown agent '{name}'. Available agents: {valid}")
        active_agents.append(agent_cls())

    return active_agents


def resolve_diff_input(
    target: str | None,
    *,
    staged: bool = False,
    branch: str | None = None,
    stdin: TextIO | None = None,
) -> str:
    in_stream = stdin or sys.stdin

    if target is not None:
        if target == "-":
            return in_stream.read()
        file_path = Path(target)
        if not file_path.exists():
            raise FileNotFoundError(f"Diff file not found: '{file_path}'")
        return file_path.read_text(encoding="utf-8", errors="replace")

    if branch or staged:
        return get_git_diff(staged=staged, branch=branch)

    if not in_stream.isatty():
        piped = in_stream.read()
        if piped.strip():
            return piped

    if is_git_repo():
        diff = get_git_diff(staged=False)

        if not diff.strip():
            staged_diff = get_git_diff(staged=True)
            if staged_diff.strip():
                return staged_diff
        return diff

    raise ValueError(
        "No diff input provided and current directory is not a git repository.\n"
        "Please provide a diff file, pipe a diff via stdin, or run inside a git repo.\n"
        "Use 'code-review --help' for options."
    )


def main(
    argv: list[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    stdin: TextIO | None = None,
) -> int:
    if stdout is None and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if stderr is None and hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args(argv)

    out_stream = stdout or sys.stdout
    err_stream = stderr or sys.stderr
    console = Console(file=out_stream, force_terminal=None)
    err_console = Console(file=err_stream, force_terminal=None)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=err_stream)
        logger.setLevel(logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING, stream=err_stream)

    if args.clear_cache:
        disk_cache = DiskCache(cache_dir=args.cache_dir)
        count = disk_cache.size()
        disk_cache.clear()
        console.print(
            f"[bold green]Cleared {count} cached review(s) from {args.cache_dir}.[/bold green]"
        )
        return 0

    try:
        agents = resolve_agents(
            args.agents,
            include_llm=args.llm,
            include_semantic=getattr(args, "semantic", False),
        )
    except ValueError as exc:
        err_console.print(f"[bold red]Configuration error:[/bold red] {exc}")
        return 2

    try:
        diff_text = resolve_diff_input(
            args.target,
            staged=args.staged,
            branch=args.branch,
            stdin=stdin,
        )
    except (FileNotFoundError, GitError, ValueError) as exc:
        err_console.print(f"[bold red]Input error:[/bold red] {exc}")
        return 2

    if not diff_text.strip():
        if args.format == "table":
            console.print("[dim]No diff changes detected to review.[/dim]")
        elif args.format == "json":
            out_stream.write('{"findings": [], "files_reviewed": 0, "review_time_ms": 0}\n')
            out_stream.flush()
        elif args.format == "markdown":
            out_stream.write("# Multi-Agent Code Review Report\n\nNo changes detected.\n")
            out_stream.flush()
        return 0

    min_sev = Severity(args.min_severity) if args.min_severity else None
    disk_cache = None if args.no_cache else DiskCache(cache_dir=args.cache_dir)
    orchestrator = ReviewOrchestrator(
        agents=agents,
        parallel=args.parallel,
        min_severity=min_sev,
        cache=disk_cache,
        use_cache=not args.no_cache,
        use_semantic_hash=getattr(args, "semantic_cache", True),
    )

    try:
        result = orchestrator.review_diff(diff_text)
    except Exception as exc:
        err_console.print(f"[bold red]Review error:[/bold red] {exc}")
        logger.exception("Review execution failed")
        return 2

    if args.format == "table":
        render_table(result, console=console)
        if args.output_file:
            args.output_file.write_text(render_markdown(result), encoding="utf-8")
    elif args.format == "json":
        json_output = render_json(result)
        out_stream.write(json_output + "\n")
        out_stream.flush()
        if args.output_file:
            args.output_file.write_text(json_output, encoding="utf-8")
    elif args.format == "markdown":
        md_output = render_markdown(result)
        out_stream.write(md_output + "\n")
        out_stream.flush()
        if args.output_file:
            args.output_file.write_text(md_output, encoding="utf-8")

    if args.fail_on:
        threshold = Severity(args.fail_on)
        thresh_rank = severity_rank(threshold)
        has_violations = any(severity_rank(f.severity) >= thresh_rank for f in result.findings)
        if has_violations:
            err_console.print(
                f"[bold red]Quality Gate Failed:[/bold red] "
                f"Found issues at or above '{args.fail_on}' threshold."
            )
            return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
