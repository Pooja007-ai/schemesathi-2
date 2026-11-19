"""Unit tests for LLM schema validation/retry (core/extract.py) and ingestion (core/ingest.py)."""

from __future__ import annotations

import json

import cv2
import numpy as np
import pytest
from fpdf import FPDF

from core.extract import ExtractionError, extract_fields_from_text
from core.ingest import compute_laplacian_variance, ingest_pdf_bytes
from core.models import DocumentType


def test_extract_retries_once_on_invalid_json_then_succeeds():
    calls = {"n": 0}

    def fake_llm(prompt: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "{not valid json"
        return json.dumps(
            {
                "full_name": "Ananya Kulkarni",
                "annual_income": 185000,
                "category": "OBC",
                "marks_percentage": None,
                "course": "B.E. CSE",
                "issue_date": "2026-08-15",
                "issuing_authority": "Tahsildar",
                "field_confidence": {"full_name": "high"},
            }
        )

    extracted, attempts = extract_fields_from_text(
        "Applicant Name: Ananya Kulkarni\nAnnual Income: Rs. 1,85,000",
        DocumentType.INCOME_CERTIFICATE,
        llm_callable=fake_llm,
    )
    assert attempts == 2
    assert extracted.full_name == "Ananya Kulkarni"
    assert extracted.annual_income == 185000.0


def test_extract_raises_after_two_validation_failures():
    def always_bad(_prompt: str) -> str:
        return json.dumps({"marks_percentage": 999})  # violates <= 100 Pydantic constraint

    with pytest.raises(ExtractionError):
        extract_fields_from_text(
            "Marks card text", DocumentType.MARKS_CARD, llm_callable=always_bad
        )


def test_laplacian_variance_distinguishes_sharp_vs_blurred_image():
    canvas = np.full((300, 500, 3), 255, dtype=np.uint8)
    cv2.putText(canvas, "SchemeSathi Test", (20, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)
    blurred = cv2.GaussianBlur(canvas, (15, 15), 5.0)

    sharp_var = compute_laplacian_variance(canvas)
    blur_var = compute_laplacian_variance(blurred)

    assert sharp_var > blur_var
    assert sharp_var > 100.0


def test_pymupdf_extracts_native_pdf_text():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "Applicant Full Name: Ananya Kulkarni | Annual Family Income: Rs. 1,85,000")
    pdf_bytes = bytes(pdf.output())

    ingested = ingest_pdf_bytes(
        pdf_bytes, "test_income.pdf", DocumentType.INCOME_CERTIFICATE
    )
    assert ingested.extraction_method == "pymupdf_text"
    assert "Ananya Kulkarni" in ingested.raw_text
