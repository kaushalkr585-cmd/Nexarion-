from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from code_review.db.init_db import seed_database
from code_review.db.models import AgentConfigRecord
from code_review.web.app import app, create_app


def test_health_check_endpoints():
    client = TestClient(app)

    resp1 = client.get("/health")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "ok"
    assert data1["app"] == "NEXARION"
    assert "version" in data1
    assert "active_provider" in data1

    resp2 = client.get("/api/health")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "ok"


def test_seed_database_execution():
    mock_db = MagicMock()

    mock_db.query.return_value.filter_by.return_value.first.return_value = None
    seed_database(mock_db)
    assert mock_db.add.called
    assert mock_db.commit.called

    mock_db.reset_mock()
    existing_agent = AgentConfigRecord(
        agent_id="ast",
        name="AST",
        description="",
    )
    mock_db.query.return_value.filter_by.return_value.first.return_value = existing_agent
    seed_database(mock_db)
    assert not mock_db.add.called


def test_spa_static_file_serving(tmp_path: Path):
    dist_dir = tmp_path / "frontend" / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)

    index_html = dist_dir / "index.html"
    index_html.write_text("<!DOCTYPE html><html><body><h1>NEXARION SPA</h1></body></html>")

    sample_css = assets_dir / "main.css"
    sample_css.write_text("body { background: #000; }")

    import unittest.mock

    with unittest.mock.patch("code_review.web.app.Path") as mock_path:
        def path_side_effect(arg):
            if arg == "frontend/dist":
                return dist_dir
            if arg == "frontend/public/avatars":
                avatars = tmp_path / "avatars"
                avatars.mkdir(parents=True, exist_ok=True)
                return avatars
            return Path(arg)

        mock_path.side_effect = path_side_effect
        custom_app = create_app()
        client = TestClient(custom_app)

        css_resp = client.get("/assets/main.css")
        assert css_resp.status_code == 200
        assert "background: #000" in css_resp.text

        spa_resp = client.get("/dashboard/overview")
        assert spa_resp.status_code == 200
        assert "NEXARION SPA" in spa_resp.text


def test_dockerfile_integrity():
    dockerfile_path = Path("Dockerfile")
    assert dockerfile_path.is_file(), "Dockerfile must exist at repository root"

    content = dockerfile_path.read_text(encoding="utf-8")

    assert "FROM node:20-alpine AS frontend-builder" in content
    assert "FROM python:3.12-slim-bookworm AS runtime" in content

    assert "useradd" in content
    assert "USER appuser" in content

    assert "HEALTHCHECK" in content
    assert "EXPOSE 8000" in content
    assert "uvicorn" in content


def test_docker_compose_integrity():
    compose_path = Path("docker-compose.yml")
    assert compose_path.is_file(), "docker-compose.yml must exist at repository root"

    content = compose_path.read_text(encoding="utf-8")
    assert "postgres:" in content
    assert "backend:" in content
    assert "ollama:" in content
    assert "postgres_data:" in content
    assert "healthcheck:" in content


def test_ci_workflow_integrity():
    ci_path = Path(".github/workflows/ci.yml")
    assert ci_path.is_file(), "ci.yml must exist under .github/workflows/"

    content = ci_path.read_text(encoding="utf-8")
    assert "lint-and-format:" in content
    assert "security-scan:" in content
    assert "backend-tests:" in content
    assert "frontend-tests:" in content
    assert "docker-build:" in content
    assert "ruff check" in content
    assert "bandit -r" in content
    assert "pytest --cov" in content
