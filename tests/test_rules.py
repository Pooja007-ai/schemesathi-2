"""Unit tests for SchemeSathi's deterministic rule engine (core/rules.py)."""

from __future__ import annotations

from datetime import date

import pytest

from core.models import (
    ConfirmedStudentProfile,
    DocumentMetaRecord,
    DocumentType,
    SchemeDefinition,
    SchemeRule,
    Verdict,
)
from core.rules import evaluate_rule, evaluate_scheme, load_schemes


def _make_scheme(rules: list[SchemeRule], required_docs=None, validity_months=12) -> SchemeDefinition:
    return SchemeDefinition(
        id="test_scheme",
        name="Test Scholarship",
        provider="Test Ministry",
        level="Post-Matric",
        source_url="https://scholarships.gov.in/",
        last_verified="2026-10-01",
        rules=rules,
        required_docs=required_docs or [DocumentType.INCOME_CERTIFICATE],
        validity_months=validity_months,
    )


def _make_profile(**overrides) -> ConfirmedStudentProfile:
    base = {
        "full_name": "Ananya Kulkarni",
        "annual_income": 250000.0,
        "category": "OBC",
        "marks_percentage": 75.0,
        "course": "B.E. Computer Science",
        "issue_date": "2026-08-01",
        "issuing_authority": "Tahsildar",
        "available_docs": [
            DocumentType.INCOME_CERTIFICATE,
            DocumentType.MARKS_CARD,
            DocumentType.COMMUNITY_CERTIFICATE,
        ],
        "document_records": [
            DocumentMetaRecord(
                filename="income.pdf",
                doc_type=DocumentType.INCOME_CERTIFICATE,
                extracted_name="Ananya Kulkarni",
                issue_date="2026-08-01",
            )
        ],
        "reference_date": date(2026, 11, 18),
    }
    base.update(overrides)
    return ConfirmedStudentProfile(**base)


@pytest.mark.parametrize(
    ("op", "actual", "expected", "should_pass"),
    [
        ("<=", 250000.0, 250000, True),   # boundary: exactly at cap
        ("<=", 250001.0, 250000, False),  # 1 rupee over cap
        ("<", 250000.0, 250000, False),   # boundary: strict < fails at exact cap
        ("<", 249999.0, 250000, True),
        (">=", 75.0, 75.0, True),         # boundary: marks exactly at minimum
        (">=", 74.9, 75.0, False),
        (">", 75.0, 75.0, False),         # boundary: strict > fails at exact threshold
        (">", 75.1, 75.0, True),
        ("==", "OBC", "obc", True),        # case-insensitive string equality
        ("==", "General", "SC", False),
        ("!=", "General", "SC", True),
        ("!=", "SC", "sc", False),
        ("in", "OBC", ["SC", "ST", "OBC"], True),
        ("in", "General", ["SC", "ST", "OBC"], False),
        ("not_in", "OBC", ["General"], True),
        ("not_in", "General", ["General"], False),
        ("contains", "B.E. Computer Science", "computer", True),
        ("contains", "B.A. History", "computer", False),
    ],
)
def test_every_rule_operator_and_boundaries(op, actual, expected, should_pass):
    if isinstance(actual, float):
        field = "annual_income" if expected >= 1000 else "marks_percentage"
    else:
        field = "course" if op == "contains" else "category"
    profile = _make_profile(**{field: actual})
    rule = SchemeRule(field=field, op=op, value=expected)
    res = evaluate_rule(rule, profile)
    assert res.passed is should_pass


def test_income_exact_cap_boundary_verdict():
    scheme = _make_scheme(
        rules=[
            SchemeRule(field="annual_income", op="<=", value=250000),
            SchemeRule(field="marks_percentage", op=">=", value=60),
        ]
    )
    at_cap = _make_profile(annual_income=250000.0, marks_percentage=60.0)
    over_cap = _make_profile(annual_income=250001.0, marks_percentage=60.0)

    res_pass = evaluate_scheme(scheme, at_cap)
    res_fail = evaluate_scheme(scheme, over_cap)

    assert res_pass.verdict == Verdict.ELIGIBLE
    assert res_fail.verdict == Verdict.NOT_ELIGIBLE
    assert "annual_income" in res_fail.summary_reason


def test_missing_field_produces_almost_verdict():
    scheme = _make_scheme(
        rules=[
            SchemeRule(field="annual_income", op="<=", value=250000),
            SchemeRule(field="marks_percentage", op=">=", value=60),
        ]
    )
    profile = _make_profile(annual_income=None)
    res = evaluate_scheme(scheme, profile)

    assert res.verdict == Verdict.ALMOST
    assert any(r.is_missing_field and r.field == "annual_income" for r in res.rule_results)


def test_missing_required_document_produces_almost_verdict():
    scheme = _make_scheme(
        rules=[SchemeRule(field="annual_income", op="<=", value=300000)],
        required_docs=[DocumentType.INCOME_CERTIFICATE, DocumentType.COMMUNITY_CERTIFICATE],
    )
    profile = _make_profile(available_docs=[DocumentType.INCOME_CERTIFICATE])
    res = evaluate_scheme(scheme, profile)

    assert res.verdict == Verdict.ALMOST
    assert res.missing_docs == [DocumentType.COMMUNITY_CERTIFICATE]


def test_expired_certificate_produces_almost_verdict():
    scheme = _make_scheme(
        rules=[SchemeRule(field="annual_income", op="<=", value=300000)],
        validity_months=6,
    )
    profile = _make_profile(
        document_records=[
            DocumentMetaRecord(
                filename="old_income.pdf",
                doc_type=DocumentType.INCOME_CERTIFICATE,
                extracted_name="Ananya Kulkarni",
                issue_date="2025-10-01",
            )
        ],
        reference_date=date(2026, 11, 18),
    )
    res = evaluate_scheme(scheme, profile)

    assert res.verdict == Verdict.ALMOST
    assert len(res.expired_docs) == 1


def test_placeholder_schemes_yaml_has_todo_verify():
    schemes = load_schemes()
    assert len(schemes) == 5
    for scheme in schemes:
        assert scheme.last_verified == "TODO_VERIFY"
        assert scheme.validity_months == "TODO_VERIFY"
        for rule in scheme.rules:
            assert rule.value == "TODO_VERIFY"
