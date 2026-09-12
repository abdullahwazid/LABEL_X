"""Statutory compliance reporting and inspection notice generation module."""

from src.reports.models import InspectionReport
from src.reports.generator import ReportGenerator

__all__ = ["InspectionReport", "ReportGenerator"]
