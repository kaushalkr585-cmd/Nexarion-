from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from code_review.agents.ast_agent import ASTAgent
from code_review.agents.bandit_agent import BanditAgent
from code_review.agents.base import BaseAgent
from code_review.agents.llm_agent import LLMAgent
from code_review.agents.ruff_agent import RuffAgent
from code_review.agents.semantic_agent import SemanticAgent
from code_review.db.database import get_session_factory
from code_review.db.models import AgentConfigRecord
from code_review.models.enums import AgentType

logger = logging.getLogger(__name__)

# Canonical map of agent_id to agent class
AGENT_ID_MAP: dict[str, type[BaseAgent]] = {
    "security": BanditAgent,
    "bandit": BanditAgent,
    "quality": RuffAgent,
    "ruff": RuffAgent,
    "performance": ASTAgent,
    "ast": ASTAgent,
    "semantic": SemanticAgent,
    "cross_file": SemanticAgent,
    "documentation": LLMAgent,
    "test": LLMAgent,
    "llm": LLMAgent,
}

_CONFIG_CACHE_LOCK = threading.Lock()
_CACHED_ENABLED_IDS: set[str] | None = None


def invalidate_agent_config_cache() -> None:
    """Invalidate cached enabled agent configuration."""
    global _CACHED_ENABLED_IDS
    with _CONFIG_CACHE_LOCK:
        _CACHED_ENABLED_IDS = None
        logger.debug("Agent configuration cache invalidated.")


def get_agent_identifiers(agent: BaseAgent) -> set[str]:
    """Return all known identifier strings and aliases for an agent instance."""
    ids: set[str] = {
        agent.name.lower(),
        agent.agent_type.value.lower(),
        agent.__class__.__name__.lower(),
    }
    if isinstance(agent, BanditAgent) or agent.agent_type == AgentType.BANDIT:
        ids.update({"security", "bandit", "banditagent"})
    elif isinstance(agent, RuffAgent) or agent.agent_type == AgentType.RUFF:
        ids.update({"quality", "ruff", "ruffagent"})
    elif isinstance(agent, ASTAgent) or agent.agent_type == AgentType.AST:
        ids.update({"performance", "ast", "astagent"})
    elif isinstance(agent, SemanticAgent) or agent.agent_type == AgentType.SEMANTIC:
        ids.update({"semantic", "cross_file", "semanticagent"})
    elif isinstance(agent, LLMAgent) or agent.agent_type == AgentType.LLM:
        ids.update({"documentation", "test", "llm", "llmagent"})
    return ids


def is_agent_enabled(agent: BaseAgent, enabled_ids: set[str] | list[str] | None) -> bool:
    """Check if an agent is permitted by the given enabled agent IDs set."""
    if enabled_ids is None:
        return True
    enabled_set = {str(i).lower().strip() for i in enabled_ids}
    agent_ids = get_agent_identifiers(agent)
    return bool(agent_ids & enabled_set)


def get_persisted_enabled_agent_ids(
    db: Session | None = None,
    *,
    use_cache: bool = True,
) -> set[str]:
    """
    Fetch the latest enabled-agent IDs from the database (authoritative source of truth).
    If db is not provided, opens a short-lived session.
    Returns the set of enabled agent_ids (e.g. {"quality", "performance"}).
    If all agents are disabled, returns an empty set.
    """
    global _CACHED_ENABLED_IDS

    if use_cache:
        with _CONFIG_CACHE_LOCK:
            if _CACHED_ENABLED_IDS is not None:
                return set(_CACHED_ENABLED_IDS)

    session_to_close: Session | None = None
    session = db
    if session is None:
        factory = get_session_factory()
        session = factory()
        session_to_close = session

    try:
        records = session.query(AgentConfigRecord).all()
        if records:
            enabled_ids = {r.agent_id.lower().strip() for r in records if r.is_enabled}
        else:
            # Fallback only when table is completely unseeded
            enabled_ids = {
                "security",
                "quality",
                "performance",
                "documentation",
                "test",
                "semantic",
            }

        with _CONFIG_CACHE_LOCK:
            _CACHED_ENABLED_IDS = set(enabled_ids)

        return set(enabled_ids)
    except Exception as exc:
        logger.warning(
            "Could not query AgentConfigRecord from DB: %s. Using default enabled set.",
            exc,
        )
        return {
            "security",
            "quality",
            "performance",
            "documentation",
            "test",
            "semantic",
        }
    finally:
        if session_to_close is not None:
            session_to_close.close()


def build_active_agents(
    enabled_agent_ids: set[str] | list[str] | None = None,
    *,
    repo_root: Path | None = None,
    llm_provider: str | None = None,
    include_semantic: bool | None = None,
    include_llm: bool | None = None,
) -> list[BaseAgent]:
    """
    Instantiate and return ONLY the agents that are enabled according to enabled_agent_ids.
    Never instantiates disabled agents.
    """
    kwargs: dict[str, Any] = {"repo_root": repo_root} if repo_root is not None else {}

    if enabled_agent_ids is None:
        # Default unconstrained pipeline
        agents: list[BaseAgent] = [
            ASTAgent(**kwargs),
            RuffAgent(**kwargs),
            BanditAgent(**kwargs),
        ]
        if include_semantic:
            agents.append(SemanticAgent(**kwargs))
        if include_llm:
            agents.append(LLMAgent(**kwargs, provider=llm_provider))
        return agents

    enabled_set = {str(a).lower().strip() for a in enabled_agent_ids}
    agents = []

    # 1. Performance / AST Agent
    if "performance" in enabled_set or "ast" in enabled_set:
        agents.append(ASTAgent(**kwargs))

    # 2. Code Quality / Ruff Agent
    if "quality" in enabled_set or "ruff" in enabled_set:
        agents.append(RuffAgent(**kwargs))

    # 3. Security / Bandit Agent
    if "security" in enabled_set or "bandit" in enabled_set:
        agents.append(BanditAgent(**kwargs))

    # 4. Semantic Agent
    should_semantic = ("semantic" in enabled_set or "cross_file" in enabled_set) and (
        include_semantic is None or include_semantic
    )
    if should_semantic:
        agents.append(SemanticAgent(**kwargs))

    # 5. LLM Agent (Documentation / Test / LLM)
    has_llm_id = bool({"documentation", "test", "llm"} & enabled_set)
    should_llm = has_llm_id and (include_llm is None or include_llm)
    if should_llm:
        agents.append(LLMAgent(**kwargs, provider=llm_provider))

    return agents
