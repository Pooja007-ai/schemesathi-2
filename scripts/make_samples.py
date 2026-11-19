"""Generate synthetic student scholarship documents for samples and evaluation.

Creates:
- data/samples/:
  - sample_income_certificate.pdf (digital text PDF)
  - sample_marks_card.pdf (digital text PDF)
  - sample_community_certificate.png (rendered scanned image for OCR + Laplacian test)
- data/eval/:
  - 6 labelled synthetic documents (PDF + PNG) + ground_truth.json
"""

from __future__ import annotations

import json
from pathlib import Path

from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT_DIR = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT_DIR / "data" / "samples"
EVAL_DIR = ROOT_DIR / "data" / "eval"


def _write_certificate_pdf(path: Path, title: str, lines: list[str]) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, "SYNTHETIC PROTOTYPE DOCUMENT - NOT OFFICIAL", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 12)
    for line in lines:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 8, line)
    pdf.output(str(path))


def _write_certificate_image(
    path: Path, title: str, lines: list[str], blur_radius: float = 0.0
) -> None:
    img = Image.new("RGB", (1240, 1600), color=(250, 248, 242))
    draw = ImageDraw.Draw(img)
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
        body_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except OSError:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    draw.rectangle([(40, 40), (1200, 1560)], outline=(30, 45, 80), width=4)
    draw.text((70, 80), "SYNTHETIC PROTOTYPE DOCUMENT - FOR TESTING ONLY", fill=(160, 60, 40), font=small_font)
    draw.text((70, 140), title, fill=(20, 33, 61), font=title_font)

    y = 230
    for line in lines:
        draw.text((70, y), line, fill=(25, 25, 25), font=body_font)
        y += 58

    if blur_radius > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    img.save(path)


def generate_samples() -> list[Path]:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    income_pdf = SAMPLES_DIR / "sample_income_certificate.pdf"
    _write_certificate_pdf(
        income_pdf,
        "FAMILY INCOME CERTIFICATE (SYNTHETIC)",
        [
            "Certificate No: SYN-INC-2026-0412",
            "Applicant Full Name: Ananya Ramesh Kulkarni",
            "Annual Family Income: Rs. 1,85,000/-",
            "Course Enrolled: B.E. Computer Science and Engineering",
            "Date of Issue: 2026-08-15",
            "Issuing Authority: Office of the Tahsildar, Bengaluru North",
        ],
    )

    marks_pdf = SAMPLES_DIR / "sample_marks_card.pdf"
    _write_certificate_pdf(
        marks_pdf,
        "STATEMENT OF MARKS (SYNTHETIC)",
        [
            "Register Number: 2026SYN0891",
            "Student Name: Ananya R Kulkarni",
            "Course / Programme: B.E. Computer Science and Engineering (Semester II)",
            "Aggregate Percentage: 84.5%",
            "Result: First Class with Distinction",
            "Date of Issue: 2026-06-20",
            "Issuing Authority: State Technical Examinations Board",
        ],
    )

    community_png = SAMPLES_DIR / "sample_community_certificate.png"
    _write_certificate_image(
        community_png,
        "COMMUNITY / CATEGORY CERTIFICATE (SYNTHETIC)",
        [
            "Certificate ID: SYN-COM-2026-1190",
            "Student Full Name: Ananya Ramesh Kulkarni",
            "Belongs to Category: OBC",
            "District: Bengaluru Urban",
            "Issue Date: 2025-11-10",
            "Issuing Authority: Revenue Divisional Officer, Bengaluru",
        ],
        blur_radius=0.0,
    )

    return [income_pdf, marks_pdf, community_png]


def generate_eval_dataset() -> Path:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    cases = [
        {
            "id": "eval_01_income_pdf",
            "filename": "eval_01_income.pdf",
            "doc_type": "income_certificate",
            "kind": "pdf",
            "title": "INCOME CERTIFICATE (SYNTHETIC EVAL 01)",
            "lines": [
                "Applicant Name: Karthik Subramanian",
                "Total Annual Family Income: Rs. 2,10,000/-",
                "Course: B.Sc. Physics",
                "Date of Issue: 2026-09-05",
                "Issuing Authority: Tahsildar, Madurai South",
            ],
            "ground_truth": {
                "full_name": "Karthik Subramanian",
                "annual_income": 210000.0,
                "category": None,
                "marks_percentage": None,
                "course": "B.Sc. Physics",
                "issue_date": "2026-09-05",
                "issuing_authority": "Tahsildar, Madurai South",
            },
        },
        {
            "id": "eval_02_marks_pdf",
            "filename": "eval_02_marks.pdf",
            "doc_type": "marks_card",
            "kind": "pdf",
            "title": "ANNUAL MARKS CARD (SYNTHETIC EVAL 02)",
            "lines": [
                "Candidate Full Name: Meera Devi Nair",
                "Course: Diploma in Civil Engineering",
                "Percentage of Marks: 78.4%",
                "Date of Issue: 2026-05-18",
                "Issuing Authority: Board of Technical Education, Kerala",
            ],
            "ground_truth": {
                "full_name": "Meera Devi Nair",
                "annual_income": None,
                "category": None,
                "marks_percentage": 78.4,
                "course": "Diploma in Civil Engineering",
                "issue_date": "2026-05-18",
                "issuing_authority": "Board of Technical Education, Kerala",
            },
        },
        {
            "id": "eval_03_community_png",
            "filename": "eval_03_community.png",
            "doc_type": "community_certificate",
            "kind": "png",
            "title": "COMMUNITY CERTIFICATE (SYNTHETIC EVAL 03)",
            "lines": [
                "Full Name: Arjun Singh Rathore",
                "Category: SC",
                "Issue Date: 2026-01-22",
                "Issuing Authority: Sub-Divisional Magistrate, Jaipur",
            ],
            "ground_truth": {
                "full_name": "Arjun Singh Rathore",
                "annual_income": None,
                "category": "SC",
                "marks_percentage": None,
                "course": None,
                "issue_date": "2026-01-22",
                "issuing_authority": "Sub-Divisional Magistrate, Jaipur",
            },
        },
        {
            "id": "eval_04_income_png",
            "filename": "eval_04_income.png",
            "doc_type": "income_certificate",
            "kind": "png",
            "title": "INCOME CERTIFICATE (SYNTHETIC EVAL 04)",
            "lines": [
                "Student Name: Fatima Begum Ansari",
                "Annual Family Income: INR 96000",
                "Category: OBC",
                "Issue Date: 2026-07-12",
                "Issuing Authority: Naib Tahsildar, Lucknow",
            ],
            "ground_truth": {
                "full_name": "Fatima Begum Ansari",
                "annual_income": 96000.0,
                "category": "OBC",
                "marks_percentage": None,
                "course": None,
                "issue_date": "2026-07-12",
                "issuing_authority": "Naib Tahsildar, Lucknow",
            },
        },
        {
            "id": "eval_05_marks_pdf",
            "filename": "eval_05_marks.pdf",
            "doc_type": "marks_card",
            "kind": "pdf",
            "title": "HIGHER SECONDARY MARKS SHEET (SYNTHETIC EVAL 05)",
            "lines": [
                "Student Full Name: Rohan Prakash Verma",
                "Course: Class 12 Science",
                "Overall Percentage: 91.2%",
                "Date of Issue: 2026-05-30",
                "Issuing Authority: Central Board of Secondary Education",
            ],
            "ground_truth": {
                "full_name": "Rohan Prakash Verma",
                "annual_income": None,
                "category": None,
                "marks_percentage": 91.2,
                "course": "Class 12 Science",
                "issue_date": "2026-05-30",
                "issuing_authority": "Central Board of Secondary Education",
            },
        },
        {
            "id": "eval_06_community_pdf",
            "filename": "eval_06_community.pdf",
            "doc_type": "community_certificate",
            "kind": "pdf",
            "title": "CASTE & CATEGORY CERTIFICATE (SYNTHETIC EVAL 06)",
            "lines": [
                "Applicant Full Name: Kavya Lakshmi Narayanan",
                "Social Category: ST",
                "Course: B.Tech Electrical Engineering",
                "Date of Issue: 2025-12-04",
                "Issuing Authority: District Collectorate, Coimbatore",
            ],
            "ground_truth": {
                "full_name": "Kavya Lakshmi Narayanan",
                "annual_income": None,
                "category": "ST",
                "marks_percentage": None,
                "course": "B.Tech Electrical Engineering",
                "issue_date": "2025-12-04",
                "issuing_authority": "District Collectorate, Coimbatore",
            },
        },
    ]

    manifest = []
    for case in cases:
        out_path = EVAL_DIR / case["filename"]
        if case["kind"] == "pdf":
            _write_certificate_pdf(out_path, case["title"], case["lines"])
        else:
            _write_certificate_image(out_path, case["title"], case["lines"])
        manifest.append(
            {
                "id": case["id"],
                "filename": case["filename"],
                "doc_type": case["doc_type"],
                "ground_truth": case["ground_truth"],
            }
        )

    gt_path = EVAL_DIR / "ground_truth.json"
    gt_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return gt_path


def main() -> None:
    samples = generate_samples()
    gt_path = generate_eval_dataset()
    print(f"Generated {len(samples)} sample documents in {SAMPLES_DIR}")
    print(f"Generated evaluation manifest at {gt_path}")


if __name__ == "__main__":
    main()
