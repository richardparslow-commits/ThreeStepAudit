"""Tests for the durable, per-visitor draft store."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from three_step_audit.evidence import EvidenceItem, EvidencePlan
from three_step_audit.models import AuditScope
from three_step_audit.storage import LEGACY_ID, DraftStore, DraftStoreError
from three_step_audit.workflow import Workflow

VISITOR_A = "a" * 32
VISITOR_B = "b" * 32


def sample_scope(title: str = "FY26 access-control review") -> AuditScope:
    return AuditScope(
        title=title,
        organization="Northwind Logistics",
        audit_type="Internal",
        standard="ISO 27001",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 6, 30),
        lead_auditor="R. Parslow",
        scope_summary="Review quarterly access reviews for all production systems.",
        in_scope_areas=["Access control", "Change management"],
        objectives=["Confirm access reviews happen quarterly"],
        created_at=datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc),
    )


def sample_plan() -> EvidencePlan:
    return EvidencePlan(
        methodology="Sampled every production system and re-performed one review.",
        items=[
            EvidenceItem(
                reference="AC-01",
                description="Quarterly access review completed for all production systems.",
                source="Identity team",
                objective="Confirm access reviews happen quarterly",
                collected_on=date(2026, 10, 1),
                result="Pass",
            )
        ],
    )


def sample_workflow(title: str = "FY26 access-control review") -> Workflow:
    return Workflow(scope=sample_scope(title), evidence=sample_plan())


class DraftStoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "var" / "drafts.sqlite3"
        self.store = DraftStore(self.db_path)

    def count_rows(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]


class DraftStoreTests(DraftStoreTestCase):
    def test_load_before_any_save_returns_none(self) -> None:
        self.assertIsNone(self.store.load(VISITOR_A))
        self.assertIsNone(self.store.saved_at(VISITOR_A))

    def test_creates_the_database_directory(self) -> None:
        self.store.save(VISITOR_A, sample_workflow())
        self.assertTrue(self.db_path.is_file())

    def test_save_then_load_round_trips_both_steps(self) -> None:
        original = sample_workflow()
        saved_at = self.store.save(VISITOR_A, original)
        self.assertIsNotNone(saved_at)

        loaded = self.store.load(VISITOR_A)
        self.assertEqual(loaded, original)
        self.assertEqual(loaded.scope.title, "FY26 access-control review")
        self.assertEqual(len(loaded.evidence.items), 1)

    def test_second_save_replaces_the_first_for_the_same_visitor(self) -> None:
        self.store.save(VISITOR_A, sample_workflow("First"))
        self.store.save(VISITOR_A, sample_workflow("Second"))
        self.assertEqual(self.store.load(VISITOR_A).scope.title, "Second")
        self.assertEqual(self.count_rows(), 1)

    def test_visitors_do_not_see_or_overwrite_each_other(self) -> None:
        self.store.save(VISITOR_A, sample_workflow("A's audit"))
        self.store.save(VISITOR_B, sample_workflow("B's audit"))

        self.assertEqual(self.store.load(VISITOR_A).scope.title, "A's audit")
        self.assertEqual(self.store.load(VISITOR_B).scope.title, "B's audit")
        self.assertEqual(self.count_rows(), 2)

        self.store.save(VISITOR_B, sample_workflow("B revised"))
        self.assertEqual(self.store.load(VISITOR_A).scope.title, "A's audit")

    def test_saved_at_is_recorded_and_advances(self) -> None:
        first = self.store.save(VISITOR_A, sample_workflow("First"))
        self.assertGreaterEqual(self.store.saved_at(VISITOR_A), first)
        second = self.store.save(VISITOR_A, sample_workflow("Second"))
        self.assertGreaterEqual(second, first)
        self.assertIsNotNone(self.store.saved_at(VISITOR_A))

    def test_clear_only_removes_one_visitors_draft(self) -> None:
        self.store.save(VISITOR_A, sample_workflow("A"))
        self.store.save(VISITOR_B, sample_workflow("B"))

        self.assertTrue(self.store.clear(VISITOR_A))
        self.assertIsNone(self.store.load(VISITOR_A))
        self.assertEqual(self.store.load(VISITOR_B).scope.title, "B")
        self.assertFalse(self.store.clear(VISITOR_A))

    def test_unreadable_payload_raises_value_error(self) -> None:
        self.store.save(VISITOR_A, sample_workflow())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE drafts SET payload = ? WHERE id = ?", ("{not json", VISITOR_A)
            )
        with self.assertRaises(ValueError):
            self.store.load(VISITOR_A)

    def test_missing_draft_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.load("")
        with self.assertRaises(ValueError):
            self.store.save("  ", sample_workflow())


class LegacyDraftTests(DraftStoreTestCase):
    def test_legacy_step_one_payload_is_read_as_a_workflow(self) -> None:
        self.store.save(VISITOR_A, sample_workflow())
        # Overwrite with the pre-step-2 document shape.
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE drafts SET payload = ? WHERE id = ?",
                (sample_scope().to_json(), VISITOR_A),
            )
        loaded = self.store.load(VISITOR_A)
        self.assertEqual(loaded.scope, sample_scope())
        self.assertIsNone(loaded.evidence)

    def test_visitor_without_a_draft_inherits_the_legacy_slot(self) -> None:
        self.store.save(LEGACY_ID, sample_workflow("Pre-isolation draft"))

        adopted = self.store.load_for_visitor(VISITOR_A)

        self.assertIsNotNone(adopted)
        self.assertEqual(adopted.scope.title, "Pre-isolation draft")
        self.assertEqual(self.store.load(VISITOR_A), adopted)
        self.assertIsNone(self.store.load(LEGACY_ID))
        self.assertEqual(self.count_rows(), 1)

    def test_legacy_slot_is_handed_to_the_first_visitor_only(self) -> None:
        self.store.save(LEGACY_ID, sample_workflow("Pre-isolation draft"))

        self.store.load_for_visitor(VISITOR_A)

        self.assertIsNone(self.store.load_for_visitor(VISITOR_B))
        self.assertIsNone(self.store.load(VISITOR_B))

    def test_visitor_with_their_own_draft_keeps_it(self) -> None:
        self.store.save(LEGACY_ID, sample_workflow("Pre-isolation draft"))
        self.store.save(VISITOR_A, sample_workflow("A's own draft"))

        kept = self.store.load_for_visitor(VISITOR_A)

        self.assertEqual(kept.scope.title, "A's own draft")
        self.assertIsNone(self.store.load(LEGACY_ID))

    def test_no_draft_anywhere_yields_none(self) -> None:
        self.assertIsNone(self.store.load_for_visitor(VISITOR_A))


class DraftStoreFailureTests(unittest.TestCase):
    def test_unusable_path_raises_store_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "not-a-directory"
            blocker.write_text("i am a file")
            store = DraftStore(blocker / "nested" / "drafts.sqlite3")
            with self.assertRaises(DraftStoreError):
                store.load(VISITOR_A)


if __name__ == "__main__":
    unittest.main()
