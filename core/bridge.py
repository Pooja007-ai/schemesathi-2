"""JSON CLI bridge for invoking SchemeSathi's Python core modules from Node/Express."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.checks import run_all_health_checks
from core.db import get_latest_eval_run, record_check_session
from core.explain import build_global_fix_checklist
from core.extract import ExtractionError, extract_fields_from_text
from core.ingest import ingest_document
from core.models import (
    ConfirmedStudentProfile,
    DocumentType,
    IngestedDocument,
)
from core.report import generate_markdown_report, generate_pdf_report
from core.rules import evaluate_all_schemes, load_schemes
from core.strings import STRINGS


def cmd_metadata() -> dict[str, Any]:
    schemes = [s.model_dump(mode="json") for s in load_schemes()]
    eval_path = ROOT_DIR / "data" / "eval" / "results.json"
    eval_data = None
    if eval_path.exists():
        eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
    else:
        eval_data = get_latest_eval_run()

    return {
        "strings": STRINGS["en"],
        "schemes": schemes,
        "eval_results": eval_data,
    }


def cmd_load_samples() -> dict[str, Any]:
    samples_dir = ROOT_DIR / "data" / "samples"
    sample_specs = [
        ("sample_income_certificate.pdf", DocumentType.INCOME_CERTIFICATE),
        ("sample_marks_card.pdf", DocumentType.MARKS_CARD),
        ("sample_community_certificate.png", DocumentType.COMMUNITY_CERTIFICATE),
    ]
    out = []
    for fname, dtype in sample_specs:
        fpath = samples_dir / fname
        if not fpath.exists():
            raise FileNotFoundError(f"Sample file missing: {fpath}. Run scripts/make_samples.py.")
        raw_bytes = fpath.read_bytes()
        out.append(
            {
                "filename": fname,
                "doc_type": dtype.value,
                "size_bytes": len(raw_bytes),
                "content_base64": base64.b64encode(raw_bytes).decode("ascii"),
            }
        )
    return {"samples": out}


def cmd_ingest_and_extract(payload: dict[str, Any]) -> dict[str, Any]:
    docs_in = payload.get("documents", [])
    records = []
    for item in docs_in:
        filename = item["filename"]
        doc_type = DocumentType(item["doc_type"])
        file_bytes = base64.b64decode(item["content_base64"])
        ingested = ingest_document(file_bytes, filename, doc_type)
        extracted = None
        error = None
        attempts = 0
        try:
            extracted_model, attempts = extract_fields_from_text(ingested.raw_text, doc_type)
            extracted = extracted_model.model_dump(mode="json")
        except ExtractionError as exc:
            error = str(exc)
            attempts = 2

        records.append(
            {
                "document": ingested.model_dump(mode="json"),
                "extracted": extracted,
                "error": error,
                "attempts": attempts,
            }
        )
    return {"records": records}


def cmd_evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    profile = ConfirmedStudentProfile.model_validate(payload["profile"])
    ingested_docs = [IngestedDocument.model_validate(d) for d in payload.get("ingested_docs", [])]
    fuzzy_threshold = float(payload.get("fuzzy_threshold", 85.0))
    sharpness_min = float(payload.get("sharpness_min_variance", 100.0))
    input_mode = payload.get("input_mode", "upload")

    schemes = load_schemes()
    health_checks = run_all_health_checks(
        profile,
        ingested_docs,
        schemes,
        fuzzy_threshold=fuzzy_threshold,
        sharpness_min_variance=sharpness_min,
    )
    scheme_results = evaluate_all_schemes(profile, schemes=schemes)
    checklist = build_global_fix_checklist(health_checks, scheme_results)

    session_id = record_check_session(
        input_mode=input_mode if input_mode in ("upload", "sample") else "upload",
        doc_count=len(ingested_docs),
        health_checks=health_checks,
        scheme_results=scheme_results,
    )

    markdown_report = generate_markdown_report(profile, health_checks, scheme_results)
    pdf_bytes = generate_pdf_report(profile, health_checks, scheme_results)

    return {
        "session_id": session_id,
        "health_checks": [h.model_dump(mode="json") for h in health_checks],
        "scheme_results": [s.model_dump(mode="json") for s in scheme_results],
        "global_checklist": checklist,
        "markdown_report": markdown_report,
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
    }


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing command"}))
        sys.exit(1)
    cmd = sys.argv[1]
    raw_stdin = sys.stdin.read().strip()
    payload = json.loads(raw_stdin) if raw_stdin else {}

    if cmd == "metadata":
        res = cmd_metadata()
    elif cmd == "samples":
        res = cmd_load_samples()
    elif cmd == "extract":
        res = cmd_ingest_and_extract(payload)
    elif cmd == "evaluate":
        res = cmd_evaluate(payload)
    else:
        raise ValueError(f"Unknown command: {cmd}")

    print(json.dumps(res))


if __name__ == "__main__":
    main()
