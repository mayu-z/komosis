"""
PDF Report Generator for RIFT Agent.

Produces a professional report.pdf from a completed run's results dict.
Uses reportlab (pure Python, no system deps).

SOURCE_OF_TRUTH §6.4:
  - report.pdf written to /outputs/{run_id}/report.pdf
  - Generated async from final data after results.json is written.

The report contains:
  1. Header with RIFT branding and run metadata
  2. Score breakdown panel
  3. Fixes applied table (all 6 bug types)
  4. CI/CD timeline log
  5. Footer with generation timestamp
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger("rift.report")

# ── Colour palette ──────────────────────────────────────────
_BRAND_BLUE = colors.HexColor("#1a56db")
_BRAND_DARK = colors.HexColor("#111827")
_HEADER_BG = colors.HexColor("#1e3a5f")
_ROW_ALT = colors.HexColor("#f0f4f8")
_GREEN = colors.HexColor("#059669")
_RED = colors.HexColor("#dc2626")
_AMBER = colors.HexColor("#d97706")
_WHITE = colors.white

# ── Status colour map ───────────────────────────────────────
_STATUS_COLORS: dict[str, colors.Color] = {
    "PASSED": _GREEN,
    "FAILED": _RED,
    "QUARANTINED": _AMBER,
    "FIXED": _GREEN,
    "passed": _GREEN,
    "failed": _RED,
    "error": _RED,
}


def generate_report_pdf(results: dict[str, Any], output_path: Path) -> Path:
    """
    Generate a PDF report from results dict and write to output_path.

    Args:
        results: The results.json dict for a completed run.
        output_path: Absolute path to write report.pdf.

    Returns:
        The output_path on success.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=f"RIFT Run Report — {results.get('run_id', 'unknown')}",
        author="RIFT Autonomous CI/CD Healing Agent",
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "RiftTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=_BRAND_DARK,
        spaceAfter=4 * mm,
    )
    heading_style = ParagraphStyle(
        "RiftHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=_BRAND_BLUE,
        spaceBefore=6 * mm,
        spaceAfter=3 * mm,
    )
    body_style = ParagraphStyle(
        "RiftBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
    )
    small_style = ParagraphStyle(
        "RiftSmall",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.gray,
    )

    elements: list[Any] = []

    # ── 1. Title ────────────────────────────────────────────
    elements.append(Paragraph("RIFT — Autonomous CI/CD Healing Agent", title_style))
    elements.append(Paragraph("Run Report", styles["Heading3"]))
    elements.append(Spacer(1, 4 * mm))

    # ── 2. Run metadata ────────────────────────────────────
    elements.append(Paragraph("Run Information", heading_style))

    run_id = results.get("run_id", "N/A")
    final_status = results.get("final_status", "N/A")
    status_color = _STATUS_COLORS.get(final_status, _BRAND_DARK)

    meta_data = [
        ["Run ID", run_id],
        ["Repository", results.get("repo_url", "N/A")],
        ["Team", results.get("team_name", "N/A")],
        ["Leader", results.get("leader_name", "N/A")],
        ["Branch", results.get("branch_name", "N/A")],
        ["Final Status", final_status],
        ["Total Time", f"{results.get('total_time_secs', 0):.1f}s"],
        ["Total Failures", str(results.get("total_failures", 0))],
        ["Total Fixes", str(results.get("total_fixes", 0))],
    ]

    meta_table = Table(meta_data, colWidths=[45 * mm, 120 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), _BRAND_DARK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        # Highlight status row
        ("TEXTCOLOR", (1, 5), (1, 5), status_color),
        ("FONTNAME", (1, 5), (1, 5), "Helvetica-Bold"),
    ]))
    elements.append(meta_table)

    # ── 3. Score breakdown ──────────────────────────────────
    elements.append(Paragraph("Score Breakdown", heading_style))

    score = results.get("score", {})
    score_data = [
        ["Component", "Value"],
        ["Base Score", str(score.get("base", 100))],
        ["Speed Bonus", f"+{score.get('speed_bonus', 0)}"],
        ["Efficiency Penalty", f"-{score.get('efficiency_penalty', 0)}"],
        ["Final Score", str(score.get("total", 0))],
    ]

    score_table = Table(score_data, colWidths=[80 * mm, 40 * mm])
    score_table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        # Final score row highlight
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e0f2fe")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, -1), (1, -1), _BRAND_BLUE),
        ("FONTSIZE", (1, -1), (1, -1), 13),
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        # Alternating rows
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [_WHITE, _ROW_ALT]),
    ]))
    elements.append(score_table)

    # ── 4. Fixes table ──────────────────────────────────────
    fixes = results.get("fixes", [])
    elements.append(Paragraph("Fixes Applied", heading_style))

    if fixes:
        fix_header = ["#", "File", "Bug Type", "Line", "Status", "Commit Message"]
        fix_rows = [fix_header]
        for idx, fix in enumerate(fixes, 1):
            fix_rows.append([
                str(idx),
                _truncate(fix.get("file", ""), 35),
                fix.get("bug_type", ""),
                str(fix.get("line_number", "")),
                fix.get("status", ""),
                _truncate(fix.get("commit_message", ""), 40),
            ])

        fix_table = Table(
            fix_rows,
            colWidths=[8 * mm, 55 * mm, 22 * mm, 12 * mm, 15 * mm, 60 * mm],
        )
        fix_table.setStyle(TableStyle([
            # Header
            ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (3, 0), (4, -1), "CENTER"),
            # Grid
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            # Alternating rows
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _ROW_ALT]),
        ]))
        elements.append(fix_table)
    else:
        elements.append(Paragraph("No fixes were applied during this run.", body_style))

    # ── 5. CI/CD timeline ───────────────────────────────────
    ci_log = results.get("ci_log", [])
    elements.append(Paragraph("CI/CD Timeline", heading_style))

    if ci_log:
        ci_header = ["Iteration", "Status", "Timestamp", "Regression"]
        ci_rows = [ci_header]
        for entry in ci_log:
            ci_rows.append([
                str(entry.get("iteration", "")),
                entry.get("status", ""),
                _truncate(entry.get("timestamp", ""), 24),
                "Yes" if entry.get("regression") else "No",
            ])

        ci_table = Table(ci_rows, colWidths=[22 * mm, 22 * mm, 65 * mm, 22 * mm])
        ci_table.setStyle(TableStyle([
            # Header
            ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ("ALIGN", (3, 1), (3, -1), "CENTER"),
            # Grid
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            # Alternating rows
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _ROW_ALT]),
        ]))
        elements.append(ci_table)
    else:
        elements.append(Paragraph("No CI runs were recorded.", body_style))

    # ── 6. Footer ───────────────────────────────────────────
    elements.append(Spacer(1, 8 * mm))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    elements.append(Paragraph(
        f"Generated by RIFT Autonomous CI/CD Healing Agent • {now}",
        small_style,
    ))

    # Build PDF
    doc.build(elements)
    logger.info("Generated report PDF: %s", output_path)
    return output_path


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if it exceeds max_len."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
