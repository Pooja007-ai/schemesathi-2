"""Evaluate field-level extraction accuracy on data/eval/ synthetic test set.

Computes real measured accuracy per field using the live ingestion and LLM
extraction pipeline. Never fabricates metrics. Writes results to
data/eval/results.json and SQLite (extraction_eval_runs).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from rapidfuzz import fuzz

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.db import record_eval_run
from core.extract import ExtractionError, extract_fields_from_text
from core.ingest import ingest_document
from core.models import DocumentType, EXTRACTED_FIELD_NAMES

load_dotenv()

EVAL_DIR = ROOT_DIR / "data" / "eval"
GROUND_TRUTH_PATH = EVAL_DIR / "ground_truth.json"
RESULTS_PATH = EVAL_DIR / "results.json"


def _field_matches(field_name: str, expected: Any, predicted: Any) -> bool:
    if expected is None and predicted is None:
        return True
    if expected is None or predicted is None:
        return False
    if field_name in ("annual_income", "marks_percentage"):
        try:
            return abs(float(expected) - float(predicted)) <= 0.01
        except (TypeError, ValueError):
            return False
    if field_name in ("issue_date", "category"):
        return str(expected).strip().lower() == str(predicted).strip().lower()
    # String fields: exact or >= 92% token_sort_ratio for punctuation differences
    exp_str = str(expected).strip()
    pred_str = str(predicted).strip()
    return exp_str.lower() == pred_str.lower() or fuzz.token_sort_ratio(exp_str, pred_str) >= 92


def run_evaluation() -> dict[str, Any]:
    if not GROUND_TRUTH_PATH.exists():
        raise FileNotFoundError(
            f"Missing {GROUND_TRUTH_PATH}. Run 'python scripts/make_samples.py' first."
        )

    manifest = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    model_name = (
        os.getenv("GEMINI_MODEL", "gemini-4-hydrogen")
        if provider == "gemini"
        else os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    )

    per_field_counts = {f: {"correct": 0, "total": 0} for f in EXTRACTED_FIELD_NAMES}
    case_results = []

    for item in manifest:
        file_path = EVAL_DIR / item["filename"]
        file_bytes = file_path.read_bytes()
        doc_type = DocumentType(item["doc_type"])
        ingested = ingest_document(file_bytes, item["filename"], doc_type)

        try:
            extracted, attempts = extract_fields_from_text(
                ingested.raw_text,
                doc_type,
                provider=provider,
                model_name=model_name,
            )
            pred_dict = extracted.model_dump()
            err = None
        except ExtractionError as exc:
            pred_dict = {f: None for f in EXTRACTED_FIELD_NAMES}
            attempts = 2
            err = str(exc)

        gt = item["ground_truth"]
        field_outcomes = {}
        for field_name in EXTRACTED_FIELD_NAMES:
            exp_val = gt.get(field_name)
            pred_val = pred_dict.get(field_name)
            matched = False if err else _field_matches(field_name, exp_val, pred_val)
            per_field_counts[field_name]["total"] += 1
            if matched:
                per_field_counts[field_name]["correct"] += 1
            field_outcomes[field_name] = {
                "expected": exp_val,
                "predicted": pred_val,
                "matched": matched,
            }

        case_results.append(
            {
                "id": item["id"],
                "filename": item["filename"],
                "extraction_method": ingested.extraction_method,
                "attempts": attempts,
                "error": err,
                "fields": field_outcomes,
            }
        )

    field_metrics = {}
    total_correct = 0
    total_fields = 0
    for field_name, counts in per_field_counts.items():
        acc = (counts["correct"] / counts["total"]) if counts["total"] else 0.0
        field_metrics[field_name] = {
            "correct": counts["correct"],
            "total": counts["total"],
            "accuracy": round(acc, 4),
        }
        total_correct += counts["correct"]
        total_fields += counts["total"]

    overall_accuracy = round(total_correct / total_fields, 4) if total_fields else 0.0
    payload = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(manifest),
        "llm_provider": provider,
        "model_name": model_name,
        "overall_accuracy": overall_accuracy,
        "field_metrics": field_metrics,
        "cases": case_results,
    }

    RESULTS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    record_eval_run(
        sample_count=len(manifest),
        llm_provider=provider,
        model_name=model_name,
        overall_accuracy=overall_accuracy,
        field_metrics=field_metrics,
    )
    return payload


def main() -> None:
    try:
        summary = run_evaluation()
        print(json.dumps(summary["field_metrics"], indent=2))
        print(f"Overall field accuracy: {summary['overall_accuracy'] * 100:.1f}%")
    except Exception as exc:  # noqa: BLE001
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
