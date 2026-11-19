"""Unit tests for document health checks (core/checks.py)."""

from __future__ import annotations

from datetime import date

from core.checks import (
    check_certificate_ages,
    check_income_vs_caps,
    check_missing_required_docs,
    check_name_consistency,
    check_scan_quality,
)
from core.models import (
    CheckTag,
    ConfirmedStudentProfile,
    DocumentMetaRecord,
    DocumentType,
    HealthStatus,
    IngestedDocument,
    SchemeDefinition,
    SchemeRule,
)


def test_name_match_passes_similar_abbreviated_names():
    profile = ConfirmedStudentProfile(
        full_name="Ananya Ramesh Kulkarni",
        document_records=[
            DocumentMetaRecord(
                filename="income.pdf",
                doc_type=DocumentType.INCOME_CERTIFICATE,
                extracted_name="Ananya Ramesh Kulkarni",
            ),
            DocumentMetaRecord(
                filename="marks.pdf",
                doc_type=DocumentType.MARKS_CARD,
                extracted_name="Ananya Kulkarni Ramesh",
            ),
        ],
    )
    res = check_name_consistency(profile, threshold=85.0)
    assert res.tag == CheckTag.STRING_SIMILARITY
    assert res.status == HealthStatus.PASS


def test_name_mismatch_fails_below_threshold():
    profile = ConfirmedStudentProfile(
        full_name="Ananya Ramesh Kulkarni",
        document_records=[
            DocumentMetaRecord(
                filename="income.pdf",
                doc_type=DocumentType.INCOME_CERTIFICATE,
                extracted_name="Ananya Ramesh Kulkarni",
            ),
            DocumentMetaRecord(
                filename="marks.pdf",
                doc_type=DocumentType.MARKS_CARD,
                extracted_name="Rohan Prakash Verma",
            ),
        ],
    )
    res = check_name_consistency(profile, threshold=85.0)
    assert res.tag == CheckTag.STRING_SIMILARITY
    assert res.status == HealthStatus.FAIL
    assert "Name mismatch detected" in res.detail


def test_name_check_warns_with_single_document():
    profile = ConfirmedStudentProfile(
        full_name="Ananya Ramesh Kulkarni",
        document_records=[
            DocumentMetaRecord(
                filename="income.pdf",
                doc_type=DocumentType.INCOME_CERTIFICATE,
                extracted_name="Ananya Ramesh Kulkarni",
            )
        ],
    )
    res = check_name_consistency(profile, threshold=85.0)
    assert res.status == HealthStatus.WARN


def test_scan_quality_image_test_labels_and_thresholds():
    blurry = IngestedDocument(
        filename="blurry.png",
        doc_type=DocumentType.COMMUNITY_CERTIFICATE,
        file_kind="image",
        raw_text="sample",
        extraction_method="tesseract_ocr",
        sharpness_variance=35.2,
        sharpness_passed=False,
    )
    res = check_scan_quality([blurry], min_variance=100.0)
    assert res.tag == CheckTag.IMAGE_TEST
    assert res.status == HealthStatus.FAIL


def test_certificate_age_and_income_and_missing_doc_checks():
    scheme = SchemeDefinition(
        id="s1",
        name="Verified Test Scheme",
        provider="Gov",
        level="Post-Matric",
        source_url="https://scholarships.gov.in/",
        last_verified="2026-10-01",
        validity_months=12,
        required_docs=[DocumentType.INCOME_CERTIFICATE, DocumentType.MARKS_CARD],
        rules=[SchemeRule(field="annual_income", op="<=", value=250000)],
    )
    profile = ConfirmedStudentProfile(
        annual_income=250000.0,
        available_docs=[DocumentType.INCOME_CERTIFICATE],
        document_records=[
            DocumentMetaRecord(
                filename="income.pdf",
                doc_type=DocumentType.INCOME_CERTIFICATE,
                issue_date="2026-05-01",
            )
        ],
        reference_date=date(2026, 11, 18),
    )

    age_res = check_certificate_ages(profile, [scheme])
    inc_res = check_income_vs_caps(profile, [scheme])
    doc_res = check_missing_required_docs(profile, [scheme])

    assert age_res.tag == CheckTag.RULE and age_res.status == HealthStatus.PASS
    assert inc_res.tag == CheckTag.RULE and inc_res.status == HealthStatus.PASS
    assert doc_res.tag == CheckTag.RULE and doc_res.status == HealthStatus.WARN
