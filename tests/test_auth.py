from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from code_review.db.database import get_db
from code_review.db.models import UserRecord
from code_review.web.app import app
from code_review.web.auth import decode_access_token


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


def test_get_google_auth_url(client: TestClient) -> None:
    resp = client.get("/api/auth/google/url?origin=http://localhost:5173")
    assert resp.status_code == 200
    data = resp.json()
    assert "url" in data
    assert "accounts.google.com" in data["url"]
    assert "client_id=" in data["url"]
    assert "state=" in data["url"]
    assert "redirect_uri=" in data["url"]


def test_google_callback_error_handling(client: TestClient) -> None:
    resp = client.get(
        "/auth/google/callback?error=access_denied&error_description=User+denied+access"
    )
    assert resp.status_code == 307 or resp.status_code == 302
    location = resp.headers["location"]
    assert "auth_error=" in location


def test_google_callback_missing_code(client: TestClient) -> None:
    resp = client.get("/auth/google/callback")
    assert resp.status_code == 307 or resp.status_code == 302
    assert "missing_authorization_code" in resp.headers["location"]


def test_google_callback_success_creates_user_and_session(client: TestClient) -> None:
    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {
        "access_token": "mock_google_access_token_123",
        "id_token": "mock_id_token",
    }

    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.status_code = 200
    mock_userinfo_resp.json.return_value = {
        "sub": "google-sub-999888777",
        "email": "new_developer@company.com",
        "email_verified": True,
        "name": "Jane Coder",
        "picture": "https://example.com/avatar.jpg",
    }

    with patch("httpx.Client") as mock_client_cls:
        mock_http = MagicMock()
        mock_http.post.return_value = mock_token_resp
        mock_http.get.return_value = mock_userinfo_resp
        mock_client_cls.return_value.__enter__.return_value = mock_http

        resp = client.get("/auth/google/callback?code=valid_test_code_456")

        assert resp.status_code == 302
        location = resp.headers["location"]
        assert "?token=" in location

        assert "nexarion_session" in resp.cookies
        token = resp.cookies["nexarion_session"]
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["email"] == "new_developer@company.com"

        db = next(get_db())
        user = db.query(UserRecord).filter_by(google_id="google-sub-999888777").first()
        assert user is not None
        assert user.email == "new_developer@company.com"
        assert user.name == "Jane Coder"
        assert user.avatar_url == "https://example.com/avatar.jpg"
        assert user.auth_provider == "google"


def test_google_callback_links_existing_verified_user(client: TestClient) -> None:
    db = next(get_db())
    existing = db.query(UserRecord).filter_by(email="kushal@example.com").first()
    assert existing is not None

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "mock_token_abc"}

    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.status_code = 200
    mock_userinfo_resp.json.return_value = {
        "sub": "google-sub-kushal-12345",
        "email": "kushal@example.com",
        "email_verified": True,
        "name": "Kushal Kumar",
        "picture": "https://example.com/kushal.png",
    }

    with patch("httpx.Client") as mock_client_cls:
        mock_http = MagicMock()
        mock_http.post.return_value = mock_token_resp
        mock_http.get.return_value = mock_userinfo_resp
        mock_client_cls.return_value.__enter__.return_value = mock_http

        resp = client.get("/auth/google/callback?code=link_code_789")
        assert resp.status_code == 302

        db.refresh(existing)
        assert existing.google_id == "google-sub-kushal-12345"


def test_logout_clears_cookie(client: TestClient) -> None:
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200

    cookie = resp.headers.get("set-cookie", "")
    assert "nexarion_session" in cookie
