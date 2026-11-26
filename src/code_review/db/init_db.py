import logging

from sqlalchemy.orm import Session

from code_review.agents.registry import (
    DEFAULT_AGENT_DEFINITIONS,
    ensure_default_agents_seeded,
)
from code_review.db.database import get_engine, init_database

logger = logging.getLogger(__name__)

# Single source of truth lives in code_review.agents.registry.DEFAULT_AGENT_DEFINITIONS
DEFAULT_AGENTS = DEFAULT_AGENT_DEFINITIONS


def seed_database(session: Session) -> None:
    ensure_default_agents_seeded(session, normalize_legacy_models=True)
    logger.info("Database initialization completed successfully.")


def setup_db() -> None:
    init_database()
    engine = get_engine()
    with Session(engine) as session:
        seed_database(session)


if __name__ == "__main__":
    setup_db()
    print("Database initialization and seed complete!")
