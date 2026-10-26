"""Tests for the step 3 findings and conclusion model."""

from __future__ import annotations

import unittest
from datetime import date

from three_step_audit.evidence import EvidenceItem, EvidencePlan
from three_step_audit.findings import OPINIONS, Conclusion, Finding, FindingRegister
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


def sample_evidence(exception: bool = True) -> EvidencePlan:
    return EvidencePlan(
        methodology="Sampled every production system and re-performed one review.",
        items=[
            EvidenceItem(
                reference="AC-01",
                description="Quarterly access review completed for all production systems.",
                source="Identity team",
                objective=OBJECTIVE_ONE,
                collected_on=date(2026, 10, 1),
                result="Pass",
            ),
            EvidenceItem(
                reference="AC-02",
                description="Leaver access revoked within the 24 hour target for 11 of 12 cases.",
                source="HR export",
                objective=OBJECTIVE_TWO,
                collected_on=date(2026, 10, 2),
                result="Exception" if exception else "Pass",
                notes="One leaver disabled after 31 hours." if exception else "",
            ),
        ],
    )


def sample_finding(**overrides: object) -> Finding:
    values: dict[str, object] = {
        "reference": "F-01",
        "title": "Leaver access exceeded the 24 hour target",
        "severity": "High",
        "objective": OBJECTIVE_TWO,
        "evidence_reference": "AC-02",
        "condition": "One of twelve leavers kept access for 31 hours after their end date.",
        "recommendation": "Tie the leaver feed to the identity provider and alert on misses.",
        "owner": "R. Parslow",
        "due_on": date(2026, 12, 1),
        "status": "Open",
    }
    values.update(overrides)
    return Finding(**values)  # type: ignore[arg-type]


def sample_conclusion(**overrides: object) -> Conclusion:
    values: dict[str, object] = {
        "opinion": "Does not conform",
        "summary": "Access reviews operate as designed, but leaver revocation missed its target "
        "once; one High finding remains open.",
        "concluded_by": "R. Parslow",
        "concluded_on": date(2026, 10, 20),
    }
    values.update(overrides)
    return Conclusion(**values)  # type: ignore[arg-type]


def sample_register(**overrides: object) -> FindingRegister:
    values: dict[str, object] = {
        "findings": [sample_finding()],
        "conclusion": sample_conclusion(),
    }
    values.update(overrides)
    return FindingRegister(**values)  # type: ignore[arg-type]


class FindingRegisterValidationTests(unittest.TestCase):
    def test_valid_register_passes(self) -> None:
        self.assertEqual(
            sample_register().validate(sample_scope(), sample_evidence(), TODAY), []
        )

    def test_required_finding_fields_are_prefixed_with_their_position(self) -> None:
        register = sample_register(
            findings=[sample_finding(reference="", title="", owner="", condition="")]
        )
        fields = [error.field for error in register.validate(sample_scope(), sample_evidence(), TODAY)]
        self.assertIn("findings.0.reference", fields)
        self.assertIn("findings.0.title", fields)
        self.assertIn("findings.0.owner", fields)
        self.assertIn("findings.0.condition", fields)

    def test_duplicate_finding_references_are_rejected(self) -> None:
        register = sample_register(
            findings=[sample_finding(), sample_finding(title="A second, different finding")]
        )
        fields = [error.field for error in register.validate(sample_scope(), sample_evidence(), TODAY)]
        self.assertIn("findings.1.reference", fields)

    def test_finding_must_relate_to_a_step_1_objective(self) -> None:
        register = sample_register(findings=[sample_finding(objective="Something else")])
        fields = [error.field for error in register.validate(sample_scope(), sample_evidence(), TODAY)]
        self.assertIn("findings.0.objective", fields)

    def test_finding_must_link_to_recorded_evidence(self) -> None:
        register = sample_register(findings=[sample_finding(evidence_reference="AC-99")])
        errors = register.validate(sample_scope(), sample_evidence(), TODAY)
        self.assertIn("findings.0.evidence_reference", [error.field for error in errors])

    def test_findings_without_step_2_are_rejected(self) -> None:
        errors = sample_register().validate(sample_scope(), None, TODAY)
        self.assertIn("findings.0.evidence_reference", [error.field for error in errors])
        self.assertIn("step 2", errors[0].message)

    def test_an_evidence_exception_needs_a_finding(self) -> None:
        errors = sample_register(findings=[]).validate(sample_scope(), sample_evidence(), TODAY)
        self.assertIn("findings", [error.field for error in errors])
        self.assertIn("AC-02", errors[0].message)

    def test_clean_evidence_allows_no_findings(self) -> None:
        register = FindingRegister(
            findings=[],
            conclusion=sample_conclusion(opinion="Conforms", summary=(
                "Both objectives are met with no exceptions raised during testing.")),
        )
        self.assertEqual(
            register.validate(sample_scope(), sample_evidence(exception=False), TODAY), []
        )


class ConclusionValidationTests(unittest.TestCase):
    def test_conforms_cannot_pass_with_an_open_high_finding(self) -> None:
        register = sample_register(conclusion=sample_conclusion(opinion="Conforms"))
        errors = register.validate(sample_scope(), sample_evidence(), TODAY)
        self.assertIn("conclusion.opinion", [error.field for error in errors])
        self.assertIn("High", errors[0].message)

    def test_conforms_is_allowed_once_the_high_finding_is_closed(self) -> None:
        register = FindingRegister(
            findings=[sample_finding(status="Remediated")],
            conclusion=sample_conclusion(opinion="Conforms"),
        )
        self.assertEqual(register.validate(sample_scope(), sample_evidence(), TODAY), [])

    def test_conclusion_fields_are_required(self) -> None:
        errors = sample_register(
            conclusion=sample_conclusion(
                summary="", concluded_by="", concluded_on=None, opinion="Unheard of"
            )
        ).validate(sample_scope(), sample_evidence(), TODAY)
        fields = [error.field for error in errors]
        self.assertIn("conclusion.summary", fields)
        self.assertIn("conclusion.concluded_by", fields)
        self.assertIn("conclusion.concluded_on", fields)
        self.assertIn("conclusion.opinion", fields)
        self.assertIn("Not concluded", OPINIONS)

    def test_conclusion_cannot_be_dated_in_the_future(self) -> None:
        errors = sample_register(
            conclusion=sample_conclusion(concluded_on=date(2026, 10, 27))
        ).validate(sample_scope(), sample_evidence(), TODAY)
        self.assertIn("conclusion.concluded_on", [error.field for error in errors])


class FindingSummaryTests(unittest.TestCase):
    def test_summary_counts_severity_status_and_open_high(self) -> None:
        register = sample_register(
            findings=[
                sample_finding(),
                sample_finding(reference="F-02", severity="Low", status="Remediated"),
            ]
        )
        totals = register.summary()
        self.assertEqual(totals["findings"], 2)
        self.assertEqual(totals["by_severity"]["High"], 1)
        self.assertEqual(totals["by_severity"]["Low"], 1)
        self.assertEqual(totals["by_status"]["Open"], 1)
        self.assertEqual(totals["open_high"], 1)


class SerializationTests(unittest.TestCase):
    def test_register_round_trips(self) -> None:
        register = sample_register()
        self.assertEqual(FindingRegister.from_dict(register.to_dict()), register)

    def test_finding_dates_are_iso_strings(self) -> None:
        raw = sample_finding().to_dict()
        self.assertEqual(raw["due_on"], "2026-12-01")
        self.assertEqual(Finding.from_dict(raw), sample_finding())

    def test_bad_types_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Finding.from_dict({"due_on": "01/12/2026"})
        with self.assertRaises(ValueError):
            FindingRegister.from_dict({"findings": "not a list"})

    def test_workflow_round_trips_all_three_steps(self) -> None:
        workflow = Workflow(
            scope=sample_scope(), evidence=sample_evidence(), findings=sample_register()
        )
        restored = Workflow.from_dict(workflow.to_dict())
        self.assertEqual(restored, workflow)
        self.assertEqual(restored.findings.conclusion.opinion, "Does not conform")

    def test_workflow_still_reads_a_two_step_document(self) -> None:
        scope = sample_scope()
        two_step = {"version": 2, "scope": scope.to_dict(), "evidence": None}
        restored = Workflow.from_dict(two_step)
        self.assertEqual(restored.scope, scope)
        self.assertIsNone(restored.findings)


if __name__ == "__main__":
    unittest.main()
