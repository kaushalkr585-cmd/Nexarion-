"""Tests for conversation sharing link generation and secure read-only access."""

import uuid

import pytest
from fastapi.testclient import TestClient

from code_review.db.database import get_db, init_database
from code_review.db.models import ConversationRecord, MessageRecord, UserRecord
from code_review.web.app import app
from code_review.web.auth import create_access_token


@pytest.fixture(autouse=True)
def setup_db():
    init_database()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def owner_user() -> UserRecord:
    db = next(get_db())
    email = f"share_owner_{uuid.uuid4().hex[:8]}@nexarion.dev"
    user = UserRecord(
        id=str(uuid.uuid4()),
        email=email,
        name="Share Owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def second_user() -> UserRecord:
    db = next(get_db())
    email = f"share_viewer_{uuid.uuid4().hex[:8]}@nexarion.dev"
    user = UserRecord(
        id=str(uuid.uuid4()),
        email=email,
        name="Second Viewer",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_owner_can_toggle_share_status(client: TestClient, owner_user: UserRecord):
    db = next(get_db())
    token = create_access_token({"sub": owner_user.id, "email": owner_user.email})
    headers = {"Authorization": f"Bearer {token}"}

    conv = ConversationRecord(
        id=str(uuid.uuid4()),
        user_id=owner_user.id,
        title="Sharable Architecture Review",
        is_shared=False,
    )
    db.add(conv)
    db.commit()

    # Verify initial private status via API
    get_resp = client.get(f"/api/conversations/{conv.id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json().get("is_shared") is False

    # Mark as shared via PATCH
    patch_resp = client.patch(
        f"/api/conversations/{conv.id}",
        headers=headers,
        json={"is_shared": True},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_shared"] is True

    # Re-fetch confirms is_shared is True
    re_get = client.get(f"/api/conversations/{conv.id}", headers=headers)
    assert re_get.status_code == 200
    assert re_get.json()["is_shared"] is True


def test_unauthenticated_and_third_party_access_for_shared_conversation(
    client: TestClient, owner_user: UserRecord, second_user: UserRecord
):
    db = next(get_db())
    second_token = create_access_token({"sub": second_user.id, "email": second_user.email})

    conv = ConversationRecord(
        id=str(uuid.uuid4()),
        user_id=owner_user.id,
        title="Public Incident Postmortem",
        is_shared=True,
    )
    db.add(conv)

    msg = MessageRecord(
        id=str(uuid.uuid4()),
        conversation_id=conv.id,
        role="assistant",
        content="Production root cause analysis content",
    )
    db.add(msg)
    db.commit()

    # 1. Unauthenticated (incognito / guest) user can load the shared conversation
    anon_resp = client.get(f"/api/conversations/{conv.id}")
    assert anon_resp.status_code == 200
    anon_data = anon_resp.json()
    assert anon_data["id"] == conv.id
    assert anon_data["title"] == "Public Incident Postmortem"
    assert anon_data["is_shared"] is True
    assert len(anon_data["messages"]) >= 1

    # 2. Another authenticated user can load the shared conversation
    second_resp = client.get(
        f"/api/conversations/{conv.id}",
        headers={"Authorization": f"Bearer {second_token}"},
    )
    assert second_resp.status_code == 200
    assert second_resp.json()["id"] == conv.id


def test_private_conversation_is_strictly_inaccessible_to_others(
    client: TestClient, owner_user: UserRecord, second_user: UserRecord
):
    db = next(get_db())
    second_token = create_access_token({"sub": second_user.id, "email": second_user.email})

    conv = ConversationRecord(
        id=str(uuid.uuid4()),
        user_id=owner_user.id,
        title="Private Secret Discussion",
        is_shared=False,
    )
    db.add(conv)
    db.commit()

    # 1. Unauthenticated viewer receives 404
    anon_resp = client.get(f"/api/conversations/{conv.id}")
    assert anon_resp.status_code == 404

    # 2. Different authenticated user receives 404
    second_resp = client.get(
        f"/api/conversations/{conv.id}",
        headers={"Authorization": f"Bearer {second_token}"},
    )
    assert second_resp.status_code == 404


def test_shared_conversation_mutation_remains_owner_only(
    client: TestClient, owner_user: UserRecord, second_user: UserRecord
):
    db = next(get_db())
    second_token = create_access_token({"sub": second_user.id, "email": second_user.email})

    conv = ConversationRecord(
        id=str(uuid.uuid4()),
        user_id=owner_user.id,
        title="Read Only Shared",
        is_shared=True,
    )
    db.add(conv)
    db.commit()

    # Unauthorized second user cannot modify title
    patch_resp = client.patch(
        f"/api/conversations/{conv.id}",
        headers={"Authorization": f"Bearer {second_token}"},
        json={"title": "Hacked Title"},
    )
    assert patch_resp.status_code == 404

    # Unauthorized second user cannot delete
    del_resp = client.delete(
        f"/api/conversations/{conv.id}",
        headers={"Authorization": f"Bearer {second_token}"},
    )
    assert del_resp.status_code == 404


def test_invalid_conversation_id_returns_404(client: TestClient):
    random_id = str(uuid.uuid4())
    resp = client.get(f"/api/conversations/{random_id}")
    assert resp.status_code == 404
