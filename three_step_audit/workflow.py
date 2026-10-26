"""The saved document for one audit: the steps captured so far."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from three_step_audit.evidence import EvidencePlan
from three_step_audit.findings import FindingRegister
from three_step_audit.models import AuditScope

#: Bumped if the saved document shape changes again.
DOCUMENT_VERSION = 3


@dataclass
class Workflow:
    """One audit across steps; either step may be missing while work is in progress."""

    scope: AuditScope | None = None
    evidence: EvidencePlan | None = None
    findings: FindingRegister | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": DOCUMENT_VERSION,
            "scope": self.scope.to_dict() if self.scope else None,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "findings": self.findings.to_dict() if self.findings else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Workflow:
        if not isinstance(data, Mapping):
            raise ValueError("draft data must be a JSON object")

        if "scope" in data or "evidence" in data or "findings" in data:
            raw_scope = data.get("scope")
            raw_evidence = data.get("evidence")
            raw_findings = data.get("findings")
            return cls(
                scope=AuditScope.from_dict(raw_scope) if raw_scope else None,
                evidence=EvidencePlan.from_dict(raw_evidence) if raw_evidence else None,
                findings=FindingRegister.from_dict(raw_findings) if raw_findings else None,
            )

        # Drafts written before step 2 existed are a bare step 1 document.
        if data.get("step") == 1:
            return cls(scope=AuditScope.from_dict(data))

        raise ValueError("unrecognised draft format")

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str) -> Workflow:
        import json

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"draft is not valid JSON: {exc.msg}") from exc
        return cls.from_dict(data)

    def file_stem(self) -> str:
        if self.scope and self.scope.title.strip():
            return self.scope.title.strip().lower().replace(" ", "-")
        return "audit"
