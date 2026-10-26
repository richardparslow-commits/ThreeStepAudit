"""Data model for step 1 of the ThreeStepAudit workflow: scope & criteria."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

AUDIT_TYPES: tuple[str, ...] = (
    "Internal",
    "External",
    "Certification readiness",
    "Follow-up",
)

STANDARDS: tuple[str, ...] = (
    "ISO 9001",
    "ISO 27001",
    "SOC 2",
    "NIST CSF",
    "HIPAA",
    "Internal policy",
    "Other",
)

SCOPE_AREAS: tuple[str, ...] = (
    "Governance & oversight",
    "Access control",
    "Change management",
    "Data handling & privacy",
    "Vendor management",
    "Incident response",
    "Financial reporting",
    "Operations & delivery",
)

MIN_SCOPE_CHARS = 20
MAX_SCOPE_CHARS = 4000
MAX_EXCLUSION_CHARS = 2000
MAX_SHORT_TEXT = 120
MAX_OBJECTIVE_CHARS = 250


@dataclass(frozen=True)
class FieldError:
    """A single validation failure, keyed by the model field it belongs to."""

    field: str
    message: str


def parse_lines(value: str) -> list[str]:
    """Turn a textarea's contents into a clean list of distinct entries.

    Blank lines are dropped, leading ``-``/``*``/``•`` bullets are removed, and
    duplicates (case-insensitive) keep only their first spelling.
    """
    entries: list[str] = []
    seen: set[str] = set()
    for raw in value.splitlines():
        line = raw.strip().lstrip("-*•").strip()
        if not line:
            continue
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        entries.append(line)
    return entries


@dataclass
class AuditScope:
    """Everything step 1 captures, and the rules that make it usable downstream."""

    title: str = ""
    organization: str = ""
    audit_type: str = AUDIT_TYPES[0]
    standard: str = STANDARDS[0]
    period_start: date | None = None
    period_end: date | None = None
    lead_auditor: str = ""
    scope_summary: str = ""
    in_scope_areas: list[str] = field(default_factory=list)
    objectives: list[str] = field(default_factory=list)
    exclusions: str = ""
    custom_standard: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def criteria(self) -> str:
        """The criteria actually applied, resolving the 'Other' free-text case."""
        if self.standard == "Other":
            return self.custom_standard.strip()
        return self.standard

    def period_label(self) -> str:
        if self.period_start is None or self.period_end is None:
            return "unspecified period"
        return f"{self.period_start:%d %b %Y} – {self.period_end:%d %b %Y}"

    def validate(self) -> list[FieldError]:
        """Return every rule violation; an empty list means step 1 can be saved."""
        errors: list[FieldError] = []

        def short_text(name: str, label: str) -> None:
            value = getattr(self, name).strip()
            if not value:
                errors.append(FieldError(name, f"{label} is required."))
            elif len(value) > MAX_SHORT_TEXT:
                errors.append(
                    FieldError(name, f"{label} must be {MAX_SHORT_TEXT} characters or fewer.")
                )

        short_text("title", "Audit title")
        short_text("organization", "Organization")
        short_text("lead_auditor", "Lead auditor")

        if self.audit_type not in AUDIT_TYPES:
            errors.append(FieldError("audit_type", "Choose one of the listed audit types."))

        if self.standard not in STANDARDS:
            errors.append(FieldError("standard", "Choose one of the listed standards."))
        elif self.standard == "Other":
            named = self.custom_standard.strip()
            if not named:
                errors.append(
                    FieldError("custom_standard", "Name the criteria you are auditing against.")
                )
            elif len(named) > 80:
                errors.append(
                    FieldError("custom_standard", "Named criteria must be 80 characters or fewer.")
                )

        if self.period_start is None:
            errors.append(FieldError("period_start", "Period start is required."))
        if self.period_end is None:
            errors.append(FieldError("period_end", "Period end is required."))
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_end < self.period_start
        ):
            errors.append(
                FieldError("period_end", "Period end cannot fall before period start.")
            )

        summary = self.scope_summary.strip()
        if len(summary) < MIN_SCOPE_CHARS:
            errors.append(
                FieldError(
                    "scope_summary",
                    f"Describe the scope in at least {MIN_SCOPE_CHARS} characters.",
                )
            )
        elif len(summary) > MAX_SCOPE_CHARS:
            errors.append(
                FieldError(
                    "scope_summary",
                    f"Scope description must be {MAX_SCOPE_CHARS} characters or fewer.",
                )
            )

        if not self.in_scope_areas:
            errors.append(FieldError("in_scope_areas", "Select at least one area in scope."))
        unknown = [area for area in self.in_scope_areas if area not in SCOPE_AREAS]
        if unknown:
            errors.append(
                FieldError("in_scope_areas", f"Unknown area(s) in scope: {', '.join(unknown)}.")
            )

        if not self.objectives:
            errors.append(FieldError("objectives", "Record at least one audit objective."))
        for objective in self.objectives:
            if not objective.strip():
                errors.append(FieldError("objectives", "Objectives cannot be blank."))
                break
            if len(objective) > MAX_OBJECTIVE_CHARS:
                errors.append(
                    FieldError(
                        "objectives",
                        f"Each objective must be {MAX_OBJECTIVE_CHARS} characters or fewer.",
                    )
                )
                break

        if len(self.exclusions) > MAX_EXCLUSION_CHARS:
            errors.append(
                FieldError(
                    "exclusions",
                    f"Exclusions must be {MAX_EXCLUSION_CHARS} characters or fewer.",
                )
            )

        return errors

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe snapshot of the step, dates and timestamps included."""
        return {
            "step": 1,
            "title": self.title,
            "organization": self.organization,
            "audit_type": self.audit_type,
            "standard": self.standard,
            "criteria": self.criteria(),
            "custom_standard": self.custom_standard,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "lead_auditor": self.lead_auditor,
            "scope_summary": self.scope_summary,
            "in_scope_areas": list(self.in_scope_areas),
            "objectives": list(self.objectives),
            "exclusions": self.exclusions,
            "created_at": self.created_at.isoformat(),
        }

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AuditScope:
        """Rebuild a scope from :meth:`to_dict` output or a saved JSON draft."""
        if not isinstance(data, Mapping):
            raise ValueError("draft data must be a JSON object")

        return cls(
            title=_text(data, "title"),
            organization=_text(data, "organization"),
            audit_type=_text(data, "audit_type", AUDIT_TYPES[0]),
            standard=_text(data, "standard", STANDARDS[0]),
            period_start=_as_date(data, "period_start"),
            period_end=_as_date(data, "period_end"),
            lead_auditor=_text(data, "lead_auditor"),
            scope_summary=_text(data, "scope_summary"),
            in_scope_areas=_text_list(data, "in_scope_areas"),
            objectives=_text_list(data, "objectives"),
            exclusions=_text(data, "exclusions"),
            custom_standard=_text(data, "custom_standard"),
            created_at=_as_datetime(data, "created_at"),
        )

    @classmethod
    def from_json(cls, payload: str) -> AuditScope:
        import json

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"draft is not valid JSON: {exc.msg}") from exc
        return cls.from_dict(data)


def _text(data: Mapping[str, Any], name: str, default: str = "") -> str:
    value = data.get(name, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _text_list(data: Mapping[str, Any], name: str) -> list[str]:
    value = data.get(name, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")
    return list(value)


def _as_date(data: Mapping[str, Any], name: str) -> date | None:
    value = data.get(name)
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{name} must be an ISO date (YYYY-MM-DD)") from exc
    raise ValueError(f"{name} must be an ISO date string")


def _as_datetime(data: Mapping[str, Any], name: str) -> datetime:
    value = data.get(name)
    if value in (None, ""):
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{name} must be an ISO timestamp") from exc
    raise ValueError(f"{name} must be an ISO timestamp string")
