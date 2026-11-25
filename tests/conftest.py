from __future__ import annotations

import pytest

from code_review.db.database import init_database


@pytest.fixture(scope="session", autouse=True)
def _ensure_database_schema() -> None:
    """Ensure schema migrations and new tables exist before any pytest session."""
    init_database()
