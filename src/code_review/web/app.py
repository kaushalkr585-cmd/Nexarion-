import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from code_review.config import get_settings
from code_review.db.database import get_engine, init_database
from code_review.db.init_db import seed_database
from code_review.web.routes import (
    agent_routes,
    auth_routes,
    conversation_routes,
    github_routes,
    overview_routes,
    pr_routes,
    provider_routes,
    review_routes,
    user_routes,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing NEXARION application and database...")
    try:
        init_database()
        engine = get_engine()
        with Session(engine) as session:
            seed_database(session)
        logger.info("NEXARION startup completed.")
    except Exception as exc:
        logger.error("Startup database initialization error: %s", exc)
    yield
    logger.info("NEXARION application shutting down.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="NEXARION — Multi-Agent AI Code Review Platform",
        version="1.0.0",
        description=(
            "Premium multi-agent AI code review platform with Ollama and Nemotron inference."
        ),
        lifespan=lifespan,
    )

    origins = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    if settings.frontend_url and settings.frontend_url not in origins:
        origins.append(settings.frontend_url)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_routes.router, prefix="/api")

    app.include_router(auth_routes.router)
    app.include_router(review_routes.router, prefix="/api")
    app.include_router(overview_routes.router, prefix="/api")
    app.include_router(conversation_routes.router, prefix="/api")
    app.include_router(pr_routes.router, prefix="/api")
    app.include_router(agent_routes.router, prefix="/api")
    app.include_router(provider_routes.router, prefix="/api")
    app.include_router(github_routes.router, prefix="/api")
    app.include_router(user_routes.router, prefix="/api/user")
    app.include_router(user_routes.router, prefix="/api/users")

    avatars_dir = Path("frontend/public/avatars")
    avatars_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/avatars", StaticFiles(directory=avatars_dir), name="avatars")

    @app.get("/health")
    @app.get("/api/health")
    def health_check() -> dict[str, str]:
        return {
            "status": "ok",
            "app": "NEXARION",
            "version": "1.0.0",
            "active_provider": settings.llm_provider,
        }

    frontend_dist = Path("frontend/dist")
    if frontend_dist.is_dir():
        app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = frontend_dist / full_path
            if file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(frontend_dist / "index.html")

    return app
app = create_app()
