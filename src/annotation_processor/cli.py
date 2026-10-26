"""Command-line interface for standalone annotation processing."""

import argparse
import csv
import json
import math
from pathlib import Path

from .dataset import load_annotations
from .validation import validate_annotations


def main() -> None:
    parser = argparse.ArgumentParser(prog="annotation-processor", description="Validate, summarize, or export AURA annotation files.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "report", "export"):
        sub = subparsers.add_parser(command)
        sub.add_argument("input", type=Path)
        sub.add_argument("--format", choices=("csv", "json"))
        if command != "validate":
            sub.add_argument("--output", type=Path, required=True)
        if command == "export":
            sub.add_argument("--output-format", choices=("csv", "json"), default="json")
    args = parser.parse_args()
    try:
        records, parse_issues = load_annotations(args.input, args.format)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    issues = parse_issues + validate_annotations(records)
    if args.command == "validate":
        print(json.dumps({"record_count": len(records), "issues": issues}, indent=2))
        raise SystemExit(1 if any(issue["severity"] == "error" for issue in issues) else 0)
    if args.command == "report":
        def finite(value):
            try:
                result = float(value)
                return result if math.isfinite(result) else None
            except (TypeError, ValueError):
                return None

        valid_durations = []
        invalid_rows = {issue.get("source_row") for issue in issues if issue.get("severity") == "error" and issue.get("source_row") is not None}
        global_error = any(issue.get("severity") == "error" and issue.get("source_row") is None for issue in issues)
        for row in records:
            start, end = finite(row.get("start_time")), finite(row.get("end_time"))
            source_row = row.get("_source_row")
            if start is not None and end is not None and start >= 0 and end > start and source_row not in invalid_rows and not global_error:
                valid_durations.append(end - start)
        report = {"record_count": len(records), "unique_videos": len({row.get("video_id") for row in records if row.get("video_id")}), "unique_labels": len({row.get("action_label") for row in records if row.get("action_label")}), "counts_by_label": _counts(records, "action_label"), "counts_by_source": _counts(records, "source"), "valid_record_count": len(valid_durations), "valid_record_percentage": round(len(valid_durations) * 100 / len(records), 2) if records else None, "valid_duration_seconds": {"min": min(valid_durations), "mean": sum(valid_durations) / len(valid_durations), "max": max(valid_durations)} if valid_durations else None, "validation_issues": issues}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output_format == "json":
        args.output.write_text(json.dumps({"schema_version": "1.0", "annotations": records}, indent=2), encoding="utf-8")
    else:
        fields = ("video_id", "start_time", "end_time", "action_label", "object_label", "actor_id", "confidence", "notes")
        with args.output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)


def _counts(records: list[dict], field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in records:
        value = row.get(field) or "unspecified"
        result[value] = result.get(value, 0) + 1
    return result


if __name__ == "__main__":
    main()
