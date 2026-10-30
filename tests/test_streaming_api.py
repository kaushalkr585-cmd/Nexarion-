from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from code_review.web.app import app


def test_send_message_stream_endpoint():
    client = TestClient(app)

    c_resp = client.post(
        "/api/conversations", json={"title": "Stream Test", "initial_message": "Hello"}
    )
    assert c_resp.status_code == 201
    conv_id = c_resp.json()["id"]

    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.stream_chat.return_value = iter(["Hello", " from", " real", " streaming!"])

    with patch("code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm):
        resp = client.post(
            f"/api/conversations/{conv_id}/messages/stream",
            json={"content": "Can you stream this?"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        body = resp.text
        assert "event: token" in body
        assert "Hello" in body
        assert "streaming!" in body
        assert "event: done" in body
        assert conv_id in body


def test_stream_error_normalization():
    client = TestClient(app)
    c_resp = client.post(
        "/api/conversations", json={"title": "Error Test", "initial_message": "Init"}
    )
    conv_id = c_resp.json()["id"]

    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True

    def fail_stream(*args, **kwargs):
        raise TimeoutError("Connection to NVIDIA NIM timed out after 40.0s")

    mock_llm.stream_chat.side_effect = fail_stream

    with patch("code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm):
        resp = client.post(
            f"/api/conversations/{conv_id}/messages/stream",
            json={"content": "Trigger timeout"},
        )
        assert resp.status_code == 200
        body = resp.text
        assert "event: error" in body
        assert "NEXARION couldn't get a response in time. Please try again." in body

        assert "nvidia" not in body.lower()
        assert "nim" not in body.lower()


def test_create_conversation_stream_first_message_lifecycle():
    client = TestClient(app)

    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.stream_chat.return_value = iter(["Hello! ", "I am NEXARION, ", "ready to assist."])

    with patch("code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm):
        resp = client.post(
            "/api/conversations/stream",
            json={"initial_message": "hi", "title": "New Discussion"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        body = resp.text
        assert "event: init" in body
        assert "event: token" in body
        assert "event: done" in body
        assert "Hello! " in body
        assert "ready to assist." in body

        init_line = [line for line in body.split("\n") if line.startswith('data: {"id":')][0]
        import json

        init_data = json.loads(init_line[6:])
        conv_id = init_data["id"]
        assert isinstance(conv_id, str) and len(conv_id) > 0

        hist_resp = client.get(f"/api/conversations/{conv_id}")
        assert hist_resp.status_code == 200
        conv_data = hist_resp.json()
        assert conv_data["id"] == conv_id
        assert len(conv_data["messages"]) == 2
        assert conv_data["messages"][0]["role"] == "user"
        assert conv_data["messages"][0]["content"] == "hi"
        assert conv_data["messages"][1]["role"] == "assistant"
        assert conv_data["messages"][1]["content"] == "Hello! I am NEXARION, ready to assist."


def test_multi_turn_conversation_stream_preserves_order_and_uniqueness():
    client = TestClient(app)

    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True

    mock_llm.stream_chat.return_value = iter(["First assistant response."])
    with patch("code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm):
        resp1 = client.post("/api/conversations/stream", json={"initial_message": "Prompt 1"})
        assert resp1.status_code == 200
        body1 = resp1.text
        init_line = [line for line in body1.split("\n") if line.startswith('data: {"id":')][0]
        import json

        conv_id = json.loads(init_line[6:])["id"]

    mock_llm.stream_chat.return_value = iter(["Second assistant response."])
    with patch("code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm):
        resp2 = client.post(
            f"/api/conversations/{conv_id}/messages/stream",
            json={"content": "Prompt 2"},
        )
        assert resp2.status_code == 200

    hist_resp = client.get(f"/api/conversations/{conv_id}")
    assert hist_resp.status_code == 200
    messages = hist_resp.json()["messages"]
    assert len(messages) == 4
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[0]["content"] == "Prompt 1"
    assert messages[1]["content"] == "First assistant response."
    assert messages[2]["content"] == "Prompt 2"
    assert messages[3]["content"] == "Second assistant response."
