"""Document ingestion: PyMuPDF text extraction, Tesseract OCR fallback, and OpenCV sharpness check."""

from __future__ import annotations

import io
import os
from typing import Optional

import cv2
import numpy as np
import pymupdf as fitz
import pytesseract
from PIL import Image

from core.models import DocumentType, IngestedDocument

DEFAULT_SHARPNESS_MIN_VARIANCE = float(os.getenv("SHARPNESS_MIN_VARIANCE", "100.0"))
MIN_NATIVE_TEXT_CHARS_PER_PAGE = 40


def compute_laplacian_variance(image_bgr: np.ndarray) -> float:
    """Classical image test: variance of the 2D Laplacian on grayscale pixels.

    Lower variance indicates fewer sharp edges (blurry / out-of-focus scan).
    Not machine learning.
    """
    if image_bgr is None or image_bgr.size == 0:
        return 0.0
    if len(image_bgr.shape) == 3:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = image_bgr
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def classify_sharpness(
    variance: float, min_variance: float = DEFAULT_SHARPNESS_MIN_VARIANCE
) -> tuple[bool, str]:
    if variance >= min_variance:
        return True, f"Sharp scan (Laplacian variance {variance:.1f} >= {min_variance:.1f})"
    return False, f"Blurry scan (Laplacian variance {variance:.1f} < {min_variance:.1f})"


def _ocr_pil_image(pil_image: Image.Image) -> str:
    try:
        return pytesseract.image_to_string(pil_image).strip()
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "Tesseract OCR binary is not installed or not on PATH. "
            "Install tesseract-ocr to extract text from scanned PDFs and images."
        ) from exc


def ingest_image_bytes(
    file_bytes: bytes,
    filename: str,
    doc_type: DocumentType,
    min_sharpness_variance: float = DEFAULT_SHARPNESS_MIN_VARIANCE,
) -> IngestedDocument:
    """Decode an image, run Laplacian variance check, and OCR with Tesseract."""
    arr = np.frombuffer(file_bytes, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError(f"Could not decode image file: {filename}")

    variance = compute_laplacian_variance(bgr)
    sharp_ok, sharp_label = classify_sharpness(variance, min_sharpness_variance)

    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    text = _ocr_pil_image(pil_img)

    warnings: list[str] = []
    if not sharp_ok:
        warnings.append(
            f"Image sharpness is below threshold ({variance:.1f} < {min_sharpness_variance:.1f}). "
            "Re-take the photo in bright light to avoid portal rejection."
        )
    if len(text.strip()) < 20:
        warnings.append("Very little text detected by OCR; check orientation or crop.")

    return IngestedDocument(
        filename=filename,
        doc_type=doc_type,
        file_kind="image",
        raw_text=text,
        extraction_method="tesseract_ocr",
        page_count=1,
        sharpness_variance=round(variance, 2),
        sharpness_passed=sharp_ok,
        sharpness_label=sharp_label,
        warnings=warnings,
    )


def ingest_pdf_bytes(
    file_bytes: bytes,
    filename: str,
    doc_type: DocumentType,
    min_sharpness_variance: float = DEFAULT_SHARPNESS_MIN_VARIANCE,
) -> IngestedDocument:
    """Extract text via PyMuPDF; fall back to rendering + Tesseract OCR for scans."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page_count = len(doc)
    if page_count == 0:
        raise ValueError(f"PDF has no pages: {filename}")

    native_pages: list[str] = []
    for page in doc:
        native_pages.append(page.get_text("text").strip())

    native_text = "\n\n".join(p for p in native_pages if p).strip()
    non_ws_len = len("".join(native_text.split()))

    # Heuristic: if native text averages >= MIN_NATIVE_TEXT_CHARS_PER_PAGE, it is digital text.
    if non_ws_len >= MIN_NATIVE_TEXT_CHARS_PER_PAGE * page_count:
        return IngestedDocument(
            filename=filename,
            doc_type=doc_type,
            file_kind="pdf",
            raw_text=native_text,
            extraction_method="pymupdf_text",
            page_count=page_count,
            sharpness_variance=None,
            sharpness_passed=None,
            sharpness_label="Not applicable (native digital PDF text)",
            warnings=[],
        )

    # Scanned PDF fallback: render pages and run OpenCV sharpness + Tesseract OCR.
    ocr_pages: list[str] = []
    variances: list[float] = []
    for page in doc:
        pix = page.get_pixmap(dpi=220)
        img_bytes = pix.tobytes("png")
        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is not None:
            variances.append(compute_laplacian_variance(bgr))
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        ocr_pages.append(_ocr_pil_image(pil_img))

    ocr_text = "\n\n".join(p for p in ocr_pages if p).strip()
    avg_variance: Optional[float] = (
        round(float(sum(variances) / len(variances)), 2) if variances else None
    )
    sharp_ok: Optional[bool] = None
    sharp_label = "Unavailable"
    warnings: list[str] = [
        "No selectable PDF text found; fell back to Tesseract OCR on rendered pages."
    ]

    if avg_variance is not None:
        sharp_ok, sharp_label = classify_sharpness(avg_variance, min_sharpness_variance)
        if not sharp_ok:
            warnings.append(
                f"Scanned PDF sharpness is low ({avg_variance:.1f} < {min_sharpness_variance:.1f})."
            )

    combined_text = ocr_text or native_text
    method = "pymupdf_plus_ocr" if native_text and ocr_text else "tesseract_ocr"

    return IngestedDocument(
        filename=filename,
        doc_type=doc_type,
        file_kind="pdf",
        raw_text=combined_text,
        extraction_method=method,
        page_count=page_count,
        sharpness_variance=avg_variance,
        sharpness_passed=sharp_ok,
        sharpness_label=sharp_label,
        warnings=warnings,
    )


def ingest_document(
    file_bytes: bytes,
    filename: str,
    doc_type: DocumentType,
    min_sharpness_variance: float = DEFAULT_SHARPNESS_MIN_VARIANCE,
) -> IngestedDocument:
    """Route uploaded PDF or image bytes to the matching ingestion pipeline."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return ingest_pdf_bytes(file_bytes, filename, doc_type, min_sharpness_variance)
    if lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp")):
        return ingest_image_bytes(file_bytes, filename, doc_type, min_sharpness_variance)
    raise ValueError(f"Unsupported file type for {filename}. Upload a PDF, PNG, or JPG.")
