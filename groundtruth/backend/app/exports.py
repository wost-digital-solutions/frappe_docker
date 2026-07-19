"""Turn extraction results into CSV / JSON exports."""
from __future__ import annotations

import csv
import io
import json
from typing import Dict, List


WATERMARK = "Exported with Groundtruth (Free plan) — groundtruth.app"


def to_json(job: Dict, watermark: bool) -> str:
    payload = {
        "source": job.get("source_name"),
        "template": job.get("template"),
        "mode": job.get("mode"),
        "extractions": [
            {
                "field": e["extraction_class"],
                "value": e["extraction_text"],
                "attributes": e.get("attributes", {}),
                "source_span": [e.get("start"), e.get("end")],
            }
            for e in job.get("extractions", [])
        ],
    }
    if watermark:
        payload["_note"] = WATERMARK
    return json.dumps(payload, indent=2, ensure_ascii=False)


def to_csv(job: Dict, watermark: bool) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["field", "value", "attributes", "source_start", "source_end"])
    for e in job.get("extractions", []):
        attrs = json.dumps(e.get("attributes", {}), ensure_ascii=False) if e.get("attributes") else ""
        writer.writerow([e["extraction_class"], e["extraction_text"], attrs, e.get("start"), e.get("end")])
    if watermark:
        writer.writerow([])
        writer.writerow([WATERMARK])
    return buf.getvalue()


def to_table(extractions: List[Dict]) -> Dict:
    """Group extractions by field for a compact table view in the UI."""
    grouped: Dict[str, List[Dict]] = {}
    for e in extractions:
        grouped.setdefault(e["extraction_class"], []).append(
            {"value": e["extraction_text"], "attributes": e.get("attributes", {})}
        )
    return grouped
