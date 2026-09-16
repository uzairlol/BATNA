"""BATNA Theory-of-Mind (ToM) consistency auditing.

Phase 8 ships the **deterministic core**: every proposal turn is audited for
reasoning↔offer consistency, reasoning↔tool consistency, and tool-provenance.
The typed report (``AuditReport`` / ``AuditFinding``) streams under
``EventType.AUDIT`` and is recorded in ``turn_history``. The LLM-judge tier is
deferred to a later phase.
"""

from batna.audit.schemas import (
    AuditEventPayload,
    AuditFinding,
    AuditKind,
    AuditReport,
    AuditSeverity,
)
from batna.audit.tom_auditor import ToMAuditor

__all__ = [
    "AuditEventPayload",
    "AuditFinding",
    "AuditKind",
    "AuditReport",
    "AuditSeverity",
    "ToMAuditor",
]
