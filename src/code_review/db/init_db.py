import logging

from sqlalchemy.orm import Session

from code_review.db.database import get_engine, init_database
from code_review.db.models import (
    AgentConfigRecord,
)

logger = logging.getLogger(__name__)

DEFAULT_AGENTS = [
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
        "model_name": "Qwen 2.5 / Nemotron",
        "capabilities": ["Doc Coverage", "Missing Comments", "API Consistency"],
    },
    {
        "agent_id": "test",
        "name": "Test Agent",
        "description": "Analyzes test coverage and test quality.",
        "is_enabled": True,
        "provider": "llm",
        "model_name": "Qwen 2.5 / Nemotron",
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


def seed_database(session: Session) -> None:
    for agent_data in DEFAULT_AGENTS:
        existing = (
            session.query(AgentConfigRecord).filter_by(agent_id=agent_data["agent_id"]).first()
        )
        if not existing:
            config = AgentConfigRecord(
                agent_id=agent_data["agent_id"],
                name=agent_data["name"],
                description=agent_data["description"],
                is_enabled=agent_data["is_enabled"],
                provider=agent_data["provider"],
                model_name=agent_data["model_name"],
                capabilities=agent_data["capabilities"],
            )
            session.add(config)

    session.commit()
    logger.info("Database initialization completed successfully.")


def setup_db() -> None:
    init_database()
    engine = get_engine()
    with Session(engine) as session:
        seed_database(session)

if __name__ == "__main__":
    setup_db()
    print("Database initialization and seed complete!")
