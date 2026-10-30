from pydantic import BaseModel, Field

from code_review.models.enums import AgentType, Category, Severity


class Finding(BaseModel):
    model_config = {"frozen": True}

    file: str = Field(
        ...,
        description="Path to the file containing the issue, relative to the repo root.",
        examples=["src/code_review/config.py"],
    )
    line: int = Field(
        ...,
        ge=1,
        description="Line number where the issue occurs (1-indexed).",
    )
    severity: Severity = Field(
        ...,
        description="How urgent this finding is.",
    )
    category: Category = Field(
        ...,
        description="The kind of issue this finding represents.",
    )
    agent: AgentType = Field(
        ...,
        description="Which review agent discovered this finding.",
    )
    message: str = Field(
        ...,
        min_length=1,
        description="Human-readable explanation of the issue.",
    )
    suggestion: str | None = Field(
        default=None,
        description="Optional recommendation for how to fix the issue.",
    )
    rule_id: str | None = Field(
        default=None,
        description="Optional rule identifier (e.g., 'S101', 'E501', 'B608').",
    )
