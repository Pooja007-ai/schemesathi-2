"""Deterministic Python rule engine for SchemeSathi.

Every eligibility decision, threshold comparison, required-document check, and
certificate validity evaluation runs here in pure Python—never in an LLM.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Optional

import yaml

from core.models import (
    ConfirmedStudentProfile,
    DocumentType,
    RuleEvaluation,
    SchemeDefinition,
    SchemeEvaluationResult,
    SchemeRule,
    Verdict,
)

DEFAULT_SCHEMES_PATH = Path(__file__).resolve().parent.parent / "data" / "schemes.yaml"
TODO_TOKEN = "TODO_VERIFY"


def is_todo_value(value: Any) -> bool:
    return isinstance(value, str) and value.strip().upper() == TODO_TOKEN


def load_schemes(path: Optional[Path] = None) -> list[SchemeDefinition]:
    target = path or DEFAULT_SCHEMES_PATH
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    items = raw.get("schemes", [])
    return [SchemeDefinition.model_validate(item) for item in items]


def parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def months_between(earlier: date, later: date) -> float:
    days = (later - earlier).days
    return days / 30.4375


def _coerce_numeric(val: Any) -> Optional[float]:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = val.replace(",", "").replace("₹", "").replace("Rs.", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _normalize_text(val: Any) -> str:
    return str(val).strip().lower()


def evaluate_rule(rule: SchemeRule, profile: ConfirmedStudentProfile) -> RuleEvaluation:
    """Evaluate a single deterministic rule against a confirmed student profile."""
    actual = getattr(profile, rule.field, None)

    if is_todo_value(rule.value):
        return RuleEvaluation(
            field=rule.field,
            op=rule.op,
            expected_value=rule.value,
            actual_value=actual,
            passed=None,
            is_todo_verify=True,
            is_missing_field=actual is None,
            reason=(
                f"{rule.field} {rule.op} TODO_VERIFY (threshold unverified; "
                f"applicant value: {actual if actual is not None else 'missing'})"
            ),
        )

    if actual is None or (isinstance(actual, str) and not actual.strip()):
        return RuleEvaluation(
            field=rule.field,
            op=rule.op,
            expected_value=rule.value,
            actual_value=actual,
            passed=None,
            is_missing_field=True,
            reason=f"Missing '{rule.field}' value; required to check ({rule.field} {rule.op} {rule.value}).",
        )

    op = rule.op
    expected = rule.value
    passed = False

    if op in ("<=", "<", ">=", ">"):
        actual_num = _coerce_numeric(actual)
        expected_num = _coerce_numeric(expected)
        if actual_num is None or expected_num is None:
            return RuleEvaluation(
                field=rule.field,
                op=op,
                expected_value=expected,
                actual_value=actual,
                passed=False,
                reason=f"Cannot compare non-numeric value '{actual}' against '{expected}'.",
            )
        if op == "<=":
            passed = actual_num <= expected_num
        elif op == "<":
            passed = actual_num < expected_num
        elif op == ">=":
            passed = actual_num >= expected_num
        elif op == ">":
            passed = actual_num > expected_num
    elif op == "==":
        actual_num = _coerce_numeric(actual)
        expected_num = _coerce_numeric(expected)
        if actual_num is not None and expected_num is not None:
            passed = actual_num == expected_num
        else:
            passed = _normalize_text(actual) == _normalize_text(expected)
    elif op == "!=":
        actual_num = _coerce_numeric(actual)
        expected_num = _coerce_numeric(expected)
        if actual_num is not None and expected_num is not None:
            passed = actual_num != expected_num
        else:
            passed = _normalize_text(actual) != _normalize_text(expected)
    elif op == "in":
        options = expected if isinstance(expected, (list, tuple, set)) else [expected]
        norm_options = {_normalize_text(o) for o in options}
        passed = _normalize_text(actual) in norm_options
    elif op == "not_in":
        options = expected if isinstance(expected, (list, tuple, set)) else [expected]
        norm_options = {_normalize_text(o) for o in options}
        passed = _normalize_text(actual) not in norm_options
    elif op == "contains":
        passed = _normalize_text(expected) in _normalize_text(actual)
    else:
        raise ValueError(f"Unsupported rule operator: {op}")

    status_word = "Passed" if passed else "Failed"
    return RuleEvaluation(
        field=rule.field,
        op=op,
        expected_value=expected,
        actual_value=actual,
        passed=passed,
        reason=f"{status_word}: {rule.field} = {actual} (rule: {rule.field} {op} {expected}).",
    )


def check_certificate_expiry(
    scheme: SchemeDefinition,
    profile: ConfirmedStudentProfile,
) -> tuple[list[str], bool]:
    """Return (expired_doc_messages, has_unverified_validity)."""
    if scheme.validity_months is None:
        return [], False
    if is_todo_value(scheme.validity_months):
        return [], True

    limit_months = int(scheme.validity_months)
    expired: list[str] = []

    # Check per-document issue dates (especially income & community certificates),
    # and fall back to profile.issue_date if document_records is empty.
    checked_any = False
    for rec in profile.document_records:
        if rec.doc_type == DocumentType.MARKS_CARD:
            continue
        if rec.issue_date:
            checked_any = True
            parsed = parse_iso_date(rec.issue_date)
            if parsed is None:
                expired.append(
                    f"{rec.filename}: unreadable issue date '{rec.issue_date}' (expected YYYY-MM-DD)."
                )
            else:
                age = months_between(parsed, profile.reference_date)
                if age > limit_months:
                    expired.append(
                        f"{rec.filename} ({rec.doc_type.value}) is {age:.1f} months old, "
                        f"exceeding {limit_months}-month validity limit."
                    )

    if not checked_any and profile.issue_date:
        parsed = parse_iso_date(profile.issue_date)
        if parsed is None:
            expired.append(
                f"Primary certificate issue date '{profile.issue_date}' is not valid YYYY-MM-DD."
            )
        else:
            age = months_between(parsed, profile.reference_date)
            if age > limit_months:
                expired.append(
                    f"Certificate is {age:.1f} months old, exceeding {limit_months}-month validity limit."
                )

    return expired, False


def evaluate_scheme(
    scheme: SchemeDefinition, profile: ConfirmedStudentProfile
) -> SchemeEvaluationResult:
    """Evaluate one scheme deterministically and assign ELIGIBLE, ALMOST, or NOT_ELIGIBLE."""
    available_set = set(profile.available_docs)
    missing_docs = [doc for doc in scheme.required_docs if doc not in available_set]

    rule_results = [evaluate_rule(rule, profile) for rule in scheme.rules]
    expired_docs, validity_todo = check_certificate_expiry(scheme, profile)

    failed_rules = [r for r in rule_results if r.passed is False]
    missing_field_rules = [r for r in rule_results if r.is_missing_field and not r.is_todo_verify]
    todo_rules = [r for r in rule_results if r.is_todo_verify]
    has_unverified = bool(todo_rules) or validity_todo or is_todo_value(scheme.last_verified)

    checklist: list[str] = []
    for doc in missing_docs:
        checklist.append(f"Upload required document: {doc.value.replace('_', ' ').title()}.")
    for exp in expired_docs:
        checklist.append(f"Renew expired/invalid certificate: {exp}")
    for r in missing_field_rules:
        checklist.append(f"Provide missing field '{r.field}' needed for rule ({r.field} {r.op} {r.expected_value}).")
    for r in failed_rules:
        checklist.append(
            f"Rule not met: {r.field} is {r.actual_value}, required {r.op} {r.expected_value}."
        )
    if has_unverified:
        checklist.append(
            f"Confirm official thresholds on {scheme.source_url} (placeholder rules marked TODO_VERIFY)."
        )

    if failed_rules:
        verdict = Verdict.NOT_ELIGIBLE
        exact_reasons = "; ".join(r.reason for r in failed_rules)
        summary_reason = f"Failed deterministic eligibility rule(s): {exact_reasons}"
    elif missing_docs or expired_docs or missing_field_rules or has_unverified:
        verdict = Verdict.ALMOST
        parts: list[str] = []
        if missing_docs:
            parts.append(
                "missing required document(s): "
                + ", ".join(d.value.replace("_", " ") for d in missing_docs)
            )
        if expired_docs:
            parts.append("expired or invalid certificate date")
        if missing_field_rules:
            parts.append(
                "missing profile field(s): " + ", ".join(r.field for r in missing_field_rules)
            )
        if has_unverified:
            parts.append(
                "scheme thresholds are marked TODO_VERIFY (confirm on official portal)"
            )
        summary_reason = "Needs attention before submission: " + "; ".join(parts) + "."
    else:
        verdict = Verdict.ELIGIBLE
        summary_reason = "All verified eligibility rules passed and required documents are present."

    return SchemeEvaluationResult(
        scheme_id=scheme.id,
        scheme_name=scheme.name,
        provider=scheme.provider,
        level=scheme.level,
        source_url=scheme.source_url,
        last_verified=scheme.last_verified,
        verdict=verdict,
        summary_reason=summary_reason,
        rule_results=rule_results,
        missing_docs=missing_docs,
        expired_docs=expired_docs,
        has_unverified_thresholds=has_unverified,
        checklist=checklist,
    )


def evaluate_all_schemes(
    profile: ConfirmedStudentProfile,
    schemes: Optional[list[SchemeDefinition]] = None,
) -> list[SchemeEvaluationResult]:
    loaded = schemes if schemes is not None else load_schemes()
    return [evaluate_scheme(scheme, profile) for scheme in loaded]
