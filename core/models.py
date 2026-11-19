"""Pydantic models and domain enums for SchemeSathi."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


class DocumentType(str, Enum):
    INCOME_CERTIFICATE = "income_certificate"
    MARKS_CARD = "marks_card"
    COMMUNITY_CERTIFICATE = "community_certificate"
    OTHER = "other"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MISSING = "missing"


class CheckTag(str, Enum):
    RULE = "RULE"
    STRING_SIMILARITY = "STRING SIMILARITY"
    IMAGE_TEST = "IMAGE TEST"


class HealthStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class Verdict(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    ALMOST = "ALMOST"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


EXTRACTED_FIELD_NAMES = (
    "full_name",
    "annual_income",
    "category",
    "marks_percentage",
    "course",
    "issue_date",
    "issuing_authority",
)


class ExtractedDocumentFields(BaseModel):
    """Fixed JSON schema returned by the LLM extractor and validated by Pydantic."""

    full_name: Optional[str] = Field(
        default=None, description="Student full name exactly as printed on the document."
    )
    annual_income: Optional[float] = Field(
        default=None,
        ge=0,
        description="Annual family income in INR as a numeric value.",
    )
    category: Optional[str] = Field(
        default=None,
        description="Social/reservation category (e.g., SC, ST, OBC, BC, MBC, EWS, General).",
    )
    marks_percentage: Optional[float] = Field(
        default=None,
        ge=0,
        le=100,
        description="Percentage of marks obtained (0-100).",
    )
    course: Optional[str] = Field(
        default=None, description="Degree, diploma, or class/course name."
    )
    issue_date: Optional[str] = Field(
        default=None,
        description="Certificate or marks card issue date in ISO YYYY-MM-DD format if available.",
    )
    issuing_authority: Optional[str] = Field(
        default=None,
        description="Office or board that issued the document (e.g., Tahsildar, CBSE).",
    )
    field_confidence: dict[str, ConfidenceLevel] = Field(
        default_factory=dict,
        description="Per-field extraction confidence reported by the extractor.",
    )
    extraction_notes: Optional[str] = Field(
        default=None, description="Short note on ambiguities or missing sections."
    )

    @field_validator("issue_date")
    @classmethod
    def normalize_blank_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("category", "full_name", "course", "issuing_authority")
    @classmethod
    def strip_strings(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class IngestedDocument(BaseModel):
    """Result of PDF/image ingestion and classical scan sharpness measurement."""

    filename: str
    doc_type: DocumentType
    file_kind: Literal["pdf", "image"]
    raw_text: str
    extraction_method: Literal["pymupdf_text", "tesseract_ocr", "pymupdf_plus_ocr"]
    page_count: int = 1
    sharpness_variance: Optional[float] = None
    sharpness_passed: Optional[bool] = None
    sharpness_label: str = "Not applicable (native digital PDF)"
    warnings: list[str] = Field(default_factory=list)


class DocumentExtractionRecord(BaseModel):
    """Links an ingested document with its LLM-extracted fields (or error)."""

    document: IngestedDocument
    extracted: Optional[ExtractedDocumentFields] = None
    error: Optional[str] = None
    attempts: int = 0


class DocumentMetaRecord(BaseModel):
    """Per-document metadata preserved after user confirmation for cross-doc checks."""

    filename: str
    doc_type: DocumentType
    extracted_name: Optional[str] = None
    issue_date: Optional[str] = None
    issuing_authority: Optional[str] = None
    sharpness_variance: Optional[float] = None
    sharpness_passed: Optional[bool] = None


class ConfirmedStudentProfile(BaseModel):
    """User-confirmed profile passed into deterministic rules & health checks."""

    full_name: Optional[str] = None
    annual_income: Optional[float] = Field(default=None, ge=0)
    category: Optional[str] = None
    marks_percentage: Optional[float] = Field(default=None, ge=0, le=100)
    course: Optional[str] = None
    issue_date: Optional[str] = None
    issuing_authority: Optional[str] = None
    available_docs: list[DocumentType] = Field(default_factory=list)
    document_records: list[DocumentMetaRecord] = Field(default_factory=list)
    reference_date: date = Field(default_factory=date.today)


class SchemeRule(BaseModel):
    field: str
    op: Literal["<=", "<", ">=", ">", "==", "!=", "in", "not_in", "contains"]
    value: Any


class SchemeDefinition(BaseModel):
    id: str
    name: str
    provider: str
    level: str
    source_url: str
    last_verified: str
    rules: list[SchemeRule] = Field(default_factory=list)
    required_docs: list[DocumentType] = Field(default_factory=list)
    validity_months: Union[int, str, None] = None


class HealthCheckResult(BaseModel):
    check_id: str
    title: str
    tag: CheckTag
    status: HealthStatus
    detail: str
    measured_value: Optional[str] = None
    threshold_value: Optional[str] = None


class RuleEvaluation(BaseModel):
    field: str
    op: str
    expected_value: Any
    actual_value: Any
    passed: Optional[bool]
    is_todo_verify: bool = False
    is_missing_field: bool = False
    reason: str


class SchemeEvaluationResult(BaseModel):
    scheme_id: str
    scheme_name: str
    provider: str
    level: str
    source_url: str
    last_verified: str
    verdict: Verdict
    summary_reason: str
    rule_results: list[RuleEvaluation] = Field(default_factory=list)
    missing_docs: list[DocumentType] = Field(default_factory=list)
    expired_docs: list[str] = Field(default_factory=list)
    has_unverified_thresholds: bool = False
    checklist: list[str] = Field(default_factory=list)
