import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from code_review.analysis.document_processor import DocumentProcessor
from code_review.db.database import get_db
from code_review.db.models import UserRecord
from code_review.web.app import app
from code_review.web.auth import create_access_token
from code_review.web.error_normalizer import normalize_ai_error


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def user_alpha() -> UserRecord:
    db = next(get_db())
    user = db.query(UserRecord).filter_by(email="alpha_diff_test@nexarion.dev").first()
    if not user:
        user = UserRecord(
            id=str(uuid.uuid4()),
            email="alpha_diff_test@nexarion.dev",
            name="Alpha Diff Tester",
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

SAMPLE_3_9KB_DIFF = """diff --git a/src/auth/service.py b/src/auth/service.py
index 1234567..89abcde 100644
--- a/src/auth/service.py
+++ b/src/auth/service.py
@@ -10,15 +10,25 @@ import jwt
 from datetime import datetime, timedelta
 from fastapi import HTTPException, status

-def verify_token(token: str) -> dict:
-    try:
-        payload = jwt.decode(token, "SECRET_KEY", algorithms=["HS256"])
-        return payload
-    except jwt.PyJWTError:
-        raise HTTPException(status_code=401, detail="Invalid token")
+def verify_token(token: str, secret_key: str, allowed_algorithms: list[str]) -> dict:
+    if not token or not secret_key:
+        raise HTTPException(
+            status_code=status.HTTP_401_UNAUTHORIZED,
+            detail="Authentication token and secret key are required."
+        )
+    try:
+        payload = jwt.decode(
+            token,
+            secret_key,
+            algorithms=allowed_algorithms or ["HS256"],
+            options={"verify_exp": True, "require": ["exp", "sub", "iat"]}
+        )
+        return payload
+    except jwt.ExpiredSignatureError:
+        raise HTTPException(status_code=401, detail="Token expired")
+    except jwt.PyJWTError as exc:
+        raise HTTPException(status_code=401, detail=f"Invalid: {exc}")

 def generate_session_token(user_id: str, secret: str, ttl_hours: int = 24) -> str:
     now = datetime.utcnow()
@@ -45,20 +55,30 @@ def generate_session_token(user_id: str, secret: str, ttl_hours: int = 24) -> s
     return jwt.encode(payload, secret, algorithm="HS256")
+
+def revoke_user_sessions(user_id: str, redis_client) -> bool:
+    \"\"\"Blacklist all active sessions for a compromised user account.\"\"\"
+    key = f"revoked_user:{user_id}"
+    try:
+        redis_client.setex(key, timedelta(days=7), "revoked")
+        return True
+    except Exception as exc:
+        logger.error("Failed to revoke session in redis: %s", exc)
+        return False
diff --git a/src/database/connection.py b/src/database/connection.py
index aaaaaaa..bbbbbbb 100644
--- a/src/database/connection.py
+++ b/src/database/connection.py
@@ -30,12 +30,22 @@ class DatabaseManager:
     def get_connection(self):
-        return self._pool.acquire()
+        try:
+            conn = self._pool.acquire(timeout=5.0)
+            if not conn.is_healthy():
+                self._pool.evict(conn)
+                conn = self._pool.acquire(timeout=5.0)
+            return conn
+        except TimeoutError:
+            logger.error("Connection pool exhausted under heavy load")
+            raise HTTPException(status_code=503, detail="Database busy")
+
+    def release_connection(self, conn):
+        if conn is not None:
+            self._pool.release(conn)
""" + ("\n# Additional padding comments to ensure realistic 3.9 KB payload size\n" * 25)


def test_diff_attachment_upload_and_extraction(
    client: TestClient, auth_headers_alpha: dict[str, str]
):
    diff_bytes = SAMPLE_3_9KB_DIFF.encode("utf-8")
    resp = client.post(
        "/api/conversations/attachments/upload",
        files={"file": ("feature_auth_fix.diff", diff_bytes, "text/x-diff")},
        headers=auth_headers_alpha,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["filename"] == "feature_auth_fix.diff"
    assert data["file_type"] == "diff"
    assert data["mime_type"] == "text/x-diff"
    assert data["file_size"] == len(diff_bytes)
    assert "id" in data


def test_patch_attachment_upload(client: TestClient, auth_headers_alpha: dict[str, str]):
    patch_bytes = SAMPLE_3_9KB_DIFF.encode("utf-8")
    resp = client.post(
        "/api/conversations/attachments/upload",
        files={"file": ("bugfix.patch", patch_bytes, "text/plain")},
        headers=auth_headers_alpha,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["filename"] == "bugfix.patch"
    assert data["file_type"] == "diff"


def test_build_document_context_block_preserves_full_diff():
    att = MagicMock(
        filename="critical_fix.diff",
        file_type="diff",
        page_count=1,
        chunks=[
            {"content": SAMPLE_3_9KB_DIFF[:2000], "page_number": 1, "chunk_index": 0},
            {"content": SAMPLE_3_9KB_DIFF[2000:], "page_number": 1, "chunk_index": 1},
        ],
        extracted_text=SAMPLE_3_9KB_DIFF,
    )

    block = DocumentProcessor.build_document_context_block([att], query="inspect this diff")
    assert "### Attached Diff File: critical_fix.diff" in block
    assert "```diff" in block
    assert "verify_token" in block
    assert "revoke_user_sessions" in block
    assert "DatabaseManager" in block


def test_create_conversation_stream_with_diff_attachment(
    client: TestClient, auth_headers_alpha: dict[str, str]
):
    diff_bytes = SAMPLE_3_9KB_DIFF.encode("utf-8")
    up_resp = client.post(
        "/api/conversations/attachments/upload",
        files={"file": ("changes.diff", diff_bytes, "text/x-diff")},
        headers=auth_headers_alpha,
    )
    assert up_resp.status_code == 201
    att_id = up_resp.json()["id"]

    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    tokens = ["The diff ", "improves ", "token verification security."]
    mock_llm.stream_chat.return_value = iter(tokens)

    with patch("code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm):
        stream_resp = client.post(
            "/api/conversations/stream",
            json={
                "initial_message": "Please inspect this diff and identify any security flaws.",
                "attachment_ids": [att_id],
                "provider": "nvidia",
            },
            headers=auth_headers_alpha,
        )
        assert stream_resp.status_code == 200
        body = stream_resp.text
        assert "event: token" in body
        assert "The diff " in body
        assert "event: done" in body

        assert mock_llm.stream_chat.called
        call_args = mock_llm.stream_chat.call_args[0][0]
        sys_msg = call_args[0]["content"]
        assert "### Attached Diff File: changes.diff" in sys_msg
        assert "verify_token" in sys_msg
        assert "revoke_user_sessions" in sys_msg


def test_send_message_stream_with_diff_attachment(
    client: TestClient, auth_headers_alpha: dict[str, str]
):
    conv_resp = client.post(
        "/api/conversations",
        json={"title": "Diff Review Thread"},
        headers=auth_headers_alpha,
    )
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["id"]

    diff_bytes = SAMPLE_3_9KB_DIFF.encode("utf-8")
    up_resp = client.post(
        f"/api/conversations/{conv_id}/attachments/upload",
        files={"file": ("database_fix.patch", diff_bytes, "text/x-diff")},
        headers=auth_headers_alpha,
    )
    assert up_resp.status_code == 201
    att_id = up_resp.json()["id"]

    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    tokens = ["Review: ", "Database connection ", "pooling looks resilient."]
    mock_llm.stream_chat.return_value = iter(tokens)

    with patch("code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm):
        stream_resp = client.post(
            f"/api/conversations/{conv_id}/messages/stream",
            json={
                "content": "Can you review this database patch?",
                "attachment_ids": [att_id],
                "provider": "ollama",
            },
            headers=auth_headers_alpha,
        )
        assert stream_resp.status_code == 200
        body = stream_resp.text
        assert "event: token" in body
        assert "pooling looks resilient." in body
        assert "event: done" in body

        call_args = mock_llm.stream_chat.call_args[0][0]
        sys_msg = call_args[0]["content"]
        assert "### Attached Diff File: database_fix.patch" in sys_msg
        assert "DatabaseManager" in sys_msg


def test_inline_diff_synthetic_id_does_not_fail_lookup(
    client: TestClient, auth_headers_alpha: dict[str, str]
):
    conv_resp = client.post(
        "/api/conversations",
        json={"title": "Inline Diff Thread"},
        headers=auth_headers_alpha,
    )
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["id"]

    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.stream_chat.return_value = iter(["Clean review"])

    with patch("code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm):
        stream_resp = client.post(
            f"/api/conversations/{conv_id}/messages/stream",
            json={
                "content": "Review this inline diff snippet",
                "diff_context": "+def add(a, b): return a + b",
                "attachment_ids": ["inline-diff-171234567890"],
                "provider": "nvidia",
            },
            headers=auth_headers_alpha,
        )
        assert stream_resp.status_code == 200
        assert "Clean review" in stream_resp.text


def test_anonymous_upload_claimed_by_authenticated_conversation(
    client: TestClient, auth_headers_alpha: dict[str, str]
):
    diff_bytes = b"--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-old\n+new\n"
    up_resp = client.post(
        "/api/conversations/attachments/upload",
        files={"file": ("anonymous.diff", diff_bytes, "text/x-diff")},
    )
    assert up_resp.status_code == 201
    att_id = up_resp.json()["id"]

    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.stream_chat.return_value = iter(["Diff analyzed"])

    with patch("code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm):
        stream_resp = client.post(
            "/api/conversations/stream",
            json={
                "initial_message": "Check anonymous diff",
                "attachment_ids": [att_id],
                "provider": "nvidia",
            },
            headers=auth_headers_alpha,
        )
        assert stream_resp.status_code == 200
        assert "Diff analyzed" in stream_resp.text


def test_error_normalizer_attachment_error_classification():
    err_att_not_found = Exception(
        "One or more specified attachments were not found or access is denied."
    )
    norm1 = normalize_ai_error(err_att_not_found, "nvidia")
    assert norm1.error_code == "ATTACHMENT_NOT_FOUND"
    assert "attached file could not be found" in norm1.user_message.lower()
    assert "model isn't configured" not in norm1.user_message.lower()

    err_unsupported = Exception("Unsupported file type '.exe'")
    norm2 = normalize_ai_error(err_unsupported, "ollama")
    assert norm2.error_code == "UNSUPPORTED_ATTACHMENT_TYPE"
    assert "not supported" in norm2.user_message.lower()
    assert "model isn't configured" not in norm2.user_message.lower()

    err_decode = Exception("Could not decode text file using supported character encodings")
    norm3 = normalize_ai_error(err_decode, "nvidia")
    assert norm3.error_code == "FILE_DECODING_ERROR"
    assert "could not read the attached file" in norm3.user_message.lower()
    assert "model isn't configured" not in norm3.user_message.lower()

    err_model = Exception("Model 'unknown-model-xyz' not found in registry")
    norm4 = normalize_ai_error(err_model, "nvidia")
    assert norm4.error_code == "INVALID_MODEL_CONFIG"
    assert "model isn't configured correctly" in norm4.user_message.lower()
