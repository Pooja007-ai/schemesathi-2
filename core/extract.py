"""LLM-based structured field extraction with Pydantic validation and 1 retry.

Principle: AI reads, rules decide. This module ONLY extracts fields from
document text into a fixed JSON schema. It never evaluates scholarship rules.
If the LLM call fails, it raises ExtractionError so the UI can let the user
enter fields manually—nothing is ever faked.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from dotenv import load_dotenv
from pydantic import ValidationError

from core.models import (
    ConfidenceLevel,
    DocumentType,
    ExtractedDocumentFields,
    EXTRACTED_FIELD_NAMES,
)

load_dotenv()


class ExtractionError(RuntimeError):
    """Raised when LLM extraction cannot complete or fails validation twice."""


EXTRACTION_SYSTEM_PROMPT = """You are a careful document transcription assistant for Indian student scholarship verification.
Extract ONLY facts explicitly stated in the provided document text.
Do NOT guess, invent, or infer missing numbers. If a field is not present in the document, set it to null and set its confidence to "missing".

Return valid JSON matching this exact schema:
{
  "full_name": string | null,
  "annual_income": number | null,
  "category": string | null,
  "marks_percentage": number | null,
  "course": string | null,
  "issue_date": "YYYY-MM-DD" | null,
  "issuing_authority": string | null,
  "field_confidence": {
    "full_name": "high" | "medium" | "low" | "missing",
    "annual_income": "high" | "medium" | "low" | "missing",
    "category": "high" | "medium" | "low" | "missing",
    "marks_percentage": "high" | "medium" | "low" | "missing",
    "course": "high" | "medium" | "low" | "missing",
    "issue_date": "high" | "medium" | "low" | "missing",
    "issuing_authority": "high" | "medium" | "low" | "missing"
  },
  "extraction_notes": string | null
}

Formatting rules:
- annual_income: plain number in INR (e.g. "Rs. 1,45,000/-" -> 145000).
- marks_percentage: numeric percentage 0-100 (if CGPA only and no percentage is written, leave null and mention CGPA in extraction_notes).
- issue_date: convert DD/MM/YYYY or DD-MM-YYYY or Month DD, YYYY into YYYY-MM-DD when unambiguous.
- category: short code when printed (e.g. SC, ST, OBC, BC, MBC, EWS, Minority, General).
"""


def _strip_code_fences(raw: str) -> str:
    cleaned = raw.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return cleaned


def _normalize_extracted_payload(data: dict[str, Any]) -> dict[str, Any]:
    conf = dict(data.get("field_confidence") or {})
    for field_name in EXTRACTED_FIELD_NAMES:
        val = data.get(field_name)
        if field_name not in conf:
            conf[field_name] = (
                ConfidenceLevel.MISSING.value if val is None else ConfidenceLevel.MEDIUM.value
            )
    data["field_confidence"] = conf
    return data


def _call_gemini(prompt: str, model_name: Optional[str] = None) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "MY_GEMINI_API_KEY":
        raise ExtractionError(
            "GEMINI_API_KEY is not configured. Set it in .env or environment secrets."
        )

    from google import genai
    from google.genai import types

    chosen_model = model_name or os.getenv("GEMINI_MODEL", "gemini-4-hydrogen").strip()
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(headers={"User-Agent": "aistudio-build"}),
    )
    response = client.models.generate_content(
        model=chosen_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=EXTRACTION_SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )
    text = getattr(response, "text", None)
    if not text:
        raise ExtractionError("Gemini returned an empty response.")
    return text


def _call_groq(prompt: str, model_name: Optional[str] = None) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ExtractionError(
            "GROQ_API_KEY is not configured. Set it in .env or environment secrets."
        )

    from groq import Groq

    chosen_model = model_name or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()
    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model=chosen_model,
        response_format={"type": "json_object"},
        temperature=0.0,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    content = completion.choices[0].message.content
    if not content:
        raise ExtractionError("Groq returned an empty response.")
    return content


def _invoke_llm(prompt: str, provider: Optional[str] = None, model_name: Optional[str] = None) -> str:
    selected = (provider or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()
    if selected == "gemini":
        return _call_gemini(prompt, model_name=model_name)
    if selected == "groq":
        return _call_groq(prompt, model_name=model_name)
    raise ExtractionError(f"Unsupported LLM_PROVIDER '{selected}'. Use 'gemini' or 'groq'.")


def extract_fields_from_text(
    raw_text: str,
    doc_type: DocumentType,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    llm_callable: Optional[Any] = None,
) -> tuple[ExtractedDocumentFields, int]:
    """Extract fixed JSON schema from raw document text with Pydantic validation & 1 retry.

    Returns (ExtractedDocumentFields, attempts_used).
    Raises ExtractionError if text is empty or LLM fails after retry.
    """
    if not raw_text or not raw_text.strip():
        raise ExtractionError(
            "No readable text was extracted from this document. Enter fields manually."
        )

    base_prompt = (
        f"Document type: {doc_type.value}\n\n"
        f"--- BEGIN DOCUMENT TEXT ---\n{raw_text.strip()}\n--- END DOCUMENT TEXT ---"
    )

    caller = llm_callable or (lambda p: _invoke_llm(p, provider=provider, model_name=model_name))
    last_error: Optional[str] = None

    for attempt in (1, 2):
        prompt = base_prompt
        if attempt == 2 and last_error:
            prompt = (
                f"{base_prompt}\n\n"
                f"Your previous JSON output failed validation with error: {last_error}\n"
                "Fix the JSON strictly to match the required schema and types."
            )
        try:
            raw_output = caller(prompt)
            parsed = json.loads(_strip_code_fences(raw_output))
            if not isinstance(parsed, dict):
                raise ValueError("Top-level JSON value must be an object.")
            normalized = _normalize_extracted_payload(parsed)
            validated = ExtractedDocumentFields.model_validate(normalized)
            return validated, attempt
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = str(exc)
            continue
        except ExtractionError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface real API errors honestly
            raise ExtractionError(f"LLM extraction failed: {exc}") from exc

    raise ExtractionError(
        f"LLM output failed Pydantic schema validation after 2 attempts: {last_error}"
    )
