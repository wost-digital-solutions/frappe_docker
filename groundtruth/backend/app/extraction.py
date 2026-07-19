"""Extraction engine.

Two modes, one interface:
  * LLM mode  — uses Google's LangExtract (Gemini / OpenAI / Ollama) when an API
                key is configured and the package is installed.
  * DEMO mode — a dependency-free heuristic extractor that still produces real
                character-grounded spans, so the whole product works out of the
                box with no keys and no network.

Both return the same shape:
    {
      "mode": "llm" | "demo",
      "model": "<id or 'demo-heuristic'>",
      "extractions": [
          {"extraction_class","extraction_text","attributes","start","end"}
      ],
    }
Every extraction carries character offsets (`start`,`end`) into the *source
text*, which is what powers the source-grounded highlighting.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from .config import settings
from .templates_lib import Template, get_template


# --------------------------------------------------------------------------- #
# PDF / file text extraction
# --------------------------------------------------------------------------- #
def extract_text_from_pdf(data: bytes) -> tuple[str, int]:
    """Return (text, page_count). Falls back gracefully if pypdf is missing."""
    try:
        from pypdf import PdfReader
        import io

        reader = PdfReader(io.BytesIO(data))
        pages = [(p.extract_text() or "") for p in reader.pages]
        return "\n\n".join(pages), len(reader.pages)
    except Exception:
        # Not a parseable PDF (or pypdf unavailable) — treat bytes as UTF-8 text.
        try:
            return data.decode("utf-8", errors="ignore"), 0
        except Exception:
            return "", 0


# --------------------------------------------------------------------------- #
# DEMO extractor — heuristic, grounded, zero-dependency
# --------------------------------------------------------------------------- #
def _demo_extract(text: str, template: Template, custom_fields: Optional[List[str]]) -> List[dict]:
    results: List[dict] = []
    seen: set = set()

    def add(cls: str, m: re.Match, group: int = 1):
        try:
            start, end = m.span(group)
        except (IndexError, re.error):
            start, end = m.span(0)
        value = text[start:end].strip()
        if not value:
            return
        key = (cls, start, end)
        if key in seen:
            return
        seen.add(key)
        results.append(
            {
                "extraction_class": cls,
                "extraction_text": value,
                "attributes": {},
                "start": start,
                "end": end,
            }
        )

    # Template regex patterns
    for cls, pattern, flags in template.demo_patterns:
        for m in re.finditer(pattern, text, flags):
            grp = 1 if m.re.groups >= 1 else 0
            add(cls, m, grp)

    # Custom fields: look for "field: value" or "field - value" patterns.
    if custom_fields:
        for raw in custom_fields:
            fieldname = raw.strip()
            if not fieldname:
                continue
            cls = re.sub(r"\s+", "_", fieldname.lower())
            # e.g. "Policy Number: ABC-123"  or  "Claimant  John Smith"
            esc = re.escape(fieldname)
            pat = rf"{esc}\s*[:\-–]\s*([^\n,;]{{2,80}})"
            for m in re.finditer(pat, text, re.IGNORECASE):
                add(cls, m, 1)

    results.sort(key=lambda r: r["start"])
    return results


# --------------------------------------------------------------------------- #
# LLM extractor — LangExtract
# --------------------------------------------------------------------------- #
def _resolve_char_interval(ex, text: str, extraction_text: str) -> tuple[int, int]:
    """Map a LangExtract extraction to character offsets in `text`."""
    ci = getattr(ex, "char_interval", None)
    if ci is not None:
        start = getattr(ci, "start_pos", None)
        end = getattr(ci, "end_pos", None)
        if isinstance(start, int) and isinstance(end, int) and end > start:
            return start, end
    # Fallback: locate the exact span in the source text.
    idx = text.find(extraction_text)
    if idx >= 0:
        return idx, idx + len(extraction_text)
    return -1, -1


def _llm_extract(text: str, template: Template, custom_fields: Optional[List[str]], model_id: str) -> List[dict]:
    import langextract as lx  # imported lazily; only needed in LLM mode

    prompt = template.prompt_description
    if template.key == "custom" and custom_fields:
        prompt = (
            template.prompt_description
            + " Fields to extract: "
            + ", ".join(f.strip() for f in custom_fields if f.strip())
            + "."
        )

    # Build LangExtract few-shot examples from our template definition.
    examples = []
    for ex in template.examples:
        examples.append(
            lx.data.ExampleData(
                text=ex.text,
                extractions=[
                    lx.data.Extraction(
                        extraction_class=e.extraction_class,
                        extraction_text=e.extraction_text,
                        attributes=e.attributes or {},
                    )
                    for e in ex.extractions
                ],
            )
        )

    api_key = settings.gemini_api_key or settings.openai_api_key or None
    result = lx.extract(
        text_or_documents=text,
        prompt_description=prompt,
        examples=examples,
        model_id=model_id,
        api_key=api_key,
        extraction_passes=1,
        max_workers=5,
    )

    out: List[dict] = []
    for ex in getattr(result, "extractions", []) or []:
        etext = getattr(ex, "extraction_text", "") or ""
        start, end = _resolve_char_interval(ex, text, etext)
        out.append(
            {
                "extraction_class": getattr(ex, "extraction_class", "entity"),
                "extraction_text": etext,
                "attributes": getattr(ex, "attributes", {}) or {},
                "start": start,
                "end": end,
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #
def run_extraction(
    text: str,
    template_key: str,
    custom_fields: Optional[List[str]] = None,
    model_id: Optional[str] = None,
) -> Dict:
    template = get_template(template_key)
    model = model_id or settings.default_model_id

    if settings.llm_enabled:
        try:
            extractions = _llm_extract(text, template, custom_fields, model)
            return {"mode": "llm", "model": model, "extractions": extractions}
        except Exception as exc:  # pragma: no cover - network/config failures
            # Never fail the request: fall back to the demo extractor and flag it.
            extractions = _demo_extract(text, template, custom_fields)
            return {
                "mode": "demo",
                "model": "demo-heuristic",
                "extractions": extractions,
                "warning": f"LLM extraction unavailable, used demo mode ({type(exc).__name__}).",
            }

    extractions = _demo_extract(text, template, custom_fields)
    return {"mode": "demo", "model": "demo-heuristic", "extractions": extractions}
