"""Data model for step 3 of the ThreeStepAudit workflow: findings & conclusion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from three_step_audit.evidence import EvidencePlan
from three_step_audit.models import AuditScope, FieldError

SEVERITIES: tuple[str, ...] = ("High", "Medium", "Low")
FINDING_STATUSES: tuple[str, ...] = ("Open", "Remediated", "Accepted")
OPINIONS: tuple[str, ...] = (
    "Conforms",
    "Conforms with exceptions",
    "Does not conform",
    "Not concluded",
)

MIN_CONDITION_CHARS = 20
MIN_RECOMMENDATION_CHARS = 20
MIN_SUMMARY_CHARS = 40
MAX_SHORT_TEXT = 80
MAX_REFERENCE_CHARS = 40
MAX_LONG_TEXT = 2000


@dataclass
class Finding:
    """One finding, traced back to a step 1 objective and a step 2 evidence item."""

    reference: str = ""
    title: str = ""
    severity: str = "Medium"
    objective: str = ""
    evidence_reference: str = ""
    condition: str = ""
    recommendation: str = ""
    owner: str = ""
    due_on: date | None = None
    status: str = "Open"

    def validate(
        self,
        scope: AuditScope,
        evidence: EvidencePlan | None,
        today: date | None = None,
    ) -> list[FieldError]:
        """Return this finding's rule violations, using unprefixed field names."""
        today = today or date.today()
        errors: list[FieldError] = []

        reference = self.reference.strip()
        if not reference:
            errors.append(FieldError("reference", "Finding reference is required."))
        elif len(reference) > MAX_REFERENCE_CHARS:
            errors.append(
                FieldError(
                    "reference", f"Reference must be {MAX_REFERENCE_CHARS} characters or fewer."
                )
            )

        title = self.title.strip()
        if not title:
            errors.append(FieldError("title", "Finding title is required."))
        elif len(title) > MAX_SHORT_TEXT:
            errors.append(
                FieldError("title", f"Title must be {MAX_SHORT_TEXT} characters or fewer.")
            )

        if self.severity not in SEVERITIES:
            errors.append(FieldError("severity", "Choose one of the listed severities."))

        if not self.objective.strip():
            errors.append(FieldError("objective", "Choose the objective this finding relates to."))
        elif self.objective not in scope.objectives:
            errors.append(
                FieldError(
                    "objective",
                    "This objective is not in the saved step 1 objectives; re-check step 1.",
                )
            )

        if evidence is None:
            errors.append(
                FieldError("evidence_reference", "Record evidence in step 2 before findings.")
            )
        elif not self.evidence_reference.strip():
            errors.append(
                FieldError("evidence_reference", "Link this finding to a piece of evidence.")
            )
        elif self.evidence_reference not in {item.reference.strip() for item in evidence.items}:
            errors.append(
                FieldError(
                    "evidence_reference",
                    "No evidence item uses that reference; re-check step 2.",
                )
            )

        condition = self.condition.strip()
        if len(condition) < MIN_CONDITION_CHARS:
            errors.append(
                FieldError(
                    "condition",
                    f"Describe what was found in at least {MIN_CONDITION_CHARS} characters.",
                )
            )
        elif len(condition) > MAX_LONG_TEXT:
            errors.append(FieldError("condition", "Finding detail is too long."))

        recommendation = self.recommendation.strip()
        if len(recommendation) < MIN_RECOMMENDATION_CHARS:
            errors.append(
                FieldError(
                    "recommendation",
                    f"Record a recommendation of at least {MIN_RECOMMENDATION_CHARS} characters.",
                )
            )
        elif len(recommendation) > MAX_LONG_TEXT:
            errors.append(FieldError("recommendation", "Recommendation is too long."))

        owner = self.owner.strip()
        if not owner:
            errors.append(FieldError("owner", "Name the owner who will remediate this."))
        elif len(owner) > MAX_SHORT_TEXT:
            errors.append(FieldError("owner", f"Owner must be {MAX_SHORT_TEXT} characters or fewer."))

        if self.due_on is None:
            errors.append(FieldError("due_on", "A remediation due date is required."))

        if self.status not in FINDING_STATUSES:
            errors.append(FieldError("status", "Choose one of the listed finding statuses."))

        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "title": self.title,
            "severity": self.severity,
            "objective": self.objective,
            "evidence_reference": self.evidence_reference,
            "condition": self.condition,
            "recommendation": self.recommendation,
            "owner": self.owner,
            "due_on": self.due_on.isoformat() if self.due_on else None,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Finding:
        if not isinstance(data, Mapping):
            raise ValueError("findings must be JSON objects")
        return cls(
            reference=_text(data, "reference"),
            title=_text(data, "title"),
            severity=_text(data, "severity", SEVERITIES[1]),
            objective=_text(data, "objective"),
            evidence_reference=_text(data, "evidence_reference"),
            condition=_text(data, "condition"),
            recommendation=_text(data, "recommendation"),
            owner=_text(data, "owner"),
            due_on=_as_date(data, "due_on"),
            status=_text(data, "status", FINDING_STATUSES[0]),
        )


@dataclass
class Conclusion:
    """The audit opinion, and who signed it off."""

    opinion: str = "Not concluded"
    summary: str = ""
    concluded_by: str = ""
    concluded_on: date | None = None

    def validate(self, findings: list[Finding], today: date | None = None) -> list[FieldError]:
        today = today or date.today()
        errors: list[FieldError] = []

        if self.opinion not in OPINIONS:
            errors.append(FieldError("opinion", "Choose one of the listed opinions."))
        else:
            open_high = [
                finding
                for finding in findings
                if finding.severity == "High" and finding.status == "Open"
            ]
            if self.opinion == "Conforms" and open_high:
                errors.append(
                    FieldError(
                        "opinion",
                        "Cannot conclude 'Conforms' while a High finding is still open "
                        f"({', '.join(f.reference.strip() or 'unnumbered' for f in open_high)}).",
                    )
                )

        summary = self.summary.strip()
        if len(summary) < MIN_SUMMARY_CHARS:
            errors.append(
                FieldError(
                    "summary",
                    f"Summarise the conclusion in at least {MIN_SUMMARY_CHARS} characters.",
                )
            )
        elif len(summary) > MAX_LONG_TEXT:
            errors.append(FieldError("summary", "Conclusion summary is too long."))

        if not self.concluded_by.strip():
            errors.append(FieldError("concluded_by", "Name who concluded the audit."))
        elif len(self.concluded_by) > MAX_SHORT_TEXT:
            errors.append(
                FieldError(
                    "concluded_by",
                    f"Name must be {MAX_SHORT_TEXT} characters or fewer.",
                )
            )

        if self.concluded_on is None:
            errors.append(FieldError("concluded_on", "Conclusion date is required."))
        elif self.concluded_on > today:
            errors.append(FieldError("concluded_on", "Conclusion cannot be dated in the future."))

        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "opinion": self.opinion,
            "summary": self.summary,
            "concluded_by": self.concluded_by,
            "concluded_on": self.concluded_on.isoformat() if self.concluded_on else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Conclusion:
        if not isinstance(data, Mapping):
            raise ValueError("conclusion must be a JSON object")
        return cls(
            opinion=_text(data, "opinion", OPINIONS[-1]),
            summary=_text(data, "summary"),
            concluded_by=_text(data, "concluded_by"),
            concluded_on=_as_date(data, "concluded_on"),
        )


@dataclass
class FindingRegister:
    """The findings and conclusion that close out an audit."""

    findings: list[Finding] = field(default_factory=list)
    conclusion: Conclusion = field(default_factory=Conclusion)

    def validate(
        self,
        scope: AuditScope,
        evidence: EvidencePlan | None,
        today: date | None = None,
    ) -> list[FieldError]:
        """Return every rule violation; an empty list means step 3 can be saved."""
        today = today or date.today()
        errors: list[FieldError] = []

        for index, finding in enumerate(self.findings):
            for error in finding.validate(scope, evidence, today):
                errors.append(FieldError(f"findings.{index}.{error.field}", error.message))

        seen: set[str] = set()
        for index, finding in enumerate(self.findings):
            reference = finding.reference.strip()
            if not reference:
                continue
            if reference in seen:
                errors.append(
                    FieldError(f"findings.{index}.reference", "This reference is already used.")
                )
            seen.add(reference)

        if evidence is not None:
            linked = {finding.evidence_reference for finding in self.findings}
            unexplained = [
                item.reference
                for item in evidence.items
                if item.result == "Exception" and item.reference not in linked
            ]
            if unexplained:
                errors.append(
                    FieldError(
                        "findings",
                        "Evidence recorded as an exception with no finding: "
                        + ", ".join(unexplained),
                    )
                )

        for error in self.conclusion.validate(self.findings, today):
            errors.append(FieldError(f"conclusion.{error.field}", error.message))

        return errors

    def summary(self) -> dict[str, Any]:
        by_severity = {severity: 0 for severity in SEVERITIES}
        by_status = {status: 0 for status in FINDING_STATUSES}
        for finding in self.findings:
            if finding.severity in by_severity:
                by_severity[finding.severity] += 1
            if finding.status in by_status:
                by_status[finding.status] += 1
        return {
            "findings": len(self.findings),
            "by_severity": by_severity,
            "by_status": by_status,
            "open_high": sum(
                1
                for finding in self.findings
                if finding.severity == "High" and finding.status == "Open"
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [finding.to_dict() for finding in self.findings],
            "conclusion": self.conclusion.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FindingRegister:
        if not isinstance(data, Mapping):
            raise ValueError("findings must be a JSON object")
        raw_findings = data.get("findings", [])
        if not isinstance(raw_findings, list):
            raise ValueError("findings must be a list")
        raw_conclusion = data.get("conclusion")
        return cls(
            findings=[Finding.from_dict(finding) for finding in raw_findings],
            conclusion=Conclusion.from_dict(raw_conclusion) if raw_conclusion else Conclusion(),
        )


def _text(data: Mapping[str, Any], name: str, default: str = "") -> str:
    value = data.get(name, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _as_date(data: Mapping[str, Any], name: str) -> date | None:
    value = data.get(name)
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{name} must be an ISO date (YYYY-MM-DD)") from exc
    raise ValueError(f"{name} must be an ISO date string")
