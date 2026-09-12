"""
Parent-facing PDF report generation.

:func:`generate_report` turns a prediction result into a printable summary a
parent can take to a teacher: the three screening indicators with their risk
bands, the behaviours that drove each one, the suggested next steps, and a
prominent disclaimer that none of this is a diagnosis.

Two paths, same output type (``bytes``):

* **ReportLab available** -- a properly typeset A4 document with headings,
  colour-coded score bands, and wrapped paragraphs.
* **ReportLab missing** -- a minimal PDF written directly with the standard
  library. It is plain (Helvetica, no wrapping niceties) but it is a
  structurally valid PDF carrying the same numbers, so the download endpoint
  degrades instead of failing.

This function never raises.

Python 3.9 compatible: typing.Optional / typing.Dict / typing.List only.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:  # pragma: no cover - depends on the deployment environment
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )
    REPORTLAB_AVAILABLE = True
except ImportError:  # pragma: no cover
    REPORTLAB_AVAILABLE = False
    logger.info(
        "ReportLab not installed -- PDF reports will use the minimal "
        "stdlib writer."
    )

CONDITION_TITLES: Dict[str, str] = {
    "dyslexia": "Reading & Letters (Dyslexia indicators)",
    "dyscalculia": "Numbers & Counting (Dyscalculia indicators)",
    "adhd": "Attention & Focus (ADHD indicators)",
}

CONDITIONS: List[str] = ["dyslexia", "dyscalculia", "adhd"]

DISCLAIMER_TITLE: str = "IMPORTANT: This is a screening tool, not a diagnosis"

DISCLAIMER_BODY: str = (
    "CogniPlay is an educational screening game. It looks for patterns in how "
    "a child plays and compares them with behaviours described in the early "
    "learning research. It cannot and does not diagnose dyslexia, "
    "dyscalculia, ADHD, or any other condition. "
    "A high indicator does not mean your child has a learning disability, and "
    "a low indicator does not rule one out. Many 4-5 year olds show these "
    "patterns simply because these skills are still developing. "
    "Only a qualified professional -- an educational psychologist, "
    "paediatrician, or specialist teacher -- can assess a child properly. "
    "Please use this report as a conversation starter with your child's "
    "school, never as a conclusion. The scores in this report were produced "
    "by an untrained heuristic model built for a student project and have not "
    "been clinically validated."
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get(mapping: Any, key: str, default: Any = None) -> Any:
    """Safe ``dict.get`` that tolerates non-dict input."""
    if isinstance(mapping, dict):
        value = mapping.get(key)
        return default if value is None else value
    return default


def _score(results: Any, condition: str) -> float:
    """Read one condition score from a results dict, clamped to [0, 1]."""
    value = _get(results, "{0}_score".format(condition), 0.0)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:  # NaN
        return 0.0
    return min(1.0, max(0.0, number))


def _level(results: Any, condition: str, score: float) -> str:
    """Read the risk band, recomputing it if the results omit one."""
    levels = _get(results, "risk_levels", {})
    band = _get(levels, condition)
    if isinstance(band, str) and band:
        return band
    if score < 0.34:
        return "Low"
    if score < 0.67:
        return "Moderate"
    return "High"


def _factors(results: Any, condition: str) -> List[Dict[str, Any]]:
    """Read the top factor list for a condition, always returning a list."""
    explanation = _get(results, "explanation", {})
    block = _get(explanation, condition, {})
    factors = _get(block, "top_factors", [])
    return factors if isinstance(factors, list) else []


def _summary(results: Any, condition: str) -> str:
    """Read the parent-facing summary sentence for a condition."""
    explanation = _get(results, "explanation", {})
    block = _get(explanation, condition, {})
    text = _get(block, "summary", "")
    return text if isinstance(text, str) else ""


def _recommendations(results: Any) -> List[str]:
    """Read the recommendation strings, always returning a list of str."""
    items = _get(results, "recommendations", [])
    if not isinstance(items, list):
        return []
    return [str(item) for item in items if item]


def _child_details(payload: Any) -> Tuple[str, str, str]:
    """Extract ``(name, age, session date)`` with friendly placeholders."""
    name = _get(payload, "child_name", "") or "Your child"
    age = _get(payload, "child_age", "")
    age_text = "{0} years".format(age) if age not in ("", None) else "Not given"
    date = _get(payload, "session_date", "") or "Not recorded"
    return str(name), str(age_text), str(date)


# ---------------------------------------------------------------------------
# ReportLab path
# ---------------------------------------------------------------------------

def _band_colour(level: str) -> Any:
    """Map a risk band onto a background colour for the score table."""
    if level == "High":
        return colors.HexColor("#F8D7DA")
    if level == "Moderate":
        return colors.HexColor("#FFF3CD")
    return colors.HexColor("#D4EDDA")


def _build_with_reportlab(payload: Any, results: Any) -> bytes:
    """Render the full typeset report. Raises on failure; caller catches."""
    import io

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="CogniPlay Screening Summary",
        author="CogniPlay",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CogniTitle", parent=styles["Title"], fontSize=22, spaceAfter=2,
        textColor=colors.HexColor("#2C3E7B"),
    )
    subtitle_style = ParagraphStyle(
        "CogniSubtitle", parent=styles["Normal"], fontSize=10,
        alignment=TA_CENTER, textColor=colors.HexColor("#666666"),
        spaceAfter=10,
    )
    heading_style = ParagraphStyle(
        "CogniHeading", parent=styles["Heading2"], fontSize=13,
        spaceBefore=12, spaceAfter=4,
        textColor=colors.HexColor("#2C3E7B"),
    )
    body_style = ParagraphStyle(
        "CogniBody", parent=styles["Normal"], fontSize=10, leading=14,
        spaceAfter=4,
    )
    bullet_style = ParagraphStyle(
        "CogniBullet", parent=body_style, leftIndent=12, bulletIndent=2,
        spaceAfter=3,
    )
    disclaimer_title_style = ParagraphStyle(
        "CogniDisclaimerTitle", parent=styles["Heading3"], fontSize=12,
        textColor=colors.HexColor("#8A1C1C"), spaceAfter=4,
    )
    disclaimer_style = ParagraphStyle(
        "CogniDisclaimer", parent=body_style, fontSize=9, leading=12.5,
        textColor=colors.HexColor("#4A1010"),
    )

    name, age_text, date_text = _child_details(payload)
    story: List[Any] = []

    # --- Header -----------------------------------------------------------
    story.append(Paragraph("CogniPlay", title_style))
    story.append(Paragraph(
        "Early Learning Screening Summary &mdash; a play-based indicator "
        "report for ages 4&ndash;5", subtitle_style,
    ))
    story.append(HRFlowable(width="100%", thickness=1,
                            color=colors.HexColor("#2C3E7B")))
    story.append(Spacer(1, 8))

    # --- Child details ----------------------------------------------------
    details = Table(
        [
            ["Child", name, "Age", age_text],
            ["Session", date_text, "Report version",
             str(_get(results, "model_version", "1.0.0"))],
        ],
        colWidths=[24 * mm, 58 * mm, 28 * mm, 44 * mm],
    )
    details.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F6FB")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD3E8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDE2F0")),
    ]))
    story.append(details)
    story.append(Spacer(1, 12))

    # --- Score table ------------------------------------------------------
    story.append(Paragraph("Screening indicators", heading_style))
    rows: List[List[Any]] = [["Area", "Indicator", "Level"]]
    band_rows: List[Tuple[int, str]] = []
    for index, condition in enumerate(CONDITIONS):
        score = _score(results, condition)
        level = _level(results, condition, score)
        rows.append([
            CONDITION_TITLES.get(condition, condition.title()),
            "{0}%".format(int(round(score * 100))),
            level,
        ])
        band_rows.append((index + 1, level))

    table = Table(rows, colWidths=[96 * mm, 30 * mm, 28 * mm])
    style_commands: List[Any] = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E7B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#AAB3CC")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD3E8")),
    ]
    for row_index, level in band_rows:
        style_commands.append(
            ("BACKGROUND", (0, row_index), (-1, row_index),
             _band_colour(level))
        )
        style_commands.append(
            ("FONTNAME", (2, row_index), (2, row_index), "Helvetica-Bold")
        )
    table.setStyle(TableStyle(style_commands))
    story.append(table)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "<i>Low: below 34%&nbsp;&nbsp;|&nbsp;&nbsp;Moderate: 34&ndash;66%"
        "&nbsp;&nbsp;|&nbsp;&nbsp;High: 67% and above</i>", body_style,
    ))

    # --- Per-condition detail --------------------------------------------
    for condition in CONDITIONS:
        score = _score(results, condition)
        level = _level(results, condition, score)
        story.append(Paragraph(
            "{0} &mdash; {1}".format(
                CONDITION_TITLES.get(condition, condition.title()), level,
            ),
            heading_style,
        ))
        summary = _summary(results, condition)
        if summary:
            story.append(Paragraph(summary, body_style))

        factors = _factors(results, condition)
        if factors:
            story.append(Paragraph("<b>What we noticed:</b>", body_style))
            for factor in factors:
                description = _get(factor, "description", "")
                value = _get(factor, "value", "")
                if not description:
                    continue
                text = "{0} <font color='#777777'>(measured: {1})</font>".format(
                    description, value,
                )
                story.append(Paragraph(text, bullet_style, bulletText="•"))

    # --- Recommendations --------------------------------------------------
    recommendations = _recommendations(results)
    if recommendations:
        story.append(Paragraph("Suggested next steps", heading_style))
        for item in recommendations:
            story.append(Paragraph(item, bullet_style, bulletText="•"))

    # --- Disclaimer -------------------------------------------------------
    story.append(Spacer(1, 14))
    disclaimer = Table(
        [[Paragraph(DISCLAIMER_TITLE, disclaimer_title_style)],
         [Paragraph(DISCLAIMER_BODY, disclaimer_style)]],
        colWidths=[154 * mm],
    )
    disclaimer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FDF2F2")),
        ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#C0392B")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(disclaimer)

    document.build(story)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Minimal stdlib PDF fallback
# ---------------------------------------------------------------------------

def _escape_pdf_text(text: str) -> str:
    """Escape a string for inclusion in a PDF literal string object."""
    safe = "".join(char if 32 <= ord(char) < 127 else " " for char in text)
    return (safe.replace("\\", r"\\")
                .replace("(", r"\(")
                .replace(")", r"\)"))


def _wrap(text: str, width: int) -> List[str]:
    """Greedy word wrap to a fixed character width (no font metrics needed)."""
    words = str(text).split()
    if not words:
        return [""]
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current = "{0} {1}".format(current, word)
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _report_lines(payload: Any, results: Any) -> List[Tuple[str, bool]]:
    """Build the report as ``(text, is_bold)`` lines for the fallback writer."""
    name, age_text, date_text = _child_details(payload)
    lines: List[Tuple[str, bool]] = [
        ("CogniPlay - Early Learning Screening Summary", True),
        ("", False),
        ("Child: {0}    Age: {1}".format(name, age_text), False),
        ("Session: {0}".format(date_text), False),
        ("Report version: {0}".format(_get(results, "model_version", "1.0.0")),
         False),
        ("", False),
        ("SCREENING INDICATORS", True),
    ]

    for condition in CONDITIONS:
        score = _score(results, condition)
        level = _level(results, condition, score)
        lines.append((
            "  {0}: {1}%  ({2})".format(
                CONDITION_TITLES.get(condition, condition.title()),
                int(round(score * 100)), level,
            ),
            False,
        ))
    lines.append(("  Low: below 34%   Moderate: 34-66%   High: 67%+", False))
    lines.append(("", False))

    for condition in CONDITIONS:
        title = CONDITION_TITLES.get(condition, condition.title())
        lines.append((title.upper(), True))
        summary = _summary(results, condition)
        if summary:
            for line in _wrap(summary, 92):
                lines.append(("  " + line, False))
        for factor in _factors(results, condition):
            description = _get(factor, "description", "")
            if not description:
                continue
            wrapped = _wrap("- {0} (measured: {1})".format(
                description, _get(factor, "value", "")), 90)
            for line in wrapped:
                lines.append(("  " + line, False))
        lines.append(("", False))

    recommendations = _recommendations(results)
    if recommendations:
        lines.append(("SUGGESTED NEXT STEPS", True))
        for item in recommendations:
            for line in _wrap("- " + item, 90):
                lines.append(("  " + line, False))
        lines.append(("", False))

    lines.append((DISCLAIMER_TITLE.upper(), True))
    for line in _wrap(DISCLAIMER_BODY, 92):
        lines.append(("  " + line, False))

    return lines


def _build_minimal_pdf(payload: Any, results: Any) -> bytes:
    """Write a valid single-page-per-chunk PDF using only the stdlib.

    Produces a truecolour-free, Helvetica-only document. Not pretty, but a
    conforming PDF that any reader will open -- which is the point: the
    ``/generate-report`` endpoint must never hand the frontend a 500 just
    because an optional dependency is absent.
    """
    page_width, page_height = 595, 842
    top_margin, left_margin = 800, 50
    line_height = 13
    lines_per_page = int((top_margin - 50) / line_height)

    all_lines = _report_lines(payload, results)
    pages: List[List[Tuple[str, bool]]] = [
        all_lines[i:i + lines_per_page]
        for i in range(0, len(all_lines), lines_per_page)
    ] or [[("CogniPlay report", True)]]

    # Object numbering: 1 catalog, 2 pages, 3 regular font, 4 bold font,
    # then per page a page object followed by its content stream.
    first_page_object = 5
    page_object_ids = [first_page_object + (i * 2) for i in range(len(pages))]

    objects: Dict[int, bytes] = {}

    kids = " ".join("{0} 0 R".format(pid) for pid in page_object_ids)
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = "<< /Type /Pages /Kids [{0}] /Count {1} >>".format(
        kids, len(pages)).encode("ascii")
    objects[3] = (b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                  b"/Encoding /WinAnsiEncoding >>")
    objects[4] = (b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                  b"/Encoding /WinAnsiEncoding >>")

    for index, page_lines in enumerate(pages):
        page_id = page_object_ids[index]
        content_id = page_id + 1

        parts: List[str] = ["BT"]
        cursor = top_margin
        for text, is_bold in page_lines:
            font = "/F2" if is_bold else "/F1"
            size = 12 if is_bold else 9.5
            parts.append("1 0 0 1 {0} {1} Tm".format(left_margin, cursor))
            parts.append("{0} {1} Tf".format(font, size))
            parts.append("({0}) Tj".format(_escape_pdf_text(text)))
            cursor -= line_height
        parts.append("ET")
        stream = "\n".join(parts).encode("latin-1", "replace")

        objects[page_id] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w} {h}] "
            "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            "/Contents {cid} 0 R >>".format(
                w=page_width, h=page_height, cid=content_id)
        ).encode("ascii")
        objects[content_id] = (
            "<< /Length {0} >>\nstream\n".format(len(stream)).encode("ascii")
            + stream
            + b"\nendstream"
        )

    # Serialise, recording byte offsets for the cross-reference table.
    output = bytearray(b"%PDF-1.4\n")
    offsets: Dict[int, int] = {}
    for object_id in sorted(objects):
        offsets[object_id] = len(output)
        output += "{0} 0 obj\n".format(object_id).encode("ascii")
        output += objects[object_id]
        output += b"\nendobj\n"

    max_id = max(objects)
    xref_offset = len(output)
    output += "xref\n0 {0}\n".format(max_id + 1).encode("ascii")
    output += b"0000000000 65535 f \n"
    for object_id in range(1, max_id + 1):
        output += "{0:010d} 00000 n \n".format(
            offsets.get(object_id, 0)).encode("ascii")
    output += (
        "trailer\n<< /Size {0} /Root 1 0 R >>\nstartxref\n{1}\n%%EOF\n".format(
            max_id + 1, xref_offset)
    ).encode("ascii")

    return bytes(output)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_report(payload: Optional[Dict[str, Any]],
                    results: Optional[Dict[str, Any]]) -> bytes:
    """Render the screening report as PDF bytes.

    Args:
        payload: The original telemetry payload (used for the child's name,
            age and session date). May be ``None`` or partial.
        results: The prediction result -- scores, risk levels, explanation
            and recommendations. May be ``None`` or partial.

    Returns:
        PDF file contents as ``bytes``. Always a valid PDF: ReportLab when
        available, otherwise the stdlib writer, otherwise a one-line
        placeholder document.

    This function never raises.
    """
    if payload is None:
        payload = {}
    if results is None:
        results = {}

    if REPORTLAB_AVAILABLE:
        try:
            return _build_with_reportlab(payload, results)
        except Exception as exc:
            logger.warning(
                "ReportLab rendering failed (%s) -- falling back to the "
                "minimal PDF writer.", exc,
            )

    try:
        return _build_minimal_pdf(payload, results)
    except Exception as exc:
        logger.error("Minimal PDF writer failed: %s", exc, exc_info=True)

    # Absolute last resort: a hand-written, known-good one-line PDF.
    try:
        return _build_minimal_pdf(
            {}, {"model_version": str(_get(results, "model_version", "1.0.0"))}
        )
    except Exception:
        return (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 595 842] >>\nendobj\n"
            b"trailer\n<< /Size 4 /Root 1 0 R >>\n%%EOF\n"
        )


__all__: List[str] = ["generate_report", "REPORTLAB_AVAILABLE",
                      "DISCLAIMER_BODY", "DISCLAIMER_TITLE"]
