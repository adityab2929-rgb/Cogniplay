"""PDF reporting package for the CogniPlay AI service.

:func:`~report.pdf_generator.generate_report` renders a parent-friendly
screening summary. Uses ReportLab when installed; otherwise emits a minimal
but structurally valid PDF so the download endpoint never fails.
"""

from typing import List

from .pdf_generator import generate_report, REPORTLAB_AVAILABLE

__all__: List[str] = ["generate_report", "REPORTLAB_AVAILABLE"]
