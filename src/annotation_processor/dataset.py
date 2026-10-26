"""CSV/JSON dataset loading with explicit parse errors."""

import csv
import json
from pathlib import Path
from typing import Any, TextIO

CANONICAL_COLUMNS = (
    "video_id", "start_time", "end_time", "action_label",
    "object_label", "actor_id", "confidence", "notes",
)
REQUIRED_COLUMNS = ("video_id", "start_time", "end_time", "action_label")


def load_annotations(source: str | Path | TextIO, input_format: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    path = Path(source) if isinstance(source, (str, Path)) else None
    kind = (input_format or (path.suffix.lstrip(".") if path else "csv")).lower()
    if path is None:
        text = source.read()
    else:
        text = path.read_text(encoding="utf-8-sig")
    if kind == "csv":
        return _load_csv(text)
    if kind == "json":
        return _load_json(text)
    raise ValueError("Format must be csv or json.")


def _load_csv(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        return [], [{"code": "EMPTY_DATASET", "severity": "error", "message": "CSV has no header row.", "source_row": 1}]
    normalized = [name.strip() if name else "" for name in reader.fieldnames]
    missing = sorted(set(REQUIRED_COLUMNS) - set(normalized))
    issues = []
    if missing:
        issues.append({"code": "MISSING_REQUIRED_FIELD", "severity": "error", "message": f"Missing CSV columns: {', '.join(missing)}.", "field": ", ".join(missing), "source_row": 1})
    unknown = sorted(set(normalized) - set(CANONICAL_COLUMNS))
    if unknown:
        issues.append({"code": "UNKNOWN_COLUMNS", "severity": "warning", "message": f"Unknown columns: {', '.join(unknown)}.", "field": ", ".join(unknown), "source_row": 1})
    records = []
    for row_number, row in enumerate(reader, start=2):
        if None in row:
            issues.append({"code": "MALFORMED_CSV_ROW", "severity": "error", "message": "Row contains more values than the header.", "source_row": row_number})
        record = {str(key).strip(): (value.strip() if isinstance(value, str) and value.strip() else None) for key, value in row.items() if key is not None}
        record["_source_row"] = row_number
        records.append(record)
    if not records and not issues:
        issues.append({"code": "EMPTY_DATASET", "severity": "error", "message": "CSV contains a header but no annotation rows.", "source_row": 1})
    return records, issues


def _load_json(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [{"code": "MALFORMED_JSON", "severity": "error", "message": f"Invalid JSON at line {exc.lineno}, column {exc.colno}.", "source_row": exc.lineno}]
    if isinstance(data, dict):
        data = data.get("annotations")
    if not isinstance(data, list):
        return [], [{"code": "MALFORMED_JSON", "severity": "error", "message": "JSON must be an array or an object with an annotations array."}]
    records, issues = [], []
    allowed_keys = set(CANONICAL_COLUMNS) | {"id", "annotation_id", "source", "status", "revision", "project_id", "created_by", "updated_by", "created_at", "updated_at"}
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            issues.append({"code": "MALFORMED_JSON", "severity": "error", "message": "Annotation must be a JSON object.", "source_row": index + 1})
            continue
        unknown = sorted(set(item) - allowed_keys)
        if unknown:
            issues.append({"code": "UNKNOWN_COLUMNS", "severity": "warning", "message": f"Unknown annotation fields: {', '.join(unknown)}.", "field": ", ".join(unknown), "source_row": index + 1})
        record = dict(item)
        record["_source_row"] = index + 1
        records.append(record)
    if not records and not issues:
        issues.append({"code": "EMPTY_DATASET", "severity": "error", "message": "JSON annotation list is empty."})
    return records, issues
