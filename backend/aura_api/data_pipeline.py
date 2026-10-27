"""Reproducible local Bronze/Silver/Gold processing for AURA annotations."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from django.db import transaction

from . import models
from .config import PIPELINE_DIR

SCHEMA_VERSION = "aura-medallion-v1"
MAX_PIPELINE_ANNOTATIONS = 100_000
ARTIFACT_NAMES = {
    "bronze.json", "silver.json", "silver.csv", "gold.json", "quarantine.json",
}
SILVER_FIELDS = (
    "annotation_id",
    "project_id",
    "video_id",
    "start_seconds",
    "end_seconds",
    "duration_seconds",
    "action_label",
    "object_label",
    "annotator_id",
    "confidence",
    "review_status",
    "source",
    "revision",
    "created_at",
)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _csv_content(rows: list[dict[str, object]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=SILVER_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _source_snapshot(project: models.Project) -> dict[str, object]:
    annotation_query = project.annotations.filter(archived_at__isnull=True)
    if annotation_query.count() > MAX_PIPELINE_ANNOTATIONS:
        raise ValueError(
            f"Pipeline input exceeds the {MAX_PIPELINE_ANNOTATIONS} annotation limit."
        )
    videos = list(
        project.videos.order_by("id").values(
            "id", "status", "duration_seconds", "width", "height", "fps",
        )
    )
    annotations = list(
        annotation_query
        .order_by("video_id", "start_time", "id")
        .values(
            "id", "project_id", "video_id", "start_time", "end_time",
            "action_label", "object_label", "actor_id", "confidence",
            "source", "status", "revision", "created_at",
        )
    )
    for row in annotations:
        if row["created_at"] is not None:
            row["created_at"] = row["created_at"].astimezone(timezone.utc).isoformat()
    return {
        "project": {
            "id": project.id,
            "task_type": project.task_type,
            "status": project.status,
            "annotation_policy_version": project.annotation_policy_version,
        },
        "videos": videos,
        "annotations": annotations,
    }


def _normalize(
    project_id: str,
    snapshot: dict[str, object],
    valid_videos: dict[str, dict[str, object]],
    active_labels: set[str],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    accepted: list[dict[str, object]] = []
    quarantined: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    video_ids = set(valid_videos)

    for item in snapshot["annotations"]:
        reasons: list[str] = []
        video_id = item["video_id"]
        start = item["start_time"]
        end = item["end_time"]
        label = item["action_label"]
        if item["project_id"] != project_id:
            reasons.append("project_reference_mismatch")
        if video_id not in video_ids:
            reasons.append("missing_video_reference")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            reasons.append("invalid_timestamp_type")
        elif start < 0 or end <= start:
            reasons.append("invalid_interval")
        elif video_id in valid_videos:
            duration = valid_videos[video_id]["duration_seconds"]
            if duration is not None and end > duration:
                reasons.append("interval_exceeds_video_duration")
        if label not in active_labels:
            reasons.append("unknown_action_label")
        if item["status"] not in {"draft", "needs_review", "approved", "rejected"}:
            reasons.append("unknown_review_status")
        if reasons:
            quarantined.append({
                "annotation_id": item["id"],
                "video_id": video_id,
                "reasons": reasons,
            })
            continue

        identity = (
            video_id, float(start), float(end), label,
            item["object_label"] or "", item["actor_id"] or "",
        )
        if identity in seen:
            quarantined.append({
                "annotation_id": item["id"],
                "video_id": video_id,
                "reasons": ["duplicate_annotation"],
            })
            continue
        seen.add(identity)
        accepted.append({
            "annotation_id": item["id"],
            "project_id": project_id,
            "video_id": video_id,
            "start_seconds": float(start),
            "end_seconds": float(end),
            "duration_seconds": float(end) - float(start),
            "action_label": label,
            "object_label": item["object_label"] or "",
            "annotator_id": item["actor_id"] or "",
            "confidence": item["confidence"],
            "review_status": item["status"],
            "source": item["source"],
            "revision": item["revision"],
            "created_at": item["created_at"],
        })
    return accepted, quarantined


def _gold_metrics(rows: list[dict[str, object]], videos: list[dict[str, object]]) -> dict[str, object]:
    by_label: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_video: dict[str, int] = {}
    throughput_by_day: dict[str, int] = {}
    overlaps = 0
    for row in rows:
        label = str(row["action_label"])
        status = str(row["review_status"])
        video_id = str(row["video_id"])
        by_label[label] = by_label.get(label, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        by_video[video_id] = by_video.get(video_id, 0) + 1
        created_at = row["created_at"]
        if isinstance(created_at, str):
            day = created_at[:10]
            throughput_by_day[day] = throughput_by_day.get(day, 0) + 1

    intervals: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        intervals.setdefault(str(row["video_id"]), []).append(row)
    for video_rows in intervals.values():
        video_rows.sort(key=lambda row: (float(row["start_seconds"]), float(row["end_seconds"])))
        active_end = -1.0
        for row in video_rows:
            start = float(row["start_seconds"])
            end = float(row["end_seconds"])
            if start < active_end:
                overlaps += 1
            active_end = max(active_end, end)

    approved = by_status.get("approved", 0)
    return {
        "annotation_count": len(rows),
        "video_count": len(videos),
        "class_balance": dict(sorted(by_label.items())),
        "review_status_counts": dict(sorted(by_status.items())),
        "annotations_per_video": dict(sorted(by_video.items())),
        "annotation_throughput_by_day": dict(sorted(throughput_by_day.items())),
        "overlapping_intervals": overlaps,
        "dataset_export_ready": bool(rows) and approved == len(rows) and overlaps == 0,
    }


def run_pipeline(project_id: str) -> dict[str, object]:
    started = time.monotonic()
    with transaction.atomic():
        project = models.Project.objects.get(pk=project_id)
        snapshot = _source_snapshot(project)
        active_labels = set(models.OntologyLabel.objects.filter(
            version=project.annotation_policy_version, active=True,
        ).values_list("code", flat=True))

    raw_bytes = _canonical_json(snapshot)
    input_hash = _sha256(raw_bytes)
    batch_id = hashlib.sha256(
        f"{project_id}:{SCHEMA_VERSION}:{input_hash}".encode("utf-8"),
    ).hexdigest()[:24]
    pipeline_root = Path(PIPELINE_DIR).resolve()
    project_dir = (pipeline_root / project_id).resolve()
    if pipeline_root not in project_dir.parents:
        raise ValueError("The project ID does not resolve under the configured pipeline directory.")
    batch_dir = (project_dir / batch_id).resolve()
    if project_dir not in batch_dir.parents:
        raise ValueError("The pipeline batch does not resolve under its project directory.")
    manifest_path = batch_dir / "run.json"
    if manifest_path.is_file():
        prior_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if prior_manifest.get("status") == "succeeded":
            artifacts_valid = True
            hashes = prior_manifest.get("output_sha256", {})
            if set(hashes) != ARTIFACT_NAMES:
                artifacts_valid = False
            for name, expected_hash in hashes.items():
                if not artifacts_valid:
                    break
                artifact_path = (batch_dir / name).resolve()
                if batch_dir not in artifact_path.parents or not artifact_path.is_file():
                    artifacts_valid = False
                    break
                if _sha256(artifact_path.read_bytes()) != expected_hash:
                    artifacts_valid = False
                    break
            if artifacts_valid:
                return prior_manifest

    run_started = datetime.now(timezone.utc).isoformat()
    bronze = {
        "batch_id": batch_id,
        "ingested_at": run_started,
        "source": "aura_django_orm",
        "schema_version": SCHEMA_VERSION,
        "content_sha256": input_hash,
        "snapshot": snapshot,
    }
    valid_videos = {row["id"]: row for row in snapshot["videos"]}
    silver_rows, quarantined = _normalize(
        project_id, snapshot, valid_videos, active_labels,
    )
    silver_json = _canonical_json(silver_rows)
    silver_csv = _csv_content(silver_rows)
    gold = _gold_metrics(silver_rows, snapshot["videos"])
    gold_json = _canonical_json(gold)
    quarantine_json = _canonical_json(quarantined)
    bronze_json = _canonical_json(bronze)
    output_hashes = {
        "bronze.json": _sha256(bronze_json),
        "silver.json": _sha256(silver_json),
        "silver.csv": _sha256(silver_csv),
        "gold.json": _sha256(gold_json),
        "quarantine.json": _sha256(quarantine_json),
    }
    relative_root = Path(project_id) / batch_id
    try:
        for filename, payload in (
            ("bronze.json", bronze_json),
            ("silver.json", silver_json),
            ("silver.csv", silver_csv),
            ("gold.json", gold_json),
            ("quarantine.json", quarantine_json),
        ):
            _write_atomic(batch_dir / filename, payload)
        manifest = {
            "batch_id": batch_id,
            "project_id": project_id,
            "status": "succeeded",
            "schema_version": SCHEMA_VERSION,
            "source": "aura_django_orm",
            "input_sha256": input_hash,
            "input_counts": {
                "videos": len(snapshot["videos"]),
                "annotations": len(snapshot["annotations"]),
            },
            "output_counts": {
                "bronze": len(snapshot["annotations"]),
                "silver": len(silver_rows),
                "quarantined": len(quarantined),
            },
            "outputs": {
                name: (relative_root / name).as_posix()
                for name in output_hashes
            },
            "output_sha256": output_hashes,
            "gold": gold,
            "started_at": run_started,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "error_summary": "",
        }
        _write_atomic(manifest_path, _canonical_json(manifest))
        return manifest
    except Exception as exc:
        failed = {
            "batch_id": batch_id,
            "project_id": project_id,
            "status": "failed",
            "schema_version": SCHEMA_VERSION,
            "source": "aura_django_orm",
            "input_sha256": input_hash,
            "input_counts": {
                "videos": len(snapshot["videos"]),
                "annotations": len(snapshot["annotations"]),
            },
            "output_counts": {"bronze": 0, "silver": 0, "quarantined": 0},
            "outputs": {},
            "output_sha256": {},
            "gold": {},
            "started_at": run_started,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "error_summary": f"Pipeline output failed ({type(exc).__name__}).",
        }
        _write_atomic(manifest_path, _canonical_json(failed))
        raise


def list_pipeline_runs(project_id: str, limit: int = 20) -> list[dict[str, object]]:
    pipeline_root = Path(PIPELINE_DIR).resolve()
    root = (pipeline_root / project_id).resolve()
    if pipeline_root not in root.parents:
        return []
    if not root.is_dir():
        return []
    results = []
    candidates = [
        path for path in root.glob("*/run.json")
        if root in path.resolve().parents and path.is_file()
    ]
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        results.append(result)
        if len(results) >= limit:
            break
    return results
