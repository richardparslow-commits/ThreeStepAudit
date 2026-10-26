"""Tests for the step 2 evidence model and the saved workflow document."""

from __future__ import annotations

import unittest
from datetime import date

from three_step_audit.evidence import TEST_RESULTS, EvidenceItem, EvidencePlan
from three_step_audit.models import AuditScope
from three_step_audit.workflow import Workflow

TODAY = date(2026, 10, 26)
OBJECTIVE_ONE = "Confirm access reviews happen quarterly"
OBJECTIVE_TWO = "Verify leavers lose access within 24h"


def sample_scope() -> AuditScope:
    return AuditScope(
        title="FY26 access-control review",
        organization="Northwind Logistics",
        audit_type="Internal",
        standard="ISO 27001",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 6, 30),
        lead_auditor="R. Parslow",
        scope_summary="Review quarterly access reviews for all production systems.",
        in_scope_areas=["Access control"],
        objectives=[OBJECTIVE_ONE, OBJECTIVE_TWO],
    )


def sample_item(**overrides: object) -> EvidenceItem:
    values: dict[str, object] = {
        "reference": "AC-01",
        "description": "Quarterly access review completed for all production systems.",
        "source": "Identity team / review log",
        "objective": OBJECTIVE_ONE,
        "collected_on": date(2026, 10, 1),
        "result": "Pass",
        "notes": "",
    }
    values.update(overrides)
    return EvidenceItem(**values)  # type: ignore[arg-type]


def build_plan(**overrides: object) -> EvidencePlan:
    values: dict[str, object] = {
        "methodology": "Sampled every production system and re-performed one review.",
        "items": [
            sample_item(),
            sample_item(reference="AC-02", objective=OBJECTIVE_TWO, source="HR export"),
        ],
    }
    values.update(overrides)
    return EvidencePlan(**values)  # type: ignore[arg-type]


class EvidenceValidationTests(unittest.TestCase):
    def test_valid_plan_passes(self) -> None:
        self.assertEqual(build_plan().validate(sample_scope(), TODAY), [])

    def test_methodology_is_required(self) -> None:
        self.assertEqual(
            [error.field for error in build_plan(methodology="").validate(sample_scope(), TODAY)],
            ["methodology"],
        )

    def test_plan_needs_at_least_one_item(self) -> None:
        self.assertEqual(
            [error.field for error in build_plan(items=[]).validate(sample_scope(), TODAY)],
            ["items"],
        )

    def test_every_objective_needs_evidence(self) -> None:
        errors = build_plan(items=[sample_item()]).validate(sample_scope(), TODAY)
        self.assertEqual([error.field for error in errors], ["items"])
        self.assertIn(OBJECTIVE_TWO, errors[0].message)

    def test_item_required_fields_are_reported_with_their_position(self) -> None:
        plan = build_plan(items=[sample_item(reference=" ", source="", collected_on=None)])
        fields = [error.field for error in plan.validate(sample_scope(), TODAY)]
        self.assertIn("items.0.reference", fields)
        self.assertIn("items.0.source", fields)
        self.assertIn("items.0.collected_on", fields)

    def test_description_has_a_minimum_length(self) -> None:
        errors = build_plan(items=[sample_item(description="short")]).validate(
            sample_scope(), TODAY
        )
        self.assertIn("items.0.description", [error.field for error in errors])

    def test_evidence_must_map_to_a_step_1_objective(self) -> None:
        plan = build_plan(items=[sample_item(objective="Something from another audit")])
        errors = plan.validate(sample_scope(), TODAY)
        self.assertIn("items.0.objective", [error.field for error in errors])
        self.assertIn("step 1", errors[0].message)

    def test_future_evidence_date_is_rejected(self) -> None:
        plan = build_plan(items=[sample_item(collected_on=date(2026, 10, 27))])
        errors = plan.validate(sample_scope(), TODAY)
        self.assertIn("items.0.collected_on", [error.field for error in errors])

    def test_unknown_result_is_rejected(self) -> None:
        plan = build_plan(items=[sample_item(result="Mostly fine")])
        errors = plan.validate(sample_scope(), TODAY)
        self.assertIn("items.0.result", [error.field for error in errors])
        self.assertIn("Not tested", TEST_RESULTS)

    def test_exception_needs_an_explanation(self) -> None:
        second_item = sample_item(reference="AC-02", objective=OBJECTIVE_TWO, source="HR export")

        plan = build_plan(items=[sample_item(result="Exception", notes=""), second_item])
        self.assertIn("items.0.notes", [error.field for error in plan.validate(sample_scope(), TODAY)])

        explained = build_plan(
            items=[
                sample_item(result="Exception", notes="Two systems missed their review."),
                second_item,
            ]
        )
        self.assertEqual(explained.validate(sample_scope(), TODAY), [])


class EvidenceSummaryTests(unittest.TestCase):
    def test_summary_counts_results_and_coverage(self) -> None:
        plan = build_plan(
            items=[
                sample_item(),
                sample_item(reference="AC-02", objective=OBJECTIVE_TWO, result="Exception",
                            notes="Two systems missed their review."),
            ]
        )
        totals = plan.summary(sample_scope())
        self.assertEqual(totals["items"], 2)
        self.assertEqual(totals["results"]["Pass"], 1)
        self.assertEqual(totals["results"]["Exception"], 1)
        self.assertEqual(totals["objectives_covered"], 2)
        self.assertEqual(totals["objectives_total"], 2)

    def test_partial_coverage_is_reported(self) -> None:
        totals = build_plan(items=[sample_item()]).summary(sample_scope())
        self.assertEqual(totals["objectives_covered"], 1)


class SerializationTests(unittest.TestCase):
    def test_evidence_round_trips_through_dict(self) -> None:
        plan = build_plan()
        self.assertEqual(EvidencePlan.from_dict(plan.to_dict()), plan)

    def test_item_dates_are_iso_strings(self) -> None:
        raw = sample_item().to_dict()
        self.assertEqual(raw["collected_on"], "2026-10-01")
        self.assertEqual(EvidenceItem.from_dict(raw), sample_item())

    def test_bad_item_types_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            EvidenceItem.from_dict({"collected_on": "01/10/2026"})
        with self.assertRaises(ValueError):
            EvidencePlan.from_dict({"items": "not a list"})

    def test_workflow_round_trips_with_both_steps(self) -> None:
        workflow = Workflow(scope=sample_scope(), evidence=build_plan())
        self.assertEqual(Workflow.from_dict(workflow.to_dict()), workflow)
        self.assertEqual(Workflow.from_json(workflow.to_json()), workflow)

    def test_workflow_reads_a_legacy_step_one_draft(self) -> None:
        scope = sample_scope()
        restored = Workflow.from_dict(scope.to_dict())
        self.assertEqual(restored.scope, scope)
        self.assertIsNone(restored.evidence)

    def test_workflow_rejects_unknown_documents(self) -> None:
        with self.assertRaises(ValueError):
            Workflow.from_dict({"surprise": True})
        with self.assertRaises(ValueError):
            Workflow.from_json("{broken")

    def test_file_stem_uses_the_audit_title(self) -> None:
        workflow = Workflow(scope=sample_scope())
        self.assertEqual(workflow.file_stem(), "fy26-access-control-review")
        self.assertEqual(Workflow().file_stem(), "audit")


if __name__ == "__main__":
    unittest.main()
