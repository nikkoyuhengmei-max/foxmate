"""Compliance subsystem for China program-trading rules.

Implements the building blocks required by 《证券市场程序化交易管理规定（试行）》
and the SSE/SZSE/BSE implementation rules: program-trading filing management,
parametrised regulatory thresholds, abnormal-trading monitoring and a tamper-
evident audit log.
"""

from aqs.compliance.audit import AuditLog, AuditEvent
from aqs.compliance.filing import ProgramTradingFiling
from aqs.compliance.monitor import ComplianceMonitor

__all__ = ["AuditLog", "AuditEvent", "ProgramTradingFiling", "ComplianceMonitor"]
