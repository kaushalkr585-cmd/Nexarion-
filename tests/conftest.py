"""Shared test setup for the backend database.

TestClient instances are often created without a context manager, so the app
lifespan is not guaranteed to run. Build the schema and seed agent defaults
before any test fixtures access PostgreSQL.
"""
import pytest
from sqlalchemy.orm import Session

# Import the complete model module before create_all so every mapped table is
# registered in Base.metadata, including UserRecord and AgentConfigRecord.
from code_review.db import models as _models  # noqa: F401
from code_review.db.database import Base, get_engine, init_database
from code_review.db.init_db import seed_database


@pytest.fixture(scope="session", autouse=True)
def initialize_test_database():
    init_database()
    # Keep this explicit: create_all is idempotent and guarantees the test
    # schema exists even when application lifespan is skipped by TestClient.
    Base.metadata.create_all(bind=get_engine())
    with Session(get_engine()) as session:
        seed_database(session)
    yield
