import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from code_review.db.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Developer")
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="user", nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    theme: Mapped[str] = mapped_column(String(20), default="dark", nullable=False)
    github_connected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    github_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    google_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_provider: Mapped[str] = mapped_column(String(50), default="local", nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pending_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    reviews: Mapped[list["ReviewRecord"]] = relationship(
        "ReviewRecord", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def has_password(self) -> bool:
        return bool(self.hashed_password)

    @property
    def google_linked(self) -> bool:
        return bool(self.google_id or self.auth_provider == "google")


class RepositoryRecord(Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PullRequestRecord(Base):
    __tablename__ = "pull_requests"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    repository_name: Mapped[str] = mapped_column(String(255), nullable=False)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    target_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    author: Mapped[str] = mapped_column(String(255), nullable=False, default="Developer")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deletions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    changed_files: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReviewRecord(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    repository_name: Mapped[str] = mapped_column(String(255), nullable=False, default="adhoc-diff")
    pr_identifier: Mapped[str] = mapped_column(String(100), nullable=False, default="manual")
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    diff_content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="ollama")
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    agents_used: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    finding_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    has_critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[UserRecord | None] = relationship("UserRecord", back_populates="reviews")
    findings: Mapped[list["FindingRecord"]] = relationship(
        "FindingRecord", back_populates="review", cascade="all, delete-orphan"
    )


class FindingRecord(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    review_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reviews.id", ondelete="CASCADE"), index=True, nullable=False
    )
    agent: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    line_start: Mapped[int] = mapped_column(Integer, nullable=False)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)

    review: Mapped[ReviewRecord] = relationship("ReviewRecord", back_populates="findings")


class AgentConfigRecord(Base):
    __tablename__ = "agent_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    agent_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="ollama", nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), default="default", nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    options: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )


class ConversationRecord(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(512), default="New Conversation", nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    section_name: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    mode: Mapped[str] = mapped_column(
        String(20), default="normal", server_default="normal", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True
    )

    messages: Mapped[list["MessageRecord"]] = relationship(
        "MessageRecord",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="MessageRecord.created_at",
    )
    attachments: Mapped[list["AttachmentRecord"]] = relationship(
        "AttachmentRecord",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    memories: Mapped[list["ConversationMemoryRecord"]] = relationship(
        "ConversationMemoryRecord",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class MessageRecord(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    feedback: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    conversation: Mapped[ConversationRecord] = relationship(
        "ConversationRecord", back_populates="messages"
    )
    attachments: Mapped[list["AttachmentRecord"]] = relationship(
        "AttachmentRecord",
        back_populates="message",
        cascade="all, delete-orphan",
        foreign_keys="[AttachmentRecord.message_id]",
    )
    memories: Mapped[list["ConversationMemoryRecord"]] = relationship(
        "ConversationMemoryRecord",
        back_populates="message",
        cascade="all, delete-orphan",
    )


class ConversationMemoryRecord(Base):
    __tablename__ = "conversation_memories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=True
    )
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False, default="message")
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    conversation: Mapped[ConversationRecord] = relationship(
        "ConversationRecord", back_populates="memories"
    )
    message: Mapped[MessageRecord | None] = relationship(
        "MessageRecord", back_populates="memories"
    )


class AttachmentRecord(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=True
    )
    message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    conversation: Mapped[ConversationRecord | None] = relationship(
        "ConversationRecord", back_populates="attachments"
    )
    message: Mapped[MessageRecord | None] = relationship(
        "MessageRecord", back_populates="attachments"
    )
    chunks: Mapped[list["DocumentChunkRecord"]] = relationship(
        "DocumentChunkRecord",
        back_populates="attachment",
        cascade="all, delete-orphan",
        order_by="DocumentChunkRecord.chunk_index",
    )


class DocumentChunkRecord(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    attachment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("attachments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    conversation_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    attachment: Mapped[AttachmentRecord] = relationship(
        "AttachmentRecord", back_populates="chunks"
    )


class GitHubConnectionRecord(Base):
    __tablename__ = "github_connections"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    auth_method: Mapped[str] = mapped_column(
        String(32), nullable=False, default="github_app"
    )  # "github_app" | "oauth" | "pat"
    github_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    github_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    installation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    permissions_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    connection_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="connected", index=True
    )  # "connected" | "expired" | "revoked" | "disconnected"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ConversationRepositoryContextRecord(Base):
    __tablename__ = "conversation_repository_contexts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    repository_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    repository_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    selected_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    last_inspected_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class PasswordResetTokenRecord(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserSessionRecord(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    auth_method: Mapped[str] = mapped_column(String(32), default="local", nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RevokedSubjectRecord(Base):
    __tablename__ = "revoked_subjects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    subject_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    revoked_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SecurityAuditLogRecord(Base):
    __tablename__ = "security_audit_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    subject_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    auth_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FeedbackRecord(Base):
    __tablename__ = "feedback_reports"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="SET NULL"), index=True, nullable=True
    )
    conversation_ref: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    message_ref: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    conversation_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_response: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="new", nullable=False, index=True
    )  # "new" | "reviewing" | "resolved"
    email_notification_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )  # "pending" | "sent" | "failed"
    email_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    user: Mapped[UserRecord] = relationship("UserRecord")
    conversation: Mapped[ConversationRecord | None] = relationship("ConversationRecord")
    message: Mapped[MessageRecord | None] = relationship("MessageRecord")


class GitHubAccessAuditRecord(Base):
    __tablename__ = "github_access_audit_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    chat_mode: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    intent: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    operation: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    repository: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision: Mapped[str] = mapped_column(
        String(16), index=True, nullable=False
    )  # "ALLOW" | "DENY"
    reason: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
