"""Downloadable Markdown and PDF report generators for SchemeSathi."""

from __future__ import annotations

from datetime import datetime, timezone

from fpdf import FPDF

from core.explain import build_global_fix_checklist
from core.models import (
    ConfirmedStudentProfile,
    HealthCheckResult,
    SchemeEvaluationResult,
)
from core.strings import t


def generate_markdown_report(
    profile: ConfirmedStudentProfile,
    health_checks: list[HealthCheckResult],
    scheme_results: list[SchemeEvaluationResult],
) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# {t('app_name')} Verification Readiness Report",
        "",
        f"Generated: {now_str}",
        f"**Notice:** {t('threshold_disclaimer')}",
        f"**Data Handling:** {t('prototype_notice')}",
        "",
        "## Confirmed Student Profile",
        f"- **Full Name:** {profile.full_name or 'Not provided'}",
        (
            f"- **Annual Income:** INR {profile.annual_income:,.0f}"
            if profile.annual_income is not None
            else "- **Annual Income:** Not provided"
        ),
        f"- **Category:** {profile.category or 'Not provided'}",
        (
            f"- **Marks Percentage:** {profile.marks_percentage:.2f}%"
            if profile.marks_percentage is not None
            else "- **Marks Percentage:** Not provided"
        ),
        f"- **Course:** {profile.course or 'Not provided'}",
        f"- **Primary Issue Date:** {profile.issue_date or 'Not provided'}",
        f"- **Issuing Authority:** {profile.issuing_authority or 'Not provided'}",
        "",
        "## Document Health Checks",
    ]

    for hc in health_checks:
        lines.append(
            f"- **[{hc.tag.value}] {hc.title} ({hc.status.value.upper()}):** {hc.detail}"
        )

    lines.extend(["", "## Scheme Verdicts"])
    for res in scheme_results:
        lines.extend(
            [
                f"### {res.scheme_name} — {res.verdict.value}",
                f"- **Provider:** {res.provider} ({res.level})",
                f"- **Reason:** {res.summary_reason}",
                f"- **Official Portal:** {res.source_url}",
                f"- **Last Verified:** {res.last_verified}",
            ]
        )
        if res.checklist:
            lines.append("- **Fix before you submit:**")
            for step in res.checklist:
                lines.append(f"  - {step}")
        lines.append("")

    global_fixes = build_global_fix_checklist(health_checks, scheme_results)
    lines.append("## Fix Before You Submit Checklist")
    if not global_fixes:
        lines.append("- No blocking issues found in verified checks.")
    else:
        for idx, item in enumerate(global_fixes, start=1):
            lines.append(f"{idx}. {item}")

    return "\n".join(lines)


def _latin1_safe(text: str) -> str:
    return text.encode("latin-1", errors="replace").decode("latin-1")


def generate_pdf_report(
    profile: ConfirmedStudentProfile,
    health_checks: list[HealthCheckResult],
    scheme_results: list[SchemeEvaluationResult],
) -> bytes:
    """Render a clean, printable PDF verification report using fpdf2."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(20, 33, 61)
    pdf.cell(0, 10, _latin1_safe(f"{t('app_name')} - Verification Report"), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 5, _latin1_safe(f"{t('threshold_disclaimer')} | {t('prototype_notice')}"))
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(20, 33, 61)
    pdf.cell(0, 8, "Confirmed Profile", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(30, 30, 30)
    income_str = (
        f"INR {profile.annual_income:,.0f}" if profile.annual_income is not None else "Not provided"
    )
    marks_str = (
        f"{profile.marks_percentage:.2f}%" if profile.marks_percentage is not None else "Not provided"
    )
    profile_lines = [
        f"Name: {profile.full_name or 'Not provided'}",
        f"Annual Income: {income_str}",
        f"Category: {profile.category or 'Not provided'}",
        f"Marks: {marks_str}",
        f"Course: {profile.course or 'Not provided'}",
        f"Issue Date: {profile.issue_date or 'Not provided'}",
        f"Issuing Authority: {profile.issuing_authority or 'Not provided'}",
    ]
    for line in profile_lines:
        pdf.cell(0, 6, _latin1_safe(line), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(20, 33, 61)
    pdf.cell(0, 8, "Document Health Checks", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(30, 30, 30)
    for hc in health_checks:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(
            pdf.epw,
            5,
            _latin1_safe(f"[{hc.tag.value}] {hc.title} ({hc.status.value.upper()}): {hc.detail}"),
        )
        pdf.ln(1)

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(20, 33, 61)
    pdf.cell(0, 8, "Scheme Verdicts", new_x="LMARGIN", new_y="NEXT")
    for res in scheme_results:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(20, 33, 61)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 6, _latin1_safe(f"{res.scheme_name} - {res.verdict.value}"))
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(40, 40, 40)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(
            pdf.epw,
            5,
            _latin1_safe(
                f"Reason: {res.summary_reason}\n"
                f"Source: {res.source_url} | Last verified: {res.last_verified}"
            ),
        )
        pdf.ln(2)

    return bytes(pdf.output())
