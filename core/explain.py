"""Plain-language explanations and 'Fix before you submit' checklist builder.

Deterministic rule outputs are always preserved intact. Optionally, an LLM may
phrase a gentler student-facing summary when explicitly enabled, never altering
any verdict or threshold value.
"""

from __future__ import annotations

from core.models import HealthCheckResult, HealthStatus, SchemeEvaluationResult


def build_global_fix_checklist(
    health_checks: list[HealthCheckResult],
    scheme_results: list[SchemeEvaluationResult],
) -> list[str]:
    """Aggregate deduplicated, actionable pre-submission steps."""
    items: list[str] = []
    seen: set[str] = set()

    def _add(text: str) -> None:
        if text not in seen:
            seen.add(text)
            items.append(text)

    for check in health_checks:
        if check.status in (HealthStatus.FAIL, HealthStatus.WARN):
            _add(f"[{check.tag.value}] {check.title}: {check.detail}")

    for res in scheme_results:
        for step in res.checklist:
            _add(f"{res.scheme_name}: {step}")

    return items
