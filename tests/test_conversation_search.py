import uuid
import pytest
from fastapi.testclient import TestClient

from code_review.db.database import get_db
from code_review.db.models import ConversationRecord, MessageRecord, UserRecord
from code_review.web.app import app
from code_review.web.auth import create_access_token


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def test_user() -> UserRecord:
    db = next(get_db())
    email = f"search_test_{uuid.uuid4().hex[:8]}@nexarion.dev"
    user = UserRecord(
        id=str(uuid.uuid4()),
        email=email,
        name="Search Tester",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def other_user() -> UserRecord:
    db = next(get_db())
    email = f"search_other_{uuid.uuid4().hex[:8]}@nexarion.dev"
    user = UserRecord(
        id=str(uuid.uuid4()),
        email=email,
        name="Other User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_conversation_search_empty_query(client: TestClient, test_user: UserRecord):
    token = create_access_token({"sub": test_user.id, "email": test_user.email})
    response = client.get(
        "/api/conversations/search?q=",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_conversation_search_title_and_message_matches(
    client: TestClient, test_user: UserRecord, other_user: UserRecord
):
    db = next(get_db())
    token = create_access_token({"sub": test_user.id, "email": test_user.email})
    other_token = create_access_token({"sub": other_user.id, "email": other_user.email})

    unique_keyword = f"QuantumCrypto_{uuid.uuid4().hex[:6]}"

    # Conversation 1: title matches keyword
    conv1 = ConversationRecord(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        title=f"Review of {unique_keyword} Module",
    )
    # Conversation 2: message matches keyword
    conv2 = ConversationRecord(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        title="Architecture Discussion",
    )
    msg2 = MessageRecord(
        id=str(uuid.uuid4()),
        conversation_id=conv2.id,
        role="user",
        content=f"How should we implement the {unique_keyword} protocol in Rust?",
    )
    # Conversation 3: belonging to other_user with the same keyword
    conv3 = ConversationRecord(
        id=str(uuid.uuid4()),
        user_id=other_user.id,
        title=f"Private {unique_keyword} Notes",
    )

    db.add_all([conv1, conv2, conv3])
    db.commit()
    db.add(msg2)
    db.commit()

    # Search as test_user
    res = client.get(
        f"/api/conversations/search?q={unique_keyword}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2

    ids = [item["id"] for item in data]
    assert conv1.id in ids
    assert conv2.id in ids
    assert conv3.id not in ids  # other user's conversation excluded!

    # Check snippet for conv2
    conv2_item = next(item for item in data if item["id"] == conv2.id)
    assert conv2_item["match_type"] == "message"
    assert unique_keyword in conv2_item["snippet"]
    assert conv2_item["role"] == "user"

    # Search as other_user
    res_other = client.get(
        f"/api/conversations/search?q={unique_keyword}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert res_other.status_code == 200
    other_data = res_other.json()
    assert len(other_data) == 1
    assert other_data[0]["id"] == conv3.id


def test_conversation_search_archived_filter(client: TestClient, test_user: UserRecord):
    db = next(get_db())
    token = create_access_token({"sub": test_user.id, "email": test_user.email})
    kw = f"ArchiveTest_{uuid.uuid4().hex[:6]}"

    conv_active = ConversationRecord(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        title=f"Active {kw}",
        is_archived=False,
    )
    conv_archived = ConversationRecord(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        title=f"Archived {kw}",
        is_archived=True,
    )
    db.add_all([conv_active, conv_archived])
    db.commit()

    # Default: include_archived=False
    res = client.get(
        f"/api/conversations/search?q={kw}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    results = res.json()
    assert len(results) == 1
    assert results[0]["id"] == conv_active.id

    # With include_archived=true
    res_all = client.get(
        f"/api/conversations/search?q={kw}&include_archived=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_all.status_code == 200
    results_all = res_all.json()
    assert len(results_all) == 2
