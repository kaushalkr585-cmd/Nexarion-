import logging
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from code_review.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
        pass


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    db_url = settings.database_url
    logger.info("Initializing database engine with URL schema: %s", db_url.split("://")[0])
    return create_engine(
        db_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=settings.debug,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    engine = get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def init_database() -> None:
    engine = get_engine()
    logger.info("Creating database tables if not present...")
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        inspector = inspect(conn)
        if "conversations" in inspector.get_table_names():
            columns = [c["name"] for c in inspector.get_columns("conversations")]
            if "is_pinned" not in columns:
                conn.execute(
                    text("ALTER TABLE conversations ADD COLUMN is_pinned BOOLEAN DEFAULT FALSE")
                )
            if "is_archived" not in columns:
                conn.execute(
                    text("ALTER TABLE conversations ADD COLUMN is_archived BOOLEAN DEFAULT FALSE")
                )
            if "section_name" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE conversations "
                        "ADD COLUMN section_name VARCHAR(100) DEFAULT NULL"
                    )
                )
            if "summary" not in columns:
                conn.execute(
                    text("ALTER TABLE conversations ADD COLUMN summary TEXT DEFAULT NULL")
                )

        if conn.dialect.name == "postgresql":
            if "conversation_memories" in inspector.get_table_names():
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_memories_content_fts "
                        "ON conversation_memories USING gin(to_tsvector('english', content))"
                    )
                )
            if "conversations" in inspector.get_table_names():
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_conversations_summary_fts "
                        "ON conversations USING gin(to_tsvector('english', coalesce(summary, '')))"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_conversations_user_archived_updated "
                        "ON conversations (user_id, is_archived, updated_at DESC)"
                    )
                )
            if "messages" in inspector.get_table_names():
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_messages_conv_created "
                        "ON messages (conversation_id, created_at ASC)"
                    )
                )
    logger.info("Database schema initialized successfully.")
