from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from code_review.agents.base import BaseAgent
from code_review.config import get_settings
from code_review.llm.client import (
    OllamaClientError,
    OllamaConnectionError,
    OllamaTimeoutError,
)
from code_review.llm.factory import LLMClientProtocol, get_llm_client
from code_review.llm.prompts import (
    REVIEW_SYSTEM_PROMPT,
    format_diff_for_review,
    parse_llm_findings,
)
from code_review.models.enums import AgentType
from code_review.models.finding import Finding
from code_review.parsers.diff_parser import DiffFile

logger = logging.getLogger(__name__)


class LLMAgent(BaseAgent):
    def __init__(
        self,
        client: LLMClientProtocol | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        temperature: float | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self._repo_root = repo_root
        if client is not None:
            self._client = client
        else:
            self._client = get_llm_client(
                provider=provider,
                model=model,
                base_url=base_url,
                timeout=timeout,
                temperature=temperature,
            )

    @property
    def agent_type(self) -> AgentType:
        return AgentType.LLM

    @property
    def client(self) -> LLMClientProtocol:
        return self._client

    @property
    def model(self) -> str:
        return getattr(self._client, "model", "ollama")

    def review(self, diff_files: list[DiffFile]) -> list[Finding]:
        if not diff_files:
            return []

        if not self._client.is_available():
            logger.warning(
                "Ollama server is not accessible at %s. Skipping LLM review.",
                getattr(self._client, "base_url", "ollama"),
            )
            return []

        reviewable_files = [diff_file for diff_file in diff_files if diff_file.added_line_numbers]
        for diff_file in diff_files:
            if not diff_file.added_line_numbers:
                logger.debug("Skipping LLM review for %s: no added lines", diff_file.path)

        if not reviewable_files:
            return []

        max_workers = max(1, min(get_settings().llm_file_concurrency, len(reviewable_files)))
        if max_workers == 1:
            return [
                finding
                for diff_file in reviewable_files
                for finding in self._review_file(diff_file)
            ]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            file_findings = executor.map(self._review_file, reviewable_files)
            return [finding for findings in file_findings for finding in findings]

    def _review_file(self, diff_file: DiffFile) -> list[Finding]:
        prompt_content = format_diff_for_review(diff_file)
        messages = [
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": prompt_content},
        ]

        logger.info(
            "Requesting LLM review for %s (%d added lines) using %s",
            diff_file.path,
            len(diff_file.added_line_numbers),
            self.model,
        )

        try:
            raw_response = self._client.chat(messages, json_format=True)
            findings = parse_llm_findings(raw_response, diff_file)
            logger.debug(
                "LLM review of %s yielded %d valid findings",
                diff_file.path,
                len(findings),
            )
            return findings
        except OllamaTimeoutError as exc:
            logger.warning("LLM review timed out for file %s: %s", diff_file.path, exc)
            return []
        except OllamaConnectionError as exc:
            logger.warning(
                "Ollama connection dropped during review of %s: %s",
                diff_file.path,
                exc,
            )
            return []
        except OllamaClientError as exc:
            logger.warning("Ollama error reviewing file %s: %s", diff_file.path, exc)
            return []
        except Exception as exc:
            logger.error(
                "Unexpected error during LLM review of %s: %s",
                diff_file.path,
                exc,
                exc_info=True,
            )
            return []
