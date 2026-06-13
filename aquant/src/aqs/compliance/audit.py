"""Tamper-evident audit log.

Every material action - strategy signal, order, fill, risk block, manual
intervention, parameter change, login, live-switch toggle - is appended here with
a hash chain so after-the-fact tampering is detectable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class AuditEvent:
    seq: int
    timestamp: str
    category: str          # order / trade / risk / compliance / system / manual
    action: str
    details: Dict[str, Any]
    prev_hash: str
    hash: str = ""


class AuditLog:
    """Append-only hash-chained log."""

    GENESIS = "0" * 64

    def __init__(self) -> None:
        self._events: List[AuditEvent] = []

    @property
    def last_hash(self) -> str:
        return self._events[-1].hash if self._events else self.GENESIS

    def record(
        self,
        category: str,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        timestamp: Optional[Any] = None,
    ) -> AuditEvent:
        details = details or {}
        ts = str(timestamp) if timestamp is not None else datetime.now(timezone.utc).isoformat()
        seq = len(self._events) + 1
        prev = self.last_hash
        payload = json.dumps(
            {"seq": seq, "timestamp": ts, "category": category, "action": action, "details": details, "prev": prev},
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()
        event = AuditEvent(seq=seq, timestamp=ts, category=category, action=action, details=details, prev_hash=prev, hash=digest)
        self._events.append(event)
        return event

    def verify(self) -> bool:
        """Re-compute the hash chain to detect tampering."""
        prev = self.GENESIS
        for e in self._events:
            payload = json.dumps(
                {"seq": e.seq, "timestamp": e.timestamp, "category": e.category, "action": e.action, "details": e.details, "prev": prev},
                sort_keys=True,
                default=str,
            )
            if hashlib.sha256(payload.encode()).hexdigest() != e.hash or e.prev_hash != prev:
                return False
            prev = e.hash
        return True

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([asdict(e) for e in self._events])

    def __len__(self) -> int:
        return len(self._events)
