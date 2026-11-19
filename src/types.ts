export type PageId = 'home' | 'checker' | 'how' | 'evaluation';

export type DocumentType =
  | 'income_certificate'
  | 'marks_card'
  | 'community_certificate'
  | 'other';

export type ConfidenceLevel = 'high' | 'medium' | 'low' | 'missing';

export interface QueuedDocument {
  filename: string;
  doc_type: DocumentType;
  size_bytes?: number;
  content_base64: string;
}

export interface IngestedDocument {
  filename: string;
  doc_type: DocumentType;
  file_kind: 'pdf' | 'image';
  raw_text: string;
  extraction_method: 'pymupdf_text' | 'tesseract_ocr' | 'pymupdf_plus_ocr';
  page_count: number;
  sharpness_variance: number | null;
  sharpness_passed: boolean | null;
  sharpness_label: string;
  warnings: string[];
}

export interface ExtractedDocumentFields {
  full_name: string | null;
  annual_income: number | null;
  category: string | null;
  marks_percentage: number | null;
  course: string | null;
  issue_date: string | null;
  issuing_authority: string | null;
  field_confidence: Record<string, ConfidenceLevel>;
  extraction_notes: string | null;
}

export interface DocumentExtractionRecord {
  document: IngestedDocument;
  extracted: ExtractedDocumentFields | null;
  error: string | null;
  attempts: number;
}

export interface HealthCheckResult {
  check_id: string;
  title: string;
  tag: 'RULE' | 'STRING SIMILARITY' | 'IMAGE TEST';
  status: 'pass' | 'warn' | 'fail';
  detail: string;
  measured_value: string | null;
  threshold_value: string | null;
}

export interface RuleEvaluation {
  field: string;
  op: string;
  expected_value: unknown;
  actual_value: unknown;
  passed: boolean | null;
  is_todo_verify: boolean;
  is_missing_field: boolean;
  reason: string;
}

export interface SchemeEvaluationResult {
  scheme_id: string;
  scheme_name: string;
  provider: string;
  level: string;
  source_url: string;
  last_verified: string;
  verdict: 'ELIGIBLE' | 'ALMOST' | 'NOT_ELIGIBLE';
  summary_reason: string;
  rule_results: RuleEvaluation[];
  missing_docs: DocumentType[];
  expired_docs: string[];
  has_unverified_thresholds: boolean;
  checklist: string[];
}

export interface EvalResults {
  measured_at?: string;
  run_at?: string;
  sample_count: number;
  llm_provider: string;
  model_name: string;
  overall_accuracy: number;
  field_metrics: Record<
    string,
    {
      correct: number;
      total: number;
      accuracy: number;
    }
  >;
}

export interface MetadataResponse {
  strings: Record<string, string>;
  schemes: Array<{
    id: string;
    name: string;
    provider: string;
    level: string;
    source_url: string;
    last_verified: string;
  }>;
  eval_results: EvalResults | null;
}
