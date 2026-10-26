import hashlib
import importlib.util
import json
import os
import re
from collections import defaultdict
from pathlib import Path

from django.db.models import Q
from django.utils import timezone

from aura_rag.core import PdfIngestionError, chunk_pages, lexical_score, parse_pdf, sha256_bytes
from aura_rag.vector import configured_embedding_provider, configured_vector_store

from . import models
from .config import MEDIA_DIR, VECTOR_STORE_DIR


def _json_dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def serialize_source(source):
    return {
        "id": source.id,
        "project_id": source.project_id,
        "video_id": source.video_id,
        "source_type": source.source_type,
        "title": source.title,
        "checksum_sha256": source.checksum_sha256,
        "byte_size": source.byte_size,
        "source_version": source.source_version,
        "page_count": source.page_count,
        "chunk_count": source.chunk_count,
        "index_backend": source.index_backend,
        "embedding_model": source.embedding_model,
        "embedding_dimensions": source.embedding_dimensions,
        "status": source.status,
        "warnings": json.loads(source.warnings_json),
        "error_summary": source.error_summary,
        "metadata": json.loads(source.metadata_json),
        "created_at": source.created_at.isoformat(),
        "processed_at": source.processed_at.isoformat() if source.processed_at else None,
    }


def _local_vector_components():
    model_path = os.getenv("AURA_EMBEDDING_MODEL_PATH", "").strip()
    if (
        not model_path or not Path(model_path).is_dir()
        or importlib.util.find_spec("chromadb") is None
        or importlib.util.find_spec("sentence_transformers") is None
    ):
        return None, None
    try:
        provider = configured_embedding_provider()
    except ImportError:
        return None, None
    if provider is None:
        return None, None
    store = configured_vector_store(VECTOR_STORE_DIR, provider.model_name)
    if store is None:
        return None, None
    return provider, store


def _delete_vector_records(chunk_rows):
    if not chunk_rows:
        return
    grouped_ids = defaultdict(list)
    for row in chunk_rows:
        if row["embedding_model"]:
            grouped_ids[row["embedding_model"]].append(row["id"])
    for model_name, chunk_ids in grouped_ids.items():
        try:
            store = configured_vector_store(VECTOR_STORE_DIR, model_name)
        except ImportError:
            store = None
        if store is not None:
            store.delete(chunk_ids)


def _persist_chunks(source, chunk_values):
    old_rows = list(source.chunks.values("id", "embedding_model"))
    _delete_vector_records(old_rows)
    source.chunks.all().delete()

    rows = []
    for index, value in enumerate(chunk_values):
        digest = value["content_sha256"]
        stable_id = hashlib.sha256(
            f"{source.id}:{source.source_version}:{index}:{digest}".encode("utf-8")
        ).hexdigest()
        rows.append(models.KnowledgeChunk(
            id=stable_id,
            source=source,
            chunk_index=index,
            source_type=value.get("source_type", source.source_type),
            content=value["content"],
            content_sha256=digest,
            page_start=value.get("page_start"),
            page_end=value.get("page_end"),
            video_start_seconds=value.get("video_start_seconds"),
            video_end_seconds=value.get("video_end_seconds"),
            annotation_id=value.get("annotation_id", ""),
            metadata_json=_json_dump(value.get("metadata", {})),
        ))
    models.KnowledgeChunk.objects.bulk_create(rows)

    backend = "lexical_sqlite"
    model_name = ""
    embedding_dimensions = None
    provider, store = _local_vector_components()
    if rows and provider is not None and store is not None:
        vectors = provider.embed([row.content for row in rows])
        embedding_dimensions = len(vectors[0]) if vectors else None
        metadatas = [{
            "project_id": source.project_id,
            "source_id": source.id,
            "source_type": source.source_type,
            "video_id": source.video_id or "",
            "page_start": row.page_start or 0,
            "chunk_index": row.chunk_index,
        } for row in rows]
        store.upsert([row.id for row in rows], [row.content for row in rows], vectors, metadatas)
        backend = "chroma_sentence_transformers"
        model_name = provider.model_name
        models.KnowledgeChunk.objects.filter(source=source).update(
            index_backend=backend, embedding_model=model_name,
            embedding_dimensions=embedding_dimensions,
        )
    source.chunk_count = len(rows)
    source.index_backend = backend
    source.embedding_model = model_name
    source.embedding_dimensions = embedding_dimensions
    source.processed_at = timezone.now()
    source.save(update_fields=[
        "chunk_count", "index_backend", "embedding_model", "embedding_dimensions", "processed_at",
    ])
    return rows


def ingest_pdf(source, content, retry_count=0):
    if retry_count and source.chunks.exists():
        source.source_version += 1
        source.save(update_fields=["source_version"])
    job = models.KnowledgeJob.objects.create(
        source=source, job_type="pdf_index", status="processing", retry_count=retry_count,
    )
    source.status = "processing"
    source.error_summary = ""
    source.save(update_fields=["status", "error_summary"])
    try:
        pages, empty_pages = parse_pdf(content)
        chunks = chunk_pages(pages)
        chunk_values = [{
            "content": chunk.text,
            "content_sha256": chunk.content_sha256,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "metadata": {"chunker_version": "page-char-overlap-v1"},
        } for chunk in chunks]
        _persist_chunks(source, chunk_values)
        warnings = []
        if empty_pages:
            warnings.append(
                f"No selectable text was extracted from page(s) {', '.join(map(str, empty_pages))}; OCR is not configured."
            )
        if not chunks:
            warnings.append("No selectable text was found; provide a text-based PDF or configure a local OCR adapter.")
        source.page_count = len(pages) + len(empty_pages)
        source.status = "partially_indexed" if empty_pages or not chunks else "indexed"
        source.warnings_json = _json_dump(warnings)
        source.error_summary = ""
        source.save(update_fields=["page_count", "status", "warnings_json", "error_summary"])
        job.status = "succeeded" if chunks else "partially_indexed"
        job.chunk_count = len(chunks)
        job.warning_count = len(warnings)
    except PdfIngestionError as exc:
        source.status = "failed"
        source.error_summary = str(exc)[:500]
        source.save(update_fields=["status", "error_summary"])
        job.status = "failed"
        job.error_summary = source.error_summary
    except Exception:
        source.status = "failed"
        source.error_summary = "PDF indexing failed; check local parser, embedding, and vector-store configuration."
        source.save(update_fields=["status", "error_summary"])
        job.status = "failed"
        job.error_summary = source.error_summary
        raise
    finally:
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "chunk_count", "warning_count", "error_summary", "completed_at"])
    return source


def _video_evidence(video):
    values = [{
        "source_type": "video_metadata",
        "content": (
            f"AURA video metadata record. Video ID: {video.id}. Project ID: {video.project_id}. "
            f"Title: {video.original_filename}. Availability status: {video.status}. "
            f"Duration seconds: {video.duration_seconds if video.duration_seconds is not None else 'unknown'}. "
            f"Resolution: {video.width or 'unknown'}x{video.height or 'unknown'}. "
            f"Frame rate: {video.fps if video.fps is not None else 'unknown'}. "
            f"Checksum: {video.checksum_sha256 or 'not recorded'}. "
            f"Source notes: {video.source_notes or 'none'}. This is stored metadata, not visual inspection."
        ),
        "metadata": {"video_id": video.id, "availability": video.status},
        "index_backend": "lexical_sqlite",
    }]
    annotations = models.Annotation.objects.filter(
        video=video, archived_at__isnull=True,
    ).order_by("start_time", "end_time", "id")
    for row in annotations:
        object_text = row.object_label or "not specified"
        content = (
            f"AURA human/data annotation record, not a visual detector result. Video ID: {video.id}. "
            f"Annotation ID: {row.id}. Interval: {row.start_time:.3f} to {row.end_time:.3f} seconds. "
            f"Action label: {row.action_label}. Object label: {object_text}. "
            f"Actor: {row.actor_id or 'not specified'}. Annotation source: {row.source}. "
            f"Review state: {row.status}. Notes: {row.notes or 'none'}."
        )
        values.append({
            "source_type": "annotation",
            "content": content,
            "content_sha256": sha256_bytes(content.encode("utf-8")),
            "annotation_id": row.id,
            "video_start_seconds": row.start_time,
            "video_end_seconds": row.end_time,
            "metadata": {"annotation_id": row.id, "review_status": row.status},
        })
    latest_validation = models.ValidationRun.objects.filter(
        project=video.project, video=video,
    ).order_by("-created_at").first()
    if latest_validation:
        for issue_index, issue in enumerate(json.loads(latest_validation.issues_json)):
            content = (
                f"AURA validation finding for video {video.id}; run {latest_validation.id}. "
                f"Issue code: {issue.get('code', 'unknown')}. Severity: {issue.get('severity', 'unknown')}. "
                f"Finding: {issue.get('message', 'No message')}. Record ID: {issue.get('record_id', 'not specified')}."
            )
            values.append({
                "source_type": "validation",
                "content": content,
                "content_sha256": sha256_bytes(content.encode("utf-8")),
                "metadata": {"validation_run_id": latest_validation.id, "issue_index": issue_index},
            })
    for item in values:
        item.setdefault("content_sha256", sha256_bytes(item["content"].encode("utf-8")))
    return values


def index_video(video):
    evidence = _video_evidence(video)
    digest = sha256_bytes(_json_dump([
        {"content": item["content"], "metadata": item["metadata"]} for item in evidence
    ]).encode("utf-8"))
    source = models.KnowledgeSource.objects.filter(
        project=video.project, video=video, source_type="video", deleted_at__isnull=True,
    ).first()
    if source and source.checksum_sha256 == digest and source.chunks.exists():
        return source
    if source is None:
        source = models.KnowledgeSource.objects.create(
            project=video.project,
            video=video,
            source_type="video",
            title=video.original_filename,
            checksum_sha256=digest,
        )
    elif source.checksum_sha256 != digest:
        source.source_version += 1
    source.checksum_sha256 = digest
    source.status = "processing"
    pixels_available = False
    if video.storage_key:
        candidate = (MEDIA_DIR / video.storage_key).resolve()
        pixels_available = MEDIA_DIR in candidate.parents and candidate.is_file()
    warnings = [] if pixels_available else [
        "Video pixels are unavailable to this index; answers use stored metadata and annotation records only."
    ]
    source.metadata_json = _json_dump({
        "visual_pixels_available": pixels_available,
        "evidence_basis": "stored video metadata and database annotations",
    })
    source.warnings_json = _json_dump(warnings)
    source.save()
    job = models.KnowledgeJob.objects.create(source=source, job_type="video_index", status="processing")
    try:
        _persist_chunks(source, evidence)
        source.status = "indexed"
        source.save(update_fields=["status"])
        job.status = "succeeded"
        job.chunk_count = len(evidence)
    except Exception:
        source.status = "failed"
        source.error_summary = "Video metadata and annotation indexing failed."
        source.save(update_fields=["status", "error_summary"])
        job.status = "failed"
        job.error_summary = source.error_summary
        raise
    finally:
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "chunk_count", "error_summary", "completed_at"])
    return source


def _scope_sources(conversation):
    sources = models.KnowledgeSource.objects.filter(
        project=conversation.project, status__in=["indexed", "partially_indexed"], deleted_at__isnull=True,
    )
    selected_ids = json.loads(conversation.selected_source_ids_json)
    if conversation.scope == "selected_video":
        return sources.filter(source_type="video", video=conversation.video)
    if conversation.scope == "video_and_documents":
        return sources.filter(
            Q(source_type="video", video=conversation.video)
            | Q(source_type="pdf", id__in=selected_ids)
        )
    if conversation.scope == "documents_only":
        return sources.filter(source_type="pdf", id__in=selected_ids)
    return sources


def _annotation_sequence_question(question):
    terms = set(re.findall(r"[a-z]+", question.casefold()))
    asks_sequence = bool(terms & {"list", "order", "chronological", "sequence", "occur", "happen", "recorded"})
    return bool(terms & {"action", "actions"}) and asks_sequence


def _lexical_candidates(question, chunks, limit):
    candidates = []
    for chunk in chunks:
        score = lexical_score(question, chunk.content)
        if score > 0:
            candidates.append((score, chunk))
    candidates.sort(key=lambda pair: (-pair[0], pair[1].chunk_index))
    return candidates[:limit]


def answer_question(conversation, question):
    allowed_sources = list(_scope_sources(conversation).select_related("video").order_by("created_at", "id"))
    allowed_ids = [source.id for source in allowed_sources]
    chunks = list(models.KnowledgeChunk.objects.filter(
        source_id__in=allowed_ids,
        source__project=conversation.project,
        source__deleted_at__isnull=True,
    ).select_related("source").order_by("chunk_index"))
    retrieval_method = "lexical_sqlite"
    model_name = ""
    candidates = []

    video_sources = {source.id: source for source in allowed_sources if source.source_type == "video"}
    if conversation.video_id and video_sources and _annotation_sequence_question(question):
        sequence_chunks = [chunk for chunk in chunks if chunk.annotation_id]
        candidates = [(1.0, chunk) for chunk in sorted(
            sequence_chunks,
            key=lambda chunk: (chunk.video_start_seconds if chunk.video_start_seconds is not None else -1, chunk.id),
        )]
        candidates = candidates[:12]
        retrieval_method = "structured_video_annotations"
    else:
        dense_sources = [source for source in allowed_sources if source.index_backend == "chroma_sentence_transformers"]
        if dense_sources and len(dense_sources) == len(allowed_sources):
            provider, store = _local_vector_components()
            if provider is not None and store is not None:
                query_vector = provider.embed([question])[0]
                dense_results = store.query(
                    question, query_vector, conversation.project_id, allowed_ids, 12,
                )
                allowed_chunk_map = {chunk.id: chunk for chunk in chunks}
                candidates = [
                    (max(0.0, 1.0 - result["distance"]), allowed_chunk_map[result["id"]])
                    for result in dense_results
                    if result["id"] in allowed_chunk_map
                ]
                retrieval_method = "dense_vector"
                model_name = provider.model_name
        if not candidates and retrieval_method != "structured_video_annotations":
            candidates = _lexical_candidates(question, chunks, 12)
            retrieval_method = "lexical_sqlite"
            model_name = ""

    citations = []
    for score, chunk in candidates:
        if retrieval_method == "lexical_sqlite" and score < 0.05:
            continue
        source = chunk.source
        citations.append({
            "citation_id": f"C{len(citations) + 1}",
            "source_id": source.id,
            "source_type": chunk.source_type,
            "source_title": source.title,
            "annotation_id": chunk.annotation_id or None,
            "video_id": source.video_id,
            "start_seconds": chunk.video_start_seconds,
            "end_seconds": chunk.video_end_seconds,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "snippet": chunk.content[:1200],
            "content_sha256": chunk.content_sha256,
            "score": round(score, 4),
            "_chunk": chunk,
        })

    if not citations:
        answer = "Insufficient evidence was found in the selected, indexed sources. Add or select relevant evidence and try again."
        if conversation.scope in {"selected_video", "video_and_documents"}:
            answer += " AURA cannot visually inspect this video unless its pixels are available and a real visual-analysis workflow has processed them."
        evidence_status = "insufficient_evidence"
    else:
        evidence_lines = []
        for citation in citations:
            location = (
                f"page {citation['page_start']}"
                if citation["page_start"] is not None
                else f"{citation['start_seconds']:.3f}–{citation['end_seconds']:.3f} seconds"
                if citation["start_seconds"] is not None
                else "source metadata"
            )
            evidence_lines.append(
                f"{citation['source_title']} ({location}): {citation['snippet']} [{citation['citation_id']}]"
            )
        answer = (
            "Retrieved evidence (deterministic extractive mode):\n\n"
            + "\n\n".join(evidence_lines)
            + "\n\nVideo citations refer to stored metadata/annotation records, not visual inspection."
        )
        evidence_status = "supported"

    return {
        "answer": answer,
        "answer_mode": "deterministic_extractive",
        "evidence_status": evidence_status,
        "citations": citations,
        "retrieval": {
            "method": retrieval_method,
            "candidate_count": len(candidates),
            "used_lexical_fallback": retrieval_method == "lexical_sqlite",
            "embedding_model": model_name or None,
        },
        "warnings": [
            warning
            for source in allowed_sources
            for warning in json.loads(source.warnings_json)
        ],
    }


def persist_message_result(conversation, question, result):
    user_message = models.KnowledgeMessage.objects.create(
        conversation=conversation, role="user", content=question,
    )
    assistant_message = models.KnowledgeMessage.objects.create(
        conversation=conversation,
        role="assistant",
        content=result["answer"],
        answer_mode=result["answer_mode"],
        evidence_status=result["evidence_status"],
        retrieval_json=_json_dump({key: value for key, value in result.items() if key not in {"answer", "citations"}}),
    )
    for citation in result["citations"]:
        chunk = citation.pop("_chunk")
        models.KnowledgeCitation.objects.create(
            message=assistant_message,
            chunk=chunk,
            citation_id=citation["citation_id"],
            source_id_snapshot=citation["source_id"],
            source_title_snapshot=citation["source_title"],
            source_type_snapshot=citation["source_type"],
            snippet=citation["snippet"],
            page_start=citation["page_start"],
            page_end=citation["page_end"],
            video_id_snapshot=citation["video_id"] or "",
            video_start_seconds=citation["start_seconds"],
            video_end_seconds=citation["end_seconds"],
            annotation_id_snapshot=citation["annotation_id"] or "",
            content_sha256=citation["content_sha256"],
            score=citation["score"],
        )
    if conversation.title == "New conversation":
        conversation.title = question[:157] + "..." if len(question) > 160 else question
    conversation.save(update_fields=["title", "updated_at"])
    result["conversation_id"] = conversation.id
    result["messages"] = [serialize_message(user_message), serialize_message(assistant_message)]
    return result


def serialize_message(message):
    citations = []
    if message.role == "assistant":
        for citation in message.citations.all():
            citations.append({
                "citation_id": citation.citation_id,
                "source_id": citation.source_id_snapshot,
                "source_title": citation.source_title_snapshot,
                "source_type": citation.source_type_snapshot,
                "annotation_id": citation.annotation_id_snapshot or None,
                "video_id": citation.video_id_snapshot or None,
                "start_seconds": citation.video_start_seconds,
                "end_seconds": citation.video_end_seconds,
                "page_start": citation.page_start,
                "page_end": citation.page_end,
                "snippet": citation.snippet,
                "content_sha256": citation.content_sha256,
                "score": citation.score,
                "stale": citation.chunk_id is None,
            })
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "answer_mode": message.answer_mode,
        "evidence_status": message.evidence_status,
        "retrieval": json.loads(message.retrieval_json),
        "citations": citations,
        "created_at": message.created_at.isoformat(),
    }


def serialize_conversation(conversation, include_messages=False):
    result = {
        "id": conversation.id,
        "project_id": conversation.project_id,
        "video_id": conversation.video_id,
        "title": conversation.title,
        "scope": conversation.scope,
        "selected_source_ids": json.loads(conversation.selected_source_ids_json),
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }
    if include_messages:
        result["messages"] = [serialize_message(message) for message in conversation.messages.prefetch_related("citations").all()]
    return result


def delete_source(source):
    chunk_rows = list(source.chunks.values("id", "embedding_model"))
    _delete_vector_records(chunk_rows)
    source.chunks.all().delete()
    if source.storage_key:
        media_root = Path(MEDIA_DIR).resolve()
        target = (media_root / source.storage_key).resolve()
        if media_root in target.parents and target.is_file():
            target.unlink()
    source.storage_key = ""
    source.status = "deleted"
    source.deleted_at = timezone.now()
    source.chunk_count = 0
    source.save(update_fields=["storage_key", "status", "deleted_at", "chunk_count"])
