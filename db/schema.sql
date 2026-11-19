-- SchemeSathi SQLite Schema
-- Prototype only: stores anonymized session summaries and evaluation run metrics.
-- Never stores uploaded student documents or raw PII.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS check_sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    input_mode TEXT NOT NULL CHECK (input_mode IN ('upload', 'sample')),
    doc_count INTEGER NOT NULL DEFAULT 0,
    health_pass_count INTEGER NOT NULL DEFAULT 0,
    health_warn_count INTEGER NOT NULL DEFAULT 0,
    health_fail_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scheme_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    scheme_id TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('ELIGIBLE', 'ALMOST', 'NOT_ELIGIBLE')),
    missing_docs_count INTEGER NOT NULL DEFAULT 0,
    failed_rules_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES check_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS extraction_eval_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    llm_provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    overall_accuracy REAL NOT NULL,
    field_metrics_json TEXT NOT NULL
);
