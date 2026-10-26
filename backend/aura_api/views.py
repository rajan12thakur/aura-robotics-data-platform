"""Django views implementing AURA's versioned JSON and media API."""

import csv
import hashlib
import importlib.util
import io
import json
import logging
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ObjectDoesNotExist
from django.middleware.csrf import get_token
from django.db import IntegrityError, connections, transaction
from django.db.models import Count, Max, Q
from django.http import FileResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from annotation_processor.dataset import load_annotations
from annotation_processor.validation import ACTION_LABELS, validate_annotations
from . import models
from .config import (
    APP_NAME, DEFAULT_REVIEWER, FRAME_SAMPLE_LIMIT, MAX_UPLOAD_MB, MEDIA_DIR,
    OUTPUT_DIR, VISION_ENABLED, VISION_MODEL, VISION_WEIGHTS_PATH,
)
from .exceptions import ApiError
from .rl import ACTION_NAMES, ENVIRONMENT_VERSION, GOAL_CELL, GRID_WIDTH, MAX_EPISODES, MAX_STEPS, OBJECT_CELL, START_CELL
from .rl_service import execute_experiment
from . import knowledge_service
from .config import RAG_MAX_PDF_MB
from .config import VECTOR_STORE_DIR

logger = logging.getLogger("aura.api")
POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "annotation_policy_v1.md"
API_ROOT = "/api/v1"
PUBLIC_ENDPOINTS = {"health", "readiness", "capabilities", "csrf_token", "auth_login", "api_index"}
ROLE_GROUPS = {
    "project_admin": {"Administrator", "Project Manager"},
    "annotation_write": {"Administrator", "Project Manager", "Annotator"},
    "review": {"Administrator", "Reviewer"},
    "export": {"Administrator", "Dataset Manager"},
    "quality": {"Administrator", "Project Manager", "Annotator", "Reviewer", "Dataset Manager"},
    "experiment": {"Administrator", "Project Manager", "ML Engineer"},
}


def _page(request, default_size=50):
    try:
        page = int(request.GET.get("page", "0"))
        size = int(request.GET.get("page_size", str(default_size)))
    except ValueError:
        raise ApiError(422, "INVALID_PAGINATION", "page and page_size must be integers.")
    if page < 0 or not 1 <= size <= 100:
        raise ApiError(422, "INVALID_PAGINATION", "page must be non-negative and page_size must be between 1 and 100.")
    return page, size


def _json(model):
    result = {}
    for field in model._meta.concrete_fields:
        value = getattr(model, field.attname)
        if isinstance(value, datetime):
            value = value.astimezone(timezone.utc).isoformat()
        result[field.attname] = value
    return result


def _error(error):
    return JsonResponse({"error": {"code": error.code, "message": error.message, "details": error.details}}, status=error.status)


def api(view):
    def wrapped(request, *args, **kwargs):
        if view.__name__ not in PUBLIC_ENDPOINTS and not request.user.is_authenticated:
            return _error(ApiError(401, "AUTHENTICATION_REQUIRED", "Sign in to access this AURA resource."))
        try:
            return view(request, *args, **kwargs)
        except ApiError as exc:
            response = _error(exc)
            response["X-Request-ID"] = getattr(request, "request_id", "")
            return response
        except json.JSONDecodeError:
            response = _error(ApiError(400, "INVALID_JSON", "Request body must contain valid JSON."))
            response["X-Request-ID"] = getattr(request, "request_id", "")
            return response
        except ObjectDoesNotExist:
            response = _error(ApiError(404, "RECORD_NOT_FOUND", "The requested record does not exist."))
            response["X-Request-ID"] = getattr(request, "request_id", "")
            return response
        except Exception:
            request_id = getattr(request, "request_id", "")
            logger.exception("Unhandled API error request_id=%s path=%s", request_id, request.path)
            response = _error(ApiError(500, "INTERNAL_ERROR", "The request could not be completed.", {"request_id": request_id}))
            response["X-Request-ID"] = request_id
            return response
    wrapped.__name__ = view.__name__
    return wrapped


def _require_role(request, role):
    if request.user.is_superuser:
        return
    groups = ROLE_GROUPS[role]
    if not request.user.groups.filter(name__in=groups).exists():
        raise ApiError(403, "PERMISSION_DENIED", "Your account does not have permission to perform this action.", {"required_role": sorted(groups)})


def _body(request):
    if not request.body:
        return {}
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ApiError(400, "INVALID_JSON", "Request body must contain valid JSON.")
    if not isinstance(data, dict):
        raise ApiError(400, "INVALID_REQUEST", "Request body must be a JSON object.")
    return data


def _required(data, name, max_length=None):
    value = data.get(name)
    if not isinstance(value, str) or not value.strip() or (max_length and len(value) > max_length):
        raise ApiError(422, "INVALID_FIELD", f"'{name}' is required and must be at most {max_length or 'the allowed'} characters.")
    return value.strip()


def _bounded(data, name, maximum, default=""):
    value = data.get(name, default)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum:
        raise ApiError(422, "INVALID_FIELD", f"'{name}' must be a string no longer than {maximum} characters.")
    return value


def _project(project_id):
    try:
        return models.Project.objects.get(pk=project_id)
    except models.Project.DoesNotExist:
        raise ApiError(404, "PROJECT_NOT_FOUND", "The requested project does not exist.")


def _video(video_id):
    try:
        return models.Video.objects.select_related("project").get(pk=video_id)
    except models.Video.DoesNotExist:
        raise ApiError(404, "VIDEO_NOT_FOUND", "The requested video does not exist.")


def _annotation(annotation_id):
    try:
        return models.Annotation.objects.select_related("project", "video").get(pk=annotation_id)
    except models.Annotation.DoesNotExist:
        raise ApiError(404, "ANNOTATION_NOT_FOUND", "The requested annotation does not exist.")


def _audit(project, event_type, summary, actor=DEFAULT_REVIEWER, **details):
    refs = {key: details.pop(key) for key in ("video_id", "annotation_id", "export_id") if key in details}
    models.AuditEvent.objects.create(
        project=project, event_type=event_type, summary=summary[:500], actor=actor,
        details_json=json.dumps(details, ensure_ascii=False), **refs,
    )


def _snapshot_annotation(row, actor, reason=""):
    snapshot = {key: getattr(row, key) for key in (
        "id", "project_id", "video_id", "start_time", "end_time",
        "action_label", "object_label", "actor_id", "confidence", "notes",
        "source", "status", "revision", "schema_version",
    ) if hasattr(row, key)}
    models.AnnotationRevision.objects.create(
        annotation=row, revision=row.revision, snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        actor=actor, reason=reason[:2000],
    )


def _annotation_rows(project_id, video_id=None):
    query = models.Annotation.objects.filter(project_id=project_id, archived_at__isnull=True).select_related("video")
    if video_id:
        query = query.filter(video_id=video_id)
    return list(query.order_by("video_id", "start_time", "id"))


def _record(row):
    return {
        "id": row.id, "video_id": row.video_id, "start_time": row.start_time,
        "end_time": row.end_time, "action_label": row.action_label,
        "object_label": row.object_label, "actor_id": row.actor_id,
        "confidence": row.confidence, "notes": row.notes, "source": row.source,
        "status": row.status, "revision": row.revision,
    }


def _validate(project, video_id=None, actor=DEFAULT_REVIEWER):
    videos = list(models.Video.objects.filter(project=project))
    if video_id:
        videos = [video for video in videos if video.id == video_id]
    rows = _annotation_rows(project.id, video_id)
    issues = validate_annotations(
        [_record(row) for row in rows],
        durations={video.id: video.duration_seconds for video in videos},
        known_videos={video.id for video in videos},
    )
    for row in rows:
        if row.video.project_id != project.id:
            issues.append({
                "code": "VIDEO_PROJECT_MISMATCH", "severity": "error",
                "message": "Annotation video belongs to a different project.",
                "record_id": row.id, "field": "video_id",
                "suggested_action": "Associate the annotation with a video from its project.",
                "policy_reference": "annotation_policy_v1.md", "related_records": [],
            })
    invalid_ids = {issue.get("record_id") for issue in issues if issue["severity"] == "error" and issue.get("record_id")}
    errors = sum(issue["severity"] == "error" for issue in issues)
    warnings = sum(issue["severity"] == "warning" for issue in issues)
    valid_count = max(0, len(rows) - len(invalid_ids))
    status = "failed" if errors else "passed_with_warnings" if warnings else "passed"
    with transaction.atomic():
        run = models.ValidationRun.objects.create(
            project=project, video_id=video_id, status=status, total_records=len(rows),
            valid_records=valid_count, error_count=errors, warning_count=warnings,
            issues_json=json.dumps(issues), actor=actor,
        )
        _audit(project, "validation.run", f"Validation {status}: {errors} errors, {warnings} warnings.", actor, video_id=video_id, run_id=run.id)
    return run


def _run(run):
    result = _json(run)
    result["issues"] = json.loads(run.issues_json)
    result.pop("issues_json", None)
    return result


def _quality(project):
    rows = _annotation_rows(project.id)
    latest = models.ValidationRun.objects.filter(project=project).order_by("-created_at").first()
    validation_is_current = bool(latest) and not project.annotations.filter(updated_at__gt=latest.created_at).exists()
    labels, sources, states = {}, {}, {}
    durations = []
    for row in rows:
        labels[row.action_label] = labels.get(row.action_label, 0) + 1
        sources[row.source] = sources.get(row.source, 0) + 1
        states[row.status] = states.get(row.status, 0) + 1
        if row.start_time >= 0 and row.end_time > row.start_time:
            durations.append(row.end_time - row.start_time)
    return {
        "project_id": project.id, "annotation_count": len(rows),
        "unique_videos": len({row.video_id for row in rows}),
        "unique_labels": len(labels), "counts_by_label": labels,
        "counts_by_source": sources, "counts_by_status": states,
        "valid_record_percentage": round(latest.valid_records * 100 / len(rows), 2) if validation_is_current and rows else None,
        "valid_percentage_definition": "latest validation run valid_records / total annotations * 100; null until validated or when empty",
        "duration_seconds": {"min": min(durations), "mean": sum(durations) / len(durations), "max": max(durations)} if durations else None,
        "latest_validation": {**_run(latest), "is_current": validation_is_current} if latest else None,
        "pending_review_count": sum(row.status in ("draft", "needs_review") for row in rows),
    }


def _video_json(video):
    result = _json(video)
    result.pop("storage_key", None)
    result["project_id"] = video.project_id
    result["managed"] = bool(video.storage_key)
    return result


def _policy_sections():
    if not POLICY_PATH.is_file():
        return []
    sections, title, lines = [], "Policy", []
    for line in POLICY_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if lines:
                sections.append((title, "\n".join(lines)))
            title, lines = line[3:], []
        else:
            lines.append(line)
    if lines:
        sections.append((title, "\n".join(lines)))
    return sections


def _policy_search(query, limit=5):
    terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    ranked = []
    for title, content in _policy_sections():
        score = len(terms & set(re.findall(r"[a-z0-9]+", (title + " " + content).lower())))
        if score:
            ranked.append((score, title, content))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [{"title": title, "source": "annotation_policy_v1.md", "policy_version": "1.0", "excerpt": content[:800]} for _, title, content in ranked[:max(1, min(limit, 10))]]


def _sample_frames(video):
    if not video.storage_key:
        raise ApiError(409, "VIDEO_PLAYBACK_UNAVAILABLE", "No managed video is available.")
    try:
        import cv2
    except ImportError:
        raise ApiError(503, "OPENCV_UNAVAILABLE", "Install optional OpenCV to extract frames.")
    path = (MEDIA_DIR / video.storage_key).resolve()
    if MEDIA_DIR not in path.parents or not path.is_file():
        raise ApiError(404, "VIDEO_FILE_UNAVAILABLE", "Managed video file is not available.")
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        raise ApiError(422, "VIDEO_DECODE_UNAVAILABLE", "OpenCV could not decode this video.")
    frames = []
    try:
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = capture.get(cv2.CAP_PROP_FPS) or 1
        sample_count = min(count, FRAME_SAMPLE_LIMIT)
        for index in range(sample_count):
            frame_index = round(index * max(0, count - 1) / max(1, sample_count - 1))
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if ok:
                frames.append({"timestamp_seconds": round(frame_index / fps, 3), "width": int(frame.shape[1]), "height": int(frame.shape[0])})
    finally:
        capture.release()
    return {"video_id": video.id, "sample_limit": FRAME_SAMPLE_LIMIT, "frames": frames, "note": "Only frame metadata is returned; previews are not stored."}


def _opencv_available():
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


@api
@require_http_methods(["GET"])
def health(request):
    return JsonResponse({"status": "ok", "app": APP_NAME, "time": datetime.now(timezone.utc).isoformat()})


@api
@require_http_methods(["GET"])
def csrf_token(request):
    return JsonResponse({"csrf_token": get_token(request)})


@api
@require_http_methods(["POST"])
def auth_login(request):
    data = _body(request)
    username = _required(data, "username", 150)
    password = data.get("password")
    if not isinstance(password, str) or not password:
        raise ApiError(400, "INVALID_CREDENTIALS", "Enter a username and password.")
    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_active:
        raise ApiError(401, "INVALID_CREDENTIALS", "Username or password is incorrect.")
    login(request, user)
    return JsonResponse({"authenticated": True, "user": _user_summary(user)})


@api
@require_http_methods(["POST"])
def auth_logout(request):
    logout(request)
    return JsonResponse({"authenticated": False})


@api
@require_http_methods(["GET"])
def auth_me(request):
    return JsonResponse({"authenticated": True, "user": _user_summary(request.user)})


def _user_summary(user):
    roles = ["Administrator"] if user.is_superuser else list(user.groups.order_by("name").values_list("name", flat=True))
    return {"id": user.pk, "username": user.get_username(), "roles": roles}


@api
@require_http_methods(["GET"])
def capabilities(request):
    embedding_path = os.getenv("AURA_EMBEDDING_MODEL_PATH", "").strip()
    embedding_configured = bool(
        embedding_path and Path(embedding_path).is_dir()
        and importlib.util.find_spec("sentence_transformers")
    )
    chroma_installed = importlib.util.find_spec("chromadb") is not None
    return JsonResponse({
        "database": "sqlite", "assistant": {"mode": "deterministic", "llm_provider_adapter": False},
        "vision": {"enabled": VISION_ENABLED, "detector_configured": bool(VISION_ENABLED and VISION_WEIGHTS_PATH and Path(VISION_WEIGHTS_PATH).is_file()), "detector_ready": False, "metadata_extraction": _opencv_available()},
        "rag": {
            "answer_mode": "deterministic_extractive",
            "retrieval_mode": "dense_vector" if embedding_configured and chroma_installed else "lexical_sqlite",
            "embedding_model": os.getenv("AURA_EMBEDDING_MODEL", "") if embedding_configured else None,
            "embedding_model_configured": embedding_configured,
            "chroma_installed": chroma_installed,
            "vector_store_path": str(VECTOR_STORE_DIR) if chroma_installed else None,
            "pdf_parser_installed": importlib.util.find_spec("pypdf") is not None,
            "ocr_configured": False,
            "external_llm_configured": False,
        },
        "upload_limit_mb": MAX_UPLOAD_MB, "rag_pdf_limit_mb": RAG_MAX_PDF_MB,
        "identity": "django_session_authentication",
    })


@api
@require_http_methods(["GET"])
def ontology_labels(request):
    version = request.GET.get("version", "1.0")
    labels = models.OntologyLabel.objects.filter(version=version, active=True).order_by("code")
    return JsonResponse({
        "version": version,
        "labels": [
            {"code": label.code, "description": label.description,
             "inclusion_rules": label.inclusion_rules, "exclusion_rules": label.exclusion_rules}
            for label in labels
        ],
    })


@api
@require_http_methods(["GET"])
def readiness(request):
    database = "ready"
    try:
        connection = connections["default"]
        connection.ensure_connection()
        if "aura_api_project" not in connection.introspection.table_names():
            database = "unmigrated"
    except Exception as exc:
        logger.error("Readiness database check failed request_id=%s error_type=%s", getattr(request, "request_id", ""), type(exc).__name__)
        database = "unavailable"
    media = MEDIA_DIR.is_dir() and os_access(MEDIA_DIR)
    output = (OUTPUT_DIR / "exports").is_dir() and os_access(OUTPUT_DIR / "exports")
    ready = database == "ready" and media and output
    return JsonResponse({
        "ready": ready,
        "checks": {"database": database, "media_directory": "writable" if media else "unavailable", "export_directory": "writable" if output else "unavailable"},
        "request_id": getattr(request, "request_id", ""),
    }, status=200 if ready else 503)


def os_access(path):
    return os.access(path, os.R_OK | os.W_OK)


@api
@require_http_methods(["GET", "POST"])
def projects(request):
    if request.method == "GET":
        result = []
        query = models.Project.objects.annotate(video_count=Count("videos", distinct=True), annotation_count=Count("annotations", distinct=True)).order_by("-created_at")
        page, page_size = _page(request)
        for project in query[page * page_size:(page + 1) * page_size]:
            item = _json(project)
            item.update(video_count=project.video_count, annotation_count=project.annotation_count)
            result.append(item)
        response = JsonResponse(result, safe=False)
        response["X-Total-Count"] = str(query.count())
        response["X-Page"] = str(page)
        response["X-Page-Size"] = str(page_size)
        return response
    _require_role(request, "project_admin")
    data = _body(request)
    project = models.Project.objects.create(
        name=_required(data, "name", 120),
        description=_bounded(data, "description", 4000),
        task_type=_bounded(data, "task_type", 80, "pick_and_place"),
    )
    _audit(project, "project.created", f"Created project '{project.name}'.", request.user.get_username())
    return JsonResponse(_json(project), status=201)


@api
@require_http_methods(["POST"])
def load_demo(request):
    _require_role(request, "project_admin")
    project, created = models.Project.objects.get_or_create(
        pk="synthetic-demo-project",
        defaults={"name": "Bottle Pick-and-Place Demonstration (Synthetic Demo)", "description": "Synthetic annotation fixture only. No real video or human-labeled data is included.", "task_type": "pick_and_place"},
    )
    video = None
    if created:
        video = models.Video.objects.create(
            id="demo-video-001", project=project, original_filename="synthetic-demo-video-unavailable.mp4",
            duration_seconds=6.6, source_notes="Synthetic demo record; this video does not exist.", status="unavailable",
        )
        rows = [(0, 1, "approach"), (1, 2.1, "reach"), (2.1, 2.8, "grasp"), (2.8, 3.6, "lift"), (3.6, 4.7, "move"), (4.7, 5.5, "place"), (5.5, 5.9, "release"), (5.9, 6.6, "withdraw")]
        models.Annotation.objects.bulk_create([
            models.Annotation(project=project, video=video, start_time=start, end_time=end, action_label=label, object_label="water_bottle", actor_id="human_1", notes="Synthetic demonstration record", source="synthetic_demo", status="draft")
            for start, end, label in rows
        ])
        _audit(project, "demo.loaded", "Loaded the explicitly requested synthetic demo fixture.", request.user.get_username())
    else:
        video = models.Video.objects.filter(project=project, pk="demo-video-001").first()
    return JsonResponse({"project": _json(project), "video": _json(video) if video else None, "created": created, "label": "Synthetic Demo"})


@api
@require_http_methods(["GET", "PATCH"])
def project_detail(request, project_id):
    project = _project(project_id)
    if request.method == "GET":
        return JsonResponse(_json(project))
    _require_role(request, "project_admin")
    data = _body(request)
    for key, limit in (("name", 120), ("description", 4000), ("task_type", 80)):
        if key in data:
            if key == "name":
                setattr(project, key, _required(data, key, limit))
            else:
                setattr(project, key, _bounded(data, key, limit))
    project.save()
    _audit(project, "project.updated", "Updated project details.", request.user.get_username())
    return JsonResponse(_json(project))


@api
@require_http_methods(["POST"])
def archive_project(request, project_id):
    _require_role(request, "project_admin")
    project = _project(project_id)
    project.status = "archived"
    project.save(update_fields=["status", "updated_at"])
    _audit(project, "project.archived", f"Archived project '{project.name}'.", request.user.get_username())
    return JsonResponse(_json(project))


@api
@require_http_methods(["GET", "POST"])
def project_videos(request, project_id):
    project = _project(project_id)
    if request.method == "POST":
        _require_role(request, "annotation_write")
        return upload_video(request, project_id)
    result = []
    query = project.videos.annotate(annotation_count=Count("annotations")).order_by("-created_at")
    page, page_size = _page(request)
    for video in query[page * page_size:(page + 1) * page_size]:
        item = _video_json(video)
        item["annotation_count"] = video.annotation_count
        result.append(item)
    response = JsonResponse(result, safe=False)
    response["X-Total-Count"] = str(query.count())
    response["X-Page"] = str(page)
    response["X-Page-Size"] = str(page_size)
    return response


@api
@require_http_methods(["POST"])
def register_video(request, project_id):
    _require_role(request, "annotation_write")
    project = _project(project_id)
    data = _body(request)
    filename = _required(data, "original_filename", 255)
    duration = data.get("duration_seconds")
    if duration is not None and (not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0):
        raise ApiError(422, "INVALID_DURATION", "duration_seconds must be a positive number.")
    dimensions = {}
    for field in ("width", "height"):
        value = data.get(field)
        if value is not None:
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ApiError(422, "INVALID_DIMENSION", f"{field} must be a positive integer.")
            dimensions[field] = value
    fps = data.get("fps")
    if fps is not None and (not isinstance(fps, (int, float)) or isinstance(fps, bool) or fps <= 0):
        raise ApiError(422, "INVALID_FPS", "fps must be a positive number.")
    video = models.Video.objects.create(
        project=project, original_filename=Path(filename).name, duration_seconds=duration,
        width=dimensions.get("width"), height=dimensions.get("height"), fps=fps,
        source_notes=_bounded(data, "source_notes", 2000),
        status="metadata_ready" if duration else "metadata_partial",
    )
    _audit(project, "video.registered", f"Registered metadata for '{video.original_filename}'.", request.user.get_username(), video_id=video.id)
    return JsonResponse(_video_json(video), status=201)


@api
@require_http_methods(["POST"])
def upload_video(request, project_id):
    _require_role(request, "annotation_write")
    project = _project(project_id)
    uploaded = request.FILES.get("file")
    if not uploaded:
        raise ApiError(400, "MISSING_UPLOAD", "Select a video file to upload.")
    filename = Path(uploaded.name).name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".mp4", ".mov", ".webm", ".mkv", ".avi"} or (uploaded.content_type and not uploaded.content_type.startswith("video/")):
        raise ApiError(415, "UNSUPPORTED_VIDEO_TYPE", "Upload a supported video file (MP4, MOV, WebM, MKV, AVI).")
    key = f"{uuid4().hex}{suffix}"
    path = (MEDIA_DIR / key).resolve()
    if MEDIA_DIR not in path.parents:
        raise ApiError(400, "INVALID_UPLOAD_PATH", "Upload path is invalid.")
    digest, size = hashlib.sha256(), 0
    try:
        with path.open("wb") as target:
            for chunk in uploaded.chunks():
                size += len(chunk)
                if size > MAX_UPLOAD_MB * 1024 * 1024:
                    raise ApiError(413, "UPLOAD_TOO_LARGE", f"Video exceeds the {MAX_UPLOAD_MB} MB limit.")
                digest.update(chunk)
                target.write(chunk)
        if size == 0:
            raise ApiError(400, "EMPTY_UPLOAD", "Uploaded video is empty.")
        metadata = {}
        if _opencv_available():
            import cv2
            cap = cv2.VideoCapture(str(path))
            try:
                if cap.isOpened():
                    fps = cap.get(cv2.CAP_PROP_FPS) or None
                    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    metadata = {"duration_seconds": frames / fps if fps and frames else None, "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None, "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None, "fps": fps}
            finally:
                cap.release()
        video = models.Video.objects.create(
            project=project, original_filename=filename, storage_key=key,
            mime_type=uploaded.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
            file_size_bytes=size, checksum_sha256=digest.hexdigest(),
            status="metadata_ready" if metadata.get("duration_seconds") else "metadata_partial", **metadata,
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    _audit(project, "video.uploaded", f"Uploaded '{filename}' ({size} bytes).", request.user.get_username(), video_id=video.id)
    return JsonResponse(_video_json(video), status=201)


@api
@require_http_methods(["GET"])
def video_detail(request, video_id):
    return JsonResponse(_video_json(_video(video_id)))


@api
@require_http_methods(["GET"])
def video_stream(request, video_id):
    video = _video(video_id)
    if not video.storage_key:
        raise ApiError(409, "VIDEO_PLAYBACK_UNAVAILABLE", "This metadata-only registration has no managed video file.")
    path = (MEDIA_DIR / video.storage_key).resolve()
    if MEDIA_DIR not in path.parents or not path.is_file():
        raise ApiError(404, "VIDEO_FILE_UNAVAILABLE", "The managed video file is not available.")
    return FileResponse(path.open("rb"), content_type=video.mime_type, filename=video.original_filename)


@api
@require_http_methods(["GET"])
def video_metadata(request, video_id):
    return JsonResponse(_video_json(_video(video_id)))


@api
@require_http_methods(["POST"])
def archive_video(request, video_id):
    _require_role(request, "annotation_write")
    video = _video(video_id)
    video.status = "archived"
    video.save(update_fields=["status"])
    _audit(video.project, "video.archived", f"Archived '{video.original_filename}'.", video_id=video.id)
    return JsonResponse(_video_json(video))


@api
@require_http_methods(["POST"])
def extract_frames(request, video_id):
    _require_role(request, "annotation_write")
    return JsonResponse(_sample_frames(_video(video_id)))


@api
@require_http_methods(["POST"])
def sample_frames(request, video_id):
    _require_role(request, "annotation_write")
    return JsonResponse(_sample_frames(_video(video_id)))


@api
@require_http_methods(["GET", "POST"])
def video_annotations(request, video_id):
    video = _video(video_id)
    if request.method == "GET":
        query = models.Annotation.objects.filter(project_id=video.project_id, video=video, archived_at__isnull=True).order_by("start_time", "id")
        page, page_size = _page(request)
        response = JsonResponse([_json(row) for row in query[page * page_size:(page + 1) * page_size]], safe=False)
        response["X-Total-Count"] = str(query.count())
        response["X-Page"] = str(page)
        response["X-Page-Size"] = str(page_size)
        return response
    _require_role(request, "annotation_write")
    data = _body(request)
    start, end = _finite_number(data.get("start_time"), "start_time"), _finite_number(data.get("end_time"), "end_time")
    if start < 0 or end <= start:
        raise ApiError(422, "INVALID_INTERVAL", "Use finite seconds with start >= 0 and end > start.")
    label = _required(data, "action_label", 80)
    source = data.get("source", "human")
    if source not in ("human", "imported", "model_suggestion", "synthetic_demo"):
        raise ApiError(422, "INVALID_ANNOTATION_SOURCE", "Annotation source is not allowed.")
    confidence = data.get("confidence")
    if confidence is not None and (not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1):
        raise ApiError(422, "INVALID_CONFIDENCE", "Confidence must be between 0 and 1.")
    if data.get("status", "draft") != "draft":
        raise ApiError(422, "REVIEW_REQUIRED", "New annotations always start as drafts; use the review endpoint for decisions.")
    if not models.OntologyLabel.objects.filter(version=video.project.annotation_policy_version, code=label, active=True).exists():
        raise ApiError(422, "UNKNOWN_ACTION_LABEL", f"Action label '{label}' is not active in ontology version {video.project.annotation_policy_version}.")
    with transaction.atomic():
        row = models.Annotation.objects.create(project=video.project, video=video, start_time=start, end_time=end, action_label=label, object_label=_bounded(data, "object_label", 120, None), actor_id=_bounded(data, "actor_id", 120, None), confidence=confidence, notes=_bounded(data, "notes", 4000, None), source=source, status="draft", created_by=request.user.get_username(), updated_by=request.user.get_username(), schema_version=video.project.annotation_policy_version)
        _snapshot_annotation(row, request.user.get_username())
        _audit(video.project, "annotation.created", f"Created '{label}' annotation.", request.user.get_username(), video_id=video.id, annotation_id=row.id)
    return JsonResponse(_json(row), status=201)


def _finite_number(value, field):
    import math
    if isinstance(value, bool):
        raise ApiError(422, "INVALID_NUMBER", f"{field} must be a finite number.")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ApiError(422, "INVALID_NUMBER", f"{field} must be a finite number.")
    if not math.isfinite(result):
        raise ApiError(422, "INVALID_NUMBER", f"{field} must be a finite number.")
    return result


@api
@require_http_methods(["GET", "PATCH", "DELETE"])
def annotation_detail(request, annotation_id):
    row = _annotation(annotation_id)
    if request.method == "GET":
        return JsonResponse(_json(row))
    if request.method == "DELETE":
        _require_role(request, "annotation_write")
        if row.status == "approved":
            raise ApiError(409, "APPROVED_ANNOTATION_LOCKED", "Approved annotations cannot be deleted; create a reviewed revision instead.")
        with transaction.atomic():
            row.archived_at = datetime.now(timezone.utc)
            row.revision += 1
            row.updated_by = request.user.get_username()
            row.save(update_fields=["archived_at", "revision", "updated_at", "updated_by"])
            _snapshot_annotation(row, request.user.get_username(), "Archived draft annotation")
            _audit(row.project, "annotation.archived", f"Archived annotation {row.id}.", request.user.get_username(), video_id=row.video_id, annotation_id=row.id)
        return JsonResponse({"deleted": True, "id": annotation_id})
    _require_role(request, "annotation_write")
    data = _body(request)
    if "status" in data:
        raise ApiError(422, "REVIEW_REQUIRED", "Review status changes must use the review endpoint.")
    allowed = ("start_time", "end_time", "action_label", "object_label", "actor_id", "confidence", "notes")
    values = {key: getattr(row, key) for key in allowed}
    values.update({key: value for key, value in data.items() if key in allowed})
    if not models.OntologyLabel.objects.filter(version=row.schema_version, code=values["action_label"], active=True).exists():
        raise ApiError(422, "UNKNOWN_ACTION_LABEL", f"Action label '{values['action_label']}' is not active in ontology version {row.schema_version}.")
    if "action_label" in data:
        values["action_label"] = _required(data, "action_label", 80)
    for field, limit in (("object_label", 120), ("actor_id", 120), ("notes", 4000)):
        if field in data:
            values[field] = _bounded(data, field, limit, None)
    start, end = _finite_number(values["start_time"], "start_time"), _finite_number(values["end_time"], "end_time")
    if start < 0 or end <= start:
        raise ApiError(422, "INVALID_INTERVAL", "Use finite seconds with start >= 0 and end > start.")
    if values["confidence"] is not None:
        confidence = _finite_number(values["confidence"], "confidence")
        if not 0 <= confidence <= 1:
            raise ApiError(422, "INVALID_CONFIDENCE", "Confidence must be between 0 and 1.")
        values["confidence"] = confidence
    prior_status = row.status
    with transaction.atomic():
        for key, value in values.items():
            if key != "status":
                setattr(row, key, value)
        if prior_status == "approved":
            row.status = "needs_review"
        elif prior_status in ("rejected", "needs_review"):
            row.status = "draft"
        row.revision += 1
        row.updated_by = request.user.get_username()
        row.save()
        _snapshot_annotation(row, request.user.get_username(), "Annotation content revised")
        _audit(row.project, "annotation.revised" if prior_status == "approved" else "annotation.updated", f"Updated annotation {row.id}.", request.user.get_username(), video_id=row.video_id, annotation_id=row.id, revision=row.revision)
    return JsonResponse(_json(row))


@api
@require_http_methods(["POST"])
def import_annotations(request, video_id):
    video = _video(video_id)
    uploaded = request.FILES.get("file")
    _require_role(request, "annotation_write")
    if not uploaded:
        raise ApiError(400, "MISSING_IMPORT", "Select a CSV or JSON annotation file.")
    if uploaded.size > 10 * 1024 * 1024:
        raise ApiError(413, "IMPORT_TOO_LARGE", "Import is limited to 10 MB.")
    try:
        content = uploaded.read().decode("utf-8-sig")
        rows, issues = load_annotations(io.StringIO(content), Path(uploaded.name).suffix.lstrip(".") or "csv")
    except UnicodeError:
        raise ApiError(400, "INVALID_ENCODING", "Import file must be UTF-8 encoded.")
    except ValueError as exc:
        raise ApiError(400, "INVALID_IMPORT_FORMAT", str(exc))
    for row in rows:
        if row.get("video_id") not in (video.id, video.original_filename, Path(uploaded.name).stem):
            issues.append({"code": "UNKNOWN_VIDEO_REFERENCE", "severity": "error", "message": "Imported row refers to a different video; import is atomic.", "source_row": row.get("_source_row")})
        row["video_id"] = video.id
        if not models.OntologyLabel.objects.filter(
            version=video.project.annotation_policy_version, code=row.get("action_label"), active=True
        ).exists():
            issues.append({"code": "UNKNOWN_ACTION_LABEL", "severity": "error", "message": "Action label is not active in the project's ontology version.", "source_row": row.get("_source_row")})
    issues += validate_annotations(rows, durations={video.id: video.duration_seconds}, known_videos={video.id})
    if any(item.get("severity") == "error" for item in issues):
        return JsonResponse({"error": {"code": "IMPORT_VALIDATION_FAILED", "message": "No annotations were imported because the file contains errors.", "details": {"issues": issues}}}, status=422)
    with transaction.atomic():
        created_rows = models.Annotation.objects.bulk_create([
            models.Annotation(project=video.project, video=video, start_time=_finite_number(row["start_time"], "start_time"), end_time=_finite_number(row["end_time"], "end_time"), action_label=row["action_label"], object_label=row.get("object_label"), actor_id=row.get("actor_id"), confidence=_finite_number(row["confidence"], "confidence") if row.get("confidence") not in (None, "") else None, notes=row.get("notes"), source="imported", status="draft")
            for row in rows
        ])
        for annotation in created_rows:
            annotation.created_by = request.user.get_username()
            annotation.updated_by = request.user.get_username()
            annotation.schema_version = video.project.annotation_policy_version
            annotation.save(update_fields=["created_by", "updated_by", "schema_version"])
            _snapshot_annotation(annotation, request.user.get_username(), "Imported annotation")
        _audit(video.project, "annotation.imported", f"Imported {len(rows)} annotation(s) from a file.", request.user.get_username(), video_id=video.id, count=len(rows), checksum_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest())
    return JsonResponse({"imported_count": len(rows), "issues": issues})


@api
@require_http_methods(["GET"])
def annotation_export_preview(request, video_id):
    video = _video(video_id)
    return JsonResponse({"columns": ["annotation_id", "project_id", "video_id", "start_time", "end_time", "action_label", "object_label", "actor_id", "confidence", "source", "status", "revision", "notes"], "annotations": [_json(row) for row in _annotation_rows(video.project_id, video.id)]})


@api
@require_http_methods(["POST"])
def validate_project(request, project_id):
    _require_role(request, "quality")
    return JsonResponse(_run(_validate(_project(project_id))))


@api
@require_http_methods(["POST"])
def validate_video(request, video_id):
    _require_role(request, "quality")
    video = _video(video_id)
    return JsonResponse(_run(_validate(video.project, video.id)))


@api
@require_http_methods(["GET"])
def validation_run_detail(request, run_id):
    try:
        return JsonResponse(_run(models.ValidationRun.objects.get(pk=run_id)))
    except models.ValidationRun.DoesNotExist:
        raise ApiError(404, "VALIDATION_RUN_NOT_FOUND", "The requested validation run does not exist.")


@api
@require_http_methods(["GET"])
def quality_summary(request, project_id):
    return JsonResponse(_quality(_project(project_id)))


@api
@require_http_methods(["GET"])
def video_overlaps(request, video_id):
    video = _video(video_id)
    issues = validate_annotations([_record(row) for row in _annotation_rows(video.project_id, video.id)])
    return JsonResponse({"video_id": video.id, "interval_convention": "[start,end)", "overlaps": [item for item in issues if item["code"] == "OVERLAPPING_INTERVAL"]})


@api
@require_http_methods(["POST"])
def review_project(request, project_id):
    _require_role(request, "review")
    project, data = _project(project_id), _body(request)
    decision = data.get("decision")
    if decision not in ("approved", "rejected", "needs_review"):
        raise ApiError(422, "INVALID_REVIEW_DECISION", "Decision must be approved, rejected, or needs_review.")
    actor = request.user.get_username()
    comment = _bounded(data, "comment", 2000)
    if decision in ("rejected", "needs_review") and (not comment or len(comment.strip()) < 3):
        raise ApiError(422, "REVIEW_REASON_REQUIRED", "Provide a meaningful reason for rejection or requested changes.")
    rows = list(project.annotations.filter(archived_at__isnull=True).select_related("video"))
    if decision == "approved" and any(row.created_by == actor for row in rows) and not request.user.is_superuser:
        raise ApiError(403, "MAKER_CHECKER_REQUIRED", "The annotation author cannot approve their own records.")
    if decision == "approved" and any(row.status not in ("needs_review", "approved") for row in rows):
        raise ApiError(409, "ANNOTATIONS_NOT_SUBMITTED", "Submit draft annotations for review before approving the project.")
    if decision == "approved":
        latest = _validate(project, actor=actor)
        if latest.error_count:
            raise ApiError(409, "APPROVAL_BLOCKED", "Run validation and resolve all hard errors before project approval.", {"latest_validation": latest.id, "error_count": latest.error_count})
    with transaction.atomic():
        for row in rows:
            if row.status == decision:
                continue
            row.status = decision
            row.revision += 1
            row.updated_by = actor
            row.save(update_fields=["status", "revision", "updated_by", "updated_at"])
            _snapshot_annotation(row, actor, comment)
            _audit(project, f"annotation.review.{decision}", f"Project decision {decision} for annotation {row.id}. {comment}".strip(), actor, annotation_id=row.id, video_id=row.video_id)
        _audit(project, f"project.review.{decision}", f"Project review decision: {decision}. {comment}".strip(), actor, decision=decision, reviewed_count=len(rows))
    return JsonResponse({"project_id": project.id, "decision": decision, "reviewed_count": len(rows), "actor": actor})


@api
@require_http_methods(["POST"])
def submit_project_for_review(request, project_id):
    _require_role(request, "annotation_write")
    project = _project(project_id)
    actor = request.user.get_username()
    rows = list(project.annotations.filter(
        archived_at__isnull=True, status="draft",
    ).select_related("video"))
    if not rows:
        raise ApiError(409, "NO_DRAFT_ANNOTATIONS", "There are no draft annotations to submit for review.")
    with transaction.atomic():
        for row in rows:
            row.status = "needs_review"
            row.revision += 1
            row.updated_by = actor
            row.save(update_fields=["status", "revision", "updated_by", "updated_at"])
            _snapshot_annotation(row, actor, "Submitted for human review")
        _audit(project, "project.review.submitted", f"Submitted {len(rows)} annotation(s) for review.", actor, submitted_count=len(rows))
    return JsonResponse({"project_id": project.id, "submitted_count": len(rows), "actor": actor})


@api
@require_http_methods(["POST"])
def review_annotation(request, annotation_id):
    _require_role(request, "review")
    row, data = _annotation(annotation_id), _body(request)
    decision = data.get("decision")
    if decision not in ("approved", "rejected", "needs_review"):
        raise ApiError(422, "INVALID_REVIEW_DECISION", "Decision must be approved, rejected, or needs_review.")
    actor = request.user.get_username()
    comment = _bounded(data, "comment", 2000)
    if decision in ("rejected", "needs_review") and (not comment or len(comment.strip()) < 3):
        raise ApiError(422, "REVIEW_REASON_REQUIRED", "Provide a meaningful reason for rejection or requested changes.")
    if decision == "approved" and row.created_by == actor and not request.user.is_superuser:
        raise ApiError(403, "MAKER_CHECKER_REQUIRED", "The annotation author cannot approve their own annotation.")
    if decision == "approved" and row.status != "needs_review":
        raise ApiError(409, "ANNOTATION_NOT_SUBMITTED", "Submit the annotation for review before approving it.")
    if decision == "approved":
        latest = _validate(row.project, actor=actor)
        if latest.error_count:
            raise ApiError(409, "APPROVAL_BLOCKED", "Run validation and resolve all hard errors before approval.")
    with transaction.atomic():
        prior = row.status
        row.status, row.updated_by = decision, actor
        row.revision += 1
        row.save(update_fields=["status", "revision", "updated_by", "updated_at"])
        _snapshot_annotation(row, actor, comment)
        _audit(row.project, f"annotation.review.{decision}", f"Review decision for annotation {row.id}: {decision}. {comment}".strip(), actor, annotation_id=row.id, video_id=row.video_id, previous_status=prior, revision=row.revision)
    return JsonResponse(_json(row))


@api
@require_http_methods(["GET"])
def audit_events(request, project_id):
    project = _project(project_id)
    page, page_size = _page(request, default_size=50)
    query = project.audit_events.order_by("-created_at")
    if request.GET.get("event_type"):
        query = query.filter(event_type=request.GET["event_type"][:80])
    total = query.count()
    result = []
    for event in query[page * page_size:(page + 1) * page_size]:
        item = _json(event)
        item["details"] = json.loads(event.details_json)
        item.pop("details_json", None)
        result.append(item)
    response = JsonResponse(result, safe=False)
    response["X-Total-Count"] = str(total)
    response["X-Page"] = str(page)
    response["X-Page-Size"] = str(page_size)
    return response


@api
@require_http_methods(["POST"])
def create_export(request, project_id):
    _require_role(request, "export")
    project, data = _project(project_id), _body(request)
    fmt = data.get("format", "json")
    if fmt not in ("csv", "json"):
        raise ApiError(422, "INVALID_EXPORT_FORMAT", "format must be csv or json.")
    include_unapproved = data.get("include_unapproved", False)
    if not isinstance(include_unapproved, bool):
        raise ApiError(422, "INVALID_EXPORT_OPTION", "include_unapproved must be a boolean.")
    video_id = data.get("video_id")
    if video_id and not models.Video.objects.filter(pk=video_id, project=project).exists():
        raise ApiError(404, "VIDEO_NOT_FOUND", "The requested video does not exist in this project.")
    query = models.Annotation.objects.filter(project=project, archived_at__isnull=True)
    if video_id:
        query = query.filter(video_id=video_id)
    if not include_unapproved:
        query = query.filter(status="approved")
    rows = list(query.order_by("video_id", "start_time", "id"))
    latest = project.validation_runs.order_by("-created_at").first()
    if latest and project.annotations.filter(updated_at__gt=latest.created_at).exists():
        latest = None
    export_id = str(uuid4())
    filename = f"aura-{project.id[:8]}-{export_id[:8]}.{fmt}"
    key = f"{export_id}.{fmt}"
    if fmt == "csv":
        output = io.StringIO(newline="")
        columns = ["annotation_id", "project_id", "video_id", "start_time", "end_time", "action_label", "object_label", "actor_id", "confidence", "source", "status", "revision", "notes"]
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({"annotation_id": row.id, "project_id": row.project_id, "video_id": row.video_id, **{field: getattr(row, field) for field in columns[3:]}})
        content = output.getvalue().encode("utf-8")
    else:
        envelope = {"schema_version": "1.0", "project": {"id": project.id, "name": project.name}, "policy": {"version": project.annotation_policy_version}, "annotations": [{"annotation_id": row.id, "project_id": row.project_id, "video_id": row.video_id, "start_time": row.start_time, "end_time": row.end_time, "action_label": row.action_label, "object_label": row.object_label, "actor_id": row.actor_id, "confidence": row.confidence, "source": row.source, "status": row.status, "revision": row.revision, "notes": row.notes} for row in rows]}
        content = json.dumps(envelope, indent=2, ensure_ascii=False).encode("utf-8")
    export_root = OUTPUT_DIR / "exports"
    resolved_root = export_root.resolve()
    final_path = (export_root / key).resolve()
    temporary_path = (export_root / f".{export_id}.tmp").resolve()
    if resolved_root not in final_path.parents or resolved_root not in temporary_path.parents:
        raise ApiError(400, "INVALID_EXPORT_PATH", "Export path is invalid.")
    checksum = hashlib.sha256(content).hexdigest()
    release_version = (models.DatasetExport.objects.filter(project=project).aggregate(version=Max("release_version"))["version"] or 0) + 1
    source_snapshot = [
        {"annotation_id": row.id, "revision": row.revision, "video_id": row.video_id,
         "asset_sha256": row.video.checksum_sha256, "schema_version": row.schema_version}
        for row in rows
    ]
    manifest = {
        "export_id": export_id, "release_version": release_version, "project_id": project.id,
        "video_id": video_id, "format": fmt, "exported_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1.0", "policy_version": project.annotation_policy_version,
        "record_count": len(rows), "statuses": sorted({row.status for row in rows}),
        "validation_run_id": latest.id if latest else None,
        "validation_status": latest.status if latest else None,
        "approval_state": "includes_unapproved" if include_unapproved else "approved_only",
        "synthetic_data": any(row.source == "synthetic_demo" for row in rows),
        "source_snapshot_sha256": hashlib.sha256(json.dumps(source_snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "sha256": checksum,
    }
    item = None
    try:
        temporary_path.write_bytes(content)
        with transaction.atomic():
            item = models.DatasetExport.objects.create(
                id=export_id, project=project, video_id=video_id, format=fmt, filename=filename,
                storage_key=key, record_count=len(rows), validation_run=latest,
                approval_state=manifest["approval_state"], manifest_json=json.dumps(manifest),
                actor=request.user.get_username(), release_version=release_version,
                source_snapshot_json=json.dumps(source_snapshot, sort_keys=True),
            )
            _audit(project, "export.created", f"Created {fmt.upper()} release v{release_version} with {len(rows)} record(s).", request.user.get_username(), export_id=export_id, record_count=len(rows), approval_state=manifest["approval_state"])
            temporary_path.replace(final_path)
    except IntegrityError as exc:
        temporary_path.unlink(missing_ok=True)
        if item is not None:
            final_path.unlink(missing_ok=True)
        raise ApiError(409, "RELEASE_VERSION_CONFLICT", "A concurrent release changed the version; retry the export.") from exc
    except Exception:
        temporary_path.unlink(missing_ok=True)
        if item is not None:
            final_path.unlink(missing_ok=True)
        raise
    result = _json(item)
    result["manifest"] = manifest
    return JsonResponse(result, status=201)


@api
@require_http_methods(["GET", "POST"])
def project_exports(request, project_id):
    project = _project(project_id)
    if request.method == "POST":
        return create_export(request, project_id)
    page, page_size = _page(request)
    query = project.exports.order_by("-created_at")
    result = []
    for item in query[page * page_size:(page + 1) * page_size]:
        row = _json(item)
        row["manifest"] = json.loads(item.manifest_json)
        result.append(row)
    response = JsonResponse(result, safe=False)
    response["X-Total-Count"] = str(query.count())
    response["X-Page"] = str(page)
    response["X-Page-Size"] = str(page_size)
    return response


@api
@require_http_methods(["GET"])
def export_detail(request, export_id):
    _require_role(request, "export")
    try:
        item = models.DatasetExport.objects.get(pk=export_id)
    except models.DatasetExport.DoesNotExist:
        raise ApiError(404, "EXPORT_NOT_FOUND", "The requested export does not exist.")
    result = _json(item)
    result["manifest"] = json.loads(item.manifest_json)
    return JsonResponse(result)


@api
@require_http_methods(["GET"])
def export_download(request, export_id):
    _require_role(request, "export")
    try:
        item = models.DatasetExport.objects.get(pk=export_id)
    except models.DatasetExport.DoesNotExist:
        raise ApiError(404, "EXPORT_NOT_FOUND", "The requested export does not exist.")
    path = (OUTPUT_DIR / "exports" / item.storage_key).resolve()
    if OUTPUT_DIR not in path.parents or not path.is_file():
        raise ApiError(404, "EXPORT_FILE_UNAVAILABLE", "Export file is not available.")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != json.loads(item.manifest_json).get("sha256"):
        raise ApiError(409, "EXPORT_CHECKSUM_MISMATCH", "Export artifact failed its stored checksum verification.")
    _audit(item.project, "export.downloaded", f"Downloaded release v{item.release_version}.", request.user.get_username(), export_id=item.id)
    return FileResponse(path.open("rb"), as_attachment=True, filename=item.filename, content_type="text/csv" if item.format == "csv" else "application/json")


@api
@require_http_methods(["GET"])
def active_policy(request):
    if not POLICY_PATH.is_file():
        raise ApiError(503, "POLICY_UNAVAILABLE", "Canonical annotation policy file is not available.")
    return JsonResponse({"version": "1.0", "title": "AURA Annotation Policy 1.0", "status": "active", "source": "annotation_policy_v1.md", "content": POLICY_PATH.read_text(encoding="utf-8")})


@api
@require_http_methods(["GET"])
def policy_search(request):
    query = request.GET.get("q", "").strip()
    if not query:
        raise ApiError(422, "EMPTY_QUERY", "Provide a policy search query.")
    try:
        limit = int(request.GET.get("limit", 5))
    except ValueError:
        raise ApiError(422, "INVALID_LIMIT", "limit must be an integer.")
    return JsonResponse({"query": query, "results": _policy_search(query, limit)})


@api
@require_http_methods(["POST"])
def assistant_ask(request):
    data = _body(request)
    question = _required(data, "question", 2000)
    project = _project(data["project_id"]) if data.get("project_id") else None
    lower = question.lower()
    evidence, tools = [], []
    if any(token in lower for token in ("policy", "label", "timestamp", "overlap rule")):
        results = _policy_search(question, 3)
        answer = "The active AURA policy says:\n" + "\n\n".join(f"{item['title']}: {item['excerpt'][:350]}" for item in results) if results else "I could not find a matching section in the active annotation policy."
        evidence = [{"type": "policy", **item} for item in results]
        tools.append({"tool": "retrieve_annotation_policy", "status": "completed"})
    elif project and any(token in lower for token in ("validation", "error", "warning", "quality")):
        summary = _quality(project)
        latest = summary["latest_validation"]
        if latest:
            evidence = [{"type": "validation_run", "run_id": latest["id"], "status": latest["status"], "error_count": latest["error_count"], "warning_count": latest["warning_count"], "issues": latest["issues"][:20]}]
            answer = f"Latest validation is {latest['status']}: {latest['error_count']} error(s), {latest['warning_count']} warning(s), across {latest['total_records']} record(s)."
            if latest["issues"]:
                answer += "\n" + "\n".join(f"{item['code']}: {item['message']}" for item in latest["issues"][:8])
        else:
            answer = f"Project '{project.name}' has not been validated yet. Use Validate project to create a factual validation snapshot."
        tools.append({"tool": "get_quality_summary", "status": "completed"})
    elif project and any(token in lower for token in ("summary", "how many", "distribution", "labels", "export")):
        summary = _quality(project)
        evidence = [{"type": "project_summary", "project_id": project.id, "annotation_count": summary["annotation_count"], "counts_by_label": summary["counts_by_label"], "counts_by_status": summary["counts_by_status"]}]
        answer = f"Project '{project.name}' contains {summary['annotation_count']} annotation(s), {summary['unique_videos']} video(s), and {summary['unique_labels']} unique label(s). Label counts: {json.dumps(summary['counts_by_label'], sort_keys=True)}. Only approved annotations are included in default exports."
        tools.append({"tool": "get_project_summary", "status": "completed"})
    else:
        answer = "I can answer questions about AURA's annotation policy, validation results, quality summaries, label distributions, and approved-export behavior. Select a project for questions about its data."
    interaction = models.AssistantInteraction.objects.create(project=project, question=question, answer=answer, evidence_json=json.dumps(evidence))
    if project:
        _audit(project, "assistant.ask", "Deterministic assistant answered a question.", tool_count=len(tools))
    return JsonResponse({"interaction_id": interaction.id, "mode": "deterministic", "answer": answer, "tool_calls": tools, "evidence": evidence, "suggested_actions": ["Validate project", "Review policy", "Open annotations"]})


@api
@require_http_methods(["GET"])
def assistant_interactions(request):
    rows = models.AssistantInteraction.objects.order_by("-created_at")
    if request.GET.get("project_id"):
        rows = rows.filter(project_id=request.GET["project_id"])
    return JsonResponse([_json(row) for row in rows[:100]], safe=False)


@api
@require_http_methods(["GET"])
def assistant_interaction_detail(request, interaction_id):
    try:
        row = models.AssistantInteraction.objects.get(pk=interaction_id)
    except models.AssistantInteraction.DoesNotExist:
        raise ApiError(404, "INTERACTION_NOT_FOUND", "The requested assistant interaction does not exist.")
    result = _json(row)
    result["evidence"] = json.loads(row.evidence_json)
    result.pop("evidence_json", None)
    return JsonResponse(result)


@api
@require_http_methods(["GET", "POST"])
def knowledge_sources(request, project_id):
    project = _project(project_id)
    if request.method == "GET":
        rows = models.KnowledgeSource.objects.filter(project=project, deleted_at__isnull=True)
        if request.GET.get("video_id"):
            rows = rows.filter(video_id=request.GET["video_id"])
        return JsonResponse([knowledge_service.serialize_source(row) for row in rows.order_by("-created_at")[:100]], safe=False)

    _require_role(request, "annotation_write")
    uploaded = request.FILES.get("file")
    if uploaded is None:
        raise ApiError(422, "PDF_REQUIRED", "Choose a PDF file to index.")
    if uploaded.size <= 0 or uploaded.size > RAG_MAX_PDF_MB * 1024 * 1024:
        raise ApiError(413, "PDF_SIZE_LIMIT", f"PDF size must be between 1 byte and {RAG_MAX_PDF_MB} MB.")
    if not uploaded.name.casefold().endswith(".pdf") or uploaded.content_type not in {"application/pdf", "application/octet-stream"}:
        raise ApiError(415, "PDF_TYPE_UNSUPPORTED", "Upload a file with a .pdf name and PDF content type.")
    content = uploaded.read()
    if not content.startswith(b"%PDF-"):
        raise ApiError(415, "PDF_SIGNATURE_INVALID", "The selected file does not have a valid PDF signature.")
    digest = hashlib.sha256(content).hexdigest()
    video_id = request.POST.get("video_id") or None
    video = _video(video_id) if video_id else None
    if video and video.project_id != project.id:
        raise ApiError(422, "VIDEO_PROJECT_MISMATCH", "The selected video does not belong to this project.")
    duplicate = models.KnowledgeSource.objects.filter(
        project=project, video=video, source_type="pdf", checksum_sha256=digest, deleted_at__isnull=True,
    ).first()
    if duplicate:
        raise ApiError(409, "PDF_DUPLICATE", "This PDF is already in the project's knowledge base.", {"source_id": duplicate.id})

    title = os.path.basename(uploaded.name.replace("\\", "/"))[:255] or "uploaded.pdf"
    source = models.KnowledgeSource.objects.create(
        project=project, video=video, uploaded_by=request.user, source_type="pdf",
        title=title, checksum_sha256=digest, byte_size=len(content), status="queued",
    )
    relative_key = f"knowledge/{source.id}.pdf"
    media_root = Path(MEDIA_DIR).resolve()
    target = (media_root / relative_key).resolve()
    if media_root not in target.parents:
        source.status = "failed"
        source.error_summary = "Private upload path could not be resolved safely."
        source.save(update_fields=["status", "error_summary"])
        raise ApiError(500, "PDF_STORAGE_PATH_INVALID", source.error_summary)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    source.storage_key = relative_key
    source.save(update_fields=["storage_key"])
    source = knowledge_service.ingest_pdf(source, content)
    _audit(project, "knowledge.pdf.indexed", "A PDF source was processed for project knowledge.", request.user.get_username(), video_id=video.id if video else None)
    return JsonResponse(knowledge_service.serialize_source(source), status=201)


@api
@require_http_methods(["GET"])
def knowledge_source_detail(request, source_id):
    try:
        source = models.KnowledgeSource.objects.get(pk=source_id, deleted_at__isnull=True)
    except models.KnowledgeSource.DoesNotExist:
        raise ApiError(404, "KNOWLEDGE_SOURCE_NOT_FOUND", "The requested knowledge source does not exist.")
    result = knowledge_service.serialize_source(source)
    result["jobs"] = [{
        "id": job.id, "job_type": job.job_type, "status": job.status,
        "retry_count": job.retry_count, "chunk_count": job.chunk_count,
        "warning_count": job.warning_count, "error_summary": job.error_summary,
        "started_at": job.started_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    } for job in source.jobs.order_by("-started_at")[:20]]
    return JsonResponse(result)


@api
@require_http_methods(["POST", "DELETE"])
def knowledge_source_lifecycle(request, source_id):
    try:
        source = models.KnowledgeSource.objects.select_related("project", "video").get(pk=source_id, deleted_at__isnull=True)
    except models.KnowledgeSource.DoesNotExist:
        raise ApiError(404, "KNOWLEDGE_SOURCE_NOT_FOUND", "The requested knowledge source does not exist.")
    if request.method == "DELETE":
        _require_role(request, "project_admin")
        knowledge_service.delete_source(source)
        _audit(source.project, "knowledge.source.deleted", "A knowledge source was removed from search.", request.user.get_username(), video_id=source.video_id)
        return JsonResponse({"id": source.id, "status": source.status})
    _require_role(request, "annotation_write")
    retry_count = source.jobs.count()
    if source.source_type == "video":
        source = knowledge_service.index_video(source.video)
    else:
        media_root = Path(MEDIA_DIR).resolve()
        path = (media_root / source.storage_key).resolve()
        if not source.storage_key or media_root not in path.parents or not path.is_file():
            raise ApiError(409, "PDF_SOURCE_FILE_MISSING", "The private PDF file is unavailable; upload the source again.")
        source = knowledge_service.ingest_pdf(source, path.read_bytes(), retry_count=retry_count)
    return JsonResponse(knowledge_service.serialize_source(source))


@api
@require_http_methods(["POST"])
def index_video_knowledge(request, video_id):
    _require_role(request, "quality")
    video = _video(video_id)
    source = knowledge_service.index_video(video)
    _audit(video.project, "knowledge.video.indexed", "Stored video metadata and annotations were indexed.", request.user.get_username(), video_id=video.id)
    return JsonResponse(knowledge_service.serialize_source(source))


@api
@require_http_methods(["GET", "POST"])
def knowledge_conversations(request, project_id):
    project = _project(project_id)
    if request.method == "GET":
        rows = models.KnowledgeConversation.objects.filter(project=project, user=request.user).order_by("-updated_at")[:100]
        return JsonResponse([knowledge_service.serialize_conversation(row) for row in rows], safe=False)

    data = _body(request)
    scope = data.get("scope", "selected_video")
    valid_scopes = {choice for choice, _ in models.KnowledgeConversation.SCOPES}
    if scope not in valid_scopes:
        raise ApiError(422, "KNOWLEDGE_SCOPE_INVALID", "Choose a supported knowledge evidence scope.")
    video_id = data.get("video_id") or None
    video = _video(video_id) if video_id else None
    if video and video.project_id != project.id:
        raise ApiError(422, "VIDEO_PROJECT_MISMATCH", "The selected video does not belong to this project.")
    if scope in {"selected_video", "video_and_documents"} and video is None:
        raise ApiError(422, "VIDEO_REQUIRED", "This evidence scope requires a selected video.")

    source_ids = data.get("source_ids", [])
    if not isinstance(source_ids, list) or any(not isinstance(source_id, str) for source_id in source_ids):
        raise ApiError(422, "KNOWLEDGE_SOURCES_INVALID", "source_ids must be a list of source identifiers.")
    if len(source_ids) > 100:
        raise ApiError(422, "KNOWLEDGE_SOURCES_INVALID", "Select no more than 100 PDF sources.")
    if len(set(source_ids)) != len(source_ids):
        raise ApiError(422, "KNOWLEDGE_SOURCES_INVALID", "source_ids must not contain duplicates.")
    if scope in {"video_and_documents", "documents_only"} and not source_ids:
        raise ApiError(422, "KNOWLEDGE_SOURCES_REQUIRED", "Select at least one PDF source for this scope.")
    if scope in {"selected_video", "project_knowledge"} and source_ids:
        raise ApiError(422, "KNOWLEDGE_SOURCES_INVALID", "This evidence scope does not accept an explicit PDF selection.")
    if source_ids:
        pdf_sources = models.KnowledgeSource.objects.filter(
            id__in=source_ids, project=project, source_type="pdf",
            status__in=["indexed", "partially_indexed"], deleted_at__isnull=True,
        )
        if scope == "video_and_documents":
            pdf_sources = pdf_sources.filter(Q(video__isnull=True) | Q(video=video))
        if pdf_sources.count() != len(source_ids):
            raise ApiError(404, "KNOWLEDGE_SOURCE_NOT_FOUND", "One or more selected PDF sources are unavailable in this project.")
    title = data.get("title", "New conversation")
    if not isinstance(title, str) or not title.strip() or len(title) > 160:
        raise ApiError(422, "KNOWLEDGE_TITLE_INVALID", "Conversation title must be 1–160 characters.")
    if scope in {"selected_video", "video_and_documents"}:
        knowledge_service.index_video(video)
    conversation = models.KnowledgeConversation.objects.create(
        project=project, video=video, user=request.user, title=title.strip(),
        scope=scope, selected_source_ids_json=json.dumps(source_ids),
    )
    return JsonResponse(knowledge_service.serialize_conversation(conversation, include_messages=True), status=201)


@api
@require_http_methods(["GET", "PATCH", "DELETE"])
def knowledge_conversation_detail(request, conversation_id):
    try:
        conversation = models.KnowledgeConversation.objects.get(pk=conversation_id, user=request.user)
    except models.KnowledgeConversation.DoesNotExist:
        raise ApiError(404, "KNOWLEDGE_CONVERSATION_NOT_FOUND", "The requested conversation does not exist.")
    if request.method == "GET":
        return JsonResponse(knowledge_service.serialize_conversation(conversation, include_messages=True))
    if request.method == "DELETE":
        conversation.delete()
        return JsonResponse({"id": conversation_id, "deleted": True})
    data = _body(request)
    title = data.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 160:
        raise ApiError(422, "KNOWLEDGE_TITLE_INVALID", "Conversation title must be 1–160 characters.")
    conversation.title = title.strip()
    conversation.save(update_fields=["title", "updated_at"])
    return JsonResponse(knowledge_service.serialize_conversation(conversation, include_messages=True))


@api
@require_http_methods(["POST"])
def knowledge_conversation_messages(request, conversation_id):
    try:
        conversation = models.KnowledgeConversation.objects.get(pk=conversation_id, user=request.user)
    except models.KnowledgeConversation.DoesNotExist:
        raise ApiError(404, "KNOWLEDGE_CONVERSATION_NOT_FOUND", "The requested conversation does not exist.")
    data = _body(request)
    question = _required(data, "question", 4000)
    result = knowledge_service.answer_question(conversation, question)
    response = knowledge_service.persist_message_result(conversation, question, result)
    return JsonResponse(response, status=201)


@api
@require_http_methods(["GET"])
def vision_status(request):
    return JsonResponse({"enabled": VISION_ENABLED, "metadata_extraction": _opencv_available(), "detector_configured": bool(VISION_ENABLED and VISION_WEIGHTS_PATH and Path(VISION_WEIGHTS_PATH).is_file()), "detector_ready": False, "model": VISION_MODEL or None, "note": "No detector inference adapter is implemented; weights are never downloaded automatically."})


@api
@require_http_methods(["POST"])
def vision_suggest(request, video_id):
    _video(video_id)
    raise ApiError(503, "VISION_DETECTOR_UNAVAILABLE", "No detector inference adapter is available. Manual annotation remains available.")


@api
@require_http_methods(["GET"])
def simulation_available(request, project_id):
    project = _project(project_id)
    present = sorted(set(project.annotations.values_list("action_label", flat=True)))
    phases = ("approach", "reach", "grasp", "lift", "move", "place", "release", "withdraw")
    return JsonResponse({"available": present, "vocabulary": list(ACTION_LABELS), "missing_task_phases": [label for label in phases if label not in present], "unmapped": [label for label in present if label not in phases]})


def _rl_experiment_json(experiment, include_policy=True):
    result = _json(experiment)
    result["configuration"] = json.loads(experiment.configuration_json)
    result["metrics"] = json.loads(experiment.metrics_json)
    result["policy_state_count"] = len(json.loads(experiment.policy_json))
    result.pop("configuration_json", None)
    result.pop("metrics_json", None)
    result.pop("policy_json", None)
    if include_policy:
        result["policy"] = json.loads(experiment.policy_json)
    result["limitations"] = [
        "Task-level grid simulator only; not a physics simulator or robot controller.",
        "Q-learning learns from simulator rewards, not directly from annotation labels.",
    ]
    return result


@api
@require_http_methods(["GET", "POST"])
def project_rl_experiments(request, project_id):
    project = _project(project_id)
    if request.method == "GET":
        query = project.rl_experiments.order_by("-created_at")
        page, page_size = _page(request)
        result = [_rl_experiment_json(run, include_policy=False) for run in query[page * page_size:(page + 1) * page_size]]
        response = JsonResponse(result, safe=False)
        response["X-Total-Count"] = str(query.count())
        response["X-Page"] = str(page)
        response["X-Page-Size"] = str(page_size)
        return response

    _require_role(request, "experiment")
    data = _body(request)
    algorithm = data.get("algorithm", "q_learning")
    episodes = data.get("episodes", 500)
    seed = data.get("seed", 7)
    max_steps = data.get("max_steps", 40)
    if algorithm not in ("q_learning", "baseline"):
        raise ApiError(422, "INVALID_RL_ALGORITHM", "algorithm must be q_learning or baseline.")
    for field, value, minimum, maximum in (
        ("episodes", episodes, 1, MAX_EPISODES),
        ("seed", seed, 0, 2**32 - 1),
        ("max_steps", max_steps, 6, MAX_STEPS),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ApiError(422, "INVALID_RL_CONFIGURATION", f"{field} must be an integer between {minimum} and {maximum}.")
    try:
        experiment, result = execute_experiment(
            project, request.user.get_username(), algorithm, episodes, seed, max_steps,
        )
    except (ValueError, RuntimeError) as exc:
        raise ApiError(422, "RL_EXPERIMENT_FAILED", str(exc)) from exc
    _audit(project, "rl.experiment.succeeded", f"Completed {algorithm} experiment with {episodes} training episode(s).", request.user.get_username(), experiment_id=experiment.id, seed=seed, policy_sha256=result["policy_sha256"], evaluation=result["metrics"]["evaluation"])
    response = _rl_experiment_json(experiment)
    response["limitations"] = result["limitations"]
    return JsonResponse(response, status=201)


@api
@require_http_methods(["GET"])
def rl_experiment_detail(request, experiment_id):
    try:
        experiment = models.RLExperiment.objects.get(pk=experiment_id)
    except models.RLExperiment.DoesNotExist:
        raise ApiError(404, "RL_EXPERIMENT_NOT_FOUND", "The requested RL experiment does not exist.")
    return JsonResponse(_rl_experiment_json(experiment))


@api
@require_http_methods(["GET"])
def rl_environment(request):
    return JsonResponse({
        "environment_version": ENVIRONMENT_VERSION,
        "grid_width": GRID_WIDTH,
        "start_cell": START_CELL,
        "object_cell": OBJECT_CELL,
        "goal_cell": GOAL_CELL,
        "actions": list(ACTION_NAMES),
        "reward_design": {"step": -0.1, "invalid_action": -1.0, "successful_pick": 1.9, "successful_place": 19.9},
        "limitations": [
            "Deterministic task-level grid only; it has no physics or robot dynamics.",
            "Q-learning learns from simulator rewards, not directly from annotation labels.",
        ],
    })


def _simulation_json(run):
    result = _json(run)
    result["source_annotation_ids"] = json.loads(run.source_ids_json)
    result["task"] = json.loads(run.task_json)
    return result


@api
@require_http_methods(["POST"])
def simulation_prepare(request, project_id):
    project = _project(project_id)
    video_id = request.GET.get("video_id")
    if video_id and not models.Video.objects.filter(pk=video_id, project=project).exists():
        raise ApiError(404, "VIDEO_NOT_FOUND", "The requested video does not exist in this project.")
    rows = _annotation_rows(project.id, video_id)
    task = {"schema_version": "1.0", "task_type": project.task_type, "object_label": next((row.object_label for row in rows if row.object_label), None), "execution_mode": "scripted_task_visualization", "phases": [{"action": row.action_label, "annotation_id": row.id, "start_time": row.start_time, "end_time": row.end_time, "object_label": row.object_label} for row in rows], "limitations": ["No robot geometry, calibrated camera coordinates, joint trajectories, force sensing, collision planning, or physical grasping are modeled."]}
    run = models.SimulationRun.objects.create(project=project, source_ids_json=json.dumps([row.id for row in rows]), task_json=json.dumps(task))
    _audit(project, "simulation.prepared", f"Prepared scripted simulation with {len(rows)} annotation-derived phase(s).", run_id=run.id)
    return JsonResponse(_simulation_json(run), status=201)


@api
@require_http_methods(["GET"])
def simulation_detail(request, run_id):
    try:
        return JsonResponse(_simulation_json(models.SimulationRun.objects.get(pk=run_id)))
    except models.SimulationRun.DoesNotExist:
        raise ApiError(404, "SIMULATION_NOT_FOUND", "The requested simulation run does not exist.")


@api
@require_http_methods(["POST"])
def simulation_start(request, run_id):
    try:
        run = models.SimulationRun.objects.select_related("project").get(pk=run_id)
    except models.SimulationRun.DoesNotExist:
        raise ApiError(404, "SIMULATION_NOT_FOUND", "The requested simulation run does not exist.")
    phases = json.loads(run.task_json).get("phases", [])
    if not phases:
        raise ApiError(409, "SIMULATION_HAS_NO_PHASES", "Create annotations before starting a simulation.")
    run.current_phase = min(run.current_phase + 1, len(phases))
    run.status = "completed" if run.current_phase >= len(phases) else "running"
    run.save(update_fields=["current_phase", "status"])
    _audit(run.project, "simulation.phase_advanced", f"Advanced scripted visualization to phase {run.current_phase} of {len(phases)}.", run_id=run.id)
    return JsonResponse(_simulation_json(run))


@api
@require_http_methods(["POST"])
def simulation_reset(request, run_id):
    try:
        run = models.SimulationRun.objects.select_related("project").get(pk=run_id)
    except models.SimulationRun.DoesNotExist:
        raise ApiError(404, "SIMULATION_NOT_FOUND", "The requested simulation run does not exist.")
    run.current_phase, run.status = 0, "prepared"
    run.save(update_fields=["current_phase", "status"])
    _audit(run.project, "simulation.reset", "Reset scripted visualization.", run_id=run.id)
    return JsonResponse(_simulation_json(run))


@api
@require_http_methods(["GET"])
def api_index(request):
    return JsonResponse({"service": APP_NAME, "api_version": "v1", "documentation": "See README.md for the versioned API route list."})
