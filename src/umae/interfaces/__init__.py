"""Interfaces and high-level services."""

from umae.interfaces.analysis_service import AnalysisResult, AnalysisService
from umae.interfaces.data_adapter import DataAdapter

__all__ = [
    "AnalysisResult",
    "AnalysisService",
    "DataAdapter",
]
