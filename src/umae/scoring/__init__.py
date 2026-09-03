"""Scoring module: signal composition, calibration, and audit logging."""

from umae.scoring.audit import SignalAuditLogger
from umae.scoring.calibrator import ConfidenceCalibrator
from umae.scoring.signal_composer import SignalComposer

__all__ = [
    "ConfidenceCalibrator",
    "SignalAuditLogger",
    "SignalComposer",
]
