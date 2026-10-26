"""Drive the real page through Streamlit's AppTest.

These are not model tests — those live beside each module and cover the rules.
Each test here boots ``streamlit_app.py`` the way a browser does, drives the
actual widgets, and checks both what the page renders and what it persists, so
the wiring between the steps is covered too.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from streamlit.testing.v1 import AppTest

from three_step_audit.storage import ENV_DB_PATH

APP = Path(__file__).resolve().parent.parent / "streamlit_app.py"
OBJECTIVE = "Confirm access reviews happen quarterly"
TITLE = "FY26 access-control review"

#: One database for the whole module. The page caches its store, so every test
#: shares this path and isolates itself by draft id instead.
_DB_DIR = ""
DB = Path()
_previous_db_env: str | None = None


def setUpModule() -> None:
    global _DB_DIR, DB, _previous_db_env
    _DB_DIR = tempfile.mkdtemp(prefix="three-step-audit-page-")
    DB = Path(_DB_DIR) / "drafts.sqlite3"
    _previous_db_env = os.environ.get(ENV_DB_PATH)
    os.environ[ENV_DB_PATH] = str(DB)


def tearDownModule() -> None:
    if _previous_db_env is None:
        os.environ.pop(ENV_DB_PATH, None)
    else:
        os.environ[ENV_DB_PATH] = _previous_db_env
    shutil.rmtree(_DB_DIR, ignore_errors=True)


def boot(draft_id: str | None = None) -> AppTest:
    """Run the page as a fresh browser session, optionally on a known draft link."""
    at = AppTest.from_file(str(APP), default_timeout=60)
    if draft_id is not None:
        at.query_params["draft"] = draft_id
    at.run()
    if at.exception:
        raise AssertionError(f"page raised on boot: {at.exception}")
    return at


def click(at: AppTest, label: str) -> AppTest:
    for button in at.button:
        if button.label == label:
            return button.click().run()
    raise AssertionError(f"no {label!r} button; page has {[b.label for b in at.button]}")


def draft_id_of(at: AppTest) -> str:
    raw = at.query_params["draft"]
    return raw[0] if isinstance(raw, list) else raw


def stored(draft_id: str) -> dict | None:
    """The draft as the app persisted it, or None if this visitor has none."""
    if not DB.exists():
        return None
    with closing(sqlite3.connect(DB)) as conn:
        row = conn.execute("SELECT payload FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    return None if row is None else json.loads(row[0])


def markdown(at: AppTest) -> list[str]:
    return [element.value for element in at.markdown]


def fill_scope(at: AppTest, title: str = TITLE, objectives: tuple[str, ...] = (OBJECTIVE,)) -> None:
    at.text_input(key="title::0").set_value(title)
    at.text_input(key="organization::0").set_value("Northwind Logistics")
    at.text_input(key="lead_auditor::0").set_value("R. Parslow")
    at.text_area(key="scope_summary::0").set_value(
        "Review quarterly access reviews for all production systems."
    )
    at.multiselect(key="in_scope_areas::0").set_value(["Access control"])
    at.text_area(key="objectives::0").set_value("\n".join(objectives))


def fill_single_evidence(at: AppTest) -> None:
    at.text_area(key="methodology::0").set_value(
        "Walked through the quarterly review log and re-performed one check."
    )
    item_id = list(at.session_state["evidence_item_ids"])[0]
    at.text_input(key=f"ev_{item_id}_reference").set_value("AC-01")
    at.text_area(key=f"ev_{item_id}_description").set_value(
        "Quarterly access review completed for all production systems."
    )
    at.text_input(key=f"ev_{item_id}_source").set_value("Identity team")


class PageWiringTest(unittest.TestCase):
    maxDiff = None

    def test_fresh_visit_offers_step_one_and_gates_step_two(self) -> None:
        at = boot()

        self.assertEqual([t.value for t in at.title], ["ThreeStepAudit"])
        self.assertTrue(
            any("Save step 1 first" in info.value for info in at.info),
            "step 2 should be gated until a scope is saved",
        )
        self.assertFalse([s.value for s in at.subheader if s.value.startswith("Step 3")])

        sidebar = [element.value for element in at.sidebar.markdown]
        self.assertEqual(len(sidebar), 3)
        self.assertIn("Scope & criteria", sidebar[0])
        self.assertIn("in progress", sidebar[0])
        self.assertIn("not started", sidebar[2])

    def test_empty_step_one_reports_errors_and_saves_nothing(self) -> None:
        at = boot()
        draft_id = draft_id_of(at)

        click(at, "Save step 1")

        self.assertTrue(any("need attention" in error.value for error in at.error))
        self.assertTrue(any("**Audit title**" in line for line in markdown(at)))
        self.assertTrue(any("**Objectives**" in line for line in markdown(at)))
        self.assertIsNone(stored(draft_id))

    def test_step_one_saves_and_reopens_from_its_own_link(self) -> None:
        at = boot()
        draft_id = draft_id_of(at)

        fill_scope(at)
        click(at, "Save step 1")

        self.assertEqual([s.value for s in at.success], ["Step 1 saved."])
        payload = stored(draft_id)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["scope"]["title"], TITLE)

        reopened = boot(draft_id)
        self.assertEqual(reopened.text_input(key="title::0").value, TITLE)
        captions = [c.value for c in reopened.caption]
        self.assertTrue(any(c.startswith("Last saved") for c in captions), captions)
        self.assertTrue(any(draft_id[:8] in c for c in captions), captions)

    def test_audit_completes_through_the_page_and_renders_the_report(self) -> None:
        at = boot()
        draft_id = draft_id_of(at)

        fill_scope(at)
        click(at, "Save step 1")

        # Step 2 is now editable; one item answers the one objective.
        fill_single_evidence(at)
        click(at, "Save step 2")
        self.assertEqual([s.value for s in at.success], ["Step 2 saved."])
        self.assertTrue(
            any("Step 3 — findings & conclusion" == s.value for s in at.subheader),
            "step 3 should unlock once evidence is saved",
        )

        # Nothing failed in testing, so drop the blank finding row and conclude.
        click(at, "Remove this finding")
        self.assertEqual(at.session_state["finding_item_ids"], [])
        at.selectbox(key="opinion::0").set_value("Conforms")
        at.text_area(key="conclusion_summary::0").set_value(
            "Access reviews operate as designed across all production systems."
        )
        at.text_input(key="concluded_by::0").set_value("R. Parslow")
        click(at, "Save step 3")

        self.assertEqual([s.value for s in at.success], ["Step 3 saved — the audit is complete."])
        self.assertTrue(
            any("opinion: Conforms" in c.value for c in at.caption),
            [c.value for c in at.caption],
        )
        self.assertEqual(list(at.session_state["finding_item_ids"]), [])

        # The export section renders the finished report inline.
        self.assertTrue(any(s.value == "Export" for s in at.subheader))
        preview = "\n".join(markdown(at))
        self.assertIn("## Conclusion", preview)
        self.assertIn("**Opinion:** Conforms", preview)
        self.assertIn("AC-01", preview)

        payload = stored(draft_id)
        self.assertEqual(payload["version"], 3)
        self.assertEqual(payload["findings"]["conclusion"]["opinion"], "Conforms")
        self.assertEqual(len(payload["evidence"]["items"]), 1)

    def test_start_over_clears_only_this_visitors_draft(self) -> None:
        first = boot()
        first_id = draft_id_of(first)
        fill_scope(first, title="Audit of alpha")
        click(first, "Save step 1")

        second = boot()
        second_id = draft_id_of(second)
        fill_scope(second, title="Audit of beta")
        click(second, "Save step 1")
        self.assertNotEqual(first_id, second_id)

        returning = boot(first_id)
        self.assertEqual(returning.text_input(key="title::0").value, "Audit of alpha")
        click(returning, "Start over")

        self.assertIsNone(stored(first_id))
        self.assertEqual(stored(second_id)["scope"]["title"], "Audit of beta")
        # The reset bumps the widget-key version, so the form is genuinely empty.
        self.assertEqual(returning.text_input(key="title::1").value, "")
        self.assertNotIn("evidence_item_ids", returning.session_state)


if __name__ == "__main__":
    unittest.main()
