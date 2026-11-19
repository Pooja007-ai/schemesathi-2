import React, { useEffect, useRef, useState } from 'react';
import { MessageSquare, RotateCcw, Send, X } from 'lucide-react';
import type { ChatMessage, HealthCheckResult, PageId, SchemeEvaluationResult } from '../types';

interface ChatAssistantProps {
  page: PageId;
  step: 1 | 2 | 3 | 4;
  queuedFiles: string[];
  healthChecks: HealthCheckResult[];
  schemeResults: SchemeEvaluationResult[];
}

const INITIAL_WELCOME: ChatMessage = {
  id: 'welcome',
  role: 'model',
  text: 'Ask me any doubt about uploading synthetic scholarship documents, scan blur warnings, name matching, or what your verification checks mean. Deterministic Python rules still decide all verdicts.',
};

const QUICK_QUESTIONS = [
  'Why could a blurry photo fail verification?',
  'My name is abbreviated on my marks card — is that okay?',
  'What does TODO_VERIFY mean on the schemes?',
  'Which documents do I need to upload?',
];

export default function ChatAssistant({
  page,
  step,
  queuedFiles,
  healthChecks,
  schemeResults,
}: ChatAssistantProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([INITIAL_WELCOME]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (open) {
      scrollEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, open]);

  async function sendQuestion(rawText: string) {
    const trimmed = rawText.trim();
    if (!trimmed || streaming) return;

    setError(null);
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      text: trimmed,
    };
    const modelMsgId = `model-${Date.now() + 1}`;
    const placeholderModelMsg: ChatMessage = {
      id: modelMsgId,
      role: 'model',
      text: '',
    };

    const nextHistory = [...messages, userMsg];
    setMessages([...nextHistory, placeholderModelMsg]);
    setInput('');
    setStreaming(true);

    // Build sanitized, non-PII session context so the assistant understands the active step/results
    const safeContext = {
      active_page: page,
      checker_step: page === 'checker' ? step : null,
      queued_document_count: queuedFiles.length,
      queued_document_names: queuedFiles,
      health_checks: healthChecks.map((hc) => ({
        title: hc.title,
        tag: hc.tag,
        status: hc.status,
        measured_value: hc.measured_value,
        threshold_value: hc.threshold_value,
      })),
      scheme_verdicts: schemeResults.map((s) => ({
        scheme_name: s.scheme_name,
        verdict: s.verdict,
        has_unverified_thresholds: s.has_unverified_thresholds,
        missing_docs: s.missing_docs,
      })),
    };

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: nextHistory.map((m) => ({ role: m.role, text: m.text })),
          context: safeContext,
        }),
      });

      const contentType = resp.headers.get('content-type') || '';
      if (!resp.ok || !contentType.includes('text/event-stream')) {
        const errPayload = await resp.json().catch(() => ({}));
        throw new Error(errPayload.error || `Chat request failed (${resp.status}).`);
      }

      const reader = resp.body?.getReader();
      if (!reader) {
        throw new Error('Streaming response body is unavailable.');
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let accumulated = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const chunkLine of lines) {
          const dataLine = chunkLine
            .split('\n')
            .find((line) => line.startsWith('data: '));
          if (!dataLine) continue;
          const payload = JSON.parse(dataLine.slice(6));
          if (payload.error) {
            throw new Error(payload.error);
          }
          if (payload.text) {
            accumulated += payload.text;
            setMessages((prev) =>
              prev.map((m) => (m.id === modelMsgId ? { ...m, text: accumulated } : m))
            );
          }
        }
      }

      if (!accumulated.trim()) {
        throw new Error('The assistant returned an empty response.');
      }
    } catch (err: any) {
      setError(err?.message || 'Unable to reach Gemini chat.');
      // Remove empty model placeholder if nothing was streamed
      setMessages((prev) => prev.filter((m) => !(m.id === modelMsgId && !m.text)));
    } finally {
      setStreaming(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    sendQuestion(input);
  }

  function handleReset() {
    if (streaming) return;
    setMessages([INITIAL_WELCOME]);
    setError(null);
  }

  return (
    <>
      {/* Launcher Button */}
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open Document Submission Assistant"
          className="fixed bottom-4 right-4 z-40 inline-flex items-center gap-2 rounded-xl bg-[#14213D] px-4 py-3 text-sm font-semibold text-[#F7F4EC] shadow-lg border border-[#F2A33A] hover:bg-[#1e3159] transition-colors whitespace-nowrap cursor-pointer"
        >
          <MessageSquare className="w-4 h-4 text-[#F2A33A]" />
          <span>Ask Document Doubts</span>
        </button>
      )}

      {/* Slide-over / Floating Chat Drawer */}
      {open && (
        <aside
          role="dialog"
          aria-label="Document Submission Assistant"
          className="fixed bottom-4 right-4 z-50 w-[calc(100vw-2rem)] sm:w-[400px] h-[540px] max-h-[82vh] rounded-2xl border border-[#E2DDD0] bg-[#FFFFFF] shadow-2xl flex flex-col overflow-hidden"
        >
          {/* Drawer Header */}
          <div className="bg-[#14213D] text-[#F7F4EC] px-4 py-3.5 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-base font-bold leading-tight truncate">
                Document Submission Assistant
              </h2>
              <p className="text-xs text-[#CBD5E1] truncate">
                Ask doubts about scans, name match &amp; rules
              </p>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                type="button"
                onClick={handleReset}
                disabled={streaming}
                title="Clear conversation"
                aria-label="Clear conversation"
                className="p-1.5 rounded-lg text-[#CBD5E1] hover:text-[#FFFFFF] hover:bg-white/10 transition-colors cursor-pointer disabled:opacity-50"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => setOpen(false)}
                title="Close chat"
                aria-label="Close chat"
                className="p-1.5 rounded-lg text-[#CBD5E1] hover:text-[#FFFFFF] hover:bg-white/10 transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Scrollable Conversation Thread */}
          <div className="flex-1 overflow-y-auto bg-[#F7F4EC]/70 p-4 space-y-3">
            {messages.map((msg) => {
              const isUser = msg.role === 'user';
              return (
                <div
                  key={msg.id}
                  className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
                      isUser
                        ? 'bg-[#14213D] text-[#F7F4EC]'
                        : 'bg-[#FFFFFF] text-[#14213D] border border-[#E2DDD0]'
                    }`}
                  >
                    {msg.text || (streaming ? 'Thinking...' : '')}
                  </div>
                </div>
              );
            })}

            {messages.length === 1 && !streaming && (
              <div className="pt-2 space-y-1.5">
                <p className="text-xs font-medium text-[#475569]">Common document doubts:</p>
                <div className="flex flex-col gap-1.5">
                  {QUICK_QUESTIONS.map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => sendQuestion(q)}
                      className="text-left rounded-lg border border-[#E2DDD0] bg-[#FFFFFF] px-3 py-2 text-xs font-medium text-[#14213D] hover:border-[#F2A33A] transition-colors cursor-pointer"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {error && (
              <div
                role="alert"
                className="rounded-lg border border-[#FECACA] bg-[#FEE2E2] px-3 py-2 text-xs text-[#991B1B]"
              >
                {error}
              </div>
            )}

            <div ref={scrollEndRef} />
          </div>

          {/* Input Bar */}
          <form
            onSubmit={handleSubmit}
            className="border-t border-[#E2DDD0] bg-[#FFFFFF] p-3 space-y-2"
          >
            <div className="flex items-end gap-2">
              <textarea
                rows={2}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendQuestion(input);
                  }
                }}
                placeholder="Ask about document format, blur, name match..."
                className="flex-1 resize-none rounded-lg border border-[#CBD5E1] bg-[#F7F4EC]/50 px-3 py-2 text-sm text-[#14213D] focus:outline-none focus:ring-2 focus:ring-[#F2A33A]"
              />
              <button
                type="submit"
                disabled={streaming || !input.trim()}
                aria-label="Send message"
                className="inline-flex items-center justify-center rounded-lg bg-[#F2A33A] px-3.5 py-2.5 text-sm font-semibold text-[#14213D] hover:bg-[#e59429] transition-colors cursor-pointer disabled:opacity-50 shrink-0"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
            <p className="text-[11px] text-[#64748B]">
              Explains document submission checks only; Python rules decide eligibility.
            </p>
          </form>
        </aside>
      )}
    </>
  );
}
