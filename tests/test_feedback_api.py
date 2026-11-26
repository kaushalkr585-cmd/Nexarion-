import os
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from code_review.db.database import get_engine, init_database
from code_review.db.models import (
    FeedbackRecord,
    UserRecord,
)
from code_review.services.email_service import send_feedback_notification
from code_review.web.app import create_app
from code_review.web.auth import create_access_token


@pytest.fixture
def client_and_db():
    init_database()
    app = create_app()
    client = TestClient(app)
    engine = get_engine()
    from sqlalchemy.orm import Session

    return client, engine, Session


def test_submit_feedback_and_resend_mock(client_and_db):
    client, engine, session_factory = client_and_db

    with session_factory(engine) as session:
        user = UserRecord(
            email=f"user_{uuid.uuid4().hex[:8]}@example.com",
            name="Test User",
            role="user",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id
        user_token = create_access_token({"sub": user.id, "email": user.email})

    with patch("code_review.web.routes.feedback_routes.send_feedback_notification") as mock_send:
        mock_send.return_value = (True, "msg_test_123", None)

        response = client.post(
            "/api/feedback",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "category": "Visual is unhelpful or broken",
                "details": "The code block overflowed horizontally and cut off text.",
                "conversation_id": "conv-123",
                "message_id": "msg-456",
                "reported_response": "Here is some code snippet that broke.",
            },
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["category"] == "Visual is unhelpful or broken"
        assert data["details"] == "The code block overflowed horizontally and cut off text."
        assert data["user_id"] == user_id
        assert data["status"] == "new"
        assert data["email_notification_status"] == "sent"
        assert data["email_message_id"] == "msg_test_123"
        assert mock_send.called

        # Confirm persisted in DB
        with session_factory(engine) as session:
            fb = session.get(FeedbackRecord, data["id"])
            assert fb is not None
            assert fb.category == "Visual is unhelpful or broken"
            assert fb.email_notification_status == "sent"
            assert fb.email_message_id == "msg_test_123"


def test_simulate_missing_resend_api_key(client_and_db):
    client, engine, session_factory = client_and_db

    with session_factory(engine) as session:
        user = UserRecord(
            email=f"user_{uuid.uuid4().hex[:8]}@example.com",
            name="Test User",
            role="user",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_token = create_access_token({"sub": user.id, "email": user.email})

    with (
        patch.dict(os.environ, {"RESEND_API_KEY": ""}, clear=False),
        patch("code_review.services.email_service.get_settings") as mock_settings,
    ):
        mock_settings.return_value.resend_api_key = ""
        mock_settings.return_value.admin_email = "kaushalkr.585@gmail.com"
        mock_settings.return_value.email_from = "onboarding@resend.dev"
        response = client.post(
            "/api/feedback",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "category": "Incorrect or incomplete",
                "details": "Explanation missed edge case",
                "reported_response": "Broken logic",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email_notification_status"] == "failed"
        assert "RESEND_API_KEY" in data["email_error"]

        # Confirm record is preserved in database despite email failure
        with session_factory(engine) as session:
            fb = session.get(FeedbackRecord, data["id"])
            assert fb is not None
            assert fb.category == "Incorrect or incomplete"
            assert fb.email_notification_status == "failed"


def test_simulate_invalid_api_key(client_and_db):
    client, engine, session_factory = client_and_db

    with session_factory(engine) as session:
        user = UserRecord(
            email=f"user_{uuid.uuid4().hex[:8]}@example.com",
            name="Test User",
            role="user",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_token = create_access_token({"sub": user.id, "email": user.email})

    with patch.dict(os.environ, {"RESEND_API_KEY": "re_invalid_fake_key_123"}):
        with patch("resend.Emails.send") as mock_resend_send:
            mock_resend_send.side_effect = Exception(
                "API key `re_invalid_fake_key_123` is invalid"
            )

            response = client.post(
                "/api/feedback",
                headers={"Authorization": f"Bearer {user_token}"},
                json={
                    "category": "Slow or buggy",
                    "details": "Response took too long to generate",
                    "reported_response": "Laggy reply",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["email_notification_status"] == "failed"
            # Ensure secret key is redacted from error message
            assert "re_invalid_fake_key_123" not in data["email_error"]
            assert "[REDACTED]" in data["email_error"] or "invalid" in data["email_error"]

            # Confirm feedback is NOT lost
            with session_factory(engine) as session:
                fb = session.get(FeedbackRecord, data["id"])
                assert fb is not None
                assert fb.status == "new"
                assert fb.email_notification_status == "failed"


def test_simulate_resend_rejection(client_and_db):
    client, engine, session_factory = client_and_db

    with session_factory(engine) as session:
        user = UserRecord(
            email=f"user_{uuid.uuid4().hex[:8]}@example.com",
            name="Test User",
            role="user",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_token = create_access_token({"sub": user.id, "email": user.email})

    with patch.dict(os.environ, {"RESEND_API_KEY": "re_valid_looking_key"}):
        with patch("resend.Emails.send") as mock_resend_send:
            mock_resend_send.side_effect = Exception(
                "You can only send testing emails to your own email address (owner@domain.com)."
            )

            response = client.post(
                "/api/feedback",
                headers={"Authorization": f"Bearer {user_token}"},
                json={
                    "category": "Other",
                    "details": "Special feedback case",
                    "reported_response": "Sample reply",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["email_notification_status"] == "failed"
            assert "You can only send testing emails" in data["email_error"]

            # Feedback preserved
            with session_factory(engine) as session:
                fb = session.get(FeedbackRecord, data["id"])
                assert fb is not None
                assert fb.email_notification_status == "failed"


def test_resend_no_id_returned_does_not_mark_as_sent():
    with patch.dict(
        os.environ, {"RESEND_API_KEY": "re_sample_123", "ADMIN_EMAIL": "test@admin.com"}
    ):
        with patch("resend.Emails.send") as mock_resend_send:
            mock_resend_send.return_value = {}  # Empty response with no "id"
            success, msg_id, err = send_feedback_notification({"category": "Other"})
            assert success is False
            assert msg_id is None
            assert "confirmed message ID" in err


def test_direct_resend_success():
    with patch.dict(
        os.environ, {"RESEND_API_KEY": "re_sample_123", "ADMIN_EMAIL": "test@admin.com"}
    ):
        with patch("resend.Emails.send") as mock_resend_send:
            mock_resend_send.return_value = {"id": "re_email_success_789"}
            success, msg_id, err = send_feedback_notification(
                {
                    "category": "Visual is unhelpful or broken",
                    "details": "Visual layout issue",
                    "user_email": "coder@user.com",
                    "reported_response": "Broken text",
                }
            )
            assert success is True
            assert msg_id == "re_email_success_789"
            assert err is None


def test_submit_feedback_invalid_category(client_and_db):
    client, engine, session_factory = client_and_db

    with session_factory(engine) as session:
        user = UserRecord(
            email=f"user_{uuid.uuid4().hex[:8]}@example.com",
            name="Test User",
            role="user",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_token = create_access_token({"sub": user.id, "email": user.email})

    response = client.post(
        "/api/feedback",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "category": "Invalid fake category",
            "details": "Some text",
        },
    )

    assert response.status_code == 422


def test_admin_access_control(client_and_db):
    client, engine, session_factory = client_and_db

    with session_factory(engine) as session:
        normal_user = UserRecord(
            email=f"regular_{uuid.uuid4().hex[:8]}@example.com",
            name="Regular User",
            role="user",
        )
        admin_user = UserRecord(
            email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
            name="Admin User",
            role="admin",
        )
        session.add_all([normal_user, admin_user])
        session.commit()
        session.refresh(normal_user)
        session.refresh(admin_user)

        user_token = create_access_token({"sub": normal_user.id, "email": normal_user.email})
        admin_token = create_access_token({"sub": admin_user.id, "email": admin_user.email})

    # 1. Non-admin user gets 403 Forbidden
    resp = client.get("/api/admin/feedback", headers={"Authorization": f"Bearer {user_token}"})
    assert resp.status_code == 403

    resp = client.get(
        "/api/admin/feedback/stats", headers={"Authorization": f"Bearer {user_token}"}
    )
    assert resp.status_code == 403

    # 2. Admin user gets 200 OK
    resp = client.get("/api/admin/feedback", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert "items" in resp.json()

    resp = client.get(
        "/api/admin/feedback/stats", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200
    stats = resp.json()
    assert "total" in stats
    assert "new_count" in stats


def test_admin_update_status(client_and_db):
    client, engine, session_factory = client_and_db

    with session_factory(engine) as session:
        admin_user = UserRecord(
            email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
            name="Admin User",
            role="admin",
        )
        session.add(admin_user)
        session.commit()
        session.refresh(admin_user)
        admin_token = create_access_token({"sub": admin_user.id, "email": admin_user.email})

        # Create a feedback record directly
        record = FeedbackRecord(
            user_id=admin_user.id,
            conversation_ref="conv-abc",
            message_ref="msg-xyz",
            category="Slow or buggy",
            reported_response="test response",
            status="new",
            dedupe_key=f"dedupe_{uuid.uuid4().hex}",
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        record_id = record.id

    # Patch status to "reviewing"
    resp = client.patch(
        f"/api/admin/feedback/{record_id}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "reviewing"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "reviewing"

    # Patch status to "resolved"
    resp = client.patch(
        f"/api/admin/feedback/{record_id}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "resolved"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"


def test_account_deletion_cascades_feedback(client_and_db):
    client, engine, session_factory = client_and_db

    with session_factory(engine) as session:
        user = UserRecord(
            email=f"del_{uuid.uuid4().hex[:8]}@example.com",
            name="User To Delete",
            role="user",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

        record = FeedbackRecord(
            user_id=user_id,
            conversation_ref="conv-1",
            message_ref="msg-1",
            category="Other",
            reported_response="to delete",
            status="new",
            dedupe_key=f"dedupe_{uuid.uuid4().hex}",
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        record_id = record.id

    # Verify record exists
    with session_factory(engine) as session:
        fb = session.get(FeedbackRecord, record_id)
        assert fb is not None

        # Delete user
        u = session.get(UserRecord, user_id)
        session.delete(u)
        session.commit()

        # Feedback should be cascaded
        fb_after = session.get(FeedbackRecord, record_id)
        assert fb_after is None
