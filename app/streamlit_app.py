"""SchemeSathi Streamlit Application.

Run with:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import streamlit as st
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.checks import run_all_health_checks
from core.db import get_latest_eval_run, record_check_session
from core.explain import build_global_fix_checklist
from core.extract import ExtractionError, extract_fields_from_text
from core.ingest import ingest_document
from core.models import (
    ConfidenceLevel,
    ConfirmedStudentProfile,
    DocumentExtractionRecord,
    DocumentMetaRecord,
    DocumentType,
    ExtractedDocumentFields,
    HealthStatus,
    Verdict,
)
from core.report import generate_markdown_report, generate_pdf_report
from core.rules import evaluate_all_schemes, load_schemes
from core.strings import t

load_dotenv()

SAMPLES_DIR = ROOT_DIR / "data" / "samples"
EVAL_RESULTS_PATH = ROOT_DIR / "data" / "eval" / "results.json"

st.set_page_config(
    page_title=f"{t('app_name')} — {t('tagline')}",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Design system: Navy #14213D, Cream #F7F4EC, Amber #F2A33A, Space Grotesk + Inter
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@600;700&display=swap');

:root {
  --ss-navy: #14213D;
  --ss-cream: #F7F4EC;
  --ss-amber: #F2A33A;
  --ss-mint-bg: #DCFCE7;
  --ss-mint-fg: #166534;
  --ss-amber-bg: #FEF3C7;
  --ss-amber-fg: #92400E;
  --ss-coral-bg: #FEE2E2;
  --ss-coral-fg: #991B1B;
}

.stApp {
  background-color: var(--ss-cream);
  color: var(--ss-navy);
  font-family: 'Inter', sans-serif;
}

h1, h2, h3, h4 {
  font-family: 'Space Grotesk', sans-serif !important;
  color: var(--ss-navy) !important;
}

.ss-notice {
  background: #FFFFFF;
  border: 1px solid #E2DDD0;
  border-radius: 10px;
  padding: 12px 16px;
  font-size: 0.95rem;
  margin-bottom: 16px;
}

.ss-card {
  background: #FFFFFF;
  border: 1px solid #E2DDD0;
  border-radius: 12px;
  padding: 18px 20px;
  margin-bottom: 14px;
}

.ss-pill {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 999px;
  font-weight: 600;
  font-size: 0.8rem;
}

.ss-pill-eligible { background: var(--ss-mint-bg); color: var(--ss-mint-fg); }
.ss-pill-almost { background: var(--ss-amber-bg); color: var(--ss-amber-fg); }
.ss-pill-not { background: var(--ss-coral-bg); color: var(--ss-coral-fg); }
.ss-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 600;
  background: #EDE9DE;
  color: #14213D;
  margin-right: 8px;
}
</style>
""",
    unsafe_allow_html=True,
)


def _init_state() -> None:
    defaults: dict[str, Any] = {
        "page": "Home",
        "step": 1,
        "input_mode": "upload",
        "loaded_files": [],  # list of {"filename", "doc_type", "bytes"}
        "extraction_records": [],  # list of DocumentExtractionRecord dicts
        "confirmed_profile": None,
        "health_checks": [],
        "scheme_results": [],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _load_sample_files() -> list[dict[str, Any]]:
    specs = [
        ("sample_income_certificate.pdf", DocumentType.INCOME_CERTIFICATE),
        ("sample_marks_card.pdf", DocumentType.MARKS_CARD),
        ("sample_community_certificate.png", DocumentType.COMMUNITY_CERTIFICATE),
    ]
    loaded = []
    for fname, dtype in specs:
        fpath = SAMPLES_DIR / fname
        if fpath.exists():
            loaded.append(
                {
                    "filename": fname,
                    "doc_type": dtype.value,
                    "bytes": fpath.read_bytes(),
                }
            )
    return loaded


def _verdict_badge(verdict: Verdict) -> str:
    if verdict == Verdict.ELIGIBLE:
        return f'<span class="ss-pill ss-pill-eligible">{t("verdict_eligible")}</span>'
    if verdict == Verdict.ALMOST:
        return f'<span class="ss-pill ss-pill-almost">{t("verdict_almost")}</span>'
    return f'<span class="ss-pill ss-pill-not">{t("verdict_not_eligible")}</span>'


def _merge_initial_profile(records: list[DocumentExtractionRecord]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "full_name": "",
        "annual_income": None,
        "category": "",
        "marks_percentage": None,
        "course": "",
        "issue_date": "",
        "issuing_authority": "",
        "field_confidence": {},
    }
    for rec in records:
        ext = rec.extracted
        if not ext:
            continue
        for field in (
            "full_name",
            "annual_income",
            "category",
            "marks_percentage",
            "course",
            "issue_date",
            "issuing_authority",
        ):
            val = getattr(ext, field)
            if val is not None and (merged[field] is None or merged[field] == ""):
                merged[field] = val
                merged["field_confidence"][field] = ext.field_confidence.get(
                    field, ConfidenceLevel.MEDIUM
                ).value
    return merged


def render_stepper(current_step: int) -> None:
    steps = [t("step_1_title"), t("step_2_title"), t("step_3_title"), t("step_4_title")]
    cols = st.columns(4)
    for idx, col in enumerate(cols, start=1):
        marker = "Active" if idx == current_step else ("Done" if idx < current_step else "Pending")
        col.markdown(
            f"<div class='ss-card'><strong>{steps[idx - 1]}</strong><br/>"
            f"<span style='font-size:0.85rem;color:#475569'>{marker}</span></div>",
            unsafe_allow_html=True,
        )


def render_home() -> None:
    st.title(t("app_name"))
    st.subheader(t("tagline"))
    st.markdown(f"<div class='ss-notice'>{t('prototype_notice')}</div>", unsafe_allow_html=True)

    st.markdown(f"### {t('hero_title')}")
    st.write(t("hero_subtitle"))

    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button(t("cta_try_samples"), type="primary", use_container_width=True):
            st.session_state["loaded_files"] = _load_sample_files()
            st.session_state["input_mode"] = "sample"
            st.session_state["page"] = "Checker"
            st.session_state["step"] = 1
            st.rerun()
    with c2:
        if st.button(t("cta_start_checker"), use_container_width=False):
            st.session_state["page"] = "Checker"
            st.session_state["step"] = 1
            st.rerun()

    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**{t('step_1_title')}**")
        st.write(t("step_1_desc"))
    with col2:
        st.markdown(f"**{t('step_2_title')}**")
        st.write(t("step_2_desc"))
    with col3:
        st.markdown(f"**{t('step_3_title')} & {t('step_4_title')}**")
        st.write(t("step_3_desc") + " " + t("step_4_desc"))


def render_checker(fuzzy_threshold: float, sharpness_min: float) -> None:
    st.header("Scholarship Verification Checker")
    st.markdown(f"<div class='ss-notice'>{t('prototype_notice')}</div>", unsafe_allow_html=True)
    render_stepper(st.session_state["step"])

    step = st.session_state["step"]

    # STEP 1: UPLOAD
    if step == 1:
        st.subheader(t("upload_heading"))
        st.write(t("upload_help"))

        if st.button(t("use_samples_btn")):
            st.session_state["loaded_files"] = _load_sample_files()
            st.session_state["input_mode"] = "sample"
            st.success(f"Loaded {len(st.session_state['loaded_files'])} synthetic sample files.")

        c1, c2, c3 = st.columns(3)
        income_up = c1.file_uploader(
            "Income Certificate (PDF / PNG / JPG)", type=["pdf", "png", "jpg", "jpeg"]
        )
        marks_up = c2.file_uploader(
            "Marks Card (PDF / PNG / JPG)", type=["pdf", "png", "jpg", "jpeg"]
        )
        comm_up = c3.file_uploader(
            "Community Certificate (PDF / PNG / JPG)", type=["pdf", "png", "jpg", "jpeg"]
        )

        uploaded_list = []
        for up, dtype in (
            (income_up, DocumentType.INCOME_CERTIFICATE),
            (marks_up, DocumentType.MARKS_CARD),
            (comm_up, DocumentType.COMMUNITY_CERTIFICATE),
        ):
            if up is not None:
                uploaded_list.append(
                    {"filename": up.name, "doc_type": dtype.value, "bytes": up.getvalue()}
                )

        if uploaded_list:
            st.session_state["loaded_files"] = uploaded_list
            st.session_state["input_mode"] = "upload"

        active_files = st.session_state["loaded_files"]
        if active_files:
            st.write("Queued synthetic files:")
            for item in active_files:
                st.write(f"- `{item['filename']}` ({item['doc_type']})")

            if st.button(t("extract_btn"), type="primary"):
                records: list[DocumentExtractionRecord] = []
                for item in active_files:
                    dtype = DocumentType(item["doc_type"])
                    ingested = ingest_document(
                        item["bytes"],
                        item["filename"],
                        dtype,
                        min_sharpness_variance=sharpness_min,
                    )
                    try:
                        extracted, attempts = extract_fields_from_text(ingested.raw_text, dtype)
                        records.append(
                            DocumentExtractionRecord(
                                document=ingested, extracted=extracted, attempts=attempts
                            )
                        )
                    except ExtractionError as exc:
                        records.append(
                            DocumentExtractionRecord(
                                document=ingested, extracted=None, error=str(exc), attempts=2
                            )
                        )
                st.session_state["extraction_records"] = [
                    r.model_dump(mode="json") for r in records
                ]
                st.session_state["step"] = 2
                st.rerun()
        else:
            if st.button("Enter fields manually without uploading"):
                st.session_state["extraction_records"] = []
                st.session_state["step"] = 2
                st.rerun()

    # STEP 2: EXTRACT & CONFIRM
    elif step == 2:
        st.subheader(t("confirm_heading"))
        st.write(t("confirm_help"))

        records = [
            DocumentExtractionRecord.model_validate(r)
            for r in st.session_state["extraction_records"]
        ]
        if any(r.error for r in records) or not records:
            st.warning(t("manual_entry_notice"))
            for r in records:
                if r.error:
                    st.error(f"{r.document.filename}: {r.error}")

        for r in records:
            with st.expander(
                f"{r.document.filename} ({r.document.extraction_method} | {r.document.sharpness_label})"
            ):
                st.text(r.document.raw_text[:1500] or "(No text extracted)")

        merged = _merge_initial_profile(records)
        confs = merged["field_confidence"]

        with st.form("confirm_fields_form"):
            col_a, col_b = st.columns(2)
            full_name = col_a.text_input(
                f"Full Name (confidence: {confs.get('full_name', 'missing')})",
                value=merged["full_name"] or "",
            )
            income_str = col_b.text_input(
                f"Annual Family Income in INR (confidence: {confs.get('annual_income', 'missing')})",
                value="" if merged["annual_income"] is None else str(int(merged["annual_income"])),
            )
            category = col_a.text_input(
                f"Category (confidence: {confs.get('category', 'missing')})",
                value=merged["category"] or "",
            )
            marks_str = col_b.text_input(
                f"Marks Percentage (confidence: {confs.get('marks_percentage', 'missing')})",
                value="" if merged["marks_percentage"] is None else str(merged["marks_percentage"]),
            )
            course = col_a.text_input(
                f"Course (confidence: {confs.get('course', 'missing')})",
                value=merged["course"] or "",
            )
            issue_date = col_b.text_input(
                f"Primary Certificate Issue Date YYYY-MM-DD (confidence: {confs.get('issue_date', 'missing')})",
                value=merged["issue_date"] or "",
            )
            issuing_authority = st.text_input(
                f"Issuing Authority (confidence: {confs.get('issuing_authority', 'missing')})",
                value=merged["issuing_authority"] or "",
            )

            confirmed = st.checkbox(t("confirm_checkbox"))
            submitted = st.form_submit_button(t("evaluate_btn"), type="primary")

        if submitted:
            if not confirmed:
                st.error("Please tick the confirmation checkbox before evaluating rules.")
            else:
                annual_income = float(income_str.replace(",", "").strip()) if income_str.strip() else None
                marks_pct = float(marks_str.strip()) if marks_str.strip() else None

                doc_records = []
                available_docs = []
                for r in records:
                    available_docs.append(r.document.doc_type)
                    doc_records.append(
                        DocumentMetaRecord(
                            filename=r.document.filename,
                            doc_type=r.document.doc_type,
                            extracted_name=r.extracted.full_name if r.extracted else None,
                            issue_date=r.extracted.issue_date if r.extracted else None,
                            issuing_authority=r.extracted.issuing_authority if r.extracted else None,
                            sharpness_variance=r.document.sharpness_variance,
                            sharpness_passed=r.document.sharpness_passed,
                        )
                    )

                profile = ConfirmedStudentProfile(
                    full_name=full_name.strip() or None,
                    annual_income=annual_income,
                    category=category.strip() or None,
                    marks_percentage=marks_pct,
                    course=course.strip() or None,
                    issue_date=issue_date.strip() or None,
                    issuing_authority=issuing_authority.strip() or None,
                    available_docs=available_docs,
                    document_records=doc_records,
                )
                st.session_state["confirmed_profile"] = profile.model_dump(mode="json")
                st.session_state["step"] = 3
                st.rerun()

        if st.button("Back to upload"):
            st.session_state["step"] = 1
            st.rerun()

    # STEP 3: EVALUATE
    elif step == 3:
        profile = ConfirmedStudentProfile.model_validate(st.session_state["confirmed_profile"])
        records = [
            DocumentExtractionRecord.model_validate(r)
            for r in st.session_state["extraction_records"]
        ]
        ingested_docs = [r.document for r in records]
        schemes = load_schemes()

        health_checks = run_all_health_checks(
            profile,
            ingested_docs,
            schemes,
            fuzzy_threshold=fuzzy_threshold,
            sharpness_min_variance=sharpness_min,
        )
        scheme_results = evaluate_all_schemes(profile, schemes=schemes)

        record_check_session(
            input_mode=st.session_state["input_mode"],
            doc_count=len(ingested_docs),
            health_checks=health_checks,
            scheme_results=scheme_results,
        )

        st.session_state["health_checks"] = [h.model_dump(mode="json") for h in health_checks]
        st.session_state["scheme_results"] = [s.model_dump(mode="json") for s in scheme_results]
        st.session_state["step"] = 4
        st.rerun()

    # STEP 4: RESULTS
    elif step == 4:
        from core.models import HealthCheckResult, SchemeEvaluationResult

        profile = ConfirmedStudentProfile.model_validate(st.session_state["confirmed_profile"])
        health_checks = [
            HealthCheckResult.model_validate(h) for h in st.session_state["health_checks"]
        ]
        scheme_results = [
            SchemeEvaluationResult.model_validate(s) for s in st.session_state["scheme_results"]
        ]

        st.info(t("threshold_disclaimer"))
        st.subheader(t("health_heading"))
        for hc in health_checks:
            st.markdown(
                f"<div class='ss-card'><span class='ss-tag'>{hc.tag.value}</span>"
                f"<strong>{hc.title}</strong> — {hc.status.value.upper()}<br/>"
                f"<span>{hc.detail}</span></div>",
                unsafe_allow_html=True,
            )

        st.subheader(t("verdicts_heading"))
        for res in scheme_results:
            st.markdown(
                f"<div class='ss-card'>{_verdict_badge(res.verdict)} "
                f"<strong>{res.scheme_name}</strong><br/>"
                f"<span style='font-size:0.9rem;color:#475569'>{res.provider} · {res.level} · "
                f"Last verified: {res.last_verified} · {t('threshold_disclaimer')}</span><br/><br/>"
                f"<strong>Reason:</strong> {res.summary_reason}<br/>"
                f"<a href='{res.source_url}' target='_blank'>Official Portal Link</a></div>",
                unsafe_allow_html=True,
            )
            if res.checklist:
                with st.expander(f"{t('checklist_heading')} ({res.scheme_name})"):
                    for step_txt in res.checklist:
                        st.write(f"- {step_txt}")

        st.subheader(t("checklist_heading"))
        global_fixes = build_global_fix_checklist(health_checks, scheme_results)
        for item in global_fixes:
            st.write(f"- {item}")

        md_report = generate_markdown_report(profile, health_checks, scheme_results)
        pdf_report = generate_pdf_report(profile, health_checks, scheme_results)

        d1, d2, d3 = st.columns(3)
        d1.download_button(
            t("download_md"),
            data=md_report,
            file_name="schemesathi_report.md",
            mime="text/markdown",
        )
        d2.download_button(
            t("download_pdf"),
            data=pdf_report,
            file_name="schemesathi_report.pdf",
            mime="application/pdf",
        )
        if d3.button("Start new check"):
            st.session_state["step"] = 1
            st.rerun()


def render_how_it_works() -> None:
    st.header(t("how_heading"))
    st.markdown(f"<div class='ss-notice'>{t('prototype_notice')}</div>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader(t("how_ai_title"))
        st.write(t("how_ai_body"))
    with c2:
        st.subheader(t("how_rules_title"))
        st.write(t("how_rules_body"))
    with c3:
        st.subheader(t("how_classical_title"))
        st.write(t("how_classical_body"))


def render_evaluation() -> None:
    st.header(t("eval_heading"))
    eval_data: Optional[dict[str, Any]] = None
    if EVAL_RESULTS_PATH.exists():
        eval_data = json.loads(EVAL_RESULTS_PATH.read_text(encoding="utf-8"))
    else:
        eval_data = get_latest_eval_run()

    if not eval_data:
        st.warning(t("eval_not_measured"))
        st.write(t("eval_instructions"))
        st.code("python scripts/evaluate_extraction.py", language="bash")
        return

    st.write(
        f"Measured at `{eval_data.get('measured_at') or eval_data.get('run_at')}` · "
        f"Provider: `{eval_data['llm_provider']}` (`{eval_data['model_name']}`) · "
        f"Samples: `{eval_data['sample_count']}` · "
        f"Overall accuracy: **{eval_data['overall_accuracy'] * 100:.1f}%**"
    )
    rows = []
    for field_name, metrics in eval_data["field_metrics"].items():
        rows.append(
            {
                "Field": field_name,
                "Correct": metrics["correct"],
                "Total": metrics["total"],
                "Accuracy": f"{metrics['accuracy'] * 100:.1f}%",
            }
        )
    st.table(rows)


def main() -> None:
    _init_state()

    with st.sidebar:
        st.title(t("app_name"))
        st.caption(t("tagline"))
        pages = [
            t("nav_home"),
            t("nav_checker"),
            t("nav_how_it_works"),
            t("nav_evaluation"),
        ]
        chosen = st.radio("Navigation", pages, index=pages.index(st.session_state["page"]))
        st.session_state["page"] = chosen

        st.divider()
        st.subheader("Check thresholds")
        fuzzy_threshold = st.slider(
            "Name match similarity threshold (%)", min_value=50, max_value=100, value=85
        )
        sharpness_min = st.slider(
            "Minimum Laplacian variance (blur check)", min_value=20, max_value=300, value=100
        )

    page = st.session_state["page"]
    if page == t("nav_home"):
        render_home()
    elif page == t("nav_checker"):
        render_checker(float(fuzzy_threshold), float(sharpness_min))
    elif page == t("nav_how_it_works"):
        render_how_it_works()
    else:
        render_evaluation()


if __name__ == "__main__":
    main()
