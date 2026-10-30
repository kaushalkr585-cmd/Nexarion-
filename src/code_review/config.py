from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    """Controls logging verbosity."""

    app_name: str = "multi-agent-code-review"
    """Application identifier used in log messages and API responses."""

    debug: bool = False
    """Enables extra validation and verbose error messages in non-production environments."""

    llm_provider: str = "ollama"
    """Active LLM provider ('ollama' or 'nvidia')."""

    llm_model: str = "qwen2.5-coder:7b"
    """Default model name for AI code reviews."""

    llm_base_url: str = "http://localhost:11434"
    """Base URL for the default LLM service endpoint."""

    llm_timeout_seconds: float = 60.0
    """Timeout in seconds for LLM review generation requests."""

    llm_file_concurrency: int = 2
    """Maximum number of changed files sent to the LLM at the same time."""

    llm_temperature: float = 0.1
    """Sampling temperature for LLM review (low values yield deterministic outputs)."""

    ollama_base_url: str = "http://localhost:11434"
    """Base URL for local Ollama instance."""

    ollama_model: str = "qwen2.5-coder:7b"
    """Model name for local Ollama inference."""

    nvidia_api_key: str = ""
    """API key for NVIDIA NIM API."""

    nvidia_model: str = "nvidia/nemotron-3-ultra-550b-a55b"
    """Model identifier for NVIDIA Nemotron."""

    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    """Base endpoint for NVIDIA NIM API."""

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/nexarion_db"
    """PostgreSQL connection string."""

    conversation_memory_enabled: bool = True
    """Whether to retrieve relevant historical conversation context across chats."""

    memory_top_k: int = 5
    """Maximum number of relevant historical memory records to retrieve."""

    memory_token_budget: int = 1500
    """Maximum estimated token budget for historical context injection."""

    memory_similarity_threshold: float = 0.55
    """Minimum semantic similarity threshold for vector matching."""

    memory_summary_turn_threshold: int = 6
    """Number of conversation messages before generating/updating compact summary."""

    embedding_provider: str = "auto"
    """Embedding provider: 'auto', 'ollama', 'nvidia', or 'none'."""

    embedding_model: str = "nomic-embed-text"
    """Embedding model name for vector semantic retrieval."""

    cloudinary_cloud_name: str = ""
    """Cloudinary cloud name for avatar storage."""

    cloudinary_api_key: str = ""
    """Cloudinary API key."""

    cloudinary_api_secret: str = ""
    """Cloudinary API secret."""

    session_secret: str = "nexarion_session_secret_dev_key"
    """Secret used for JWT token signing."""

    google_client_id: str = ""
    """Google OAuth Client ID."""

    google_client_secret: str = ""
    """Google OAuth Client Secret."""

    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    """Google OAuth callback redirect URI."""

    frontend_url: str = "http://localhost:5173"
    """Allowed frontend origin for CORS and redirects."""

    backend_url: str = "http://localhost:8000"
    """Base URL of the backend API service."""

    github_token: str = ""
    """Default or service personal access token for GitHub API."""

    github_client_id: str = ""
    """GitHub OAuth App client ID."""

    github_client_secret: str = ""
    """GitHub OAuth App client secret."""

    github_webhook_secret: str = ""
    """GitHub webhook signature verification secret."""

    github_app_id: str = ""
    """GitHub App ID for bot-driven installation access."""

    github_app_private_key: str = ""
    """GitHub App private RSA key in PEM format or path to key file."""

    github_auto_review: bool = True
    """Whether incoming PR webhooks automatically trigger a multi-agent review."""

    github_post_review_comments: bool = True
    """Whether automated reviews post summary reviews and inline comments back to GitHub."""

    github_set_commit_status: bool = True
    """Whether to publish commit status checks (pending, success, failure) to GitHub."""

    github_dashboard_url: str = ""
    """Publicly accessible URL to NEXARION dashboard for status checks and review links."""

    cache_enabled: bool = True
    """Whether to cache review results to avoid duplicate analysis."""

    cache_backend: Literal["memory", "disk"] = "memory"
    """Cache backend storage type ('memory' or 'disk')."""

    cache_dir: str = ".cache/code_review"
    """Directory for persistent disk cache files."""

    cache_ttl_seconds: float = 86400.0
    """Time-to-live for cached reviews in seconds (default: 24 hours)."""

    cache_max_entries: int = 1000
    """Maximum number of entries in memory cache before LRU eviction."""

    max_concurrency: int = 8
    """Maximum concurrency limit for async parallel agent review execution."""

    max_attachment_size_mb: int = 10
    """Maximum allowed size per document attachment in megabytes."""

    max_attachments_per_message: int = 5
    """Maximum number of attachments allowed per message."""

    attachment_chunk_size_chars: int = 2000
    """Maximum character length per document chunk for large document retrieval."""

    attachment_chunk_overlap_chars: int = 200
    """Character overlap between consecutive chunks for contextual continuity."""

    attachment_retention_days: int = 30
    """Retention duration in days for uploaded document attachments."""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
