"""Re-export for backwards and plural import compatibility."""
from src.report.pdf_generator import LegalMetrologyPDFReport, build_pdf_report, sanitize_text

__all__ = ["LegalMetrologyPDFReport", "build_pdf_report", "sanitize_text"]
