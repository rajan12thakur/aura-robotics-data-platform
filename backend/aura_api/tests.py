import hashlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from . import data_pipeline, knowledge_service, views
from .models import (
    Annotation, AnnotationRevision, AuditEvent, DatasetExport, KnowledgeChunk, KnowledgeConversation,
    KnowledgeSource, Project, RLExperiment, Video,
)
from .rl import GridPickPlace, run_experiment
from aura_rag.evaluation import evaluate_retrieval_fixture, lexical_fixture_retriever


class AuraApiTests(TestCase):
    def setUp(self):
        self.annotator = User.objects.create_user(username="annotator", password="test-password")
        Group.objects.get_or_create(name="Annotator")
        self.annotator.groups.add(Group.objects.get(name="Annotator"))
        self.client.force_login(self.annotator)
        self.project = Project.objects.create(name="Test project")
        self.video = Video.objects.create(
            project=self.project, original_filename="test.mp4", duration_seconds=20, status="metadata_ready",
        )

    def post_json(self, path, data):
        return self.client.post(path, data=json.dumps(data), content_type="application/json")

    def make_pdf(self, text="Before a pick, verify the gripper is open and the workspace is clear.", password=None):
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        if text is not None:
            font = DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            })
            resources = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
            })
            stream = DecodedStreamObject()
            escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1"))
            page[NameObject("/Resources")] = resources
            page[NameObject("/Contents")] = writer._add_object(stream)
        if password:
            writer.encrypt(password)
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()

    def test_unauthenticated_api_request_is_rejected(self):
        response = Client().get("/api/v1/projects")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "AUTHENTICATION_REQUIRED")

    def test_health_and_readiness_are_public_diagnostics(self):
        client = Client()
        self.assertEqual(client.get("/api/v1/health").status_code, 200)
        self.assertEqual(client.get("/api/v1/health/ready").status_code, 200)

    def test_grid_environment_has_defined_success_and_invalid_action_rewards(self):
        env = GridPickPlace(max_steps=10)
        self.assertEqual(env.reset(), (0, 2, 0))
        state, reward, done, info = env.step("up")
        self.assertEqual((state, reward, done, info["event"]), ((0, 2, 0), -1.0, False, "boundary"))
        for action in ("right", "right", "pick", "down", "down", "place"):
            state, reward, done, _ = env.step(action)
        self.assertEqual(state, (8, 8, 0))
        self.assertEqual(reward, 19.9)
        self.assertTrue(done)

    def test_q_learning_is_reproducible_and_evaluated_against_baseline(self):
        first = run_experiment("q_learning", episodes=100, seed=123, max_steps=30)
        second = run_experiment("q_learning", episodes=100, seed=123, max_steps=30)
        self.assertEqual(first["metrics"], second["metrics"])
        self.assertEqual(first["policy"], second["policy"])
        self.assertEqual(first["metrics"]["evaluation"]["baseline_policy"]["success_rate"], 1.0)
        self.assertEqual(first["metrics"]["evaluation"]["learned_policy"]["episode_count"], 20)
        self.assertTrue(first["policy"])

    def test_video_knowledge_is_persisted_and_cites_actual_annotations(self):
        for index, action in enumerate(("approach", "grasp", "place")):
            Annotation.objects.create(
                project=self.project, video=self.video, start_time=float(index),
                end_time=float(index + 1), action_label=action, status="approved",
            )
        indexed = self.client.post(f"/api/v1/videos/{self.video.id}/knowledge/index")
        self.assertEqual(indexed.status_code, 200)
        source = KnowledgeSource.objects.get(pk=indexed.json()["id"])
        self.assertEqual(source.status, "indexed")
        self.assertEqual(source.chunk_count, 4)
        self.assertIn("stored video metadata and database annotations", source.metadata_json)
        self.assertIn("Video pixels are unavailable", source.warnings_json)

        conversation = self.post_json(
            f"/api/v1/projects/{self.project.id}/knowledge/conversations",
            {"video_id": self.video.id, "scope": "selected_video", "source_ids": []},
        )
        self.assertEqual(conversation.status_code, 201)
        response = self.post_json(
            f"/api/v1/knowledge/conversations/{conversation.json()['id']}/messages",
            {"question": "List the actions recorded for this video in chronological order."},
        )
        self.assertEqual(response.status_code, 201)
        citations = response.json()["citations"]
        actual_ids = list(Annotation.objects.filter(video=self.video).order_by("start_time").values_list("id", flat=True))
        self.assertEqual([citation["annotation_id"] for citation in citations], actual_ids)
        self.assertTrue(all(citation["start_seconds"] is not None for citation in citations))
        self.assertEqual(response.json()["retrieval"]["method"], "structured_video_annotations")
        self.assertIn("not visual inspection", response.json()["answer"])
        persisted = self.client.get(f"/api/v1/knowledge/conversations/{conversation.json()['id']}")
        self.assertEqual(len(persisted.json()["messages"]), 2)

    def test_dense_index_persists_model_provenance_and_revalidates_scope(self):
        source = KnowledgeSource.objects.create(
            project=self.project,
            source_type="pdf",
            title="synthetic-source.pdf",
            checksum_sha256="a" * 64,
            status="indexed",
            index_status="processing",
        )
        chunk_values = [{
            "content": "Before a pick, verify the gripper is open and workspace is clear.",
            "content_sha256": hashlib.sha256(b"Before a pick, verify the gripper is open and workspace is clear.").hexdigest(),
            "page_start": 1,
            "page_end": 1,
        }]

        class FakeProvider:
            model_name = "synthetic-test-embedding"
            model_revision = "fixture-revision-1"

            def embed(self, texts):
                return [[0.6, 0.8] for _ in texts]

        class FakeStore:
            def upsert(self, ids, texts, embeddings, metadatas):
                self.chunk_id = ids[0]
                self.metadata = metadatas[0]
                self.embedding = embeddings[0]

            def delete(self, ids):
                self.deleted_ids = ids

            def query(self, text, embedding, project_id, source_ids, limit):
                self.query_args = (project_id, source_ids, limit)
                return [
                    {"id": self.chunk_id, "distance": 0.1},
                    {"id": "f" * 64, "distance": 0.0},
                ]

        store = FakeStore()
        provider = FakeProvider()
        available = {
            "available": True,
            "model_configured": True,
            "sentence_transformers_installed": True,
            "chroma_installed": True,
        }
        with patch.object(knowledge_service, "dense_backend_status", return_value=available), patch.object(
            knowledge_service, "_local_vector_components", return_value=(provider, store),
        ):
            rows, warning = knowledge_service._persist_chunks(source, chunk_values)

            source.refresh_from_db()
            chunk = source.chunks.get()
            self.assertIsNone(warning)
            self.assertEqual(source.index_status, "ready")
            self.assertEqual(source.dense_index_status, "ready")
            self.assertEqual(source.index_backend, "chroma_sentence_transformers")
            self.assertEqual(source.embedding_model_revision, "fixture-revision-1")
            self.assertEqual(source.embedding_dimensions, 2)
            self.assertEqual(chunk.source_checksum_sha256, source.checksum_sha256)
            self.assertEqual(chunk.index_version, source.index_version)
            self.assertEqual(chunk.embedding_model_revision, "fixture-revision-1")
            self.assertEqual(store.metadata["project_id"], self.project.id)
            self.assertEqual(store.metadata["source_id"], source.id)
            self.assertEqual(store.metadata["source_checksum_sha256"], source.checksum_sha256)
            self.assertEqual(store.metadata["chunk_checksum_sha256"], chunk.content_sha256)
            self.assertEqual(store.metadata["index_version"], source.index_version)

            conversation = self.post_json(
                f"/api/v1/projects/{self.project.id}/knowledge/conversations",
                {"scope": "documents_only", "source_ids": [source.id]},
            )
            response = self.post_json(
                f"/api/v1/knowledge/conversations/{conversation.json()['id']}/messages",
                {"question": "Which manipulator condition precedes a grasp?"},
            )
            self.assertEqual(response.status_code, 201, response.content)
            self.assertEqual(response.json()["retrieval"]["method"], "dense_local")
            self.assertEqual([item["source_id"] for item in response.json()["citations"]], [source.id])
            self.assertEqual(store.query_args, (self.project.id, [source.id], 12))

            provider.model_revision = "fixture-revision-2"
            fallback_response = self.post_json(
                f"/api/v1/knowledge/conversations/{conversation.json()['id']}/messages",
                {"question": "Which manipulator condition precedes a grasp?"},
            )
            self.assertEqual(fallback_response.status_code, 201)
            self.assertEqual(fallback_response.json()["retrieval"]["method"], "lexical_sqlite")
            self.assertTrue(any("current model/index" in warning for warning in fallback_response.json()["warnings"]))
            source.refresh_from_db()
            self.assertEqual(source.dense_index_status, "stale")

    def test_dense_index_failure_keeps_lexical_index_available(self):
        source = KnowledgeSource.objects.create(
            project=self.project,
            source_type="pdf",
            title="synthetic-fallback.pdf",
            checksum_sha256="b" * 64,
            status="processing",
            index_status="processing",
        )

        class InvalidProvider:
            model_name = "synthetic-invalid"
            model_revision = "bad-fixture"

            def embed(self, texts):
                return [[1.0], [1.0, 2.0]]

        class UnusedStore:
            def upsert(self, *args):
                raise AssertionError("Invalid vectors must not be written to Chroma.")

            def delete(self, ids):
                self.deleted_ids = ids

        with patch.object(knowledge_service, "dense_backend_status", return_value={
            "available": True,
            "model_configured": True,
            "sentence_transformers_installed": True,
            "chroma_installed": True,
        }), patch.object(
            knowledge_service, "_local_vector_components", return_value=(InvalidProvider(), UnusedStore()),
        ):
            _, warning = knowledge_service._persist_chunks(source, [
                {"content": "A synthetic fallback source has clear evidence.", "content_sha256": "c" * 64},
                {"content": "Another valid text chunk.", "content_sha256": "d" * 64},
            ])
        source.refresh_from_db()
        self.assertEqual(source.status, "processing")
        self.assertEqual(source.index_status, "ready")
        self.assertEqual(source.dense_index_status, "failed")
        self.assertEqual(source.index_backend, "lexical_sqlite")
        self.assertIsNone(source.embedding_dimensions)
        self.assertIn("lexical indexing remains available", warning)

    def test_dense_index_without_runtime_components_is_not_marked_ready(self):
        source = KnowledgeSource.objects.create(
            project=self.project,
            source_type="pdf",
            title="synthetic-unavailable-dense.pdf",
            checksum_sha256="e" * 64,
            status="processing",
            index_status="processing",
        )
        with patch.object(knowledge_service, "dense_backend_status", return_value={
            "available": True,
            "model_configured": True,
            "sentence_transformers_installed": True,
            "chroma_installed": True,
        }), patch.object(knowledge_service, "_local_vector_components", return_value=(None, None)):
            _, warning = knowledge_service._persist_chunks(source, [{
                "content": "Synthetic text remains searchable in lexical mode.",
                "content_sha256": "f" * 64,
            }])
        source.refresh_from_db()
        self.assertEqual(source.index_status, "ready")
        self.assertEqual(source.dense_index_status, "failed")
        self.assertEqual(source.index_backend, "lexical_sqlite")
        self.assertIn("lexical indexing remains available", warning)

    def test_dense_vector_deletion_supports_legacy_model_collection(self):
        class FakeStore:
            deleted_ids = None

            def delete(self, ids):
                self.deleted_ids = ids

        store = FakeStore()
        with patch.object(knowledge_service, "configured_vector_store", return_value=store) as factory:
            knowledge_service._delete_vector_records([{
                "id": "legacy-chunk",
                "embedding_model": "legacy-model",
                "embedding_model_revision": "",
            }])
        factory.assert_called_once_with(
            knowledge_service.VECTOR_STORE_DIR, "legacy-model", "",
        )
        self.assertEqual(store.deleted_ids, ["legacy-chunk"])

    def test_synthetic_retrieval_evaluation_fixture_reports_computed_metrics(self):
        fixture_path = Path(__file__).resolve().parents[2] / "data" / "examples" / "rag_retrieval_evaluation.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        metrics = evaluate_retrieval_fixture(fixture, lexical_fixture_retriever, top_k=2)
        self.assertEqual(metrics["positive_question_count"], 3)
        self.assertEqual(metrics["negative_question_count"], 1)
        self.assertEqual(metrics["recall_at_k"], 1.0)
        self.assertEqual(metrics["negative_abstention_rate"], 1.0)

    def test_pdf_upload_citation_scope_abstention_duplicate_and_deletion(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        with patch("aura_api.views.MEDIA_DIR", Path(temporary.name)), patch(
            "aura_api.knowledge_service.MEDIA_DIR", Path(temporary.name),
        ):
            content = self.make_pdf()
            upload = SimpleUploadedFile("robot-guideline.pdf", content, content_type="application/pdf")
            response = self.client.post(f"/api/v1/projects/{self.project.id}/knowledge/sources", {"file": upload})
            self.assertEqual(response.status_code, 201, response.content)
            source = KnowledgeSource.objects.get(pk=response.json()["id"])
            self.assertEqual(source.status, "indexed")
            self.assertEqual(source.page_count, 1)
            self.assertEqual(source.index_backend, "lexical_sqlite")
            self.assertIsNone(source.embedding_dimensions)
            self.assertEqual(source.index_status, "ready")
            self.assertEqual(source.dense_index_status, "not_configured")
            self.assertEqual(source.checksum_sha256, hashlib.sha256(content).hexdigest())
            chunk = source.chunks.get()
            self.assertEqual((chunk.page_start, chunk.page_end), (1, 1))
            self.assertIn("workspace is clear", chunk.content)

            duplicate = SimpleUploadedFile("duplicate.pdf", content, content_type="application/pdf")
            duplicate_response = self.client.post(f"/api/v1/projects/{self.project.id}/knowledge/sources", {"file": duplicate})
            self.assertEqual(duplicate_response.status_code, 409)

            foreign_project = Project.objects.create(name="Other project")
            foreign_source = KnowledgeSource.objects.create(
                project=foreign_project, source_type="pdf", title="private.pdf",
                checksum_sha256="f" * 64, status="indexed", chunk_count=1,
            )
            KnowledgeChunk.objects.create(
                id="e" * 64, source=foreign_source, chunk_index=0, source_type="pdf",
                content="Orbit-only secret phrase from another project",
                content_sha256="d" * 64,
            )
            wrong_scope = self.post_json(
                f"/api/v1/projects/{self.project.id}/knowledge/conversations",
                {"scope": "documents_only", "source_ids": [foreign_source.id]},
            )
            self.assertEqual(wrong_scope.status_code, 404)

            created = self.post_json(
                f"/api/v1/projects/{self.project.id}/knowledge/conversations",
                {"scope": "documents_only", "source_ids": [source.id]},
            )
            self.assertEqual(created.status_code, 201)
            conversation_id = created.json()["id"]
            grounded = self.post_json(
                f"/api/v1/knowledge/conversations/{conversation_id}/messages",
                {"question": "What should be verified before a pick?"},
            )
            self.assertEqual(grounded.status_code, 201)
            citation = grounded.json()["citations"][0]
            self.assertEqual(citation["page_start"], 1)
            self.assertEqual(citation["source_id"], source.id)
            self.assertGreater(citation["score"], 0)
            self.assertEqual(grounded.json()["answer_mode"], "deterministic_extractive")

            abstained = self.post_json(
                f"/api/v1/knowledge/conversations/{conversation_id}/messages",
                {"question": "What is the capital of France?"},
            )
            self.assertEqual(abstained.json()["evidence_status"], "insufficient_evidence")
            self.assertEqual(abstained.json()["citations"], [])

            admin_group, _ = Group.objects.get_or_create(name="Administrator")
            self.annotator.groups.add(admin_group)
            deleted = self.client.delete(f"/api/v1/knowledge/sources/{source.id}/lifecycle")
            self.assertEqual(deleted.status_code, 200)
            self.assertEqual(KnowledgeChunk.objects.filter(source=source).count(), 0)
            self.assertEqual(KnowledgeSource.objects.get(pk=source.id).status, "deleted")
            self.assertEqual(self.client.get(f"/api/v1/projects/{self.project.id}/knowledge/sources").json(), [])
            old_conversation = self.client.get(f"/api/v1/knowledge/conversations/{conversation_id}").json()
            stored_citation = old_conversation["messages"][1]["citations"][0]
            self.assertTrue(stored_citation["stale"])

    def test_pdf_failure_states_and_reindex_are_persisted_without_duplicate_chunks(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        with patch("aura_api.views.MEDIA_DIR", Path(temporary.name)), patch(
            "aura_api.knowledge_service.MEDIA_DIR", Path(temporary.name),
        ):
            upload = SimpleUploadedFile("guideline.pdf", self.make_pdf(), content_type="application/pdf")
            response = self.client.post(f"/api/v1/projects/{self.project.id}/knowledge/sources", {"file": upload})
            source_id = response.json()["id"]
            source = KnowledgeSource.objects.get(pk=source_id)
            initial_ids = list(source.chunks.values_list("id", flat=True))
            retried = self.client.post(f"/api/v1/knowledge/sources/{source_id}/lifecycle")
            self.assertEqual(retried.status_code, 200)
            updated_source = KnowledgeSource.objects.get(pk=source_id)
            self.assertEqual(updated_source.chunk_count, 1)
            self.assertEqual(updated_source.source_version, 2)
            new_ids = list(KnowledgeChunk.objects.filter(source_id=source_id).values_list("id", flat=True))
            self.assertEqual(len(new_ids), 1)
            self.assertNotEqual(new_ids, initial_ids)
            self.assertEqual(source.jobs.count(), 2)

            encrypted = SimpleUploadedFile(
                "encrypted.pdf", self.make_pdf(password="secret"), content_type="application/pdf",
            )
            encrypted_response = self.client.post(
                f"/api/v1/projects/{self.project.id}/knowledge/sources", {"file": encrypted},
            )
            encrypted_source = KnowledgeSource.objects.get(pk=encrypted_response.json()["id"])
            self.assertEqual(encrypted_source.status, "failed")
            self.assertIn("encrypted", encrypted_source.error_summary)

            scanned = SimpleUploadedFile(
                "scanned.pdf", self.make_pdf(text=None), content_type="application/pdf",
            )
            scanned_response = self.client.post(
                f"/api/v1/projects/{self.project.id}/knowledge/sources", {"file": scanned},
            )
            scanned_source = KnowledgeSource.objects.get(pk=scanned_response.json()["id"])
            self.assertEqual(scanned_source.status, "partially_indexed")
            self.assertEqual(scanned_source.chunk_count, 0)
            self.assertIn("OCR is not configured", scanned_source.warnings_json)

            corrupt = SimpleUploadedFile(
                "corrupt.pdf", b"%PDF-1.4\ninvalid structure", content_type="application/pdf",
            )
            corrupt_response = self.client.post(
                f"/api/v1/projects/{self.project.id}/knowledge/sources", {"file": corrupt},
            )
            corrupt_source = KnowledgeSource.objects.get(pk=corrupt_response.json()["id"])
            self.assertEqual(corrupt_source.status, "failed")
            self.assertEqual(corrupt_source.index_status, "failed")
            self.assertEqual(corrupt_source.dense_index_status, "failed")
            self.assertIn("could not be read", corrupt_source.error_summary)

    def test_invalid_pdf_signature_is_rejected_before_storage(self):
        invalid = SimpleUploadedFile("not-really.pdf", b"not a pdf", content_type="application/pdf")
        response = self.client.post(f"/api/v1/projects/{self.project.id}/knowledge/sources", {"file": invalid})
        self.assertEqual(response.status_code, 415)
        self.assertFalse(KnowledgeSource.objects.exists())

    def test_video_upload_checks_content_safely_stores_and_streams_ranges(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        media_dir = Path(temporary.name)
        content = b"\x00\x00\x00\x18ftypisom" + b"synthetic-video-data"
        with patch("aura_api.views.MEDIA_DIR", media_dir):
            upload = SimpleUploadedFile(
                "..\\unsafe-name.mp4", content, content_type="video/mp4",
            )
            response = self.client.post(
                f"/api/v1/projects/{self.project.id}/videos", {"file": upload},
            )
            self.assertEqual(response.status_code, 201, response.content)
            video = Video.objects.get(pk=response.json()["id"])
            self.assertEqual(video.original_filename, "unsafe-name.mp4")
            self.assertTrue(video.storage_key)
            self.assertNotIn("unsafe-name", video.storage_key)
            self.assertEqual(video.checksum_sha256, hashlib.sha256(content).hexdigest())
            self.assertTrue((media_dir / video.storage_key).is_file())

            stream = self.client.get(
                f"/api/v1/videos/{video.id}/stream",
                HTTP_RANGE="bytes=4-11",
            )
            self.assertEqual(stream.status_code, 206)
            self.assertEqual(stream["Content-Range"], f"bytes 4-11/{len(content)}")
            self.assertEqual(stream["Content-Length"], "8")
            self.assertEqual(b"".join(stream.streaming_content), content[4:12])
            stream.close()

            invalid = SimpleUploadedFile(
                "fake.mp4", b"not a video", content_type="video/mp4",
            )
            rejected = self.client.post(
                f"/api/v1/projects/{self.project.id}/videos", {"file": invalid},
            )
            self.assertEqual(rejected.status_code, 415)
            self.assertEqual(rejected.json()["error"]["code"], "VIDEO_SIGNATURE_INVALID")
            self.assertEqual(Video.objects.count(), 2)

    def test_pipeline_builds_idempotent_medallion_outputs_and_quarantines_bad_rows(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        first = Annotation.objects.create(
            project=self.project, video=self.video,
            start_time=1, end_time=2, action_label="reach",
            object_label="part", actor_id="annotator", status="approved",
        )
        duplicate = Annotation.objects.create(
            project=self.project, video=self.video,
            start_time=1, end_time=2, action_label="reach",
            object_label="part", actor_id="annotator", status="approved",
        )
        invalid = Annotation.objects.create(
            project=self.project, video=self.video,
            start_time=3, end_time=4, action_label="unknown-label",
            status="draft",
        )
        pipeline_root = Path(temporary.name)
        with patch.object(data_pipeline, "PIPELINE_DIR", pipeline_root):
            result = data_pipeline.run_pipeline(self.project.id)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["output_counts"], {
                "bronze": 3, "silver": 1, "quarantined": 2,
            })
            self.assertEqual(result["gold"]["class_balance"], {"reach": 1})
            self.assertTrue(result["gold"]["dataset_export_ready"])
            self.assertNotIn("storage_key", json.dumps(result))
            silver_path = pipeline_root / result["outputs"]["silver.json"]
            silver_rows = json.loads(silver_path.read_text(encoding="utf-8"))
            self.assertIn(silver_rows[0]["annotation_id"], {first.id, duplicate.id})
            self.assertNotIn("notes", silver_rows[0])
            quarantine = json.loads(
                (pipeline_root / result["outputs"]["quarantine.json"]).read_text(encoding="utf-8"),
            )
            reasons = {reason for item in quarantine for reason in item["reasons"]}
            self.assertIn("duplicate_annotation", reasons)
            self.assertIn("unknown_action_label", reasons)

            repeated = data_pipeline.run_pipeline(self.project.id)
            self.assertEqual(repeated, result)
            (pipeline_root / result["outputs"]["gold.json"]).write_text("tampered", encoding="utf-8")
            repaired = data_pipeline.run_pipeline(self.project.id)
            self.assertEqual(repaired["batch_id"], result["batch_id"])
            self.assertEqual(
                hashlib.sha256((pipeline_root / result["outputs"]["gold.json"]).read_bytes()).hexdigest(),
                result["output_sha256"]["gold.json"],
            )
        self.assertTrue(Annotation.objects.filter(pk=invalid.id).exists())

    def test_pipeline_records_failure_and_successful_retry(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        pipeline_root = Path(temporary.name)
        original_write = data_pipeline._write_atomic
        failed_once = False

        def fail_on_silver(path, content):
            nonlocal failed_once
            if path.name == "silver.json" and not failed_once:
                failed_once = True
                raise OSError("synthetic write failure")
            return original_write(path, content)

        with patch.object(data_pipeline, "PIPELINE_DIR", pipeline_root):
            with patch.object(data_pipeline, "_write_atomic", side_effect=fail_on_silver):
                with self.assertRaises(OSError):
                    data_pipeline.run_pipeline(self.project.id)
            runs = data_pipeline.list_pipeline_runs(self.project.id)
            self.assertEqual(runs[0]["status"], "failed")
            self.assertIn("OSError", runs[0]["error_summary"])
            retried = data_pipeline.run_pipeline(self.project.id)
            self.assertEqual(retried["status"], "succeeded")
            self.assertEqual(retried["output_counts"]["silver"], 0)

    def test_pipeline_api_persists_run_metadata_and_requires_quality_role(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        with patch.object(data_pipeline, "PIPELINE_DIR", Path(temporary.name)):
            response = self.client.post(f"/api/v1/projects/{self.project.id}/pipeline/runs")
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()["status"], "succeeded")
            self.assertEqual(response.json()["output_counts"]["silver"], 0)
            self.assertFalse(response.json()["gold"]["dataset_export_ready"])
            history = self.client.get(f"/api/v1/projects/{self.project.id}/pipeline/runs")
            self.assertEqual(history.status_code, 200)
            self.assertEqual(history.json()[0]["batch_id"], response.json()["batch_id"])
            self.assertTrue(AuditEvent.objects.filter(
                project=self.project, event_type="pipeline.run.succeeded",
            ).exists())
        auditor = User.objects.create_user(username="pipeline-no-role")
        self.client.force_login(auditor)
        forbidden = self.client.post(f"/api/v1/projects/{self.project.id}/pipeline/runs")
        self.assertEqual(forbidden.status_code, 403)

    def test_pipeline_management_command_emits_run_manifest_json(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = io.StringIO()
        with patch.object(data_pipeline, "PIPELINE_DIR", Path(temporary.name)):
            call_command(
                "aura_run_pipeline",
                project_id=self.project.id,
                stdout=output,
            )
        manifest = json.loads(output.getvalue())
        self.assertEqual(manifest["project_id"], self.project.id)
        self.assertEqual(manifest["status"], "succeeded")

    def test_project_knowledge_retrieval_does_not_cross_project_boundary(self):
        foreign_project = Project.objects.create(name="Separate project")
        source = KnowledgeSource.objects.create(
            project=foreign_project, source_type="pdf", title="other.pdf",
            checksum_sha256="a" * 64, status="indexed", chunk_count=1,
        )
        KnowledgeChunk.objects.create(
            id="b" * 64, source=source, chunk_index=0, source_type="pdf",
            content="quasar-only confidential material",
            content_sha256="c" * 64,
        )
        conversation = self.post_json(
            f"/api/v1/projects/{self.project.id}/knowledge/conversations",
            {"scope": "project_knowledge", "source_ids": []},
        )
        result = self.post_json(
            f"/api/v1/knowledge/conversations/{conversation.json()['id']}/messages",
            {"question": "Explain the quasar-only confidential material"},
        ).json()
        self.assertEqual(result["evidence_status"], "insufficient_evidence")
        self.assertEqual(result["citations"], [])

    def test_login_requires_csrf_and_creates_authenticated_session(self):
        user = User.objects.create_user(username="login-user", password="test-password")
        client = Client(enforce_csrf_checks=True)
        client.get("/api/v1/auth/csrf")
        token = client.cookies["csrftoken"].value
        rejected = client.post(
            "/api/v1/auth/login", data=json.dumps({"username": user.username, "password": "test-password"}),
            content_type="application/json",
        )
        self.assertEqual(rejected.status_code, 403)
        accepted = client.post(
            "/api/v1/auth/login", data=json.dumps({"username": user.username, "password": "test-password"}),
            content_type="application/json", HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertTrue(client.get("/api/v1/auth/me").json()["authenticated"])

    def test_invalid_login_does_not_create_an_authenticated_session(self):
        user = User.objects.create_user(username="invalid-login-user", password="test-password")
        client = Client(enforce_csrf_checks=True)
        client.get("/api/v1/auth/csrf")
        token = client.cookies["csrftoken"].value
        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": user.username, "password": "incorrect-password"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "INVALID_CREDENTIALS")
        self.assertEqual(client.get("/api/v1/auth/me").status_code, 401)
        self.assertEqual(client.get("/api/v1/projects").status_code, 401)

    def test_logout_invalidates_the_frontend_session(self):
        user = User.objects.create_user(username="logout-user", password="test-password")
        client = Client(enforce_csrf_checks=True)
        client.get("/api/v1/auth/csrf")
        token = client.cookies["csrftoken"].value
        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": user.username, "password": "test-password"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(login_response.status_code, 200)
        session_cookie = login_response.cookies["sessionid"]
        self.assertTrue(session_cookie["httponly"])
        self.assertEqual(session_cookie["samesite"], "Lax")
        self.assertEqual(client.get("/api/v1/auth/me").status_code, 200)
        self.assertEqual(client.get("/api/v1/projects").status_code, 200)

        logout_response = client.post(
            "/api/v1/auth/logout",
            data="{}",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )
        self.assertEqual(logout_response.status_code, 200)
        self.assertFalse(logout_response.json()["authenticated"])
        self.assertEqual(client.get("/api/v1/auth/me").status_code, 401)
        self.assertEqual(client.get("/api/v1/projects").status_code, 401)

    def test_admin_login_uses_the_same_django_session_as_the_api(self):
        user = User(
            username="admin-session-user",
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
        user.set_password("test-password")
        user.save()
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get("/admin/").status_code, 302)
        self.assertEqual(client.get("/admin/login/").status_code, 200)

        admin_login = client.post(
            "/admin/login/",
            {
                "username": user.username,
                "password": "test-password",
                "next": "/admin/",
                "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
            },
        )
        self.assertEqual(admin_login.status_code, 302)
        api_identity = client.get("/api/v1/auth/me")
        self.assertEqual(api_identity.status_code, 200)
        self.assertEqual(api_identity.json()["user"]["username"], user.username)
        self.assertIn("Administrator", api_identity.json()["user"]["roles"])
        self.assertEqual(client.get("/admin/").status_code, 200)

    def test_frontend_origin_cors_preflight_allows_credentials_and_csrf_header(self):
        client = Client()
        response = client.options(
            "/api/v1/projects",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-csrftoken",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:5173")
        self.assertEqual(response["Access-Control-Allow-Credentials"], "true")
        self.assertIn("x-csrftoken", response["Access-Control-Allow-Headers"])

    def test_annotation_creation_enforces_role_and_interval(self):
        invalid = self.post_json(
            f"/api/v1/videos/{self.video.id}/annotations",
            {"start_time": -1, "end_time": 1, "action_label": "reach"},
        )
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["error"]["code"], "INVALID_INTERVAL")
        valid = self.post_json(
            f"/api/v1/videos/{self.video.id}/annotations",
            {"start_time": 1, "end_time": 2, "action_label": "reach"},
        )
        self.assertEqual(valid.status_code, 201)
        self.assertEqual(AnnotationRevision.objects.filter(annotation_id=valid.json()["id"]).count(), 1)

    def test_role_is_required_for_project_creation(self):
        response = self.post_json("/api/v1/projects", {"name": "Forbidden"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "PERMISSION_DENIED")

    def test_export_download_is_role_protected(self):
        response = self.client.get("/api/v1/exports/missing-release/download")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "PERMISSION_DENIED")

    def test_rl_experiment_endpoint_enforces_role_and_persists_results(self):
        denied = self.post_json(
            f"/api/v1/projects/{self.project.id}/rl-experiments",
            {"algorithm": "q_learning", "episodes": 100, "seed": 17},
        )
        self.assertEqual(denied.status_code, 403)

        engineer = Group.objects.create(name="ML Engineer")
        self.annotator.groups.add(engineer)
        response = self.post_json(
            f"/api/v1/projects/{self.project.id}/rl-experiments",
            {"algorithm": "q_learning", "episodes": 100, "seed": 17},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["status"], "succeeded")
        self.assertEqual(response.json()["metrics"]["evaluation"]["baseline_policy"]["success_rate"], 1.0)
        run = RLExperiment.objects.get(pk=response.json()["id"])
        self.assertEqual(run.random_seed, 17)
        expected_policy_digest = hashlib.sha256(
            json.dumps(json.loads(run.policy_json), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(run.policy_sha256, expected_policy_digest)
        self.assertIsNotNone(run.started_at)
        self.assertIsNotNone(run.completed_at)
        details = self.client.get(f"/api/v1/rl-experiments/{run.id}")
        self.assertEqual(details.status_code, 200)
        self.assertEqual(details.json()["id"], run.id)
        listed = self.client.get(f"/api/v1/projects/{self.project.id}/rl-experiments")
        self.assertNotIn("policy", listed.json()[0])

    def test_import_is_atomic_when_ontology_label_is_unknown(self):
        content = (
            "video_id,start_time,end_time,action_label\n"
            f"{self.video.id},1,2,reach\n"
            f"{self.video.id},3,4,not-a-label\n"
        )
        upload = SimpleUploadedFile("annotations.csv", content.encode(), content_type="text/csv")
        response = self.client.post(f"/api/v1/videos/{self.video.id}/annotations/import", {"file": upload})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "IMPORT_VALIDATION_FAILED")
        self.assertEqual(Annotation.objects.filter(video=self.video).count(), 0)

    def test_import_preview_is_non_mutating_and_commit_skips_duplicate_rows(self):
        content = (
            "video_id,start_time,end_time,action_label\n"
            f"{self.video.id},1,2,reach\n"
            f"{self.video.id},1,2,reach\n"
        )
        preview_file = SimpleUploadedFile(
            "annotations.csv", content.encode(), content_type="text/csv",
        )
        preview = self.client.post(
            f"/api/v1/videos/{self.video.id}/annotations/import/preview",
            {"file": preview_file},
        )
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(preview.json()["total_records"], 2)
        self.assertEqual(preview.json()["importable_count"], 1)
        self.assertEqual(preview.json()["skipped_duplicate_count"], 1)
        self.assertEqual(Annotation.objects.filter(video=self.video).count(), 0)

        upload = SimpleUploadedFile(
            "annotations.csv", content.encode(), content_type="text/csv",
        )
        committed = self.client.post(
            f"/api/v1/videos/{self.video.id}/annotations/import",
            {"file": upload},
        )
        self.assertEqual(committed.status_code, 200, committed.content)
        self.assertEqual(committed.json()["imported_count"], 1)
        self.assertEqual(committed.json()["skipped_duplicate_count"], 1)
        self.assertEqual(Annotation.objects.filter(video=self.video).count(), 1)

        repeated = SimpleUploadedFile(
            "annotations.csv", content.splitlines()[0].encode() + b"\n"
            + f"{self.video.id},1,2,reach\n".encode(),
            content_type="text/csv",
        )
        duplicate_preview = self.client.post(
            f"/api/v1/videos/{self.video.id}/annotations/import/preview",
            {"file": repeated},
        )
        self.assertEqual(duplicate_preview.status_code, 200)
        self.assertEqual(duplicate_preview.json()["importable_count"], 0)
        self.assertEqual(duplicate_preview.json()["skipped_duplicate_count"], 1)

    def test_review_requires_reason_and_prevents_maker_checker(self):
        row = Annotation.objects.create(
            project=self.project, video=self.video, start_time=1, end_time=2,
            action_label="reach", status="needs_review", created_by=self.annotator.username,
        )
        reviewer = User.objects.create_user(username="reviewer", password="test-password")
        reviewer.groups.add(Group.objects.create(name="Reviewer"))
        client = Client()
        client.force_login(reviewer)
        path = f"/api/v1/annotations/{row.id}/review"
        missing_reason = client.post(
            path, data=json.dumps({"decision": "rejected"}), content_type="application/json",
        )
        self.assertEqual(missing_reason.status_code, 422)
        self.assertEqual(missing_reason.json()["error"]["code"], "REVIEW_REASON_REQUIRED")

        self.annotator.groups.add(Group.objects.get(name="Reviewer"))
        self.client.force_login(self.annotator)
        own_approval = self.post_json(path, {"decision": "approved"})
        self.assertEqual(own_approval.status_code, 403)
        self.assertEqual(own_approval.json()["error"]["code"], "MAKER_CHECKER_REQUIRED")

    def test_submission_requires_reviewer_approval_and_captures_transitions(self):
        created = self.post_json(
            f"/api/v1/videos/{self.video.id}/annotations",
            {"start_time": 1, "end_time": 2, "action_label": "reach"},
        )
        self.assertEqual(created.status_code, 201)
        row = Annotation.objects.get(pk=created.json()["id"])
        submitted = self.client.post(f"/api/v1/projects/{self.project.id}/submit-review")
        self.assertEqual(submitted.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.status, "needs_review")
        self.assertEqual(row.revision, 2)

        reviewer = User.objects.create_user(username="independent-reviewer", password="test-password")
        reviewer.groups.add(Group.objects.create(name="Reviewer"))
        client = Client()
        client.force_login(reviewer)
        approved = client.post(
            f"/api/v1/projects/{self.project.id}/review",
            data=json.dumps({"decision": "approved"}), content_type="application/json",
        )
        self.assertEqual(approved.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.status, "approved")
        self.assertEqual(row.revision, 3)
        self.assertEqual(row.revisions.count(), 3)

    def test_csv_release_is_approved_only_and_download_checksum_is_verified(self):
        DatasetManager = Group.objects.get_or_create(name="Dataset Manager")[0]
        self.annotator.groups.add(DatasetManager)
        Annotation.objects.create(
            project=self.project, video=self.video, start_time=1, end_time=2,
            action_label="reach", status="approved", created_by="another-annotator",
        )
        Annotation.objects.create(
            project=self.project, video=self.video, start_time=3, end_time=4,
            action_label="grasp", status="draft", created_by=self.annotator.username,
        )
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory).resolve()
            (output_dir / "exports").mkdir()
            with patch.object(views, "OUTPUT_DIR", output_dir):
                first = self.post_json(
                    f"/api/v1/projects/{self.project.id}/exports", {"format": "csv"},
                )
                second = self.post_json(
                    f"/api/v1/projects/{self.project.id}/exports", {"format": "csv"},
                )
                self.assertEqual(first.status_code, 201)
                self.assertEqual(second.status_code, 201)
                self.assertEqual(first.json()["manifest"]["record_count"], 1)
                self.assertEqual(first.json()["manifest"]["sha256"], second.json()["manifest"]["sha256"])
                self.assertEqual(first.json()["release_version"], 1)
                self.assertEqual(second.json()["release_version"], 2)
                json_first = self.post_json(
                    f"/api/v1/projects/{self.project.id}/exports", {"format": "json"},
                )
                json_second = self.post_json(
                    f"/api/v1/projects/{self.project.id}/exports", {"format": "json"},
                )
                self.assertEqual(json_first.json()["manifest"]["sha256"], json_second.json()["manifest"]["sha256"])
                self.assertTrue((output_dir / "exports" / first.json()["storage_key"]).is_file(), first.json())

                download_path = f"/api/v1/exports/{first.json()['id']}/download"
                resolved_download_path = (views.OUTPUT_DIR / "exports" / first.json()["storage_key"]).resolve()
                self.assertIn(views.OUTPUT_DIR, resolved_download_path.parents)
                self.assertTrue(resolved_download_path.is_file())
                response = self.client.get(download_path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"reach", b"".join(response.streaming_content))

                export = DatasetExport.objects.get(pk=first.json()["id"])
                (output_dir / "exports" / export.storage_key).write_bytes(b"tampered")
                mismatch = self.client.get(download_path)
                self.assertEqual(mismatch.status_code, 409)
                self.assertEqual(mismatch.json()["error"]["code"], "EXPORT_CHECKSUM_MISMATCH")
