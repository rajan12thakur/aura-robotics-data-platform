"""Deterministic annotation validation and overlap analysis."""

import math
from typing import Any, Iterable

ACTION_LABELS = ("approach", "reach", "grasp", "lift", "move", "place", "release", "withdraw", "inspect", "other")


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def validate_annotations(records: Iterable[dict[str, Any]], *, durations: dict[str, float | None] | None = None, known_videos: set[str] | None = None) -> list[dict[str, Any]]:
    rows = list(records)
    issues: list[dict[str, Any]] = []
    if not rows:
        issues.append(_issue("EMPTY_DATASET", "error", "Dataset contains no annotations."))
        return issues
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        record_id = row.get("id")
        source_row = row.get("_source_row", index + 1)
        for field in ("video_id", "start_time", "end_time", "action_label"):
            if row.get(field) is None or str(row.get(field)).strip() == "":
                issues.append(_issue("MISSING_REQUIRED_FIELD", "error", f"Required field '{field}' is missing.", record_id, source_row, field))
        video_id = str(row.get("video_id") or "")
        start, end = _number(row.get("start_time")), _number(row.get("end_time"))
        label = str(row.get("action_label") or "").strip().lower()
        if row.get("start_time") is not None and start is None:
            issues.append(_issue("INVALID_START_TIME", "error", "Start time must be a finite number of seconds.", record_id, source_row, "start_time"))
        if row.get("end_time") is not None and end is None:
            issues.append(_issue("INVALID_END_TIME", "error", "End time must be a finite number of seconds.", record_id, source_row, "end_time"))
        if start is not None and start < 0:
            issues.append(_issue("NEGATIVE_START_TIME", "error", "Start time cannot be negative.", record_id, source_row, "start_time"))
        if start is not None and end is not None and end <= start:
            issues.append(_issue("NON_POSITIVE_INTERVAL", "error", "End time must be greater than start time.", record_id, source_row, "end_time"))
        duration = (durations or {}).get(video_id)
        if start is not None and end is not None and duration is not None and end > duration + 0.05:
            issues.append(_issue("END_EXCEEDS_VIDEO_DURATION", "error", f"End time exceeds known video duration ({duration:.3f}s).", record_id, source_row, "end_time"))
        if row.get("action_label") and label not in ACTION_LABELS:
            issues.append(_issue("UNKNOWN_ACTION_LABEL", "error", f"Action label '{label}' is not in the AURA vocabulary.", record_id, source_row, "action_label"))
        confidence_value = row.get("confidence")
        if confidence_value not in (None, ""):
            confidence = _number(confidence_value)
            if confidence is None or not 0 <= confidence <= 1:
                issues.append(_issue("INVALID_CONFIDENCE", "error", "Confidence must be a finite number between 0 and 1.", record_id, source_row, "confidence"))
        if known_videos is not None and video_id not in known_videos:
            issues.append(_issue("UNKNOWN_VIDEO_REFERENCE", "error", f"Video '{video_id}' is not registered in this project.", record_id, source_row, "video_id"))
        normalized.append({"id": record_id, "source_row": source_row, "video_id": video_id, "start": start, "end": end, "label": label, "object": str(row.get("object_label") or "").strip().lower(), "actor": str(row.get("actor_id") or "").strip().lower()})
    duplicate_keys: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in normalized:
        key = (row["video_id"].strip().lower(), row["start"], row["end"], row["label"], row["object"], row["actor"])
        if row["start"] is None or row["end"] is None or not row["label"]:
            continue
        if key in duplicate_keys:
            prior = duplicate_keys[key]
            issues.append(_issue("DUPLICATE_ANNOTATION", "error", "Record duplicates another annotation by video, interval, label, object, and actor.", row["id"], row["source_row"], references=[prior["id"] or f"row:{prior['source_row']}"]))
        else:
            duplicate_keys[key] = row
    by_video: dict[str, list[dict[str, Any]]] = {}
    for row in normalized:
        if row["start"] is not None and row["end"] is not None and row["end"] > row["start"] and row["start"] >= 0:
            by_video.setdefault(row["video_id"], []).append(row)
    for video_id, video_rows in by_video.items():
        video_rows.sort(key=lambda item: item["start"])
        active: list[dict[str, Any]] = []
        for row in video_rows:
            active = [item for item in active if item["end"] > row["start"]]
            for prior in active:
                issues.append(_issue("OVERLAPPING_INTERVAL", "warning", f"Interval overlaps record {prior['id'] or 'row:' + str(prior['source_row'])} on video '{video_id}'.", row["id"], row["source_row"], references=[prior["id"] or f"row:{prior['source_row']}"]))
            active.append(row)
    if durations is not None:
        checked = {row["video_id"] for row in normalized if row["video_id"] in durations and durations[row["video_id"]] is None}
        for video_id in checked:
            issues.append(_issue("VIDEO_DURATION_UNAVAILABLE", "info", f"Duration is unavailable for video '{video_id}'; boundary checks could not be performed.", field="end_time"))
    return issues


def _issue(code: str, severity: str, message: str, record_id: str | None = None, source_row: int | None = None, field: str | None = None, references: list[str] | None = None) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "record_id": record_id, "source_row": source_row, "field": field, "suggested_action": "Review the source record and correct it if appropriate.", "policy_reference": "annotation_policy_v1.md", "related_records": references or []}
