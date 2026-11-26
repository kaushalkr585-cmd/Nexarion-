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
from code_review.config import get_settings
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

# Authoritative Single Source of Truth for Nexarion's registered agents (7 total,
# explicitly including Orchestrator Agent). Used across DB seeding, /api/agents,
# ReviewOrchestrator synchronization, and Nexarion's conversational system prompt.
DEFAULT_AGENT_DEFINITIONS: list[dict[str, Any]] = [
    {
        "agent_id": "security",
        "name": "Security Agent",
        "description": "Finds security vulnerabilities, secrets, and risky patterns.",
        "is_enabled": True,
        "provider": "bandit",
        "model_name": "Bandit + SAST",
        "capabilities": ["SAST", "Secret Detection", "Dependency Check"],
    },
    {
        "agent_id": "quality",
        "name": "Code Quality Agent",
        "description": "Analyzes code quality, readability, and best practices.",
        "is_enabled": True,
        "provider": "ruff",
        "model_name": "Ruff Linter",
        "capabilities": ["Linting", "Code Smells", "Best Practices"],
    },
    {
        "agent_id": "performance",
        "name": "Performance Agent",
        "description": "Detects performance issues and optimization opportunities.",
        "is_enabled": True,
        "provider": "ast",
        "model_name": "AST Metrics",
        "capabilities": ["Complexity Analysis", "Bottleneck Detection", "Resource Usage"],
    },
    {
        "agent_id": "documentation",
        "name": "Documentation Agent",
        "description": "Checks documentation, comments, and API usage.",
        "is_enabled": True,
        "provider": "llm",
        "model_name": "Active Runtime LLM",
        "capabilities": ["Doc Coverage", "Missing Comments", "API Consistency"],
    },
    {
        "agent_id": "test",
        "name": "Test Agent",
        "description": "Analyzes test coverage and test quality.",
        "is_enabled": True,
        "provider": "llm",
        "model_name": "Active Runtime LLM",
        "capabilities": ["Coverage Analysis", "Test Best Practices", "Missing Tests"],
    },
    {
        "agent_id": "semantic",
        "name": "Semantic & Cross-File Agent",
        "description": (
            "Performs cross-file dependency checks, multi-hunk resource analysis, "
            "and pattern detection."
        ),
        "is_enabled": True,
        "provider": "system",
        "model_name": "Semantic AST Graph",
        "capabilities": [
            "Cross-File Consistency",
            "Signature Verification",
            "Multi-Hunk Context",
            "Clone Detection",
        ],
    },
    {
        "agent_id": "orchestrator",
        "name": "Orchestrator Agent",
        "description": "Coordinates all agents and generates final review.",
        "is_enabled": True,
        "provider": "system",
        "model_name": "ReviewOrchestrator",
        "capabilities": ["Result Aggregation", "Priority Ranking", "Summary Generation"],
    },
]

DEFAULT_AGENT_IDS: set[str] = {entry["agent_id"] for entry in DEFAULT_AGENT_DEFINITIONS}
_CANONICAL_AGENT_ORDER: dict[str, int] = {
    entry["agent_id"]: idx for idx, entry in enumerate(DEFAULT_AGENT_DEFINITIONS)
}
_LEGACY_LLM_MODEL_LABELS: set[str] = {
    "",
    "active runtime llm",
    "qwen 2.5 / nemotron",
    "nemotron",
    "llm",
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
            enabled_ids = set(DEFAULT_AGENT_IDS)

        with _CONFIG_CACHE_LOCK:
            _CACHED_ENABLED_IDS = set(enabled_ids)

        return set(enabled_ids)
    except Exception as exc:
        logger.warning(
            "Could not query AgentConfigRecord from DB: %s. Using default enabled set.",
            exc,
        )
        return set(DEFAULT_AGENT_IDS)
    finally:
        if session_to_close is not None:
            session_to_close.close()


def ensure_default_agents_seeded(
    db: Session,
    *,
    normalize_legacy_models: bool = True,
) -> None:
    """
    Ensure all canonical default agents exist in AgentConfigRecord without
    overwriting user toggle states. Optionally replaces legacy hardcoded LLM
    model placeholders (e.g. 'Qwen 2.5 / Nemotron') with 'Active Runtime LLM'.
    """
    dirty = False
    for agent_data in DEFAULT_AGENT_DEFINITIONS:
        existing = db.query(AgentConfigRecord).filter_by(agent_id=agent_data["agent_id"]).first()
        if not existing:
            db.add(
                AgentConfigRecord(
                    agent_id=agent_data["agent_id"],
                    name=agent_data["name"],
                    description=agent_data["description"],
                    is_enabled=agent_data["is_enabled"],
                    provider=agent_data["provider"],
                    model_name=agent_data["model_name"],
                    capabilities=list(agent_data["capabilities"]),
                )
            )
            dirty = True
        elif (
            normalize_legacy_models
            and (existing.provider or "").strip().lower() in {"llm", "nvidia", "ollama"}
            and (existing.model_name or "").strip().lower() in _LEGACY_LLM_MODEL_LABELS
        ):
            existing.model_name = agent_data["model_name"]
            dirty = True

    # Remove orphaned legacy test-fixture alias rows ('ast', 'ruff') when canonical agents exist
    existing_ids = {
        (row.agent_id or "").lower().strip() for row in db.query(AgentConfigRecord).all()
    }
    if {"quality", "performance"}.issubset(existing_ids):
        orphan_rows = (
            db.query(AgentConfigRecord)
            .filter(
                AgentConfigRecord.agent_id.in_(["ast", "ruff"]),
                AgentConfigRecord.provider == "deterministic",
            )
            .all()
        )
        for orphan in orphan_rows:
            if (orphan.model_name or "").strip().lower() in {"", "default", "none"}:
                db.delete(orphan)
                dirty = True

    if dirty:
        db.commit()
        invalidate_agent_config_cache()


def resolve_runtime_llm_info(
    provider: str | None = None,
    model: str | None = None,
) -> tuple[str, str, str]:
    """
    Resolve the active runtime LLM provider display name, model identifier,
    and formatted description from runtime configuration.
    Returns (provider_name, resolved_model, model_display_name).
    """
    settings = get_settings()
    active_provider = (provider or settings.llm_provider or "llm").lower().strip()
    candidate_model = (model or "").strip()

    if active_provider == "ollama":
        if candidate_model.lower() in {"", "ollama", "default", "none"}:
            candidate_model = settings.ollama_model or settings.llm_model or "qwen2.5-coder:7b"
        return ("Ollama", candidate_model, f"local {candidate_model} via Ollama")

    if active_provider in {"nvidia", "llm"} or "nemotron" in candidate_model.lower():
        if candidate_model.lower() in {"", "llm", "nvidia", "default", "none"}:
            candidate_model = settings.nvidia_model or "nvidia/nemotron-3-ultra-550b-a55b"
        lower_model = candidate_model.lower()
        if "nemotron" in lower_model and "ultra" in lower_model:
            display = f"NVIDIA Nemotron Ultra ({candidate_model})"
        elif "nemotron" in lower_model:
            display = f"NVIDIA Nemotron ({candidate_model})"
        else:
            display = f"{candidate_model} via NVIDIA"
        return ("NVIDIA NIM", candidate_model, display)

    resolved_model = candidate_model or settings.llm_model or active_provider
    return (active_provider, resolved_model, f"{resolved_model} via {active_provider}")


def _sanitize_public_model_label(provider: str, raw_model_name: str | None) -> str:
    clean = (raw_model_name or "").strip()
    lower_clean = clean.lower()
    if provider in {"llm", "nvidia", "ollama", ""} and (
        lower_clean in _LEGACY_LLM_MODEL_LABELS
        or any(
            tok in lower_clean
            for tok in ("nemotron", "qwen", "gemini", "claude", "gpt-", "openai", "anthropic")
        )
    ):
        return "Active Runtime LLM"
    return clean or ("Active Runtime LLM" if provider in {"llm", "nvidia", "ollama"} else provider)


def get_registered_agents(
    db: Session | None = None,
    *,
    runtime_provider: str | None = None,
    runtime_model: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return the authoritative, ordered list of registered agents with live
    activation status, capabilities, and resolved execution engine details.
    """
    _, _, model_display_name = resolve_runtime_llm_info(runtime_provider, runtime_model)
    session_to_close: Session | None = None
    session = db
    if session is None:
        factory = get_session_factory()
        session = factory()
        session_to_close = session

    try:
        records = session.query(AgentConfigRecord).all()
        if records:
            ordered_records = sorted(
                records,
                key=lambda r: (
                    _CANONICAL_AGENT_ORDER.get((r.agent_id or "").lower().strip(), 999),
                    r.id or 0,
                ),
            )
            source_items = [
                {
                    "agent_id": (r.agent_id or "").lower().strip(),
                    "name": r.name,
                    "description": r.description,
                    "is_enabled": bool(r.is_enabled),
                    "provider": (r.provider or "").lower().strip(),
                    "model_name": r.model_name,
                    "capabilities": list(r.capabilities or []),
                }
                for r in ordered_records
            ]
        else:
            source_items = [dict(item) for item in DEFAULT_AGENT_DEFINITIONS]
    except Exception as exc:
        logger.warning("Failed reading registered agents from DB (%s); using defaults.", exc)
        source_items = [dict(item) for item in DEFAULT_AGENT_DEFINITIONS]
    finally:
        if session_to_close is not None:
            session_to_close.close()

    registered: list[dict[str, Any]] = []
    for item in source_items:
        agent_id = item["agent_id"]
        provider_key = item["provider"]
        is_enabled = bool(item["is_enabled"])
        public_model_label = _sanitize_public_model_label(provider_key, item.get("model_name"))
        runtime_engine = model_display_name if provider_key == "llm" else public_model_label
        registered.append(
            {
                "agent_id": agent_id,
                "name": item["name"],
                "description": item["description"],
                "is_enabled": is_enabled,
                "status": "Active" if is_enabled else "Disabled",
                "provider": provider_key,
                "model_name": public_model_label,
                "runtime_engine": runtime_engine,
                "capabilities": list(item.get("capabilities") or []),
                "is_orchestrator": agent_id == "orchestrator",
            }
        )
    return registered


def get_agent_registry_summary(
    db: Session | None = None,
    *,
    runtime_provider: str | None = None,
    runtime_model: str | None = None,
) -> dict[str, Any]:
    """Return structured counts, statuses, and metadata for all registered agents."""
    agents = get_registered_agents(
        db=db,
        runtime_provider=runtime_provider,
        runtime_model=runtime_model,
    )
    active = [a for a in agents if a["is_enabled"]]
    disabled = [a for a in agents if not a["is_enabled"]]
    orchestrator = next((a for a in agents if a["is_orchestrator"]), None)
    return {
        "agents": agents,
        "total_registered": len(agents),
        "active_count": len(active),
        "disabled_count": len(disabled),
        "active_agents": active,
        "disabled_agents": disabled,
        "active_agent_ids": [a["agent_id"] for a in active],
        "disabled_agent_ids": [a["agent_id"] for a in disabled],
        "orchestrator_agent": orchestrator,
        "orchestrator_registered": orchestrator is not None,
        "orchestrator_enabled": bool(orchestrator and orchestrator["is_enabled"]),
    }


def format_agent_registry_prompt_context(
    db: Session | None = None,
    *,
    runtime_provider: str | None = None,
    runtime_model: str | None = None,
) -> tuple[str, str]:
    """
    Build synchronized prompt blocks from the live agent registry:
      1. public_registry_block: safe agent counts, names, descriptions, capabilities,
         and live Active/Disabled status with zero leaked LLM provider/model names.
      2. confidential_runtime_block: exact runtime LLM/provider mapping per agent
         strictly restricted to explicit user queries asking what model/provider runs.
    """
    summary = get_agent_registry_summary(
        db=db,
        runtime_provider=runtime_provider,
        runtime_model=runtime_model,
    )
    provider_name, resolved_model, model_display_name = resolve_runtime_llm_info(
        runtime_provider, runtime_model
    )

    agents = summary["agents"]
    active_names = ", ".join(a["name"] for a in summary["active_agents"]) or "None"
    disabled_names = ", ".join(a["name"] for a in summary["disabled_agents"]) or "None"
    orchestrator = summary["orchestrator_agent"]
    orchestrator_status = orchestrator["status"] if orchestrator else "Not registered"

    roster_lines: list[str] = []
    for idx, agent in enumerate(agents, start=1):
        caps = ", ".join(agent["capabilities"]) if agent["capabilities"] else "General analysis"
        role_tag = (
            "AI Reasoning Engine"
            if agent["provider"] in {"llm", "nvidia", "ollama"}
            else f"Deterministic/System Engine ({agent['model_name']})"
        )
        roster_lines.append(
            f"  {idx}. {agent['name']} [id: `{agent['agent_id']}` | Status: {agent['status']} | "
            f"Execution: {role_tag}] — {agent['description']} Capabilities: {caps}."
        )

    public_block = (
        "LIVE AGENT REGISTRY (Authoritative Single Source of Truth):\n"
        f"- Total Registered Agents: {summary['total_registered']}\n"
        f"- Currently Active (Enabled) Agents: {summary['active_count']} ({active_names})\n"
        f"- Currently Disabled Agents: {summary['disabled_count']} ({disabled_names})\n"
        f"- Orchestrator Role: Orchestrator Agent IS counted as one of the "
        f"{summary['total_registered']} registered agents (current status: {orchestrator_status}); "
        "it coordinates execution across active agents, merges results, ranks priorities, "
        "and generates unified reviews.\n"
        "- Registered Agent Details:\n" + "\n".join(roster_lines) + "\n- Agent Awareness Rules:\n"
        f"  * Always state the exact registered count ({summary['total_registered']}) and "
        f"active count ({summary['active_count']}) separately when asked how many agents Nexarion has.\n"
        "  * Always include Orchestrator Agent in the registered agent count and list.\n"
        "  * Report only agents, descriptions, capabilities, and Active/Disabled statuses listed above. "
        "Never invent agents or unconfigured capabilities.\n"
        "  * When describing agents normally, do NOT expose internal LLM names or inference providers; "
        "state only their analytical/engineering roles."
    )

    llm_agent_names = [a["name"] for a in agents if a["provider"] in {"llm", "nvidia", "ollama"}]
    non_llm_details = [
        f"{a['name']} ({a['model_name']})"
        for a in agents
        if a["provider"] not in {"llm", "nvidia", "ollama"}
    ]
    llm_agents_str = ", ".join(llm_agent_names) if llm_agent_names else "None"
    non_llm_str = "; ".join(non_llm_details) if non_llm_details else "None"

    confidential_block = (
        "CONFIDENTIAL RUNTIME MODEL CONFIGURATION (DISCLOSE ONLY WHEN EXPLICITLY ASKED):\n"
        f"- Active Chat & AI-Reasoning LLM: {model_display_name} "
        f"(provider: {provider_name}, configured model: `{resolved_model}`).\n"
        f"- LLM-Backed Registered Agents: {llm_agents_str} (use {model_display_name}).\n"
        f"- Deterministic / Local / System Agents (no external LLM inference): {non_llm_str}."
    )

    return public_block, confidential_block


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
