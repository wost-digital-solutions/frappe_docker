"""Extraction templates.

Each template bundles everything needed for both extraction modes:
  - `prompt_description` + `examples` -> used to drive LangExtract in LLM mode.
  - `demo_patterns` -> regex-based heuristics so the product works end-to-end
    with ZERO configuration (no API key, no external calls) for demos & the
    Free tier's offline fallback.

The example/prompt structure mirrors LangExtract's few-shot format so switching
to real LLM extraction is a drop-in.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class ExampleExtraction:
    extraction_class: str
    extraction_text: str
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass
class Example:
    text: str
    extractions: List[ExampleExtraction]


@dataclass
class Template:
    key: str
    name: str
    icon: str            # emoji, used in UI cards
    description: str
    prompt_description: str
    fields: List[str]                       # column order for tables
    examples: List[Example]
    # (extraction_class, regex, flags) — first capturing group is the value.
    demo_patterns: List[Tuple[str, str, int]] = field(default_factory=list)


import re  # noqa: E402

_I = re.IGNORECASE
_M = re.MULTILINE


TEMPLATES: Dict[str, Template] = {
    "invoice": Template(
        key="invoice",
        name="Invoices & Receipts",
        icon="🧾",
        description="Pull invoice numbers, dates, totals, tax, vendor and line items from any invoice or receipt.",
        prompt_description=(
            "Extract structured invoice fields. Use the exact text from the document. "
            "Do not paraphrase. Capture invoice_number, invoice_date, due_date, vendor, "
            "customer, subtotal, tax, total, and each line_item with its amount."
        ),
        fields=["invoice_number", "invoice_date", "due_date", "vendor", "total", "tax", "line_item"],
        examples=[
            Example(
                text="Invoice #INV-2045\nDate: 2024-03-14\nAcme Corp\nConsulting services  $1,200.00\nTax (10%)  $120.00\nTotal Due: $1,320.00",
                extractions=[
                    ExampleExtraction("invoice_number", "INV-2045"),
                    ExampleExtraction("invoice_date", "2024-03-14"),
                    ExampleExtraction("vendor", "Acme Corp"),
                    ExampleExtraction("line_item", "Consulting services", {"amount": "$1,200.00"}),
                    ExampleExtraction("tax", "$120.00"),
                    ExampleExtraction("total", "$1,320.00"),
                ],
            )
        ],
        demo_patterns=[
            ("invoice_number", r"(?:invoice|inv)(?:\s*(?:no\.?|number|#))?[\s#:_-]*([A-Z]{0,5}[-/]?\d[\dA-Z\-/]*)", _I),
            ("invoice_date", r"invoice\s*date[\s:]*([0-9]{1,4}[-/][0-9]{1,2}[-/][0-9]{1,4})", _I),
            ("due_date", r"due\s*date[\s:]*([0-9]{1,4}[-/][0-9]{1,2}[-/][0-9]{1,4})", _I),
            ("total", r"\btotal\s*(?:due|amount)?[\s:]*([$€£]\s?[0-9][0-9.,]*)", _I),
            ("subtotal", r"sub\s*total[\s:]*([$€£]\s?[0-9][0-9.,]*)", _I),
            ("tax", r"(?:^|\n)\s*(?:tax|vat|iva)\b[^$€£\n]*([$€£]\s?[0-9][0-9.,]*)", _I),
        ],
    ),
    "contract": Template(
        key="contract",
        name="Contracts & Agreements",
        icon="📜",
        description="Extract parties, effective dates, term, governing law, payment and termination clauses — each cited to its clause.",
        prompt_description=(
            "Extract key legal terms from this contract. Use exact text spans. Capture the "
            "parties, effective_date, term/duration, governing_law, payment_terms, "
            "termination clause, and any liability or confidentiality clauses. Add an "
            "attribute noting the clause or section where each was found when possible."
        ),
        fields=["party", "effective_date", "term", "governing_law", "payment_terms", "termination"],
        examples=[
            Example(
                text="This Agreement is entered into as of January 1, 2024 by and between Alpha LLC (\"Provider\") and Beta Inc (\"Client\"). This Agreement shall remain in effect for twelve (12) months. This Agreement shall be governed by the laws of the State of Delaware.",
                extractions=[
                    ExampleExtraction("effective_date", "January 1, 2024"),
                    ExampleExtraction("party", "Alpha LLC", {"role": "Provider"}),
                    ExampleExtraction("party", "Beta Inc", {"role": "Client"}),
                    ExampleExtraction("term", "twelve (12) months"),
                    ExampleExtraction("governing_law", "laws of the State of Delaware"),
                ],
            )
        ],
        demo_patterns=[
            ("effective_date", r"(?:as of|effective\s*(?:date|as of)?)[\s:]*((?:[A-Z][a-z]+ [0-9]{1,2},? [0-9]{4})|[0-9]{1,4}[-/][0-9]{1,2}[-/][0-9]{1,4})", _I),
            ("governing_law", r"governed by (?:the )?(laws of [^.\n]{3,60})", _I),
            ("term", r"(?:remain in effect for|term of|period of)\s+([^.\n]{3,50})", _I),
            ("party", r"\b((?:[A-Z][A-Za-z&.]+ ){1,4}(?:LLC|Inc\.?|Ltd\.?|GmbH|Corp\.?|Company|S\.A\.|Lda))", 0),
            ("payment_terms", r"(net\s*[0-9]{1,3}\s*days)", _I),
            ("termination", r"(?:may (?:be )?terminat\w+[^.\n]{3,80})", _I),
        ],
    ),
    "resume": Template(
        key="resume",
        name="Resumes / CVs",
        icon="👤",
        description="Turn a stack of CVs into a structured candidate table: name, email, phone, skills, titles and education.",
        prompt_description=(
            "Extract candidate information from this resume/CV. Use exact text. Capture "
            "candidate_name, email, phone, current_title, years_experience, skill (one per "
            "skill), company, and education/degree. Do not invent information."
        ),
        fields=["candidate_name", "email", "phone", "current_title", "skill", "education"],
        examples=[
            Example(
                text="Jane Doe\nSenior Data Engineer\njane.doe@email.com | +1 415 555 0100\nSkills: Python, SQL, Airflow, AWS\nEducation: B.Sc. Computer Science, MIT",
                extractions=[
                    ExampleExtraction("candidate_name", "Jane Doe"),
                    ExampleExtraction("current_title", "Senior Data Engineer"),
                    ExampleExtraction("email", "jane.doe@email.com"),
                    ExampleExtraction("phone", "+1 415 555 0100"),
                    ExampleExtraction("skill", "Python"),
                    ExampleExtraction("skill", "SQL"),
                    ExampleExtraction("education", "B.Sc. Computer Science, MIT"),
                ],
            )
        ],
        demo_patterns=[
            ("email", r"([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})", 0),
            ("phone", r"(\+?\d[\d\s().\-]{7,}\d)", 0),
            ("education", r"(?:B\.?Sc|M\.?Sc|Ph\.?D|Bachelor|Master|MBA|B\.?A\.?|M\.?A\.?)[^.\n]{0,60}", _I),
        ],
    ),
    "research": Template(
        key="research",
        name="Research Papers",
        icon="🔬",
        description="Extract findings, methods, datasets, metrics and limitations from papers — grounded to the sentence.",
        prompt_description=(
            "Extract structured information from this research paper or abstract. Use exact "
            "text spans. Capture the main finding, method, dataset, metric (with its value), "
            "sample_size, and limitation statements."
        ),
        fields=["finding", "method", "dataset", "metric", "sample_size", "limitation"],
        examples=[
            Example(
                text="We fine-tuned a transformer on the SQuAD dataset (n=100,000) and achieved an F1 score of 89.2, outperforming the baseline. A limitation is the reliance on English-only data.",
                extractions=[
                    ExampleExtraction("method", "fine-tuned a transformer"),
                    ExampleExtraction("dataset", "SQuAD dataset"),
                    ExampleExtraction("sample_size", "n=100,000"),
                    ExampleExtraction("metric", "F1 score of 89.2"),
                    ExampleExtraction("limitation", "reliance on English-only data"),
                ],
            )
        ],
        demo_patterns=[
            ("metric", r"((?:F1|accuracy|precision|recall|AUC|BLEU|score)\s*(?:score)?\s*of?\s*[0-9]{1,3}(?:\.[0-9]+)?%?)", _I),
            ("sample_size", r"(n\s*=\s*[0-9,]+)", _I),
            ("dataset", r"([A-Z][A-Za-z0-9\-]+ (?:dataset|corpus|benchmark))", 0),
            ("limitation", r"(?:limitation[s]? (?:is|are|include)[^.\n]{5,120})", _I),
        ],
    ),
    "clinical": Template(
        key="clinical",
        name="Clinical Notes",
        icon="🩺",
        description="Extract medications, dosages, diagnoses and vitals from clinical notes — every value grounded for audit.",
        prompt_description=(
            "Extract clinical entities from this note. Use exact text spans, in order of "
            "appearance. Capture medication (with dosage and frequency attributes), "
            "diagnosis, symptom, and vital_sign. Do not paraphrase or infer values that "
            "are not present."
        ),
        fields=["medication", "diagnosis", "symptom", "vital_sign"],
        examples=[
            Example(
                text="Patient presents with hypertension. Started on Lisinopril 10mg once daily. BP 150/95. Reports occasional headaches.",
                extractions=[
                    ExampleExtraction("diagnosis", "hypertension"),
                    ExampleExtraction("medication", "Lisinopril", {"dosage": "10mg", "frequency": "once daily"}),
                    ExampleExtraction("vital_sign", "BP 150/95"),
                    ExampleExtraction("symptom", "headaches"),
                ],
            )
        ],
        demo_patterns=[
            ("medication", r"([A-Z][a-z]{3,}(?:in|ol|ide|pril|statin|mycin|azole|cillin))\b", 0),
            ("vital_sign", r"((?:BP|HR|SpO2|Temp|RR)\s*[:=]?\s*[0-9][0-9/.\s]*)", _I),
            ("dosage", r"([0-9]{1,4}\s?(?:mg|ml|mcg|g|units?))", _I),
        ],
    ),
    "custom": Template(
        key="custom",
        name="Custom fields",
        icon="✨",
        description="Type the fields you want (e.g. \"policy number, claimant, incident date\") and extract them from any document.",
        prompt_description=(
            "Extract the following fields from the document using exact text spans. "
            "Do not paraphrase or invent values. If a field is not present, omit it."
        ),
        fields=[],
        examples=[],
        demo_patterns=[],
    ),
}

TEMPLATE_ORDER = ["invoice", "contract", "resume", "research", "clinical", "custom"]


def get_template(key: str) -> Template:
    return TEMPLATES.get(key, TEMPLATES["custom"])


def public_catalog() -> List[dict]:
    """Serializable catalog for the frontend (no regex internals)."""
    return [
        {
            "key": t.key,
            "name": t.name,
            "icon": t.icon,
            "description": t.description,
            "fields": t.fields,
        }
        for k in TEMPLATE_ORDER
        for t in [TEMPLATES[k]]
    ]
