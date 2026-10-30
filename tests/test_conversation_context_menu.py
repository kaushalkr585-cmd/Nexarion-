from __future__ import annotations

import uuid

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
    user = db.query(UserRecord).filter_by(email="menu_alpha@nexarion.dev").first()
    if not user:
        user = UserRecord(
            id=str(uuid.uuid4()),
            email="menu_alpha@nexarion.dev",
            name="Menu Alpha",
            github_connected=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture
def user_beta() -> UserRecord:
    db = next(get_db())
    user = db.query(UserRecord).filter_by(email="menu_beta@nexarion.dev").first()
    if not user:
        user = UserRecord(
            id=str(uuid.uuid4()),
            email="menu_beta@nexarion.dev",
            name="Menu Beta",
            github_connected=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture
def auth_headers_alpha(user_alpha: UserRecord) -> dict[str, str]:
    token = create_access_token({"sub": user_alpha.id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_beta(user_beta: UserRecord) -> dict[str, str]:
    token = create_access_token({"sub": user_beta.id})
    return {"Authorization": f"Bearer {token}"}


def test_conversation_rename_valid_and_validation(
    client: TestClient,
    auth_headers_alpha: dict[str, str],
):
    resp = client.post(
        "/api/conversations",
        json={"title": "Original Title"},
        headers=auth_headers_alpha,
    )
    assert resp.status_code == 201
    conv_id = resp.json()["id"]

    patch_resp = client.patch(
        f"/api/conversations/{conv_id}",
        json={"title": "Refactored Core Architecture"},
        headers=auth_headers_alpha,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["title"] == "Refactored Core Architecture"

    empty_resp = client.patch(
        f"/api/conversations/{conv_id}",
        json={"title": "   "},
        headers=auth_headers_alpha,
    )
    assert empty_resp.status_code == 400


def test_conversation_pin_and_unpin(
    client: TestClient,
    auth_headers_alpha: dict[str, str],
):
    resp = client.post(
        "/api/conversations",
        json={"title": "Pin Test"},
        headers=auth_headers_alpha,
    )
    assert resp.status_code == 201
    conv_id = resp.json()["id"]
    assert resp.json()["is_pinned"] is False

    pin_resp = client.patch(
        f"/api/conversations/{conv_id}",
        json={"is_pinned": True},
        headers=auth_headers_alpha,
    )
    assert pin_resp.status_code == 200
    assert pin_resp.json()["is_pinned"] is True

    unpin_resp = client.patch(
        f"/api/conversations/{conv_id}",
        json={"is_pinned": False},
        headers=auth_headers_alpha,
    )
    assert unpin_resp.status_code == 200
    assert unpin_resp.json()["is_pinned"] is False


def test_conversation_archive_and_filtering(
    client: TestClient,
    auth_headers_alpha: dict[str, str],
):
    resp = client.post(
        "/api/conversations",
        json={"title": "Archive Test"},
        headers=auth_headers_alpha,
    )
    assert resp.status_code == 201
    conv_id = resp.json()["id"]

    list_before = client.get("/api/conversations", headers=auth_headers_alpha).json()
    assert any(c["id"] == conv_id for c in list_before)

    arch_resp = client.patch(
        f"/api/conversations/{conv_id}",
        json={"is_archived": True},
        headers=auth_headers_alpha,
    )
    assert arch_resp.status_code == 200
    assert arch_resp.json()["is_archived"] is True

    list_after = client.get("/api/conversations", headers=auth_headers_alpha).json()
    assert not any(c["id"] == conv_id for c in list_after)

    list_with_arch = client.get(
        "/api/conversations?include_archived=true",
        headers=auth_headers_alpha,
    ).json()
    assert any(c["id"] == conv_id for c in list_with_arch)


def test_conversation_section_assignment(
    client: TestClient,
    auth_headers_alpha: dict[str, str],
):
    resp = client.post(
        "/api/conversations",
        json={"title": "Section Test"},
        headers=auth_headers_alpha,
    )
    conv_id = resp.json()["id"]
    assert resp.json()["section_name"] is None

    sec_resp = client.patch(
        f"/api/conversations/{conv_id}",
        json={"section_name": "Sprint 42"},
        headers=auth_headers_alpha,
    )
    assert sec_resp.status_code == 200
    assert sec_resp.json()["section_name"] == "Sprint 42"

    clear_sec_resp = client.patch(
        f"/api/conversations/{conv_id}",
        json={"section_name": None},
        headers=auth_headers_alpha,
    )
    assert clear_sec_resp.status_code == 200
    assert clear_sec_resp.json()["section_name"] is None


def test_conversation_user_isolation(
    client: TestClient,
    auth_headers_alpha: dict[str, str],
    auth_headers_beta: dict[str, str],
):
    resp = client.post(
        "/api/conversations",
        json={"title": "Alpha Private Chat"},
        headers=auth_headers_alpha,
    )
    conv_id = resp.json()["id"]

    beta_patch = client.patch(
        f"/api/conversations/{conv_id}",
        json={"title": "Hacked Title"},
        headers=auth_headers_beta,
    )
    assert beta_patch.status_code == 404

    beta_del = client.delete(
        f"/api/conversations/{conv_id}",
        headers=auth_headers_beta,
    )
    assert beta_del.status_code == 404

    alpha_get = client.get(
        f"/api/conversations/{conv_id}",
        headers=auth_headers_alpha,
    )
    assert alpha_get.status_code == 200
    assert alpha_get.json()["title"] == "Alpha Private Chat"
