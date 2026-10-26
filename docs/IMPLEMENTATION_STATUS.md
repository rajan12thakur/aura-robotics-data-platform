# AURA implementation ledger and Phase 0 audit

This is the current audit of the working repository, not a claim that the
complete industrial-platform prompt is done. Statuses describe observed code
and commands; optional dependencies and unrun capabilities are labelled.

## Current repository baseline

| Audit item | Observed evidence |
|---|---|
| Branch and recent history | Branch `feature/1-initialize-aura-platform`; latest commit at audit was `f657e7f` (`Merge remote-tracking branch 'origin/main'`). No commit/push was made for this continuation. |
| Worktree | Already contained a modified `.gitignore`, modified `README.md`, and untracked application/docs/data files before this slice. Existing work was retained. |
| Runtime | Python 3.11.0, Django 5.2.18, Node 22.20.0, npm 10.9.3. |
| Framework/package baseline | Django ORM, SQLite default, React 18, TypeScript, Vite. Base project dependencies were Django and django-cors-headers; `pypdf` was added for this slice. |
| Database migrations | Applied `0001` through `0005` before this slice; forward migrations `0006_knowledgechunk_knowledgeconversation_and_more` and `0007_knowledgechunk_embedding_dimensions_and_more` are now applied. |
| Local database before RAG migration | `data/aura.db` had 1 project (`synthetic-demo-project`), 1 video (`demo-video-001`, metadata-only/unavailable), 8 draft annotation rows, 8 annotation revisions, 10 ontology labels, 0 exports, and 0 RL runs. |
| Data after migration | The same project, video, annotation IDs/statuses/times/labels, 8 revisions, and 10 ontology labels remain. No knowledge records were added to the user's local DB by automated tests. |
| Backup | Before migrations, copied the SQLite DB to `data/aura.db.pre-rag-20261027-010446` and `data/aura.db.pre-score-metadata-20261027-012008`. Earlier pre-existing backups were not changed. |
| Baseline checks before edits | `python manage.py test aura_api.tests --verbosity 1`: 13 tests passed. `Set-Location frontend; npm run build`: TypeScript and Vite passed. |
| Existing app and tests | One Django app, `backend/aura_api`; focused suite `backend/aura_api/tests.py`; 18 tests pass after the latest RAG metadata change. |
| Existing pages | Overview, Projects, Annotation Workspace, Dataset Quality, AI Assistant, Simulation, Policy & Guidelines, Audit Trail, Settings. Added Video & Document Chat. |
| Existing media/sample data | `data/examples/sample_annotations.csv`; `data/media/` is the private managed-media root; synthetic demo video has no available pixels. Added a clearly synthetic PDF guideline fixture. |
| Preserved paths | `.dist/`, `LICENSE`, `AURA_MASTER_IMPLEMENTATION_PROMPT.md`, existing demo records, environment templates, and unrelated work were not reset or deleted. |

## Verified demo-record inventory after migrations

Read from `data/aura.db` after applying migration 0007. The demo is synthetic;
the registered video has no available pixels.

| Record | ID | Contents |
|---|---|---|
| Project | `synthetic-demo-project` | `Bottle Pick-and-Place Demonstration (Synthetic Demo)` |
| Video | `demo-video-001` | `synthetic-demo-video-unavailable.mp4`; status `unavailable`; parent project `synthetic-demo-project` |
| Annotation | `1134396d-60de-4bf8-9965-08cafca358ee` | 0.0–1.0 s, `approach`, draft |
| Annotation | `53c59c2a-2876-463b-8498-2b45a267e2ea` | 1.0–2.1 s, `reach`, draft |
| Annotation | `4bb17a20-041e-40d4-8f43-c3542d400d31` | 2.1–2.8 s, `grasp`, draft |
| Annotation | `5be0f0d7-a501-46e6-9109-38cb5b84810a` | 2.8–3.6 s, `lift`, draft |
| Annotation | `ef4e8b22-5dd5-4f64-9806-dd0f0e0790d1` | 3.6–4.7 s, `move`, draft |
| Annotation | `74b551d8-78b9-4aa0-9223-2191cbfa7c54` | 4.7–5.5 s, `place`, draft |
| Annotation | `64e490fd-3c19-4dbc-9a49-9470eac855b2` | 5.5–5.9 s, `release`, draft |
| Annotation | `b69c4bda-5699-49f8-ae5f-cedc8571c13f` | 5.9–6.6 s, `withdraw`, draft |
| Related records | — | 8 annotation revisions; 10 labels (`approach`, `grasp`, `inspect`, `lift`, `move`, `other`, `place`, `reach`, `release`, `withdraw`); 0 dataset exports; 0 RL experiments |

## API and persistence map

All endpoints use Django views under `/api/v1/`, session authentication for
private operations, and the existing structured API error wrapper.

| Area | Route groups |
|---|---|
| Auth/operations | `/health`, `/health/ready`, `/auth/*`, `/config/capabilities` |
| Projects/media | `/projects`, `/projects/{id}`, `/projects/{id}/videos`, `/videos/{id}`, `/videos/{id}/metadata`, `/videos/{id}/stream`, `/videos/{id}/vision/*` |
| Annotation/quality/review | `/videos/{id}/annotations*`, `/annotations/{id}*`, `/projects/{id}/validate`, `/projects/{id}/quality-summary`, `/projects/{id}/submit-review`, `/projects/{id}/review`, `/validation-runs/{id}` |
| Dataset exports/audit | `/projects/{id}/exports`, `/exports/{id}*`, `/projects/{id}/audit-events` |
| Assistant/policy | `/assistant/*`, `/policy/*` |
| Simulation/RL | `/projects/{id}/simulation/*`, `/simulation-runs/{id}*`, `/rl/environment`, `/projects/{id}/rl-experiments`, `/rl-experiments/{id}` |
| Knowledge sources | `GET/POST /projects/{id}/knowledge/sources`, `GET /knowledge/sources/{id}`, `POST/DELETE /knowledge/sources/{id}/lifecycle`, `POST /videos/{id}/knowledge/index` |
| Knowledge chat | `GET/POST /projects/{id}/knowledge/conversations`, `GET/PATCH/DELETE /knowledge/conversations/{id}`, `POST /knowledge/conversations/{id}/messages` |

The ORM tables for this slice are `KnowledgeSource`, `KnowledgeChunk`,
`KnowledgeJob`, `KnowledgeConversation`, `KnowledgeMessage`, and
`KnowledgeCitation`. Django project roles are global groups; there is no
project-membership ACL model yet. Retrieval itself is constrained to the
conversation's project, video and explicit PDF source IDs before scoring.

## Current feature ledger

| Feature | Current evidence / code path | Status | Gaps | Next action | Test evidence |
|---|---|---|---|---|---|
| Django projects/media/annotations | `backend/aura_api/models.py`, `views.py`, `urls.py`; React `App.tsx` | Implemented baseline | Temporal annotations only; no object tracks/boxes | Continue annotation/ontology slice after RAG | Existing API tests and baseline checks |
| Validation/review/releases | `ValidationRun`, `AnnotationRevision`, `DatasetExport`; existing endpoints | Implemented baseline | No full adjudication queue; no medallion artifacts | Add governance/pipeline incrementally | Existing focused tests |
| Tabular Q-learning | `rl.py`, `rl_service.py`, `RLExperiment`, Simulation UI | Implemented and previously verified | No DQN or physical policy | Keep baseline and add DQN only as separate optional work | Prior 13-test baseline covered RL |
| PDF source lifecycle | `knowledge_service.py`, `KnowledgeSource`, private generated media keys | Implemented and verified in local lexical mode | Synchronous; no OCR; user project ACL is global role model | Add asynchronous job runner and richer access policy | Real generated PDF API test checks signature, SHA, parse, page, duplicate and removal |
| Video evidence indexing | `knowledge_service.py` reads real `Video`, `Annotation`, and latest validation records | Implemented and verified for metadata/annotations | No frame captions, CV detections, simulation lineage, or notes entity; no visual analysis | Index additional evidence only when it exists | Test verifies actual annotation IDs/times, order, persistence and unavailable-pixels warning |
| Retrieval and citations | `src/aura_rag/core.py`, `knowledge_service.py`; structured sequence route and lexical SQLite fallback | Partially implemented; lexical/extractive mode is the active verified mode | Chroma not installed or exercised; no sentence-transformer model configured; no hybrid reranker/time-range filter; no answer citation UI navigation beyond evidence drawer | Install optional RAG extras and explicitly configure local model; verify persistent Chroma path, filtered query, deletion/restart | Tests cover persisted citation scores, citations, abstention, source/project scope and deletion |
| Conversation persistence | `KnowledgeConversation`, `KnowledgeMessage`, `KnowledgeCitation`; user-owned conversation endpoints | Implemented and verified | No configurable retention/export | Add retention policy after access model | API test reloads persisted messages and stale citation snapshot |
| React Video & Document Chat | `frontend/src/KnowledgeWorkspace.tsx`, API client and typed models | Implemented in lexical mode; production build passed after final metadata update | No browser walkthrough; no progress meter for upload; citation drawer shows snippets/page/timestamp but does not render PDF or seek video | Browser test after local server setup | `npm run build` passed |
| ChromaDB / sentence-transformers | Optional `rag` extra; `src/aura_rag/vector.py` lazily opens persistent Chroma and local-only configured model | Implemented but not installed or fully verified | Model files are not bundled/downloaded; current `chromadb` and `sentence_transformers` modules are absent | Install `python -m pip install -e ".[rag]"`, explicitly prepare local model directory, run adapter persistence/scoping tests | Capability reports `lexical_sqlite`; no dense result claimed |
| LLM / LangChain / tools | Current implementation uses deterministic extractive answers; no external provider | Not implemented beyond deterministic fallback | No LangChain chain/agent, external LLM, tool traces, evaluation | Keep no-key fallback; design safe provider/agent as a separate phase | No provider calls made |
| Medallion pipeline | No Bronze/Silver/Gold job models or artifact workflow | Not implemented | No durable ETL, quarantine, retries, lineage outputs | Implement the next full vertical slice after RAG foundation | Not tested |
| CV detector/object annotation | Optional OpenCV metadata only; no configured weights | Not implemented for inference | No YOLO adapter, boxes/tracks, CV evaluation | Add only with explicit local model configuration and human review | No detector was run |
| Supervised ML/PyTorch/DQN | No supervised model registry or PyTorch training path | Not implemented | No dataset/split/model artifacts | Define a defensible labeled task and testable baseline | Not run |
| BFSI pack | No separate BFSI models or UI | Not implemented | No synthetic document processing/review domain | Implement isolated domain pack after shared sources/ETL are mature | Not run |
| Production hardening | Existing session/CSRF, roles, request IDs, health/readiness | Partially implemented | No project memberships, throttling, OpenAPI, security review or production run | Harden before any public deployment | Existing auth tests; no deployment review |

## Configuration and optional dependencies

| Setting/package | Purpose / observed state |
|---|---|
| `DJANGO_SECRET_KEY`, `AURA_ENV`, `AURA_ALLOWED_HOSTS` | Existing Django security configuration |
| `AURA_DATABASE_PATH`, `AURA_DB_*`, `AURA_DATA_DIR`, `AURA_MEDIA_DIR`, `AURA_OUTPUT_DIR` | Existing database and file roots |
| `AURA_RAG_MAX_PDF_MB` | New PDF limit; defaults to 25 MB |
| `AURA_VECTOR_STORE_DIR` | New ignored runtime Chroma path; defaults to `data/vector_store/` |
| `AURA_EMBEDDING_MODEL`, `AURA_EMBEDDING_MODEL_PATH` | Optional explicit model label and already-present local model directory; nothing is downloaded on startup |
| `pypdf>=5,<7` | Added to base dependencies; installed version observed was 6.21.2 |
| `chromadb>=0.6,<2`, `sentence-transformers>=3,<6` | Optional `rag` extra; not installed during this pass |
| `langchain`, OCR, YOLO, MLflow, PyTorch | Not installed/configured as part of this slice |

## Verification after the RAG slice

Baseline before edits: 13 Django tests and frontend production build passed.
After adding the knowledge models/API/UI and metadata fields, the final focused
command `python manage.py test aura_api.tests --verbosity 2` passed 18 tests. Also
passed: `python manage.py check`, `python manage.py makemigrations --check
--dry-run`, `python -m compileall -q backend src`, `git diff --check`, and
`Set-Location frontend; npm run build`. Migrations 0006 and 0007 applied
successfully.
The synthetic PDF generator created a one-page PDF and `pypdf` extracted its
actual text. No browser walkthrough, Chroma persistence test, embedding-model
run, OCR, provider-backed LLM, detector inference, or deployment test was run.
