from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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


class MessageEditRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=16384)
    provider: str | None = None
    model: str | None = None
    diff_context: str | None = None
    attachment_ids: list[str] = Field(default_factory=list)


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


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    is_pinned: bool = False
    is_archived: bool = False
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
    section_name: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]
    attachments: list[AttachmentResponse] = Field(default_factory=list)


class ConversationUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    is_pinned: bool | None = None
    is_archived: bool | None = None
    section_name: str | None = Field(default=None, max_length=100)
