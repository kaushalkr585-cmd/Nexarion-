from __future__ import annotations

import argparse
import sys
from pathlib import Path

from code_review.agents.llm_agent import LLMAgent
from code_review.llm.client import OllamaClient
from code_review.orchestrator import ReviewOrchestrator, default_agents
from code_review.parsers.diff_parser import parse_diff


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-Agent Code Review Interactive Demo")
    parser.add_argument(
        "diff_path",
        nargs="?",
        default="tests/fixtures/sample_logic.diff",
        help="Path to unified diff file (default: tests/fixtures/sample_logic.diff)",
    )
    parser.add_argument(
        "--llm-only",
        action="store_true",
        help="Run only the LLMAgent instead of the full suite",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override model name (e.g. qwen2.5-coder:7b or qwen2.5-coder:1.5b)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="Generation temperature (default: 0.1)",
    )

    args = parser.parse_args()

    diff_file_path = Path(args.diff_path)
    if not diff_file_path.exists():
        print(f"Error: Diff file not found: {diff_file_path}", file=sys.stderr)
        sys.exit(1)

    diff_text = diff_file_path.read_text(encoding="utf-8")
    diff_files = parse_diff(diff_text)

    print("\n========================================================")
    print(" MULTI-AGENT CODE REVIEW SYSTEM - DEMO RUN")
    print(f" Reviewing: {diff_file_path} ({len(diff_files)} file(s))")
    print("========================================================\n")

    client = OllamaClient(
        model=args.model or "qwen2.5-coder:7b",
        temperature=args.temperature,
    )

    if not client.is_available():
        print(f"[!] Warning: Ollama is not accessible at {client.base_url}")
        print("    Ensure Ollama is running (`ollama serve`).\n")

    if args.llm_only:
        print(f"[*] Running in LLM-ONLY mode using model: {client.model}...")
        llm_agent = LLMAgent(client=client)
        orchestrator = ReviewOrchestrator(agents=[llm_agent])
    else:
        print(f"[*] Running FULL MULTI-AGENT review (AST + Ruff + Bandit + LLM:{client.model})...")
        agents = default_agents(include_llm=True)

        for a in agents:
            if isinstance(a, LLMAgent) and args.model:
                a._client = client
        orchestrator = ReviewOrchestrator(agents=agents)

    result = orchestrator.review_diff(diff_text)

    print(f"\nReview completed in {result.review_time_ms:.1f} ms")
    print(f"Total findings: {result.total_findings} (Critical: {result.has_critical})\n")

    if not result.findings:
        print("[+] No issues discovered! Clean code.")
        return

    severity_colors = {
        "critical": "\033[91m",
        "error": "\033[31m",
        "warning": "\033[33m",
        "info": "\033[36m",
    }
    reset_color = "\033[0m"

    for idx, finding in enumerate(result.findings, 1):
        sev_color = severity_colors.get(finding.severity.value, "")
        print(
            f"{idx}. {sev_color}[{finding.severity.upper()}]{reset_color} "
            f"{finding.file}:{finding.line} "
            f"(Agent: {finding.agent.upper()}"
            f"{f' | Rule: {finding.rule_id}' if finding.rule_id else ''})"
        )
        print(f"   Category: {finding.category.value}")
        print(f"   Issue:    {finding.message}")
        if finding.suggestion:
            print(f"   Fix:      \033[92m{finding.suggestion}\033[0m")
        print()

if __name__ == "__main__":
    main()
