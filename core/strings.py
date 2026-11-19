"""Centralized UI strings for SchemeSathi.

Keeping all user-facing copy in one dictionary allows future addition of
Tamil ('ta'), Hindi ('hi'), and other regional languages without touching UI code.
"""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "app_name": "SchemeSathi",
        "tagline": "Will my application survive verification?",
        "prototype_notice": (
            "Documents are sent to an external LLM API for extraction. "
            "Use synthetic documents only."
        ),
        "threshold_disclaimer": "Prototype. Confirm thresholds on the official portal.",
        "nav_home": "Home",
        "nav_checker": "Checker",
        "nav_how_it_works": "How it works",
        "nav_evaluation": "Evaluation",
        "hero_title": "Check your scholarship documents before the portal rejects them.",
        "hero_subtitle": (
            "SchemeSathi reads your income certificate, marks card, and community "
            "certificate, spots blurry scans, name mismatches, or missing records, "
            "and checks each rule transparently."
        ),
        "cta_try_samples": "Try with sample documents",
        "cta_start_checker": "Start checking documents",
        "step_1_title": "1. Upload",
        "step_1_desc": "Add PDFs or photos of your income, marks, and community documents—or load synthetic samples.",
        "step_2_title": "2. Extract & confirm",
        "step_2_desc": "Text is read with PyMuPDF or Tesseract OCR, structured by an LLM, and reviewed by you.",
        "step_3_title": "3. Evaluate",
        "step_3_desc": "Deterministic Python rules and classical checks inspect every scheme and document.",
        "step_4_title": "4. Results",
        "step_4_desc": "Get clear verdicts, exact failure reasons, and a Fix-before-you-submit checklist.",
        "upload_heading": "Upload synthetic student documents",
        "upload_help": (
            "Upload PDF or image files (PNG, JPG) for each document type. "
            "If you are testing, load our synthetic sample packet instead."
        ),
        "use_samples_btn": "Use sample documents",
        "extract_btn": "Read & extract fields",
        "confirm_heading": "Review and confirm extracted fields",
        "confirm_help": (
            "Edit any value below before continuing. Confidence flags reflect what the "
            "extractor saw in the text; you have the final say."
        ),
        "confirm_checkbox": "I have reviewed these synthetic fields and want to run the rule check.",
        "evaluate_btn": "Run eligibility & document checks",
        "manual_entry_notice": (
            "Automatic extraction failed or is unavailable. Enter or correct the fields "
            "manually below—the rule engine works the same way."
        ),
        "health_heading": "Document health checks",
        "verdicts_heading": "Scheme verdicts",
        "checklist_heading": "Fix before you submit",
        "download_md": "Download Markdown report",
        "download_pdf": "Download PDF report",
        "how_heading": "How SchemeSathi works",
        "how_ai_title": "What uses AI (LLM)",
        "how_ai_body": (
            "Only reading unstructured document text into structured JSON fields "
            "(name, income, category, marks, course, issue date, issuing authority) "
            "and optionally phrasing a plain-language summary. AI never decides eligibility."
        ),
        "how_rules_title": "What uses deterministic Python rules",
        "how_rules_body": (
            "Every eligibility threshold, income cap, certificate age check, and "
            "required-document check runs in pure Python against schemes.yaml. "
            "Same input always gives the same verdict."
        ),
        "how_classical_title": "What uses classical algorithms (not ML)",
        "how_classical_body": (
            "Cross-document name matching uses RapidFuzz token-sort string similarity. "
            "Scan sharpness uses OpenCV Laplacian variance—a classical edge-contrast "
            "image test, not machine learning."
        ),
        "eval_heading": "Extraction accuracy evaluation",
        "eval_not_measured": "Not yet measured",
        "eval_instructions": (
            "Run scripts/evaluate_extraction.py against data/eval/ to measure "
            "field-level extraction accuracy on the labelled synthetic test set."
        ),
        "verdict_eligible": "ELIGIBLE",
        "verdict_almost": "ALMOST",
        "verdict_not_eligible": "NOT ELIGIBLE",
        "nav_chat": "Ask Doubts",
        "chat_heading": "Document Submission Assistant",
        "chat_subtitle": "Ask doubts about uploading documents, scan quality, name matching, or what checks mean. Rules still decide eligibility.",
        "chat_placeholder": "Ask a question about document submission...",
        "chat_disclaimer": "AI explains document checks only; Python rules decide eligibility.",
    }
}


def t(key: str, lang: str = "en") -> str:
    """Look up a localized UI string, falling back to English or the key itself."""
    bundle = STRINGS.get(lang, STRINGS["en"])
    return bundle.get(key, STRINGS["en"].get(key, key))
