import logging
import time
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from code_review.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str) -> str:
    """Ensure standard postgresql+psycopg driver prefix for Render/Neon compatibility."""
    if not url:
        return url
    clean = url.strip()
    if clean.startswith("postgres://"):
        return "postgresql+psycopg://" + clean[len("postgres://") :]
    if clean.startswith("postgresql://") and not clean.startswith("postgresql+psycopg://"):
        return "postgresql+psycopg://" + clean[len("postgresql://") :]
    return clean


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    db_url = normalize_database_url(settings.database_url)
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


def init_database(max_retries: int = 3, retry_delay: float = 2.0) -> None:
    engine = get_engine()
    logger.info("Creating database tables if not present...")
    for attempt in range(1, max_retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            break
        except Exception as exc:
            if attempt < max_retries:
                logger.warning(
                    "Database table creation attempt %d/%d failed: %s. Retrying in %ss...",
                    attempt,
                    max_retries,
                    exc,
                    retry_delay,
                )
                time.sleep(retry_delay)
            else:
                logger.error(
                    "Failed to initialize database tables after %d attempts: %s",
                    max_retries,
                    exc,
                )
                raise exc

    with engine.begin() as conn:
        inspector = inspect(conn)
        table_names = set(inspector.get_table_names())

        if "users" in table_names:
            cols_info = inspector.get_columns("users")
            user_cols = {c["name"]: c for c in cols_info}
            if "role" not in user_cols:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN role VARCHAR(50) NOT NULL DEFAULT 'user'")
                )
            if "token_version" not in user_cols:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 1")
                )
            if "password_changed_at" not in user_cols:
                col_type = (
                    "TIMESTAMP WITH TIME ZONE"
                    if conn.dialect.name == "postgresql"
                    else "TIMESTAMP"
                )
                conn.execute(
                    text(
                        f"ALTER TABLE users ADD COLUMN password_changed_at {col_type} DEFAULT NULL"
                    )
                )
            elif conn.dialect.name == "postgresql":
                col_type_str = str(user_cols["password_changed_at"]["type"]).upper()
                if "TIME ZONE" not in col_type_str and "TIMESTAMPTZ" not in col_type_str:
                    conn.execute(
                        text(
                            "ALTER TABLE users ALTER COLUMN password_changed_at "
                            "TYPE TIMESTAMP WITH TIME ZONE"
                        )
                    )

        if "conversation_memories" in table_names:
            mem_cols = {c["name"] for c in inspector.get_columns("conversation_memories")}
            if "updated_at" not in mem_cols:
                col_type = (
                    "TIMESTAMP WITH TIME ZONE"
                    if conn.dialect.name == "postgresql"
                    else "TIMESTAMP"
                )
                conn.execute(
                    text(
                        f"ALTER TABLE conversation_memories ADD COLUMN updated_at {col_type} DEFAULT CURRENT_TIMESTAMP"
                    )
                )

        if "conversations" in table_names:
            columns = {c["name"] for c in inspector.get_columns("conversations")}
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
            if "is_shared" not in columns:
                conn.execute(
                    text("ALTER TABLE conversations ADD COLUMN is_shared BOOLEAN DEFAULT FALSE")
                )

        if conn.dialect.name == "postgresql":
            if "conversation_memories" in table_names:
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_memories_content_fts "
                        "ON conversation_memories USING gin(to_tsvector('english', content))"
                    )
                )
            if "conversations" in table_names:
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
            if "messages" in table_names:
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_messages_conv_created "
                        "ON messages (conversation_id, created_at ASC)"
                    )
                )

        if "github_connections" in table_names:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_github_conn_user_status "
                    "ON github_connections (user_id, connection_status)"
                )
            )
        if "conversation_repository_contexts" in table_names:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_conv_repo_ctx_user "
                    "ON conversation_repository_contexts (user_id, conversation_id)"
                )
            )
        if "feedback_reports" in table_names:
            fb_columns = {c["name"] for c in inspector.get_columns("feedback_reports")}
            if "conversation_ref" not in fb_columns:
                conn.execute(
                    text(
                        "ALTER TABLE feedback_reports ADD COLUMN conversation_ref VARCHAR(64) DEFAULT 'direct'"
                    )
                )
            if "message_ref" not in fb_columns:
                conn.execute(
                    text(
                        "ALTER TABLE feedback_reports ADD COLUMN message_ref VARCHAR(64) DEFAULT 'direct'"
                    )
                )
            if "conversation_title" not in fb_columns:
                conn.execute(
                    text(
                        "ALTER TABLE feedback_reports ADD COLUMN conversation_title VARCHAR(512) DEFAULT NULL"
                    )
                )
            if "email_message_id" not in fb_columns:
                conn.execute(
                    text(
                        "ALTER TABLE feedback_reports ADD COLUMN email_message_id VARCHAR(120) DEFAULT NULL"
                    )
                )

            # Ensure conversation_id and message_id are nullable for direct or deleted conversation feedback
            if conn.dialect.name == "postgresql":
                try:
                    conn.execute(
                        text(
                            "ALTER TABLE feedback_reports ALTER COLUMN conversation_id DROP NOT NULL"
                        )
                    )
                    conn.execute(
                        text("ALTER TABLE feedback_reports ALTER COLUMN message_id DROP NOT NULL")
                    )
                except Exception as exc:
                    logger.debug("Feedback column nullability alter: %s", exc)

                try:
                    conn.execute(text("DROP INDEX IF EXISTS ix_feedback_reports_dedupe_key"))
                    conn.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_feedback_reports_dedupe_key ON feedback_reports (dedupe_key)"
                        )
                    )
                except Exception as exc:
                    logger.debug("Feedback dedupe_key index migration: %s", exc)

            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_feedback_status_created "
                    "ON feedback_reports (status, created_at DESC)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_feedback_email_status "
                    "ON feedback_reports (email_notification_status)"
                )
            )
    logger.info("Database schema initialized successfully.")
