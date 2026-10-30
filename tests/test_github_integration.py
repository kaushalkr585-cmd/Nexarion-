from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from code_review.config import get_settings
from code_review.db.database import get_db
from code_review.db.models import FindingRecord, ReviewRecord, UserRecord
from code_review.github.service import GitHubService
from code_review.models.enums import AgentType, Category, Severity
from code_review.models.finding import Finding
from code_review.models.review import ReviewResult
from code_review.orchestrator import ReviewOrchestrator
from code_review.web.app import app
from code_review.web.auth import create_access_token
from code_review.web.routes.github_routes import (
    _PROCESSED_DELIVERIES,
    _is_duplicate_delivery,
    process_github_webhook_pr_review,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    yield from get_db()


@pytest.fixture
def user_a(db_session: Session) -> UserRecord:
    user = db_session.query(UserRecord).filter_by(email="test_gh_user@nexarion.dev").first()
    if not user:
        user = UserRecord(
            id=str(uuid.uuid4()),
            email="test_gh_user@nexarion.dev",
            name="GitHub Test User",
            github_connected=True,
            github_token="ghp_testtoken123",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers_a(user_a: UserRecord) -> dict[str, str]:
    token = create_access_token({"sub": user_a.id, "email": user_a.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_diff() -> str:
    return (
        "diff --git a/src/auth.py b/src/auth.py\n"
        "index 1234567..89abcdef 100644\n"
        "--- a/src/auth.py\n"
        "+++ b/src/auth.py\n"
        "@@ -10,6 +10,8 @@ def authenticate(user, password):\n"
        "     if not user:\n"
        "         return False\n"
        "+    query = f\"SELECT * FROM users WHERE name = '{user}'\"\n"
        "+    execute_sql(query)\n"
        "     return verify_password(password)\n"
    )


class TestWebhookSignatureAndDeduplication:
    def test_verify_webhook_signature_valid(self) -> None:
        secret = "test_webhook_secret_key_123"
        payload = b'{"action": "opened", "number": 42}'
        signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        assert GitHubService.verify_webhook_signature(payload, signature, secret) is True

    def test_verify_webhook_signature_invalid(self) -> None:
        secret = "test_webhook_secret_key_123"
        payload = b'{"action": "opened", "number": 42}'
        bad_sig = "sha256=invalidhash0000000000000000000000000000000000000000000000000000"

        assert GitHubService.verify_webhook_signature(payload, bad_sig, secret) is False

    def test_verify_webhook_signature_malformed(self) -> None:
        secret = "test_webhook_secret_key_123"
        payload = b'{"action": "opened"}'

        assert GitHubService.verify_webhook_signature(payload, None, secret) is False
        assert GitHubService.verify_webhook_signature(payload, "bad_prefix_hash", secret) is False

    def test_delivery_deduplication(self) -> None:
        delivery_id = "delivery-uuid-test-999"
        _PROCESSED_DELIVERIES.clear()

        assert _is_duplicate_delivery(delivery_id) is False
        assert _is_duplicate_delivery(delivery_id) is True
        assert _is_duplicate_delivery(None) is False


class TestGitHubWebhookEndpoint:
    def test_webhook_rejected_when_signature_invalid(self, client: TestClient) -> None:
        with patch.object(get_settings(), "github_webhook_secret", "super_secret"):
            headers = {
                "X-GitHub-Event": "ping",
                "X-Hub-Signature-256": "sha256=wrong_signature_hash",
                "Content-Type": "application/json",
            }
            resp = client.post("/api/github/webhook", content=b'{"zen": "hello"}', headers=headers)
            assert resp.status_code == 401
            assert "Invalid webhook signature" in resp.json()["detail"]

    def test_webhook_ping_event_accepted(self, client: TestClient) -> None:
        secret = "super_secret"
        payload_dict = {"zen": "Approachable is better than simple.", "hook_id": 12345}
        payload = json.dumps(payload_dict).encode()
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        with patch.object(get_settings(), "github_webhook_secret", secret):
            headers = {
                "X-GitHub-Event": "ping",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Delivery": "delivery-ping-001",
                "Content-Type": "application/json",
            }
            resp = client.post("/api/github/webhook", content=payload, headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "pong"
            assert data["zen"] == "Approachable is better than simple."
            assert data["hook_id"] == 12345

    def test_webhook_pr_opened_dispatches_fast_202(self, client: TestClient) -> None:
        secret = "test_secret"
        payload_data = {
            "action": "opened",
            "repository": {
                "name": "backend-core",
                "full_name": "acme/backend-core",
                "owner": {"login": "acme"},
            },
            "pull_request": {
                "number": 105,
                "title": "Add auth middleware",
                "head": {"sha": "c0ffee1234567890abcdef1234567890abcdef12"},
                "base": {"ref": "main"},
                "user": {"login": "octocat"},
            },
        }
        raw_body = json.dumps(payload_data).encode()
        sig = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()

        worker_target = "code_review.web.routes.github_routes.process_github_webhook_pr_review"
        with (
            patch.object(get_settings(), "github_webhook_secret", secret),
            patch(worker_target) as mock_worker,
        ):
            headers = {
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Delivery": "delivery-pr-opened-001",
                "Content-Type": "application/json",
            }
            resp = client.post("/api/github/webhook", content=raw_body, headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "accepted"
            assert data["pull_request"] == 105
            assert data["repository"] == "acme/backend-core"
            mock_worker.assert_called_once()

    def test_webhook_pr_unmonitored_action_ignored(self, client: TestClient) -> None:
        payload_data = {
            "action": "labeled",
            "repository": {"name": "backend-core", "owner": {"login": "acme"}},
            "pull_request": {"number": 105},
        }
        headers = {
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        }
        with patch.object(get_settings(), "github_webhook_secret", ""):
            resp = client.post("/api/github/webhook", json=payload_data, headers=headers)
            assert resp.status_code == 200
            assert resp.json()["status"] == "ignored"
            assert resp.json()["action"] == "labeled"


class TestReviewFormattingAndInlineComments:
    def test_format_pr_review_with_inline_and_suggestions(self, sample_diff: str) -> None:
        service = GitHubService()
        findings = [
            Finding(
                file="src/auth.py",
                line=13,
                severity=Severity.CRITICAL,
                category=Category.SECURITY,
                agent=AgentType.BANDIT,
                message="Possible SQL injection in formatted string",
                suggestion="execute_sql('SELECT * FROM users WHERE name = :user', {'user': user})",
                rule_id="B608",
            ),
            Finding(
                file="src/auth.py",
                line=999,
                severity=Severity.INFO,
                category=Category.CODE_QUALITY,
                agent=AgentType.AST,
                message="Global complexity warning outside of diff",
            ),
        ]

        summary_md, inline_comments, verdict = service.format_pr_review(
            findings=findings,
            owner="acme",
            repo="backend-core",
            pull_number=105,
            diff_text=sample_diff,
            duration_seconds=1.25,
            commit_sha="c0ffee1234",
            dashboard_url="https://nexarion.dev/reviews",
        )

        assert verdict == "REQUEST_CHANGES"

        assert "NEXARION Multi-Agent Code Review — PR #105" in summary_md
        assert "Changes Requested" in summary_md
        assert "`c0ffee1`" in summary_md
        assert "Total Findings" in summary_md
        assert "https://nexarion.dev/reviews" in summary_md

        assert len(inline_comments) == 1
        inline = inline_comments[0]
        assert inline["path"] == "src/auth.py"
        assert inline["line"] == 13
        assert inline["side"] == "RIGHT"
        assert "```suggestion" in inline["body"]
        assert "B608" in inline["body"]

        assert "Structural Findings" in summary_md
        assert "Global complexity warning" in summary_md

    def test_post_pull_request_review_resilience_422_fallback(self) -> None:
        service = GitHubService(token="fake_token")

        mock_422_response = MagicMock()
        mock_422_response.status_code = 422
        mock_422_response.text = (
            '{"message": "Validation Failed", "errors": ["line must be part of diff"]}'
        )

        mock_200_response = MagicMock()
        mock_200_response.status_code = 200
        mock_200_response.json.return_value = {
            "id": 98765,
            "html_url": "https://github.com/acme/repo/pull/1#review-98765",
        }

        def side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            if kwargs.get("json", {}).get("comments"):
                import httpx

                raise httpx.HTTPStatusError(
                    "422 Unprocessable", request=MagicMock(), response=mock_422_response
                )
            return mock_200_response

        with patch("httpx.Client.post", side_effect=side_effect) as mock_post:
            result = service.post_pull_request_review(
                owner="acme",
                repo="backend-core",
                pull_number=105,
                body="Initial review summary",
                event="COMMENT",
                comments=[{"path": "src/auth.py", "line": 42, "body": "Bad line"}],
            )

            assert result["id"] == 98765
            assert mock_post.call_count == 2


class TestCommitStatusAndPublishing:
    def test_create_commit_status(self) -> None:
        service = GitHubService(token="fake_token")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "state": "success",
            "context": "nexarion/multi-agent-review",
        }
        mock_resp.status_code = 201

        with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
            res = service.create_commit_status(
                owner="acme",
                repo="repo-a",
                sha="abc123456",
                state="success",
                description="NEXARION review passed",
                target_url="https://nexarion.dev/review/1",
            )
            assert res["state"] == "success"
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            assert "statuses/abc123456" in call_url

    def test_manual_post_review_endpoint(
        self,
        client: TestClient,
        db_session: Any,
        auth_headers_a: dict[str, str],
        user_a: UserRecord,
    ) -> None:
        user_a.github_connected = True
        user_a.github_token = "ghp_mock_token_for_user_a_12345"
        db_session.commit()

        rev = ReviewRecord(
            user_id=user_a.id,
            repository_name="acme/backend-core",
            pr_identifier="#105",
            title="PR #105: Auth fix",
            diff_content="diff --git a/a.py b/a.py\n+print('hello')",
            provider="ollama",
            model_name="qwen2.5-coder:7b",
            finding_count=1,
            has_critical=False,
            duration_seconds=0.8,
        )
        db_session.add(rev)
        db_session.flush()

        db_session.add(
            FindingRecord(
                review_id=rev.id,
                agent="ast",
                title="Print statement detected",
                description="Remove debug print statement",
                severity="WARNING",
                category="QUALITY",
                file_path="a.py",
                line_start=1,
                line_end=1,
            )
        )
        db_session.commit()

        mock_gh_review = {
            "id": 112233,
            "html_url": "https://github.com/acme/backend-core/pull/105#pullrequestreview-112233",
        }

        with patch.object(GitHubService, "post_pull_request_review", return_value=mock_gh_review):
            resp = client.post(
                "/api/github/repos/acme/backend-core/pulls/105/post-review",
                headers=auth_headers_a,
                json={"review_id": rev.id, "commit_sha": "abc12345"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "published"
            assert data["github_review_id"] == 112233
            assert data["total_findings"] == 1


class TestBackgroundWebhookReviewExecution:
    def test_background_webhook_review_saves_and_publishes(
        self, sample_diff: str, db_session: Any
    ) -> None:
        mock_diff_info = {
            "owner": "acme",
            "repo": "backend-core",
            "number": 105,
            "title": "SQL Injection fix",
            "author": "octocat",
            "state": "open",
            "head_sha": "c0ffee12345",
            "diff": sample_diff,
        }

        mock_rev_id = {"id": 555}
        mock_result = ReviewResult(
            findings=[
                Finding(
                    file="src/auth.py",
                    line=13,
                    severity=Severity.CRITICAL,
                    category=Category.SECURITY,
                    agent=AgentType.BANDIT,
                    message="SQL injection detected",
                    suggestion="Use parameters",
                    rule_id="B608",
                )
            ],
            files_reviewed=1,
            review_time_ms=120,
        )

        with (
            patch.object(GitHubService, "get_pull_request_diff", return_value=mock_diff_info),
            patch.object(GitHubService, "create_commit_status") as mock_status,
            patch.object(
                GitHubService, "post_pull_request_review", return_value=mock_rev_id
            ) as mock_post_rev,
            patch.object(ReviewOrchestrator, "review_diff", return_value=mock_result),
        ):
            process_github_webhook_pr_review(
                owner="acme",
                repo="backend-core",
                pull_number=105,
                pr_title="SQL Injection fix",
                head_sha="c0ffee12345",
                author="octocat",
            )

            review = (
                db_session.query(ReviewRecord)
                .filter(ReviewRecord.repository_name == "acme/backend-core")
                .first()
            )
            assert review is not None
            assert review.pr_identifier == "#105"
            assert len(review.findings) > 0

            assert mock_status.call_count >= 2
            mock_post_rev.assert_called_once()
