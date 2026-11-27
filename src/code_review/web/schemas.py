from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

ChatMode = Literal["normal", "github"]


def _validate_optional_chat_mode(value: Any) -> ChatMode | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid chat mode: must be 'normal' or 'github'.")
    cleaned = value.strip().lower()
    if cleaned not in ("normal", "github"):
        raise ValueError("Invalid chat mode: must be 'normal' or 'github'.")
    return cleaned  # type: ignore[return-value]


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str | None = Field(default=None, max_length=128)
    new_password: str = Field(..., min_length=1, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=512)
    new_password: str = Field(..., min_length=1, max_length=128)


class PasswordStrengthCheckRequest(BaseModel):
    password: str = Field(..., max_length=128)
    name: str | None = None
    email: str | None = None


class ReauthPasswordRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)


class AccountDeletionRequest(BaseModel):
    confirmation_text: str = Field(..., min_length=1, max_length=32)
    password: str | None = Field(default=None, max_length=128)
    reauth_token: str | None = Field(default=None, max_length=1024)
    github_pat: str | None = Field(default=None, max_length=512)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    avatar_url: str | None = None
    plan: str = ""
    theme: str = "dark"
    github_connected: bool = False
    github_username: str | None = None
    auth_provider: str = "local"
    google_email: str | None = None
    google_linked: bool = False
    role: str = "user"
    has_password: bool = False
    email_verified: bool = True
    pending_email: str | None = None
    created_at: datetime


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


class UserUpdateRequest(BaseModel):
    name: str | None = None
    theme: str | None = None
    email: EmailStr | None = None


class ReviewCreateRequest(BaseModel):
    diff_text: str = Field(..., min_length=5, description="Unified git diff to analyze")
    title: str = Field(default="Adhoc Review", max_length=255)
    repository_name: str = Field(default="adhoc-diff", max_length=255)
    pr_identifier: str = Field(default="manual", max_length=100)
    provider: str = Field(default="llm", description="LLM provider: 'llm', 'nvidia', or 'ollama'")
    include_llm: bool = Field(default=True)
    agents: list[str] | None = Field(default=None, description="Subset of agent IDs to run")


class FindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent: str
    title: str
    description: str
    severity: str
    category: str
    file_path: str
    line_start: int
    line_end: int | None = None
    suggested_fix: str | None = None
    rule_id: str | None = None
    evidence: str | None = None


class ReviewSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_name: str
    pr_identifier: str
    title: str
    provider: str
    model_name: str
    agents_used: list[str]
    finding_count: int
    has_critical: bool
    duration_seconds: float
    created_at: datetime


class ReviewDetailResponse(ReviewSummaryResponse):
    diff_content: str
    findings: list[FindingResponse]


class OverviewMetricsResponse(BaseModel):
    total_reviews: int
    total_findings: int
    critical_findings: int
    pull_requests_count: int | None = None
    open_pull_requests_count: int | None = None
    active_agents_count: int
    total_agents_count: int
    github_connected: bool
    recent_reviews: list[ReviewSummaryResponse] = Field(default_factory=list)


class PullRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_name: str
    pr_number: int
    title: str
    source_branch: str
    target_branch: str
    author: str
    status: str
    additions: int
    deletions: int
    changed_files: int
    created_at: datetime


class AgentConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    name: str
    description: str
    is_enabled: bool
    provider: str
    model_name: str
    capabilities: list[str]
    options: dict[str, Any] = Field(default_factory=dict)


class AgentUpdateRequest(BaseModel):
    is_enabled: bool | None = None
    provider: str | None = None
    model_name: str | None = None
    options: dict[str, Any] | None = None


class ProviderStatusItem(BaseModel):
    provider: str
    name: str
    is_available: bool
    current_model: str
    endpoint: str
    type: str
    note: str | None = None
    available_models: list[str] = Field(default_factory=list)


class ProviderStatusResponse(BaseModel):
    active_provider: str
    providers: list[ProviderStatusItem]


class ProviderTestRequest(BaseModel):
    provider: str
    model: str | None = None
    api_key: str | None = None


class ProviderTestResponse(BaseModel):
    provider: str
    success: bool
    message: str
    latency_ms: float | None = None
    models: list[str] = Field(default_factory=list)


class AttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_type: str
    mime_type: str
    file_size: int
    page_count: int = 1
    chunk_count: int = 0
    created_at: datetime


class AttachmentUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_type: str
    mime_type: str
    file_size: int
    page_count: int = 1
    chunk_count: int = 0
    created_at: datetime
    message: str = "Attachment processed successfully"


class MessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=16384)
    provider: str | None = None
    model: str | None = None
    diff_context: str | None = None
    attachment_ids: list[str] = Field(default_factory=list)
    mode: ChatMode | None = None
    github_mode: bool | None = None
    github_repo: str | None = None
    selected_text: str | None = Field(default=None, max_length=4000)
    selected_message_id: str | None = Field(default=None, max_length=100)

    @field_validator("mode", mode="before")
    @classmethod
    def validate_mode(cls, v: Any) -> ChatMode | None:
        return _validate_optional_chat_mode(v)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime
    feedback: str | None = None
    attachments: list[AttachmentResponse] = Field(default_factory=list)


class MessageFeedbackRequest(BaseModel):
    feedback: str | None = Field(
        default=None, description="'helpful', 'unhelpful', or null to clear"
    )


class MessageRegenerateRequest(BaseModel):
    message_id: str | None = None
    provider: str | None = None
    model: str | None = None
    diff_context: str | None = None
    mode: ChatMode | None = None
    github_mode: bool | None = None
    github_repo: str | None = None

    @field_validator("mode", mode="before")
    @classmethod
    def validate_mode(cls, v: Any) -> ChatMode | None:
        return _validate_optional_chat_mode(v)


class MessageEditRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=16384)
    provider: str | None = None
    model: str | None = None
    diff_context: str | None = None
    attachment_ids: list[str] = Field(default_factory=list)
    mode: ChatMode | None = None
    github_mode: bool | None = None
    github_repo: str | None = None
    selected_text: str | None = Field(default=None, max_length=4000)
    selected_message_id: str | None = Field(default=None, max_length=100)

    @field_validator("mode", mode="before")
    @classmethod
    def validate_mode(cls, v: Any) -> ChatMode | None:
        return _validate_optional_chat_mode(v)


class AttachmentContentResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    mime_type: str
    file_size: int
    content: str
    page_count: int = 1


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default="New Review Discussion", max_length=512)
    initial_message: str | None = None
    diff_context: str | None = None
    provider: str | None = None
    model: str | None = None
    attachment_ids: list[str] = Field(default_factory=list)
    mode: ChatMode | None = None
    github_mode: bool | None = None
    github_repo: str | None = None

    @field_validator("mode", mode="before")
    @classmethod
    def validate_mode(cls, v: Any) -> ChatMode | None:
        return _validate_optional_chat_mode(v)


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    is_pinned: bool = False
    is_archived: bool = False
    is_shared: bool = False
    mode: ChatMode = "normal"
    section_name: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    is_pinned: bool = False
    is_archived: bool = False
    is_shared: bool = False
    mode: ChatMode = "normal"
    section_name: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]
    attachments: list[AttachmentResponse] = Field(default_factory=list)


class ConversationUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    is_pinned: bool | None = None
    is_archived: bool | None = None
    is_shared: bool | None = None
    mode: ChatMode | None = None
    section_name: str | None = Field(default=None, max_length=100)

    @field_validator("mode", mode="before")
    @classmethod
    def validate_mode(cls, v: Any) -> ChatMode | None:
        return _validate_optional_chat_mode(v)


class ConversationSearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    match_type: str  # "title", "message", or "both"
    snippet: str
    role: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


# ============================================================================
# Feedback Schemas
# ============================================================================

FEEDBACK_CATEGORIES: list[str] = [
    "Visual is unhelpful or broken",
    "Incorrect or incomplete",
    "Not what I asked for",
    "Slow or buggy",
    "Style or tone",
    "Safety or legal concern",
    "Other",
]


class FeedbackCreateRequest(BaseModel):
    category: str = Field(..., min_length=2, max_length=100)
    details: str | None = Field(default=None, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=64)
    message_id: str | None = Field(default=None, max_length=64)
    reported_response: str = Field(default="", max_length=32768)


class FeedbackStatusUpdateRequest(BaseModel):
    status: str = Field(..., pattern=r"^(new|reviewing|resolved)$")


class FeedbackUserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    avatar_url: str | None = None
    role: str = "user"


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    user: FeedbackUserSummary | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    conversation_ref: str | None = None
    message_ref: str | None = None
    conversation_title: str | None = None
    category: str
    details: str | None = None
    reported_response: str
    status: str
    email_notification_status: str
    email_error: str | None = None
    email_message_id: str | None = None
    email_sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class FeedbackListResponse(BaseModel):
    items: list[FeedbackResponse]
    total: int
    page: int
    limit: int
    pages: int


class FeedbackStatsResponse(BaseModel):
    total: int
    new_count: int
    reviewing_count: int
    resolved_count: int
    failed_emails: int
