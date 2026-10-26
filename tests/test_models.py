"""Focused tests for the step 1 scope model."""

from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timezone

from three_step_audit.models import AUDIT_TYPES, AuditScope, parse_lines


def make_scope(**overrides: object) -> AuditScope:
    values: dict[str, object] = {
        "title": "FY26 access-control review",
        "organization": "Northwind Logistics",
        "audit_type": "Internal",
        "standard": "ISO 27001",
        "period_start": date(2026, 1, 1),
        "period_end": date(2026, 6, 30),
        "lead_auditor": "R. Parslow",
        "scope_summary": "Review quarterly access reviews for all production systems.",
        "in_scope_areas": ["Access control", "Change management"],
        "objectives": ["Confirm access reviews happen quarterly"],
    }
    values.update(overrides)
    return AuditScope(**values)  # type: ignore[arg-type]


class ValidationTests(unittest.TestCase):
    def test_valid_scope_passes(self) -> None:
        self.assertEqual(make_scope().validate(), [])

    def test_missing_required_fields_are_named(self) -> None:
        errors = make_scope(
            title="  ",
            organization="",
            lead_auditor="",
            scope_summary="",
        ).validate()
        fields = {error.field for error in errors}
        self.assertEqual(fields, {"title", "organization", "lead_auditor", "scope_summary"})

    def test_period_end_before_start_is_rejected(self) -> None:
        errors = make_scope(period_start=date(2026, 6, 30), period_end=date(2026, 1, 1)).validate()
        self.assertEqual([error.field for error in errors], ["period_end"])
        self.assertIn("before period start", errors[0].message)

    def test_other_standard_requires_a_name(self) -> None:
        errors = make_scope(standard="Other").validate()
        self.assertEqual([error.field for error in errors], ["custom_standard"])

        named = make_scope(standard="Other", custom_standard="Supplier code of conduct v4")
        self.assertEqual(named.validate(), [])
        self.assertEqual(named.criteria(), "Supplier code of conduct v4")

    def test_unknown_standard_and_audit_type_are_rejected(self) -> None:
        self.assertEqual(
            [error.field for error in make_scope(standard="ISO 9999").validate()], ["standard"]
        )
        self.assertEqual(
            [error.field for error in make_scope(audit_type="Vibes").validate()], ["audit_type"]
        )
        self.assertIn("Internal", AUDIT_TYPES)

    def test_scope_summary_has_a_minimum_length(self) -> None:
        errors = make_scope(scope_summary="too short").validate()
        self.assertEqual([error.field for error in errors], ["scope_summary"])

    def test_scope_needs_an_area_and_an_objective(self) -> None:
        self.assertEqual(
            [error.field for error in make_scope(in_scope_areas=[]).validate()], ["in_scope_areas"]
        )
        self.assertEqual(
            [error.field for error in make_scope(objectives=[]).validate()], ["objectives"]
        )

    def test_unknown_area_is_rejected(self) -> None:
        errors = make_scope(in_scope_areas=["Access control", "Vibes"]).validate()
        self.assertEqual([error.field for error in errors], ["in_scope_areas"])

    def test_long_objective_is_rejected(self) -> None:
        errors = make_scope(objectives=["x" * 251]).validate()
        self.assertEqual([error.field for error in errors], ["objectives"])


class SerializationTests(unittest.TestCase):
    def test_dict_round_trip(self) -> None:
        original = make_scope(
            exclusions="Vendor systems",
            custom_standard="",
            created_at=datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc),
        )
        restored = AuditScope.from_dict(original.to_dict())
        self.assertEqual(restored, original)

    def test_json_round_trip_is_iso_formatted(self) -> None:
        original = make_scope()
        payload = original.to_json()
        raw = json.loads(payload)
        self.assertEqual(raw["step"], 1)
        self.assertEqual(raw["period_start"], "2026-01-01")
        self.assertEqual(raw["criteria"], "ISO 27001")
        self.assertEqual(AuditScope.from_json(payload), original)

    def test_from_dict_rejects_bad_types(self) -> None:
        data = make_scope().to_dict()
        data["in_scope_areas"] = "Access control"
        with self.assertRaises(ValueError):
            AuditScope.from_dict(data)

    def test_from_dict_rejects_bad_dates(self) -> None:
        data = make_scope().to_dict()
        data["period_start"] = "01/01/2026"
        with self.assertRaises(ValueError):
            AuditScope.from_dict(data)

    def test_from_json_rejects_garbage(self) -> None:
        with self.assertRaises(ValueError):
            AuditScope.from_json("{not json")

    def test_minimal_draft_loads_with_defaults(self) -> None:
        scope = AuditScope.from_dict({"title": "Weekly check"})
        self.assertEqual(scope.title, "Weekly check")
        self.assertEqual(scope.objectives, [])
        self.assertIsNotNone(scope.created_at)


class ParseLinesTests(unittest.TestCase):
    def test_strips_blanks_bullets_and_duplicates(self) -> None:
        text = "\n- Confirm access reviews\n\n* Verify leavers\n  • confirm ACCESS reviews\n"
        self.assertEqual(
            parse_lines(text),
            ["Confirm access reviews", "Verify leavers"],
        )

    def test_empty_input_yields_no_objectives(self) -> None:
        self.assertEqual(parse_lines("   \n\t\n"), [])


if __name__ == "__main__":
    unittest.main()
