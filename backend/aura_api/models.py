"""Django ORM models for persistent AURA workflow state."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


def stable_id():
    return str(uuid.uuid4())


class Project(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=stable_id, editable=False)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    task_type = models.CharField(max_length=80, default="pick_and_place")
    status = models.CharField(max_length=20, default="active")
    annotation_policy_version = models.CharField(max_length=20, default="1.0")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)


class OntologyLabel(models.Model):
    version = models.CharField(max_length=20, default="1.0")
    code = models.CharField(max_length=80)
    description = models.TextField()
    inclusion_rules = models.TextField(blank=True, default="")
    exclusion_rules = models.TextField(blank=True, default="")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["version", "code"], name="ontology_label_version_code_uniq")]
        ordering = ["code"]


class Video(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=stable_id, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="videos")
    original_filename = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=255, blank=True, null=True)
    mime_type = models.CharField(max_length=100, default="application/octet-stream")
    file_size_bytes = models.PositiveBigIntegerField(blank=True, null=True)
    duration_seconds = models.FloatField(blank=True, null=True)
    width = models.PositiveIntegerField(blank=True, null=True)
    height = models.PositiveIntegerField(blank=True, null=True)
    fps = models.FloatField(blank=True, null=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True, null=True)
    status = models.CharField(max_length=30, default="unavailable")
    source_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)


class Annotation(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=stable_id, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="annotations")
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="annotations")
    start_time = models.FloatField()
    end_time = models.FloatField()
    action_label = models.CharField(max_length=80)
    object_label = models.CharField(max_length=120, blank=True, null=True)
    actor_id = models.CharField(max_length=120, blank=True, null=True)
    confidence = models.FloatField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    source = models.CharField(max_length=30, default="human")
    schema_version = models.CharField(max_length=20, default="1.0")
    status = models.CharField(max_length=30, default="draft")
    revision = models.PositiveIntegerField(default=1)
    archived_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=120, default="Local Reviewer")
    updated_by = models.CharField(max_length=120, default="Local Reviewer")

    class Meta:
        indexes = [models.Index(fields=["project", "video", "start_time"])]
        constraints = [
            models.CheckConstraint(condition=Q(start_time__gte=0), name="annotation_start_nonnegative"),
            models.CheckConstraint(condition=Q(end_time__gt=F("start_time")), name="annotation_interval_positive"),
            models.CheckConstraint(condition=Q(confidence__isnull=True) | (Q(confidence__gte=0) & Q(confidence__lte=1)), name="annotation_confidence_range"),
        ]


class AnnotationRevision(models.Model):
    annotation = models.ForeignKey(Annotation, on_delete=models.PROTECT, related_name="revisions")
    revision = models.PositiveIntegerField()
    snapshot_json = models.TextField()
    actor = models.CharField(max_length=120)
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["annotation", "revision"], name="annotation_revision_number_uniq")]
        ordering = ["annotation_id", "revision"]


class ValidationRun(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=stable_id, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="validation_runs")
    video = models.ForeignKey(Video, on_delete=models.SET_NULL, blank=True, null=True)
    policy_version = models.CharField(max_length=20, default="1.0")
    status = models.CharField(max_length=30)
    total_records = models.PositiveIntegerField(default=0)
    valid_records = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    issues_json = models.TextField(default="[]")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.CharField(max_length=120, default="Local Reviewer")


class AuditEvent(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=stable_id, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="audit_events")
    video_id = models.CharField(max_length=36, blank=True, null=True)
    annotation_id = models.CharField(max_length=36, blank=True, null=True)
    export_id = models.CharField(max_length=36, blank=True, null=True)
    event_type = models.CharField(max_length=80, db_index=True)
    actor = models.CharField(max_length=120)
    summary = models.CharField(max_length=500)
    details_json = models.TextField(default="{}")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)


class DatasetExport(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=stable_id, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="exports")
    video = models.ForeignKey(Video, on_delete=models.SET_NULL, blank=True, null=True)
    format = models.CharField(max_length=10)
    filename = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=255)
    record_count = models.PositiveIntegerField()
    validation_run = models.ForeignKey(ValidationRun, on_delete=models.SET_NULL, blank=True, null=True)
    approval_state = models.CharField(max_length=40)
    manifest_json = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    actor = models.CharField(max_length=120)
    release_version = models.PositiveIntegerField(default=1)
    source_snapshot_json = models.TextField(default="[]")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "release_version"], name="dataset_release_version_uniq"),
            models.UniqueConstraint(fields=["storage_key"], name="dataset_export_storage_key_uniq"),
        ]


class AssistantInteraction(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=stable_id, editable=False)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, blank=True, null=True)
    question = models.TextField()
    answer = models.TextField()
    mode = models.CharField(max_length=30, default="deterministic")
    evidence_json = models.TextField(default="[]")
    created_at = models.DateTimeField(default=timezone.now)


class KnowledgeSource(models.Model):
    SOURCE_TYPES = [("pdf", "PDF"), ("video", "Video metadata and annotations")]
    STATUSES = [
        ("queued", "Queued"), ("processing", "Processing"), ("indexed", "Indexed"),
        ("partially_indexed", "Partially indexed"), ("failed", "Failed"), ("deleted", "Deleted"),
    ]

    id = models.CharField(primary_key=True, max_length=36, default=stable_id, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="knowledge_sources")
    video = models.ForeignKey(Video, on_delete=models.SET_NULL, blank=True, null=True, related_name="knowledge_sources")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    source_type = models.CharField(max_length=24, choices=SOURCE_TYPES)
    title = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=255, blank=True, default="")
    checksum_sha256 = models.CharField(max_length=64)
    byte_size = models.PositiveBigIntegerField(default=0)
    source_version = models.PositiveIntegerField(default=1)
    page_count = models.PositiveIntegerField(blank=True, null=True)
    chunk_count = models.PositiveIntegerField(default=0)
    index_backend = models.CharField(max_length=40, blank=True, default="lexical_sqlite")
    embedding_model = models.CharField(max_length=255, blank=True, default="")
    embedding_dimensions = models.PositiveIntegerField(blank=True, null=True)
    index_status = models.CharField(max_length=24, default="pending", db_index=True)
    dense_index_status = models.CharField(max_length=24, default="not_configured", db_index=True)
    index_version = models.PositiveIntegerField(default=1)
    embedding_model_revision = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(max_length=24, choices=STATUSES, default="queued", db_index=True)
    warnings_json = models.TextField(default="[]")
    error_summary = models.CharField(max_length=500, blank=True, default="")
    metadata_json = models.TextField(default="{}")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [models.Index(fields=["project", "source_type", "status"])]


class KnowledgeChunk(models.Model):
    id = models.CharField(primary_key=True, max_length=64)
    source = models.ForeignKey(KnowledgeSource, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.PositiveIntegerField()
    source_type = models.CharField(max_length=24)
    content = models.TextField()
    content_sha256 = models.CharField(max_length=64)
    page_start = models.PositiveIntegerField(blank=True, null=True)
    page_end = models.PositiveIntegerField(blank=True, null=True)
    video_start_seconds = models.FloatField(blank=True, null=True)
    video_end_seconds = models.FloatField(blank=True, null=True)
    annotation_id = models.CharField(max_length=36, blank=True, default="")
    index_backend = models.CharField(max_length=40, default="lexical_sqlite")
    embedding_model = models.CharField(max_length=255, blank=True, default="")
    embedding_dimensions = models.PositiveIntegerField(blank=True, null=True)
    source_checksum_sha256 = models.CharField(max_length=64, blank=True, default="")
    index_version = models.PositiveIntegerField(default=1)
    embedding_model_revision = models.CharField(max_length=128, blank=True, default="")
    metadata_json = models.TextField(default="{}")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["chunk_index"]
        constraints = [models.UniqueConstraint(fields=["source", "chunk_index"], name="knowledge_chunk_source_index_uniq")]
        indexes = [models.Index(fields=["source", "page_start"]), models.Index(fields=["source", "video_start_seconds"])]


class KnowledgeJob(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=stable_id, editable=False)
    source = models.ForeignKey(KnowledgeSource, on_delete=models.CASCADE, related_name="jobs")
    job_type = models.CharField(max_length=24, default="index")
    status = models.CharField(max_length=24, db_index=True)
    retry_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    error_summary = models.CharField(max_length=500, blank=True, default="")
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(blank=True, null=True)


class KnowledgeConversation(models.Model):
    SCOPES = [
        ("selected_video", "Selected video"),
        ("video_and_documents", "Selected video and selected PDFs"),
        ("documents_only", "Selected PDFs only"),
        ("project_knowledge", "Project knowledge"),
    ]

    id = models.CharField(primary_key=True, max_length=36, default=stable_id, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="knowledge_conversations")
    video = models.ForeignKey(Video, on_delete=models.SET_NULL, blank=True, null=True, related_name="knowledge_conversations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="knowledge_conversations")
    title = models.CharField(max_length=160, default="New conversation")
    scope = models.CharField(max_length=32, choices=SCOPES, default="selected_video")
    selected_source_ids_json = models.TextField(default="[]")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)


class KnowledgeMessage(models.Model):
    conversation = models.ForeignKey(KnowledgeConversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=12, choices=[("user", "User"), ("assistant", "Assistant")])
    content = models.TextField()
    answer_mode = models.CharField(max_length=40, blank=True, default="")
    evidence_status = models.CharField(max_length=24, blank=True, default="")
    retrieval_json = models.TextField(default="{}")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]


class KnowledgeCitation(models.Model):
    message = models.ForeignKey(KnowledgeMessage, on_delete=models.CASCADE, related_name="citations")
    chunk = models.ForeignKey(KnowledgeChunk, on_delete=models.SET_NULL, blank=True, null=True, related_name="citations")
    citation_id = models.CharField(max_length=12)
    source_id_snapshot = models.CharField(max_length=36)
    source_title_snapshot = models.CharField(max_length=255)
    source_type_snapshot = models.CharField(max_length=24)
    snippet = models.TextField()
    page_start = models.PositiveIntegerField(blank=True, null=True)
    page_end = models.PositiveIntegerField(blank=True, null=True)
    video_id_snapshot = models.CharField(max_length=36, blank=True, default="")
    video_start_seconds = models.FloatField(blank=True, null=True)
    video_end_seconds = models.FloatField(blank=True, null=True)
    annotation_id_snapshot = models.CharField(max_length=36, blank=True, default="")
    content_sha256 = models.CharField(max_length=64)
    score = models.FloatField(default=0)


class SimulationRun(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=stable_id, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="simulation_runs")
    source_ids_json = models.TextField(default="[]")
    task_json = models.TextField(default="{}")
    current_phase = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=30, default="prepared")
    created_at = models.DateTimeField(default=timezone.now)


class RLExperiment(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=stable_id, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="rl_experiments")
    algorithm = models.CharField(max_length=30, default="q_learning")
    status = models.CharField(max_length=20, default="queued", db_index=True)
    environment_version = models.CharField(max_length=30, default="grid-pick-place-v1")
    random_seed = models.PositiveIntegerField(default=7)
    configuration_json = models.TextField(default="{}")
    metrics_json = models.TextField(default="{}")
    policy_json = models.TextField(default="{}")
    policy_sha256 = models.CharField(max_length=64, blank=True, default="")
    error_summary = models.CharField(max_length=500, blank=True, default="")
    actor = models.CharField(max_length=150)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
