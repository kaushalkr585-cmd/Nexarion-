"""Shared test setup for the backend database.

The API tests use TestClient without entering it as a context manager, so the
application lifespan is not guaranteed to run. Create the test schema and seed
the default agent configuration once for the test session instead.
"""
import pytest
from sqlalchemy.orm import Session

from code_review.db.database import get_engine, init_database
from code_review.db.init_db import seed_database
from code_review.db.models import AgentConfigRecord  # noqa: F401


@pytest.fixture(scope="session", autouse=True)
def initialize_test_database():
    init_database()
    with Session(get_engine()) as session:
        seed_database(session)
    yield
