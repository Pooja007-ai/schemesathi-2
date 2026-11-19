"""SQLite persistence for anonymized check session summaries and eval metrics."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.models import HealthCheckResult, HealthStatus, SchemeEvaluationResult

ROOT_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT_DIR / "db" / "schema.sql"


def get_db_path() -> Path:
    env_path = os.getenv("SCHEMESATHI_DB_PATH", "db/schemesathi.db")
    path = Path(env_path)
    if not path.is_absolute():
        path = ROOT_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def init_db(db_path: Optional[Path] = None) -> Path:
    target = db_path or get_db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with sqlite3.connect(target) as conn:
        conn.executescript(schema_sql)
    return target


def record_check_session(
    input_mode: str,
    doc_count: int,
    health_checks: list[HealthCheckResult],
    scheme_results: list[SchemeEvaluationResult],
    db_path: Optional[Path] = None,
) -> str:
    """Store anonymized counts for a verification check run (never raw docs or PII)."""
    target = init_db(db_path)
    session_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    pass_count = sum(1 for c in health_checks if c.status == HealthStatus.PASS)
    warn_count = sum(1 for c in health_checks if c.status == HealthStatus.WARN)
    fail_count = sum(1 for c in health_checks if c.status == HealthStatus.FAIL)

    with sqlite3.connect(target) as conn:
        conn.execute(
            """
            INSERT INTO check_sessions (
                id, created_at, input_mode, doc_count,
                health_pass_count, health_warn_count, health_fail_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, now_iso, input_mode, doc_count, pass_count, warn_count, fail_count),
        )
        for res in scheme_results:
            failed_rules = sum(1 for r in res.rule_results if r.passed is False)
            conn.execute(
                """
                INSERT INTO scheme_results (
                    session_id, scheme_id, verdict,
                    missing_docs_count, failed_rules_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    res.scheme_id,
                    res.verdict.value,
                    len(res.missing_docs),
                    failed_rules,
                    now_iso,
                ),
            )
        conn.commit()
    return session_id


def record_eval_run(
    sample_count: int,
    llm_provider: str,
    model_name: str,
    overall_accuracy: float,
    field_metrics: dict[str, Any],
    db_path: Optional[Path] = None,
) -> None:
    target = init_db(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(target) as conn:
        conn.execute(
            """
            INSERT INTO extraction_eval_runs (
                run_at, sample_count, llm_provider, model_name,
                overall_accuracy, field_metrics_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso,
                sample_count,
                llm_provider,
                model_name,
                overall_accuracy,
                json.dumps(field_metrics),
            ),
        )
        conn.commit()


def get_latest_eval_run(db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    target = init_db(db_path)
    with sqlite3.connect(target) as conn:
        row = conn.execute(
            """
            SELECT run_at, sample_count, llm_provider, model_name,
                   overall_accuracy, field_metrics_json
            FROM extraction_eval_runs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    if not row:
        return None
    return {
        "run_at": row[0],
        "sample_count": row[1],
        "llm_provider": row[2],
        "model_name": row[3],
        "overall_accuracy": row[4],
        "field_metrics": json.loads(row[5]),
    }
