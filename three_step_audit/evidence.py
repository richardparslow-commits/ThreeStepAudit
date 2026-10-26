"""Data model for step 2 of the ThreeStepAudit workflow: evidence & testing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from three_step_audit.models import AuditScope, FieldError

TEST_RESULTS: tuple[str, ...] = ("Not tested", "Pass", "Exception", "Not applicable")

MIN_METHODOLOGY_CHARS = 20
MAX_METHODOLOGY_CHARS = 2000
MIN_DESCRIPTION_CHARS = 10
MIN_EXCEPTION_NOTE_CHARS = 10
MAX_SHORT_TEXT = 80
MAX_REFERENCE_CHARS = 40


@dataclass
class EvidenceItem:
    """One piece of evidence, tested against one objective from step 1."""

    reference: str = ""
    description: str = ""
    source: str = ""
    objective: str = ""
    collected_on: date | None = None
    result: str = "Not tested"
    notes: str = ""

    def validate(self, scope: AuditScope, today: date | None = None) -> list[FieldError]:
        """Return this item's rule violations, using unprefixed field names."""
        today = today or date.today()
        errors: list[FieldError] = []

        reference = self.reference.strip()
        if not reference:
            errors.append(FieldError("reference", "Evidence reference is required."))
        elif len(reference) > MAX_REFERENCE_CHARS:
            errors.append(
                FieldError(
                    "reference", f"Reference must be {MAX_REFERENCE_CHARS} characters or fewer."
                )
            )

        description = self.description.strip()
        if len(description) < MIN_DESCRIPTION_CHARS:
            errors.append(
                FieldError(
                    "description",
                    f"Describe the evidence in at least {MIN_DESCRIPTION_CHARS} characters.",
                )
            )
        elif len(description) > 500:
            errors.append(FieldError("description", "Description must be 500 characters or fewer."))

        source = self.source.strip()
        if not source:
            errors.append(FieldError("source", "Say where the evidence comes from."))
        elif len(source) > MAX_SHORT_TEXT:
            errors.append(
                FieldError("source", f"Source must be {MAX_SHORT_TEXT} characters or fewer.")
            )

        if not self.objective.strip():
            errors.append(FieldError("objective", "Choose the objective this evidence supports."))
        elif self.objective not in scope.objectives:
            errors.append(
                FieldError(
                    "objective",
                    "This objective is not in the saved step 1 objectives; re-check step 1.",
                )
            )

        if self.collected_on is None:
            errors.append(FieldError("collected_on", "Evidence date is required."))
        elif self.collected_on > today:
            errors.append(FieldError("collected_on", "Evidence cannot be dated in the future."))

        if self.result not in TEST_RESULTS:
            errors.append(FieldError("result", "Choose one of the listed test results."))
        elif self.result == "Exception" and len(self.notes.strip()) < MIN_EXCEPTION_NOTE_CHARS:
            errors.append(
                FieldError(
                    "notes",
                    "An exception needs a note explaining what failed and why it was accepted.",
                )
            )

        if len(self.notes) > 500:
            errors.append(FieldError("notes", "Notes must be 500 characters or fewer."))

        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "description": self.description,
            "source": self.source,
            "objective": self.objective,
            "collected_on": self.collected_on.isoformat() if self.collected_on else None,
            "result": self.result,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvidenceItem:
        if not isinstance(data, Mapping):
            raise ValueError("evidence items must be JSON objects")
        return cls(
            reference=_text(data, "reference"),
            description=_text(data, "description"),
            source=_text(data, "source"),
            objective=_text(data, "objective"),
            collected_on=_as_date(data, "collected_on"),
            result=_text(data, "result", TEST_RESULTS[0]),
            notes=_text(data, "notes"),
        )


@dataclass
class EvidencePlan:
    """The methodology and the evidence gathered for one audit."""

    methodology: str = ""
    items: list[EvidenceItem] = field(default_factory=list)

    def validate(self, scope: AuditScope, today: date | None = None) -> list[FieldError]:
        """Return every rule violation; an empty list means step 2 can be saved."""
        today = today or date.today()
        errors: list[FieldError] = []

        methodology = self.methodology.strip()
        if len(methodology) < MIN_METHODOLOGY_CHARS:
            errors.append(
                FieldError(
                    "methodology",
                    f"Describe the testing approach in at least {MIN_METHODOLOGY_CHARS} characters.",
                )
            )
        elif len(methodology) > MAX_METHODOLOGY_CHARS:
            errors.append(
                FieldError(
                    "methodology",
                    f"Methodology must be {MAX_METHODOLOGY_CHARS} characters or fewer.",
                )
            )

        if not self.items:
            errors.append(FieldError("items", "Record at least one piece of evidence."))

        covered: set[str] = set()
        for index, item in enumerate(self.items):
            for error in item.validate(scope, today):
                errors.append(FieldError(f"items.{index}.{error.field}", error.message))
            if item.objective in scope.objectives:
                covered.add(item.objective)

        if self.items:
            missing = [objective for objective in scope.objectives if objective not in covered]
            if missing:
                errors.append(
                    FieldError(
                        "items",
                        "No evidence recorded for objective(s): " + "; ".join(missing),
                    )
                )

        return errors

    def summary(self, scope: AuditScope) -> dict[str, Any]:
        """Counts for the review card: what was tested and what is still open."""
        results = {result: 0 for result in TEST_RESULTS}
        for item in self.items:
            if item.result in results:
                results[item.result] += 1
        covered = {item.objective for item in self.items if item.objective in scope.objectives}
        return {
            "items": len(self.items),
            "results": results,
            "objectives_total": len(scope.objectives),
            "objectives_covered": len(covered),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "methodology": self.methodology,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvidencePlan:
        if not isinstance(data, Mapping):
            raise ValueError("evidence must be a JSON object")
        raw_items = data.get("items", [])
        if not isinstance(raw_items, list):
            raise ValueError("evidence items must be a list")
        return cls(
            methodology=_text(data, "methodology"),
            items=[EvidenceItem.from_dict(item) for item in raw_items],
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
