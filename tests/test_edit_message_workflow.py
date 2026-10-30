from __future__ import annotations

import uuid
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from code_review.db.database import get_db
from code_review.db.models import UserRecord
from code_review.web.app import app
from code_review.web.auth import create_access_token


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def user_alpha() -> UserRecord:
    db = next(get_db())
    user = db.query(UserRecord).filter_by(email="alpha_editor@nexarion.dev").first()
    if not user:
        user = UserRecord(
            id=str(uuid.uuid4()),
            email="alpha_editor@nexarion.dev",
            name="Alpha Editor",
            github_connected=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture
def user_beta() -> UserRecord:
    db = next(get_db())
    user = db.query(UserRecord).filter_by(email="beta_editor@nexarion.dev").first()
    if not user:
        user = UserRecord(
            id=str(uuid.uuid4()),
            email="beta_editor@nexarion.dev",
            name="Beta Editor",
            github_connected=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture
def auth_headers_alpha(user_alpha: UserRecord) -> dict[str, str]:
    token = create_access_token({"sub": user_alpha.id, "email": user_alpha.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_beta(user_beta: UserRecord) -> dict[str, str]:
    token = create_access_token({"sub": user_beta.id, "email": user_beta.email})
    return {"Authorization": f"Bearer {token}"}


def test_edit_message_stream_workflow_and_regeneration(
    client: TestClient, auth_headers_alpha: dict[str, str]
):
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True

    mock_llm.chat.return_value = "```python\ndef add(a, b):\n    return a + b\n```"

    with patch(
        "code_review.web.routes.conversation_routes.get_llm_client",
        return_value=mock_llm,
    ):
        create_resp = client.post(
            "/api/conversations",
            json={
                "title": "Math Helpers",
                "initial_message": "Write a Python function to add two numbers",
            },
            headers=auth_headers_alpha,
        )
        assert create_resp.status_code == 201
        conv_data = create_resp.json()
        conv_id = conv_data["id"]
        user_msg_id = conv_data["messages"][0]["id"]
        old_asst_id = conv_data["messages"][1]["id"]
        assert "add(a, b)" in conv_data["messages"][1]["content"]

        def mock_stream(payload) -> Generator[str, None, None]:
            user_prompts = [m["content"] for m in payload if m.get("role") == "user"]
            assert "Write a Python function to multiply two numbers" in user_prompts
            assert "Write a Python function to add two numbers" not in user_prompts
            yield "```python\n"
            yield "def multiply(a, b):\n"
            yield "    return a * b\n"
            yield "```"

        mock_llm.stream_chat.side_effect = mock_stream

        edit_payload = {
            "content": "Write a Python function to multiply two numbers",
        }
        stream_resp = client.post(
            f"/api/conversations/{conv_id}/messages/{user_msg_id}/edit/stream",
            json=edit_payload,
            headers=auth_headers_alpha,
        )
        assert stream_resp.status_code == 200
        assert "text/event-stream" in stream_resp.headers["content-type"]

        raw_text = stream_resp.text
        assert "event: token" in raw_text
        assert "event: done" in raw_text
        assert "multiply" in raw_text

        get_resp = client.get(
            f"/api/conversations/{conv_id}",
            headers=auth_headers_alpha,
        )
        assert get_resp.status_code == 200
        refreshed_conv = get_resp.json()
        messages = refreshed_conv["messages"]

        assert len(messages) == 2

        assert messages[0]["id"] == user_msg_id
        assert messages[0]["content"] == "Write a Python function to multiply two numbers"

        assert messages[1]["role"] == "assistant"
        assert messages[1]["id"] != old_asst_id
        assert "multiply(a, b)" in messages[1]["content"]
        assert "add(a, b)" not in messages[1]["content"]


def test_edit_subsequent_messages_truncated(
    client: TestClient, auth_headers_alpha: dict[str, str]
):
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.chat.return_value = "Turn 1 original assistant response."

    with patch(
        "code_review.web.routes.conversation_routes.get_llm_client",
        return_value=mock_llm,
    ):
        create_resp = client.post(
            "/api/conversations",
            json={"title": "Multi Turn", "initial_message": "Turn 1 Prompt"},
            headers=auth_headers_alpha,
        )
        conv_id = create_resp.json()["id"]
        turn_1_user_id = create_resp.json()["messages"][0]["id"]

        mock_llm.chat.return_value = "Turn 2 assistant response."
        msg_resp = client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "Turn 2 question"},
            headers=auth_headers_alpha,
        )
        assert len(msg_resp.json()["messages"]) == 4

        def mock_stream(payload) -> Generator[str, None, None]:
            yield "Regenerated Turn 1 assistant reply."

        mock_llm.stream_chat.side_effect = mock_stream

        stream_resp = client.post(
            f"/api/conversations/{conv_id}/messages/{turn_1_user_id}/edit/stream",
            json={"content": "Edited Turn 1 Prompt"},
            headers=auth_headers_alpha,
        )
        assert stream_resp.status_code == 200

        get_resp = client.get(
            f"/api/conversations/{conv_id}",
            headers=auth_headers_alpha,
        )
        msgs = get_resp.json()["messages"]
        assert len(msgs) == 2
        assert msgs[0]["id"] == turn_1_user_id
        assert msgs[0]["content"] == "Edited Turn 1 Prompt"
        assert msgs[1]["content"] == "Regenerated Turn 1 assistant reply."


def test_edit_middle_turn_preserves_earlier_messages(
    client: TestClient, auth_headers_alpha: dict[str, str]
):
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.chat.return_value = "Turn 1 Reply"

    with patch(
        "code_review.web.routes.conversation_routes.get_llm_client",
        return_value=mock_llm,
    ):
        create_resp = client.post(
            "/api/conversations",
            json={"title": "Three Turns", "initial_message": "Turn 1 User Prompt"},
            headers=auth_headers_alpha,
        )
        conv_id = create_resp.json()["id"]

        mock_llm.chat.return_value = "Turn 2 Reply"
        t2_resp = client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "Turn 2 User Prompt"},
            headers=auth_headers_alpha,
        )
        turn_2_user_id = t2_resp.json()["messages"][2]["id"]

        mock_llm.chat.return_value = "Turn 3 Reply"
        client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "Turn 3 User Prompt"},
            headers=auth_headers_alpha,
        )

        def mock_stream(payload) -> Generator[str, None, None]:
            user_prompts = [m["content"] for m in payload if m.get("role") == "user"]
            assert "Turn 1 User Prompt" in user_prompts
            assert "Edited Turn 2 User Prompt" in user_prompts
            yield "New Turn 2 Reply"

        mock_llm.stream_chat.side_effect = mock_stream

        client.post(
            f"/api/conversations/{conv_id}/messages/{turn_2_user_id}/edit/stream",
            json={"content": "Edited Turn 2 User Prompt"},
            headers=auth_headers_alpha,
        )

        get_resp = client.get(
            f"/api/conversations/{conv_id}",
            headers=auth_headers_alpha,
        )
        msgs = get_resp.json()["messages"]

        assert len(msgs) == 4
        assert msgs[0]["content"] == "Turn 1 User Prompt"
        assert msgs[1]["content"] == "Turn 1 Reply"
        assert msgs[2]["id"] == turn_2_user_id
        assert msgs[2]["content"] == "Edited Turn 2 User Prompt"
        assert msgs[3]["content"] == "New Turn 2 Reply"


def test_edit_message_validation_empty_content(
    client: TestClient, auth_headers_alpha: dict[str, str]
):
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.chat.return_value = "Initial response"

    with patch(
        "code_review.web.routes.conversation_routes.get_llm_client",
        return_value=mock_llm,
    ):
        create_resp = client.post(
            "/api/conversations",
            json={"title": "Validation Test", "initial_message": "Valid prompt"},
            headers=auth_headers_alpha,
        )
        conv_id = create_resp.json()["id"]
        user_msg_id = create_resp.json()["messages"][0]["id"]

        err_resp = client.post(
            f"/api/conversations/{conv_id}/messages/{user_msg_id}/edit/stream",
            json={"content": "   \n\t   "},
            headers=auth_headers_alpha,
        )
        assert err_resp.status_code == 400
        assert "Message content cannot be empty" in err_resp.json()["detail"]


def test_edit_message_user_isolation(
    client: TestClient,
    auth_headers_alpha: dict[str, str],
    auth_headers_beta: dict[str, str],
):
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.chat.return_value = "Alpha response"

    with patch(
        "code_review.web.routes.conversation_routes.get_llm_client",
        return_value=mock_llm,
    ):
        create_resp = client.post(
            "/api/conversations",
            json={"title": "Alpha Private", "initial_message": "Alpha secret"},
            headers=auth_headers_alpha,
        )
        conv_id = create_resp.json()["id"]
        user_msg_id = create_resp.json()["messages"][0]["id"]

        forbidden_resp = client.post(
            f"/api/conversations/{conv_id}/messages/{user_msg_id}/edit/stream",
            json={"content": "Hacked content"},
            headers=auth_headers_beta,
        )
        assert forbidden_resp.status_code == 404


def test_cannot_edit_assistant_message(client: TestClient, auth_headers_alpha: dict[str, str]):
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.chat.return_value = "Assistant text"

    with patch(
        "code_review.web.routes.conversation_routes.get_llm_client",
        return_value=mock_llm,
    ):
        create_resp = client.post(
            "/api/conversations",
            json={"title": "Role Test", "initial_message": "User text"},
            headers=auth_headers_alpha,
        )
        conv_id = create_resp.json()["id"]
        asst_msg_id = create_resp.json()["messages"][1]["id"]

        bad_role_resp = client.post(
            f"/api/conversations/{conv_id}/messages/{asst_msg_id}/edit/stream",
            json={"content": "Attempt edit assistant"},
            headers=auth_headers_alpha,
        )
        assert bad_role_resp.status_code == 400
        assert "Only user messages can be edited" in bad_role_resp.json()["detail"]


def test_regenerate_when_conversation_ends_with_user_prompt(
    client: TestClient, auth_headers_alpha: dict[str, str]
):
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.chat.return_value = "Reply 1"

    with patch(
        "code_review.web.routes.conversation_routes.get_llm_client",
        return_value=mock_llm,
    ):
        create_resp = client.post(
            "/api/conversations",
            json={"title": "Retry Test", "initial_message": "Original"},
            headers=auth_headers_alpha,
        )
        conv_id = create_resp.json()["id"]
        user_msg_id = create_resp.json()["messages"][0]["id"]

        mock_llm.stream_chat.side_effect = RuntimeError("GPU server unavailable")

        fail_stream_resp = client.post(
            f"/api/conversations/{conv_id}/messages/{user_msg_id}/edit/stream",
            json={"content": "Updated Prompt with retry"},
            headers=auth_headers_alpha,
        )
        assert fail_stream_resp.status_code == 200
        assert "event: error" in fail_stream_resp.text

        conv_rec = client.get(
            f"/api/conversations/{conv_id}",
            headers=auth_headers_alpha,
        ).json()
        assert len(conv_rec["messages"]) == 1
        assert conv_rec["messages"][0]["content"] == "Updated Prompt with retry"

        def recover_stream(payload) -> Generator[str, None, None]:
            yield "Recovered assistant answer."

        mock_llm.stream_chat.side_effect = recover_stream

        regen_resp = client.post(
            f"/api/conversations/{conv_id}/regenerate/stream",
            json={"message_id": "temp-asst-12345"},
            headers=auth_headers_alpha,
        )
        assert regen_resp.status_code == 200
        assert "event: token" in regen_resp.text
        assert "Recovered assistant answer" in regen_resp.text

        final_conv = client.get(
            f"/api/conversations/{conv_id}",
            headers=auth_headers_alpha,
        ).json()
        assert len(final_conv["messages"]) == 2
        assert final_conv["messages"][1]["content"] == "Recovered assistant answer."
