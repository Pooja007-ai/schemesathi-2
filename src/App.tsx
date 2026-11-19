import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Download,
  ExternalLink,
  FileText,
  Info,
  ShieldAlert,
  Upload,
  XCircle,
} from 'lucide-react';
import ChatAssistant from './components/ChatAssistant';
import type {
  ConfidenceLevel,
  DocumentExtractionRecord,
  DocumentType,
  HealthCheckResult,
  MetadataResponse,
  PageId,
  QueuedDocument,
  SchemeEvaluationResult,
} from './types';

interface ProfileFormState {
  full_name: string;
  annual_income: string;
  category: string;
  marks_percentage: string;
  course: string;
  issue_date: string;
  issuing_authority: string;
}

const EMPTY_FORM: ProfileFormState = {
  full_name: '',
  annual_income: '',
  category: '',
  marks_percentage: '',
  course: '',
  issue_date: '',
  issuing_authority: '',
};

const DOC_SLOTS: Array<{ type: DocumentType; label: string; hint: string }> = [
  {
    type: 'income_certificate',
    label: 'Income Certificate',
    hint: 'PDF or photo (PNG/JPG) showing annual family income & issue date',
  },
  {
    type: 'marks_card',
    label: 'Marks Card',
    hint: 'PDF or photo showing percentage / marks & course',
  },
  {
    type: 'community_certificate',
    label: 'Community Certificate',
    hint: 'PDF or photo showing category & issuing authority',
  },
];

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      const commaIdx = result.indexOf(',');
      resolve(commaIdx >= 0 ? result.slice(commaIdx + 1) : result);
    };
    reader.onerror = () => reject(new Error(`Could not read file ${file.name}`));
    reader.readAsDataURL(file);
  });
}

function verdictStyle(verdict: SchemeEvaluationResult['verdict']) {
  if (verdict === 'ELIGIBLE') {
    return {
      label: 'ELIGIBLE',
      classes: 'bg-[#DCFCE7] text-[#166534] border-[#BBF7D0]',
      icon: CheckCircle2,
    };
  }
  if (verdict === 'ALMOST') {
    return {
      label: 'ALMOST',
      classes: 'bg-[#FEF3C7] text-[#92400E] border-[#FDE68A]',
      icon: AlertTriangle,
    };
  }
  return {
    label: 'NOT ELIGIBLE',
    classes: 'bg-[#FEE2E2] text-[#991B1B] border-[#FECACA]',
    icon: XCircle,
  };
}

function healthStatusLabel(status: HealthCheckResult['status']) {
  if (status === 'pass') return { text: 'PASS', cls: 'text-[#166534] bg-[#DCFCE7]' };
  if (status === 'warn') return { text: 'REVIEW', cls: 'text-[#92400E] bg-[#FEF3C7]' };
  return { text: 'FAIL', cls: 'text-[#991B1B] bg-[#FEE2E2]' };
}

export default function App() {
  const [page, setPage] = useState<PageId>('home');
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [metadata, setMetadata] = useState<MetadataResponse | null>(null);

  const [inputMode, setInputMode] = useState<'upload' | 'sample'>('upload');
  const [queuedDocs, setQueuedDocs] = useState<Record<DocumentType, QueuedDocument | null>>({
    income_certificate: null,
    marks_card: null,
    community_certificate: null,
    other: null,
  });

  const [fuzzyThreshold, setFuzzyThreshold] = useState<number>(85);
  const [sharpnessMin, setSharpnessMin] = useState<number>(100);

  const [loading, setLoading] = useState<boolean>(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);

  const [records, setRecords] = useState<DocumentExtractionRecord[]>([]);
  const [formState, setFormState] = useState<ProfileFormState>(EMPTY_FORM);
  const [fieldConfidence, setFieldConfidence] = useState<Record<string, ConfidenceLevel>>({});
  const [confirmedChecked, setConfirmedChecked] = useState<boolean>(false);
  const [expandedTextIdx, setExpandedTextIdx] = useState<number | null>(null);

  const [healthChecks, setHealthChecks] = useState<HealthCheckResult[]>([]);
  const [schemeResults, setSchemeResults] = useState<SchemeEvaluationResult[]>([]);
  const [globalChecklist, setGlobalChecklist] = useState<string[]>([]);
  const [markdownReport, setMarkdownReport] = useState<string>('');
  const [pdfBase64, setPdfBase64] = useState<string>('');
  const [openChecklistIds, setOpenChecklistIds] = useState<Record<string, boolean>>({});
  const [evalRunning, setEvalRunning] = useState<boolean>(false);
  const [evalError, setEvalError] = useState<string | null>(null);

  const s = metadata?.strings ?? {};

  useEffect(() => {
    fetch('/api/metadata')
      .then((res) => res.json())
      .then((data) => {
        if (!data.error) {
          setMetadata(data);
        }
      })
      .catch(() => {
        // Metadata load errors handled smoothly via static copy defaults
      });
  }, []);

  async function handleLoadSamples(jumpToChecker: boolean) {
    setErrorBanner(null);
    setLoading(true);
    try {
      const resp = await fetch('/api/samples');
      const data = await resp.json();
      if (!resp.ok || data.error) {
        throw new Error(data.error || 'Could not load synthetic sample documents.');
      }
      const nextQueued: Record<DocumentType, QueuedDocument | null> = {
        income_certificate: null,
        marks_card: null,
        community_certificate: null,
        other: null,
      };
      for (const sample of data.samples as QueuedDocument[]) {
        nextQueued[sample.doc_type] = sample;
      }
      setQueuedDocs(nextQueued);
      setInputMode('sample');
      setRecords([]);
      setConfirmedChecked(false);
      if (jumpToChecker) {
        setPage('checker');
        setStep(1);
      }
    } catch (err: any) {
      setErrorBanner(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleFileSelect(docType: DocumentType, file: File | undefined) {
    if (!file) return;
    setErrorBanner(null);
    try {
      const b64 = await fileToBase64(file);
      setQueuedDocs((prev) => ({
        ...prev,
        [docType]: {
          filename: file.name,
          doc_type: docType,
          size_bytes: file.size,
          content_base64: b64,
        },
      }));
      setInputMode('upload');
    } catch (err: any) {
      setErrorBanner(err.message);
    }
  }

  async function handleExtractStep() {
    const docsToSend = Object.values(queuedDocs).filter(Boolean) as QueuedDocument[];
    if (docsToSend.length === 0) {
      setErrorBanner('Please upload at least one synthetic document or click "Use sample documents".');
      return;
    }

    setErrorBanner(null);
    setLoading(true);
    try {
      const resp = await fetch('/api/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ documents: docsToSend }),
      });
      const data = await resp.json();
      if (!resp.ok || data.error) {
        throw new Error(data.error || 'Document ingestion failed.');
      }

      const recs: DocumentExtractionRecord[] = data.records || [];
      setRecords(recs);

      const merged: ProfileFormState = { ...EMPTY_FORM };
      const confs: Record<string, ConfidenceLevel> = {};
      for (const rec of recs) {
        const ext = rec.extracted;
        if (!ext) continue;
        if (!merged.full_name && ext.full_name) {
          merged.full_name = ext.full_name;
          confs.full_name = ext.field_confidence?.full_name || 'medium';
        }
        if (!merged.annual_income && ext.annual_income !== null) {
          merged.annual_income = String(ext.annual_income);
          confs.annual_income = ext.field_confidence?.annual_income || 'medium';
        }
        if (!merged.category && ext.category) {
          merged.category = ext.category;
          confs.category = ext.field_confidence?.category || 'medium';
        }
        if (!merged.marks_percentage && ext.marks_percentage !== null) {
          merged.marks_percentage = String(ext.marks_percentage);
          confs.marks_percentage = ext.field_confidence?.marks_percentage || 'medium';
        }
        if (!merged.course && ext.course) {
          merged.course = ext.course;
          confs.course = ext.field_confidence?.course || 'medium';
        }
        if (!merged.issue_date && ext.issue_date) {
          merged.issue_date = ext.issue_date;
          confs.issue_date = ext.field_confidence?.issue_date || 'medium';
        }
        if (!merged.issuing_authority && ext.issuing_authority) {
          merged.issuing_authority = ext.issuing_authority;
          confs.issuing_authority = ext.field_confidence?.issuing_authority || 'medium';
        }
      }

      setFormState(merged);
      setFieldConfidence(confs);
      setConfirmedChecked(false);
      setStep(2);
    } catch (err: any) {
      setErrorBanner(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleManualEntryStart() {
    setRecords([]);
    setFormState(EMPTY_FORM);
    setFieldConfidence({});
    setConfirmedChecked(false);
    setErrorBanner(null);
    setStep(2);
  }

  async function handleEvaluate(e: React.FormEvent) {
    e.preventDefault();
    if (!confirmedChecked) {
      setErrorBanner('Please confirm you reviewed the fields before running the rule engine.');
      return;
    }

    setErrorBanner(null);
    setStep(3);
    setLoading(true);
    try {
      const annualIncome = formState.annual_income.trim()
        ? Number(formState.annual_income.replace(/,/g, '').trim())
        : null;
      const marksPct = formState.marks_percentage.trim()
        ? Number(formState.marks_percentage.trim())
        : null;

      if (annualIncome !== null && Number.isNaN(annualIncome)) {
        throw new Error('Annual income must be a valid number.');
      }
      if (marksPct !== null && (Number.isNaN(marksPct) || marksPct < 0 || marksPct > 100)) {
        throw new Error('Marks percentage must be between 0 and 100.');
      }

      const availableDocs = records.map((r) => r.document.doc_type);
      const docRecords = records.map((r) => ({
        filename: r.document.filename,
        doc_type: r.document.doc_type,
        extracted_name: r.extracted?.full_name ?? null,
        issue_date: r.extracted?.issue_date ?? null,
        issuing_authority: r.extracted?.issuing_authority ?? null,
        sharpness_variance: r.document.sharpness_variance,
        sharpness_passed: r.document.sharpness_passed,
      }));

      const resp = await fetch('/api/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input_mode: inputMode,
          fuzzy_threshold: fuzzyThreshold,
          sharpness_min_variance: sharpnessMin,
          ingested_docs: records.map((r) => r.document),
          profile: {
            full_name: formState.full_name.trim() || null,
            annual_income: annualIncome,
            category: formState.category.trim() || null,
            marks_percentage: marksPct,
            course: formState.course.trim() || null,
            issue_date: formState.issue_date.trim() || null,
            issuing_authority: formState.issuing_authority.trim() || null,
            available_docs: availableDocs,
            document_records: docRecords,
          },
        }),
      });
      const data = await resp.json();
      if (!resp.ok || data.error) {
        throw new Error(data.error || 'Evaluation failed.');
      }

      setHealthChecks(data.health_checks || []);
      setSchemeResults(data.scheme_results || []);
      setGlobalChecklist(data.global_checklist || []);
      setMarkdownReport(data.markdown_report || '');
      setPdfBase64(data.pdf_base64 || '');
      setStep(4);
    } catch (err: any) {
      setErrorBanner(err.message);
      setStep(2);
    } finally {
      setLoading(false);
    }
  }

  function downloadMarkdown() {
    const blob = new Blob([markdownReport], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'schemesathi_report.md';
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadPdf() {
    const binary = atob(pdfBase64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    const blob = new Blob([bytes], { type: 'application/pdf' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'schemesathi_report.pdf';
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleRunEvaluationScript() {
    setEvalRunning(true);
    setEvalError(null);
    try {
      const resp = await fetch('/api/run-eval', { method: 'POST' });
      const data = await resp.json();
      if (!resp.ok || data.error) {
        throw new Error(data.error || 'Evaluation script failed.');
      }
      setMetadata(data);
    } catch (err: any) {
      setEvalError(err.message);
    } finally {
      setEvalRunning(false);
    }
  }

  const queuedCount = Object.values(queuedDocs).filter(Boolean).length;

  return (
    <div className="min-h-screen bg-[#F7F4EC] text-[#14213D] flex flex-col">
      {/* Top Bar Contract: Brand — 4 single-line links — 1 primary CTA */}
      <header className="border-b border-[#E2DDD0] bg-[#FFFFFF]">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-8">
          <button
            type="button"
            onClick={() => setPage('home')}
            className="text-xl font-bold tracking-tight text-[#14213D] whitespace-nowrap shrink-0 cursor-pointer"
          >
            SchemeSathi
          </button>

          <nav className="flex items-center gap-5 sm:gap-7 overflow-x-auto">
            {(
              [
                ['home', 'Home'],
                ['checker', 'Checker'],
                ['how', 'How it works'],
                ['evaluation', 'Evaluation'],
              ] as Array<[PageId, string]>
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setPage(id)}
                className={`text-sm font-medium whitespace-nowrap shrink-0 pb-1 border-b-2 transition-colors cursor-pointer ${
                  page === id
                    ? 'border-[#F2A33A] text-[#14213D]'
                    : 'border-transparent text-[#475569] hover:text-[#14213D]'
                }`}
              >
                {label}
              </button>
            ))}
          </nav>

          <button
            type="button"
            onClick={() => handleLoadSamples(true)}
            disabled={loading}
            className="hidden sm:inline-flex items-center justify-center px-4 py-2 text-sm font-semibold rounded-lg bg-[#F2A33A] text-[#14213D] hover:bg-[#e59429] transition-colors whitespace-nowrap shrink-0 cursor-pointer disabled:opacity-60"
          >
            Try Sample Docs
          </button>
        </div>
      </header>

      {/* Synthetic Document Handling Notice */}
      <div className="bg-[#14213D] text-[#F7F4EC]">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-2.5 flex flex-wrap items-center justify-between gap-2 text-xs sm:text-sm">
          <span>
            {s.prototype_notice ||
              'Documents are sent to an external LLM API for extraction. Use synthetic documents only.'}
          </span>
          <span className="text-[#F2A33A] font-medium">
            {s.threshold_disclaimer || 'Prototype. Confirm thresholds on the official portal.'}
          </span>
        </div>
      </div>

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-8 sm:py-10">
        {errorBanner && (
          <div
            role="alert"
            className="mb-6 rounded-xl border border-[#FECACA] bg-[#FEE2E2] px-4 py-3 text-sm text-[#991B1B] flex items-start justify-between gap-3"
          >
            <span>{errorBanner}</span>
            <button
              type="button"
              onClick={() => setErrorBanner(null)}
              className="text-xs font-semibold underline shrink-0 cursor-pointer"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* HOME PAGE */}
        {page === 'home' && (
          <div className="space-y-10">
            <section className="rounded-2xl border border-[#E2DDD0] bg-[#FFFFFF] p-6 sm:p-10">
              <p className="text-sm font-semibold text-[#92400E] mb-2">
                {s.tagline || 'Will my application survive verification?'}
              </p>
              <h1 className="text-3xl sm:text-5xl font-bold tracking-tight text-[#14213D] max-w-3xl leading-tight">
                {s.hero_title || 'Check your scholarship documents before the portal rejects them.'}
              </h1>
              <p className="mt-4 text-base sm:text-lg text-[#334155] max-w-2xl leading-relaxed">
                {s.hero_subtitle ||
                  'SchemeSathi reads your income certificate, marks card, and community certificate, spots blurry scans, name mismatches, or missing records, and checks each rule transparently.'}
              </p>

              <div className="mt-7 flex flex-wrap items-center gap-4">
                <button
                  type="button"
                  onClick={() => handleLoadSamples(true)}
                  disabled={loading}
                  className="px-6 py-3 rounded-lg bg-[#F2A33A] text-[#14213D] font-semibold text-base hover:bg-[#e59429] transition-colors cursor-pointer disabled:opacity-60"
                >
                  {loading ? 'Loading samples...' : 'Try with sample documents'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setPage('checker');
                    setStep(1);
                  }}
                  className="px-6 py-3 rounded-lg border border-[#14213D] text-[#14213D] font-semibold text-base hover:bg-[#F7F4EC] transition-colors cursor-pointer"
                >
                  Start checking documents
                </button>
              </div>
            </section>

            <section className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <div className="rounded-xl border border-[#E2DDD0] bg-[#FFFFFF] p-6">
                <p className="text-xs font-semibold text-[#92400E] mb-1">Step 01</p>
                <h2 className="text-xl font-bold text-[#14213D] mb-2">Upload synthetic docs</h2>
                <p className="text-sm sm:text-base text-[#475569] leading-relaxed">
                  Add PDFs or photos of your income certificate, marks card, and community
                  certificate—or load our synthetic sample packet in one click.
                </p>
              </div>

              <div className="rounded-xl border border-[#E2DDD0] bg-[#FFFFFF] p-6">
                <p className="text-xs font-semibold text-[#92400E] mb-1">Step 02</p>
                <h2 className="text-xl font-bold text-[#14213D] mb-2">Read &amp; confirm fields</h2>
                <p className="text-sm sm:text-base text-[#475569] leading-relaxed">
                  PyMuPDF and Tesseract OCR read the text, an LLM fills the 7-field JSON form,
                  and you review and edit every field before any rule runs.
                </p>
              </div>

              <div className="rounded-xl border border-[#E2DDD0] bg-[#FFFFFF] p-6">
                <p className="text-xs font-semibold text-[#92400E] mb-1">Step 03</p>
                <h2 className="text-xl font-bold text-[#14213D] mb-2">Fix before you submit</h2>
                <p className="text-sm sm:text-base text-[#475569] leading-relaxed">
                  Deterministic Python rules, RapidFuzz name matching, and OpenCV sharpness
                  tests surface exact rejection risks and a downloadable checklist.
                </p>
              </div>
            </section>
          </div>
        )}

        {/* CHECKER PAGE (4-STEP STEPPER) */}
        {page === 'checker' && (
          <div className="space-y-6">
            {/* Stepper Header */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { num: 1, label: '1. Upload' },
                { num: 2, label: '2. Extract & confirm' },
                { num: 3, label: '3. Evaluate' },
                { num: 4, label: '4. Results' },
              ].map((st) => {
                const active = step === st.num;
                const done = step > st.num;
                return (
                  <div
                    key={st.num}
                    className={`rounded-xl border px-4 py-3 transition-colors ${
                      active
                        ? 'border-[#F2A33A] bg-[#FFFFFF] ring-2 ring-[#F2A33A]/40'
                        : done
                          ? 'border-[#14213D]/30 bg-[#FFFFFF]'
                          : 'border-[#E2DDD0] bg-[#FFFFFF]/60 text-[#64748B]'
                    }`}
                  >
                    <p className="text-sm font-bold text-[#14213D]">{st.label}</p>
                    <p className="text-xs text-[#64748B] mt-0.5">
                      {active ? 'Current step' : done ? 'Completed' : 'Upcoming'}
                    </p>
                  </div>
                );
              })}
            </div>

            {/* STEP 1: UPLOAD */}
            {step === 1 && (
              <section className="rounded-2xl border border-[#E2DDD0] bg-[#FFFFFF] p-6 sm:p-8 space-y-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h1 className="text-2xl font-bold text-[#14213D]">
                      Upload synthetic student documents
                    </h1>
                    <p className="text-sm sm:text-base text-[#475569] mt-1">
                      PDFs use PyMuPDF text extraction with Tesseract OCR fallback; images use
                      OpenCV sharpness check + Tesseract OCR.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleLoadSamples(false)}
                    disabled={loading}
                    className="px-4 py-2.5 rounded-lg bg-[#F2A33A] text-[#14213D] text-sm font-semibold hover:bg-[#e59429] transition-colors cursor-pointer disabled:opacity-60"
                  >
                    Use sample documents
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {DOC_SLOTS.map((slot) => {
                    const queued = queuedDocs[slot.type];
                    return (
                      <label
                        key={slot.type}
                        className="block rounded-xl border border-dashed border-[#CBD5E1] bg-[#F7F4EC]/60 p-5 hover:border-[#14213D] transition-colors cursor-pointer"
                      >
                        <div className="flex items-center justify-between gap-2 mb-2">
                          <span className="text-base font-bold text-[#14213D]">{slot.label}</span>
                          <Upload className="w-4 h-4 text-[#475569]" />
                        </div>
                        <p className="text-xs text-[#475569] mb-4">{slot.hint}</p>
                        <input
                          type="file"
                          accept=".pdf,.png,.jpg,.jpeg"
                          onChange={(e) => handleFileSelect(slot.type, e.target.files?.[0])}
                          className="sr-only"
                        />
                        {queued ? (
                          <div className="rounded-lg bg-[#FFFFFF] border border-[#E2DDD0] px-3 py-2 text-xs font-medium text-[#14213D] truncate">
                            {queued.filename}
                          </div>
                        ) : (
                          <span className="inline-block text-xs font-semibold text-[#14213D] underline">
                            Choose PDF or image
                          </span>
                        )}
                      </label>
                    );
                  })}
                </div>

                {/* Configurable Classical Check Thresholds */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-[#E2DDD0]">
                  <div>
                    <label
                      htmlFor="fuzzy-threshold"
                      className="block text-sm font-medium text-[#14213D]"
                    >
                      Name match similarity threshold:{' '}
                      <span className="font-bold tabular-nums">{fuzzyThreshold}%</span>
                    </label>
                    <input
                      id="fuzzy-threshold"
                      type="range"
                      min={50}
                      max={100}
                      value={fuzzyThreshold}
                      onChange={(e) => setFuzzyThreshold(Number(e.target.value))}
                      className="w-full mt-2 accent-[#14213D]"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="sharpness-threshold"
                      className="block text-sm font-medium text-[#14213D]"
                    >
                      Minimum scan Laplacian variance:{' '}
                      <span className="font-bold tabular-nums">{sharpnessMin}</span>
                    </label>
                    <input
                      id="sharpness-threshold"
                      type="range"
                      min={20}
                      max={300}
                      value={sharpnessMin}
                      onChange={(e) => setSharpnessMin(Number(e.target.value))}
                      className="w-full mt-2 accent-[#14213D]"
                    />
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-4">
                  <button
                    type="button"
                    onClick={handleExtractStep}
                    disabled={loading || queuedCount === 0}
                    className="px-6 py-3 rounded-lg bg-[#14213D] text-[#F7F4EC] font-semibold text-sm sm:text-base hover:bg-[#1e3159] transition-colors cursor-pointer disabled:opacity-50"
                  >
                    {loading
                      ? 'Reading documents & calling extractor...'
                      : `Read & extract fields (${queuedCount} file${queuedCount === 1 ? '' : 's'})`}
                  </button>
                  <button
                    type="button"
                    onClick={handleManualEntryStart}
                    className="px-4 py-3 rounded-lg border border-[#CBD5E1] text-sm font-medium text-[#14213D] hover:bg-[#F7F4EC] cursor-pointer"
                  >
                    Enter fields manually without uploading
                  </button>
                </div>
              </section>
            )}

            {/* STEP 2: EXTRACT & CONFIRM */}
            {step === 2 && (
              <section className="rounded-2xl border border-[#E2DDD0] bg-[#FFFFFF] p-6 sm:p-8 space-y-6">
                <div>
                  <h1 className="text-2xl font-bold text-[#14213D]">
                    Review and confirm extracted fields
                  </h1>
                  <p className="text-sm sm:text-base text-[#475569] mt-1">
                    Edit any field below. You must confirm these values before the deterministic
                    rule engine evaluates your eligibility.
                  </p>
                </div>

                {records.length > 0 && (
                  <div className="space-y-3">
                    {records.map((rec, idx) => (
                      <div
                        key={rec.document.filename + idx}
                        className="rounded-xl border border-[#E2DDD0] bg-[#F7F4EC]/60 p-4"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <p className="text-sm font-bold text-[#14213D]">
                              {rec.document.filename}
                            </p>
                            <p className="text-xs text-[#475569]">
                              Method: {rec.document.extraction_method} · {rec.document.sharpness_label}
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedTextIdx(expandedTextIdx === idx ? null : idx)
                            }
                            className="inline-flex items-center gap-1 text-xs font-semibold text-[#14213D] underline cursor-pointer"
                          >
                            {expandedTextIdx === idx ? 'Hide extracted text' : 'View extracted text'}
                            {expandedTextIdx === idx ? (
                              <ChevronUp className="w-3.5 h-3.5" />
                            ) : (
                              <ChevronDown className="w-3.5 h-3.5" />
                            )}
                          </button>
                        </div>

                        {rec.error && (
                          <div className="mt-3 rounded-lg border border-[#FECACA] bg-[#FEE2E2] px-3 py-2 text-xs text-[#991B1B]">
                            <strong>LLM Extraction Error:</strong> {rec.error}. Enter or adjust
                            fields manually below.
                          </div>
                        )}

                        {expandedTextIdx === idx && (
                          <pre className="mt-3 max-h-48 overflow-auto rounded-lg bg-[#FFFFFF] border border-[#E2DDD0] p-3 text-xs text-[#334155] whitespace-pre-wrap">
                            {rec.document.raw_text || '(No text extracted)'}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <form onSubmit={handleEvaluate} className="space-y-5">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {(
                      [
                        ['full_name', 'Full Name', 'text', 'e.g. Ananya Ramesh Kulkarni'],
                        ['annual_income', 'Annual Family Income (INR)', 'text', 'e.g. 185000'],
                        ['category', 'Category', 'text', 'e.g. SC, ST, OBC, EWS, General'],
                        ['marks_percentage', 'Marks Percentage (%)', 'text', 'e.g. 84.5'],
                        ['course', 'Course / Programme', 'text', 'e.g. B.E. Computer Science'],
                        ['issue_date', 'Primary Issue Date (YYYY-MM-DD)', 'text', 'e.g. 2026-08-15'],
                        [
                          'issuing_authority',
                          'Issuing Authority',
                          'text',
                          'e.g. Office of the Tahsildar',
                        ],
                      ] as Array<[keyof ProfileFormState, string, string, string]>
                    ).map(([key, label, type, placeholder]) => {
                      const conf = fieldConfidence[key] || 'missing';
                      return (
                        <div key={key} className={key === 'issuing_authority' ? 'sm:col-span-2' : ''}>
                          <div className="flex items-center justify-between mb-1">
                            <label
                              htmlFor={`field-${key}`}
                              className="text-sm font-semibold text-[#14213D]"
                            >
                              {label}
                            </label>
                            <span className="text-xs text-[#475569]">
                              Confidence: <strong className="uppercase">{conf}</strong>
                            </span>
                          </div>
                          <input
                            id={`field-${key}`}
                            type={type}
                            value={formState[key]}
                            placeholder={placeholder}
                            onChange={(e) =>
                              setFormState((prev) => ({ ...prev, [key]: e.target.value }))
                            }
                            className="w-full rounded-lg border border-[#CBD5E1] bg-[#FFFFFF] px-3.5 py-2.5 text-sm sm:text-base text-[#14213D] focus:outline-none focus:ring-2 focus:ring-[#F2A33A]"
                          />
                        </div>
                      );
                    })}
                  </div>

                  <label className="flex items-start gap-3 rounded-xl border border-[#E2DDD0] bg-[#F7F4EC]/70 p-4 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={confirmedChecked}
                      onChange={(e) => setConfirmedChecked(e.target.checked)}
                      className="mt-1 h-4 w-4 accent-[#14213D]"
                    />
                    <span className="text-sm text-[#14213D]">
                      I have reviewed these synthetic fields and confirm they are ready to check
                      against the rules in <code className="font-mono">schemes.yaml</code>.
                    </span>
                  </label>

                  <div className="flex flex-wrap items-center gap-4">
                    <button
                      type="submit"
                      disabled={loading}
                      className="px-6 py-3 rounded-lg bg-[#F2A33A] text-[#14213D] font-semibold text-sm sm:text-base hover:bg-[#e59429] transition-colors cursor-pointer disabled:opacity-50"
                    >
                      Run eligibility &amp; document checks
                    </button>
                    <button
                      type="button"
                      onClick={() => setStep(1)}
                      className="px-4 py-3 rounded-lg border border-[#CBD5E1] text-sm font-medium text-[#14213D] hover:bg-[#F7F4EC] cursor-pointer"
                    >
                      Back to upload
                    </button>
                  </div>
                </form>
              </section>
            )}

            {/* STEP 3: LOADING */}
            {step === 3 && (
              <section className="rounded-2xl border border-[#E2DDD0] bg-[#FFFFFF] p-10 text-center">
                <p className="text-lg font-bold text-[#14213D]">
                  Running deterministic Python rules and classical checks...
                </p>
                <p className="text-sm text-[#475569] mt-2">
                  Checking document age, RapidFuzz name similarity, OpenCV sharpness, and
                  schemes.yaml thresholds.
                </p>
              </section>
            )}

            {/* STEP 4: RESULTS */}
            {step === 4 && (
              <div className="space-y-8">
                <div className="rounded-xl border border-[#FDE68A] bg-[#FEF3C7] px-5 py-3.5 text-sm text-[#92400E] flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2 font-medium">
                    <Info className="w-4 h-4 shrink-0" />
                    <span>
                      Prototype. Confirm thresholds on the official portal. All placeholder
                      schemes in schemes.yaml currently use TODO_VERIFY thresholds.
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={downloadMarkdown}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#FFFFFF] border border-[#E2DDD0] text-xs font-semibold text-[#14213D] hover:bg-[#F7F4EC] cursor-pointer"
                    >
                      <Download className="w-3.5 h-3.5" />
                      Download Markdown
                    </button>
                    <button
                      type="button"
                      onClick={downloadPdf}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#14213D] text-xs font-semibold text-[#F7F4EC] hover:bg-[#1e3159] cursor-pointer"
                    >
                      <FileText className="w-3.5 h-3.5" />
                      Download PDF
                    </button>
                  </div>
                </div>

                {/* Document Health Checks */}
                <section className="space-y-3">
                  <h2 className="text-2xl font-bold text-[#14213D]">Document health checks</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {healthChecks.map((hc) => {
                      const st = healthStatusLabel(hc.status);
                      return (
                        <div
                          key={hc.check_id}
                          className="rounded-xl border border-[#E2DDD0] bg-[#FFFFFF] p-5 space-y-2"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-bold tracking-wide text-[#475569]">
                              {hc.tag}
                            </span>
                            <span
                              className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${st.cls}`}
                            >
                              {st.text}
                            </span>
                          </div>
                          <h3 className="text-base font-bold text-[#14213D]">{hc.title}</h3>
                          <p className="text-sm text-[#334155] leading-relaxed">{hc.detail}</p>
                          {(hc.measured_value || hc.threshold_value) && (
                            <p className="text-xs text-[#64748B] tabular-nums pt-1 border-t border-[#F1EDE3]">
                              Measured: {hc.measured_value || '—'} · Limit:{' '}
                              {hc.threshold_value || '—'}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>

                {/* Scheme Verdict Cards */}
                <section className="space-y-4">
                  <h2 className="text-2xl font-bold text-[#14213D]">Scheme verdicts</h2>
                  <div className="space-y-4">
                    {schemeResults.map((res) => {
                      const vs = verdictStyle(res.verdict);
                      const VerdictIcon = vs.icon;
                      const isOpen = !!openChecklistIds[res.scheme_id];
                      return (
                        <div
                          key={res.scheme_id}
                          className="rounded-xl border border-[#E2DDD0] bg-[#FFFFFF] p-6 space-y-3"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <h3 className="text-lg font-bold text-[#14213D]">
                                {res.scheme_name}
                              </h3>
                              <p className="text-xs text-[#475569] mt-0.5">
                                {res.provider} · {res.level} · Last verified: {res.last_verified} ·
                                Prototype. Confirm thresholds on the official portal.
                              </p>
                            </div>
                            <span
                              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-bold shrink-0 ${vs.classes}`}
                            >
                              <VerdictIcon className="w-3.5 h-3.5" />
                              {vs.label}
                            </span>
                          </div>

                          <p className="text-sm sm:text-base text-[#14213D]">
                            <strong>Reason:</strong> {res.summary_reason}
                          </p>

                          <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-[#F1EDE3]">
                            <a
                              href={res.source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 text-xs font-semibold text-[#14213D] underline"
                            >
                              Official portal source
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>

                            {res.checklist.length > 0 && (
                              <button
                                type="button"
                                onClick={() =>
                                  setOpenChecklistIds((prev) => ({
                                    ...prev,
                                    [res.scheme_id]: !prev[res.scheme_id],
                                  }))
                                }
                                className="text-xs font-semibold text-[#92400E] underline cursor-pointer"
                              >
                                {isOpen
                                  ? 'Hide Fix before you submit'
                                  : `Fix before you submit (${res.checklist.length})`}
                              </button>
                            )}
                          </div>

                          {isOpen && res.checklist.length > 0 && (
                            <ul className="mt-2 space-y-1.5 rounded-lg bg-[#F7F4EC] p-4 text-sm text-[#14213D] list-disc list-inside">
                              {res.checklist.map((item, i) => (
                                <li key={i}>{item}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>

                {/* Global Fix-Before-You-Submit Checklist */}
                <section className="rounded-xl border border-[#E2DDD0] bg-[#FFFFFF] p-6 space-y-3">
                  <h2 className="text-xl font-bold text-[#14213D]">Fix before you submit</h2>
                  {globalChecklist.length === 0 ? (
                    <p className="text-sm text-[#166534]">
                      No document or verified-rule issues detected.
                    </p>
                  ) : (
                    <ol className="list-decimal list-inside space-y-2 text-sm text-[#334155]">
                      {globalChecklist.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ol>
                  )}

                  <div className="pt-4">
                    <button
                      type="button"
                      onClick={() => setStep(1)}
                      className="px-5 py-2.5 rounded-lg border border-[#14213D] text-sm font-semibold text-[#14213D] hover:bg-[#F7F4EC] cursor-pointer"
                    >
                      Check another synthetic packet
                    </button>
                  </div>
                </section>
              </div>
            )}
          </div>
        )}

        {/* HOW IT WORKS PAGE */}
        {page === 'how' && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-[#E2DDD0] bg-[#FFFFFF] p-6 sm:p-8">
              <h1 className="text-3xl font-bold text-[#14213D]">How SchemeSathi works</h1>
              <p className="mt-2 text-base text-[#475569] max-w-3xl">
                SchemeSathi separates unstructured reading from deterministic decisions. Only the
                field-reading step calls an LLM; every rule and check is inspectable Python code.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <div className="rounded-xl border border-[#E2DDD0] bg-[#FFFFFF] p-6 space-y-2">
                <span className="text-xs font-bold text-[#92400E]">AI (LLM)</span>
                <h2 className="text-xl font-bold text-[#14213D]">Structured reading only</h2>
                <p className="text-sm text-[#334155] leading-relaxed">
                  Gemini or Groq converts raw PyMuPDF / Tesseract text into 7 typed JSON fields
                  validated with Pydantic (with 1 automatic retry). AI never approves or rejects an
                  applicant.
                </p>
              </div>

              <div className="rounded-xl border border-[#E2DDD0] bg-[#FFFFFF] p-6 space-y-2">
                <span className="text-xs font-bold text-[#166534]">RULE</span>
                <h2 className="text-xl font-bold text-[#14213D]">Deterministic Python rules</h2>
                <p className="text-sm text-[#334155] leading-relaxed">
                  Income caps, marks percentages, category membership, certificate expiry dates, and
                  required document lists are evaluated deterministically against{' '}
                  <code className="font-mono">data/schemes.yaml</code>.
                </p>
              </div>

              <div className="rounded-xl border border-[#E2DDD0] bg-[#FFFFFF] p-6 space-y-2">
                <span className="text-xs font-bold text-[#14213D]">
                  STRING SIMILARITY &amp; IMAGE TEST
                </span>
                <h2 className="text-xl font-bold text-[#14213D]">Classical checks (not ML)</h2>
                <p className="text-sm text-[#334155] leading-relaxed">
                  Cross-document name consistency uses RapidFuzz token-sort string similarity. Scan
                  blur detection uses OpenCV Laplacian edge variance—classical image math, not
                  machine learning.
                </p>
              </div>
            </div>

            <div className="rounded-xl border border-[#E2DDD0] bg-[#FFFFFF] p-6 flex items-start gap-3">
              <ShieldAlert className="w-5 h-5 text-[#92400E] shrink-0 mt-0.5" />
              <div className="text-sm text-[#334155] space-y-1">
                <p className="font-bold text-[#14213D]">Data handling &amp; synthetic-only notice</p>
                <p>
                  Documents are sent to an external LLM API for extraction. Use synthetic documents
                  only. SQLite stores only anonymized session summary counts and evaluation metrics—no
                  uploaded files or raw PII are persisted.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* EVALUATION PAGE */}
        {page === 'evaluation' && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-[#E2DDD0] bg-[#FFFFFF] p-6 sm:p-8 flex flex-wrap items-start justify-between gap-4">
              <div>
                <h1 className="text-3xl font-bold text-[#14213D]">
                  Extraction accuracy evaluation
                </h1>
                <p className="mt-2 text-sm sm:text-base text-[#475569] max-w-2xl">
                  Measured field-by-field on the labelled synthetic documents in{' '}
                  <code className="font-mono">data/eval/</code> using{' '}
                  <code className="font-mono">scripts/evaluate_extraction.py</code>.
                </p>
              </div>
              <button
                type="button"
                onClick={handleRunEvaluationScript}
                disabled={evalRunning}
                className="px-4 py-2.5 rounded-lg bg-[#14213D] text-[#F7F4EC] text-sm font-semibold hover:bg-[#1e3159] transition-colors cursor-pointer disabled:opacity-50"
              >
                {evalRunning ? 'Running evaluation...' : 'Run evaluation on data/eval/'}
              </button>
            </div>

            {evalError && (
              <div className="rounded-xl border border-[#FECACA] bg-[#FEE2E2] px-4 py-3 text-sm text-[#991B1B]">
                {evalError}
              </div>
            )}

            {!metadata?.eval_results ? (
              <div className="rounded-xl border border-[#E2DDD0] bg-[#FFFFFF] p-8 text-center space-y-3">
                <p className="text-xl font-bold text-[#14213D]">Not yet measured</p>
                <p className="text-sm text-[#475569] max-w-lg mx-auto">
                  No fabricated numbers are shown. Configure <code className="font-mono">GEMINI_API_KEY</code>{' '}
                  (or <code className="font-mono">GROQ_API_KEY</code>) and run{' '}
                  <code className="font-mono">python scripts/evaluate_extraction.py</code> or click
                  the button above.
                </p>
              </div>
            ) : (
              <div className="rounded-xl border border-[#E2DDD0] bg-[#FFFFFF] p-6 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-[#475569]">
                  <span>
                    Provider: <strong className="text-[#14213D]">{metadata.eval_results.llm_provider}</strong>{' '}
                    ({metadata.eval_results.model_name}) · Samples:{' '}
                    <strong className="text-[#14213D] tabular-nums">
                      {metadata.eval_results.sample_count}
                    </strong>
                  </span>
                  <span className="text-base font-bold text-[#14213D] tabular-nums">
                    Overall accuracy: {(metadata.eval_results.overall_accuracy * 100).toFixed(1)}%
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-sm">
                    <thead>
                      <tr className="border-b border-[#E2DDD0] text-[#475569]">
                        <th className="py-2.5 pr-4 font-semibold">Field</th>
                        <th className="py-2.5 px-4 font-semibold text-right">Correct</th>
                        <th className="py-2.5 px-4 font-semibold text-right">Total</th>
                        <th className="py-2.5 pl-4 font-semibold text-right">Accuracy</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(metadata.eval_results.field_metrics).map(([field, m]) => (
                        <tr key={field} className="border-b border-[#F1EDE3]">
                          <td className="py-2.5 pr-4 font-mono text-xs sm:text-sm text-[#14213D]">
                            {field}
                          </td>
                          <td className="py-2.5 px-4 text-right tabular-nums">{m.correct}</td>
                          <td className="py-2.5 px-4 text-right tabular-nums">{m.total}</td>
                          <td className="py-2.5 pl-4 text-right font-semibold tabular-nums">
                            {(m.accuracy * 100).toFixed(1)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
      <ChatAssistant
        page={page}
        step={step}
        queuedFiles={Object.values(queuedDocs)
          .filter(Boolean)
          .map((d) => d!.filename)}
        healthChecks={healthChecks}
        schemeResults={schemeResults}
      />
    </div>
  );
}
