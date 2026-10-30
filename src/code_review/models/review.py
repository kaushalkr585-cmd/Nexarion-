from datetime import UTC, datetime

from pydantic import BaseModel, Field, computed_field

from code_review.models.enums import Severity, severity_rank
from code_review.models.finding import Finding


class ReviewResult(BaseModel):
    findings: list[Finding] = Field(
        default_factory=list,
        description="All findings from all agents, unsorted.",
    )
    files_reviewed: int = Field(
        default=0,
        ge=0,
        description="How many files were analysed in this review.",
    )
    review_time_ms: int = Field(
        default=0,
        ge=0,
        description="Wall-clock time for the review in milliseconds.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when the review was created.",
    )
    cached: bool = Field(
        default=False,
        description="Whether this review result was retrieved from cache.",
    )

    @computed_field
    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @computed_field
    @property
    def has_critical(self) -> bool:
        return any(f.severity == Severity.CRITICAL for f in self.findings)

    @computed_field
    @property
    def findings_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in Severity}
        for finding in self.findings:
            counts[finding.severity.value] += 1
        return counts

    def sorted_findings(self, *, reverse: bool = True) -> list[Finding]:
        return sorted(
            self.findings,
            key=lambda f: severity_rank(f.severity),
            reverse=reverse,
        )
