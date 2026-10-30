from __future__ import annotations

from collections.abc import Callable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from code_review.models.enums import AgentType, Severity
from code_review.models.review import ReviewResult

SEVERITY_STYLES: dict[Severity, str] = {
    Severity.CRITICAL: "bold white on red",
    Severity.ERROR: "bold red",
    Severity.WARNING: "bold yellow",
    Severity.INFO: "bold cyan",
}

SEVERITY_BADGES: dict[Severity, str] = {
    Severity.CRITICAL: "[bold white on red] CRITICAL [/]",
    Severity.ERROR: "[bold red] ERROR [/]",
    Severity.WARNING: "[bold yellow] WARNING [/]",
    Severity.INFO: "[bold cyan] INFO [/]",
}

AGENT_COLORS: dict[AgentType, str] = {
    AgentType.AST: "dim cyan",
    AgentType.RUFF: "bold blue",
    AgentType.BANDIT: "bold magenta",
    AgentType.LLM: "bold green",
}


def render_table(result: ReviewResult, console: Console | None = None) -> None:
    con = console or Console()

    counts = result.findings_by_severity
    crit_count = counts.get(Severity.CRITICAL.value, 0)
    err_count = counts.get(Severity.ERROR.value, 0)
    warn_count = counts.get(Severity.WARNING.value, 0)
    info_count = counts.get(Severity.INFO.value, 0)

    is_cached = getattr(result, "cached", False)
    cached_badge = "  [bold green][CACHED][/bold green]" if is_cached else ""
    summary_text = (
        f"[bold]Files Reviewed:[/bold] {result.files_reviewed}   "
        f"[bold]Duration:[/bold] {result.review_time_ms}ms{cached_badge}   "
        f"[bold]Total Findings:[/bold] {result.total_findings}\n\n"
        f"[bold white on red] Critical: {crit_count} [/]  "
        f"[bold red] Error: {err_count} [/]  "
        f"[bold yellow] Warning: {warn_count} [/]  "
        f"[bold cyan] Info: {info_count} [/]"
    )

    if crit_count > 0 or err_count > 0:
        border_color = "red"
    elif warn_count > 0:
        border_color = "yellow"
    else:
        border_color = "green"

    con.print()
    con.print(
        Panel(
            summary_text,
            title="[bold]Multi-Agent Code Review Results[/bold]",
            subtitle=result.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            border_style=border_color,
            expand=False,
        )
    )

    if result.total_findings == 0:
        con.print(
            Panel(
                "[bold green]No issues detected across files. Code looks clean![/bold green]",
                border_style="green",
                expand=False,
            )
        )
        con.print()
        return

    table = Table(
        title="Detected Findings",
        show_header=True,
        header_style="bold magenta",
        show_lines=True,
        expand=True,
    )

    table.add_column("Severity", justify="center", width=12, no_wrap=True)
    table.add_column("Location", style="cyan", width=26, no_wrap=False)
    table.add_column("Agent", justify="center", width=8, no_wrap=True)
    table.add_column("Category", style="dim", width=14, no_wrap=True)
    table.add_column("Rule", style="dim yellow", width=12, no_wrap=True)
    table.add_column("Description & Suggestion", style="none", ratio=1)

    for finding in result.findings:
        sev_badge = SEVERITY_BADGES.get(finding.severity, finding.severity.value.upper())
        agent_color = AGENT_COLORS.get(finding.agent, "white")
        agent_text = f"[{agent_color}]{finding.agent.value.upper()}[/]"
        location = f"[cyan]{finding.file}[/]:[bold]{finding.line}[/]"

        desc = Text()
        desc.append(finding.message)
        if finding.suggestion:
            desc.append("\nSuggestion: ")
            desc.append(finding.suggestion, style="dim italic green")

        table.add_row(
            sev_badge,
            location,
            agent_text,
            finding.category.value,
            finding.rule_id or "—",
            desc,
        )

    con.print(table)
    con.print()


def render_json(result: ReviewResult) -> str:
    return result.model_dump_json(indent=2)


def render_markdown(result: ReviewResult) -> str:
    counts = result.findings_by_severity
    crit = counts.get(Severity.CRITICAL.value, 0)
    err = counts.get(Severity.ERROR.value, 0)
    warn = counts.get(Severity.WARNING.value, 0)
    info = counts.get(Severity.INFO.value, 0)

    lines: list[str] = [
        "# Multi-Agent Code Review Report",
        "",
        "## Summary",
        "",
        f"- **Files Reviewed:** {result.files_reviewed}",
        f"- **Review Time:** {result.review_time_ms} ms",
        f"- **Total Findings:** {result.total_findings}",
        f"- **Timestamp:** {result.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "| Critical | Error | Warning | Info |",
        "| :---: | :---: | :---: | :---: |",
        f"| {crit} | {err} | {warn} | {info} |",
        "",
    ]

    if result.total_findings == 0:
        lines.extend(
            [
                "### Status",
                "",
                "**No issues detected.** All checked diff hunks passed inspection.",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "## Findings",
            "",
            "| Severity | File:Line | Agent | Category | Rule ID | Message | Suggestion |",
            "|---|---|:---:|---|---|---|---|",
        ]
    )

    for f in result.findings:
        sugg = f.suggestion or "—"
        rule = f.rule_id or "—"

        clean_msg = f.message.replace("|", "\\|").replace("\n", " ")
        clean_sugg = sugg.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| **{f.severity.value.upper()}** | `{f.file}:{f.line}` | {f.agent.value.upper()} | "
            f"`{f.category.value}` | `{rule}` | {clean_msg} | {clean_sugg} |"
        )

    lines.append("")
    return "\n".join(lines)

FORMATTERS: dict[str, Callable[[ReviewResult], str | None]] = {
    "table": lambda res: None,
    "json": render_json,
    "markdown": render_markdown,
}
