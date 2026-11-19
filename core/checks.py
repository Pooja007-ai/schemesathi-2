"""Document health checks for SchemeSathi.

Every check is explicitly tagged with its true method:
- RULE: deterministic Python comparison
- STRING SIMILARITY: RapidFuzz token-sort ratio (not ML)
- IMAGE TEST: OpenCV Laplacian variance (classical image test, not ML)
"""

from __future__ import annotations

import os
from typing import Optional

from rapidfuzz import fuzz

from core.models import (
    CheckTag,
    ConfirmedStudentProfile,
    DocumentType,
    HealthCheckResult,
    HealthStatus,
    IngestedDocument,
    SchemeDefinition,
)
from core.rules import is_todo_value, months_between, parse_iso_date

DEFAULT_FUZZY_NAME_THRESHOLD = float(os.getenv("FUZZY_NAME_THRESHOLD", "85"))
DEFAULT_SHARPNESS_MIN_VARIANCE = float(os.getenv("SHARPNESS_MIN_VARIANCE", "100.0"))


def check_name_consistency(
    profile: ConfirmedStudentProfile,
    threshold: float = DEFAULT_FUZZY_NAME_THRESHOLD,
) -> HealthCheckResult:
    """Compare applicant names across documents using RapidFuzz string similarity."""
    named_docs = [
        (rec.filename, rec.extracted_name.strip())
        for rec in profile.document_records
        if rec.extracted_name and rec.extracted_name.strip()
    ]

    if len(named_docs) < 2:
        return HealthCheckResult(
            check_id="name_match",
            title="Name match across documents",
            tag=CheckTag.STRING_SIMILARITY,
            status=HealthStatus.WARN,
            detail=(
                "Need names extracted from at least 2 documents to compare cross-document spelling."
            ),
            measured_value=f"{len(named_docs)} document(s) with name",
            threshold_value=f">= {threshold:.0f}% similarity",
        )

    lowest_score = 100.0
    lowest_pair: Optional[tuple[tuple[str, str], tuple[str, str]]] = None

    for i in range(len(named_docs)):
        for j in range(i + 1, len(named_docs)):
            score = float(fuzz.token_sort_ratio(named_docs[i][1], named_docs[j][1]))
            if score < lowest_score:
                lowest_score = score
                lowest_pair = (named_docs[i], named_docs[j])

    # Also compare against confirmed full_name if present
    if profile.full_name and profile.full_name.strip():
        for doc_name_pair in named_docs:
            score = float(fuzz.token_sort_ratio(profile.full_name.strip(), doc_name_pair[1]))
            if score < lowest_score:
                lowest_score = score
                lowest_pair = (("Confirmed profile", profile.full_name.strip()), doc_name_pair)

    if lowest_score >= threshold:
        return HealthCheckResult(
            check_id="name_match",
            title="Name match across documents",
            tag=CheckTag.STRING_SIMILARITY,
            status=HealthStatus.PASS,
            detail=(
                f"Lowest RapidFuzz token-sort similarity across documents is {lowest_score:.1f}% "
                f"(passes >= {threshold:.0f}%)."
            ),
            measured_value=f"{lowest_score:.1f}%",
            threshold_value=f">= {threshold:.0f}%",
        )

    pair_desc = ""
    if lowest_pair:
        pair_desc = (
            f" ({lowest_pair[0][0]}: '{lowest_pair[0][1]}' vs "
            f"{lowest_pair[1][0]}: '{lowest_pair[1][1]}')"
        )
    return HealthCheckResult(
        check_id="name_match",
        title="Name match across documents",
        tag=CheckTag.STRING_SIMILARITY,
        status=HealthStatus.FAIL,
        detail=(
            f"Name mismatch detected{pair_desc}. RapidFuzz similarity {lowest_score:.1f}% "
            f"is below {threshold:.0f}%."
        ),
        measured_value=f"{lowest_score:.1f}%",
        threshold_value=f">= {threshold:.0f}%",
    )


def check_scan_quality(
    ingested_docs: list[IngestedDocument],
    min_variance: float = DEFAULT_SHARPNESS_MIN_VARIANCE,
) -> HealthCheckResult:
    """Classical image test: summarize Laplacian variance across uploaded scans."""
    scanned = [d for d in ingested_docs if d.sharpness_variance is not None]
    if not scanned:
        return HealthCheckResult(
            check_id="scan_quality",
            title="Scan quality (Laplacian variance)",
            tag=CheckTag.IMAGE_TEST,
            status=HealthStatus.PASS,
            detail="All uploaded files contain native digital PDF text; no image blur check needed.",
            measured_value="Digital PDF",
            threshold_value=f">= {min_variance:.0f} variance",
        )

    min_doc = min(scanned, key=lambda d: d.sharpness_variance or 0.0)
    min_val = min_doc.sharpness_variance or 0.0
    if min_val >= min_variance:
        return HealthCheckResult(
            check_id="scan_quality",
            title="Scan quality (Laplacian variance)",
            tag=CheckTag.IMAGE_TEST,
            status=HealthStatus.PASS,
            detail=(
                f"All scanned pages pass classical Laplacian edge-sharpness check "
                f"(lowest: {min_doc.filename} at {min_val:.1f})."
            ),
            measured_value=f"{min_val:.1f}",
            threshold_value=f">= {min_variance:.0f}",
        )

    return HealthCheckResult(
        check_id="scan_quality",
        title="Scan quality (Laplacian variance)",
        tag=CheckTag.IMAGE_TEST,
        status=HealthStatus.FAIL,
        detail=(
            f"Blurry scan detected in {min_doc.filename} (Laplacian variance {min_val:.1f} < "
            f"{min_variance:.0f}). Re-scan in bright light to prevent verification rejection."
        ),
        measured_value=f"{min_val:.1f}",
        threshold_value=f">= {min_variance:.0f}",
    )


def check_certificate_ages(
    profile: ConfirmedStudentProfile,
    schemes: list[SchemeDefinition],
) -> HealthCheckResult:
    """Deterministic RULE check: certificate age vs each scheme's validity limit."""
    concrete_limits = [
        int(s.validity_months)
        for s in schemes
        if s.validity_months is not None and not is_todo_value(s.validity_months)
    ]

    dated_certs = [
        r for r in profile.document_records if r.issue_date and r.doc_type != DocumentType.MARKS_CARD
    ]
    if not dated_certs and profile.issue_date:
        dated_certs_count = 1
    else:
        dated_certs_count = len(dated_certs)

    if not concrete_limits:
        return HealthCheckResult(
            check_id="certificate_age",
            title="Certificate age vs scheme validity limit",
            tag=CheckTag.RULE,
            status=HealthStatus.WARN,
            detail=(
                f"Found {dated_certs_count} dated certificate(s), but scheme validity_months "
                "thresholds in schemes.yaml are currently TODO_VERIFY."
            ),
            measured_value=f"{dated_certs_count} dated doc(s)",
            threshold_value="TODO_VERIFY",
        )

    strictest = min(concrete_limits)
    failures: list[str] = []
    max_age = 0.0

    for rec in dated_certs:
        parsed = parse_iso_date(rec.issue_date)
        if parsed is None:
            failures.append(f"{rec.filename}: invalid date '{rec.issue_date}'")
            continue
        age = months_between(parsed, profile.reference_date)
        max_age = max(max_age, age)
        if age > strictest:
            failures.append(f"{rec.filename} is {age:.1f} months old (limit {strictest}m)")

    if not dated_certs and profile.issue_date:
        parsed = parse_iso_date(profile.issue_date)
        if parsed is None:
            failures.append(f"Invalid date '{profile.issue_date}'")
        else:
            age = months_between(parsed, profile.reference_date)
            max_age = age
            if age > strictest:
                failures.append(f"Certificate is {age:.1f} months old (limit {strictest}m)")

    if failures:
        return HealthCheckResult(
            check_id="certificate_age",
            title="Certificate age vs scheme validity limit",
            tag=CheckTag.RULE,
            status=HealthStatus.FAIL,
            detail="; ".join(failures),
            measured_value=f"{max_age:.1f} months",
            threshold_value=f"<= {strictest} months",
        )

    if dated_certs_count == 0:
        return HealthCheckResult(
            check_id="certificate_age",
            title="Certificate age vs scheme validity limit",
            tag=CheckTag.RULE,
            status=HealthStatus.WARN,
            detail="No certificate issue date provided to verify certificate age.",
            measured_value="Missing",
            threshold_value=f"<= {strictest} months",
        )

    return HealthCheckResult(
        check_id="certificate_age",
        title="Certificate age vs scheme validity limit",
        tag=CheckTag.RULE,
        status=HealthStatus.PASS,
        detail=f"Certificate age ({max_age:.1f} months) is within strictest limit ({strictest} months).",
        measured_value=f"{max_age:.1f} months",
        threshold_value=f"<= {strictest} months",
    )


def check_income_vs_caps(
    profile: ConfirmedStudentProfile,
    schemes: list[SchemeDefinition],
) -> HealthCheckResult:
    """Deterministic RULE check: confirmed annual income vs scheme caps."""
    income_caps = [
        float(rule.value)
        for s in schemes
        for rule in s.rules
        if rule.field == "annual_income"
        and rule.op in ("<=", "<")
        and not is_todo_value(rule.value)
    ]

    if not income_caps:
        income_display = (
            f"INR {profile.annual_income:,.0f}" if profile.annual_income is not None else "Missing"
        )
        return HealthCheckResult(
            check_id="income_cap",
            title="Income vs scheme cap",
            tag=CheckTag.RULE,
            status=HealthStatus.WARN,
            detail=(
                f"Confirmed income is {income_display}. Income thresholds in schemes.yaml "
                "are marked TODO_VERIFY."
            ),
            measured_value=income_display,
            threshold_value="TODO_VERIFY",
        )

    if profile.annual_income is None:
        return HealthCheckResult(
            check_id="income_cap",
            title="Income vs scheme cap",
            tag=CheckTag.RULE,
            status=HealthStatus.FAIL,
            detail="Annual income is missing; cannot verify income caps.",
            measured_value="Missing",
            threshold_value=f"<= INR {min(income_caps):,.0f}",
        )

    min_cap = min(income_caps)
    max_cap = max(income_caps)
    if profile.annual_income <= min_cap:
        return HealthCheckResult(
            check_id="income_cap",
            title="Income vs scheme cap",
            tag=CheckTag.RULE,
            status=HealthStatus.PASS,
            detail=(
                f"Annual income INR {profile.annual_income:,.0f} is within all verified scheme caps "
                f"(lowest cap INR {min_cap:,.0f})."
            ),
            measured_value=f"INR {profile.annual_income:,.0f}",
            threshold_value=f"<= INR {min_cap:,.0f}",
        )
    if profile.annual_income <= max_cap:
        return HealthCheckResult(
            check_id="income_cap",
            title="Income vs scheme cap",
            tag=CheckTag.RULE,
            status=HealthStatus.WARN,
            detail=(
                f"Annual income INR {profile.annual_income:,.0f} exceeds the strictest cap "
                f"(INR {min_cap:,.0f}) but fits higher caps up to INR {max_cap:,.0f}."
            ),
            measured_value=f"INR {profile.annual_income:,.0f}",
            threshold_value=f"<= INR {max_cap:,.0f}",
        )

    return HealthCheckResult(
        check_id="income_cap",
        title="Income vs scheme cap",
        tag=CheckTag.RULE,
        status=HealthStatus.FAIL,
        detail=(
            f"Annual income INR {profile.annual_income:,.0f} exceeds all verified scheme caps "
            f"(highest cap INR {max_cap:,.0f})."
        ),
        measured_value=f"INR {profile.annual_income:,.0f}",
        threshold_value=f"<= INR {max_cap:,.0f}",
    )


def check_missing_required_docs(
    profile: ConfirmedStudentProfile,
    schemes: list[SchemeDefinition],
) -> HealthCheckResult:
    """Deterministic RULE check: missing required documents per scheme."""
    available = set(profile.available_docs)
    missing_by_scheme: list[str] = []

    for scheme in schemes:
        missing = [d.value.replace("_", " ") for d in scheme.required_docs if d not in available]
        if missing:
            missing_by_scheme.append(f"{scheme.name}: missing {', '.join(missing)}")

    if not missing_by_scheme:
        return HealthCheckResult(
            check_id="missing_docs",
            title="Missing required documents per scheme",
            tag=CheckTag.RULE,
            status=HealthStatus.PASS,
            detail="All required document types across the configured schemes are uploaded.",
            measured_value=f"{len(available)} doc type(s)",
            threshold_value="All required present",
        )

    return HealthCheckResult(
        check_id="missing_docs",
        title="Missing required documents per scheme",
        tag=CheckTag.RULE,
        status=HealthStatus.WARN,
        detail="; ".join(missing_by_scheme),
        measured_value=f"{len(missing_by_scheme)} scheme(s) missing docs",
        threshold_value="0 missing",
    )


def run_all_health_checks(
    profile: ConfirmedStudentProfile,
    ingested_docs: list[IngestedDocument],
    schemes: list[SchemeDefinition],
    fuzzy_threshold: float = DEFAULT_FUZZY_NAME_THRESHOLD,
    sharpness_min_variance: float = DEFAULT_SHARPNESS_MIN_VARIANCE,
) -> list[HealthCheckResult]:
    """Run all 5 document health checks with honest RULE / STRING SIMILARITY / IMAGE TEST labels."""
    return [
        check_certificate_ages(profile, schemes),
        check_name_consistency(profile, threshold=fuzzy_threshold),
        check_income_vs_caps(profile, schemes),
        check_missing_required_docs(profile, schemes),
        check_scan_quality(ingested_docs, min_variance=sharpness_min_variance),
    ]
