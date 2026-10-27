# AURA video and document knowledge (current implementation)

## Honest capability state

The application now has a **Video & Document Chat** workspace backed by
Django persistence and a deterministic, extractive answer service. The
verified local retrieval mode is `lexical_sqlite`, which searches persisted,
project-scoped chunks using lexical overlap. It is labelled as lexical search;
it is not presented as vector similarity or as a generated LLM response.

The optional persistent ChromaDB and sentence-transformers adapters are
implemented behind lazy interfaces. They were not installed or exercised in
this run, and no embedding model is configured. Dense indexes are isolated by
embedding model name and revision. When a local model path and both optional
packages are available, the ingestion service validates vector counts,
dimensions and finite values before recording a ready dense index. Failed
dense indexing keeps the lexical ORM index available and reports the failure.
No model is downloaded or loaded at application startup. Chroma telemetry is
disabled in the local adapter.

There is no external LLM, LangChain agent, OCR, video-caption model, CV
detector, or visual question answering. The assistant does not execute tools
or arbitrary code. Video results cite actual stored metadata and annotation
rows; a missing video file is explicitly reported as unavailable for visual
inspection.

## Data model and lifecycle

- `KnowledgeSource` records a project-scoped PDF or video evidence source,
  source version, checksum, state, page/chunk counts, backend/model label,
  lexical and dense index states, index version, model revision, warnings,
  and sanitized error summary.
- `KnowledgeChunk` stores normalized text in Django, stable ID/checksum,
  source checksum and index version, PDF-page or video-time/annotation
  provenance, source type, and indexing backend. The ORM is authoritative;
  Chroma is an optional derived index.
- `KnowledgeJob` records synchronous indexing lifecycle, timestamps, retry
  count, counts, and safe error details. The HTTP request waits for this
  bounded work; it is not represented as an asynchronous worker.
- `KnowledgeConversation`, `KnowledgeMessage`, and `KnowledgeCitation`
  persist user-owned chats, deterministic answers, retrieval metadata, and
  citation snapshots. Removing a source removes its searchable chunks and
  private PDF while retaining old citation snapshots as stale.

The current product has global Django role groups, not project-membership
ACLs. The chatbot enforces project, selected-video, and explicit selected-PDF
filters before database scoring or vector query; conversations are restricted
to their authenticated owner. Do not deploy it in a multi-tenant environment
until project membership/authorization is implemented.

## PDF ingestion

The upload endpoint accepts `.pdf` files with PDF content type and `%PDF-`
signature, rejects empty/oversized inputs, and uses a generated server-side
storage key under the configured private media root. It stores SHA-256 and
detects duplicate content within the project/video scope. `pypdf` extracts
page-level text; deterministic page-local chunks retain page numbers and
content checksums. Corrupt and encrypted PDFs are recorded as failed sources.
Pages without selectable text are explicitly marked; OCR is not configured.

The included [synthetic guideline PDF](../data/examples/synthetic_robot_operating_guideline.pdf)
is fictional retrieval-demo content, not an approved operating/safety policy.
It contains no real customer data or robot deployment commands. The generator
command refuses to overwrite an existing destination:

```powershell
python manage.py aura_create_synthetic_guideline
```

Upload the fixture through **Video & Document Chat**. PDFs may be project-wide
or associated with the currently selected video. The source list displays
lexical and dense index states, model revision, chunk count, checksum prefix,
warnings and retrieval backend. Each answer records its actual retrieval mode;
dense local search is identified as `dense_local`, and lexical fallback as
`lexical_sqlite`.
Retry/re-index and removal are explicit actions. Uploading and indexing run
synchronously in the local API request, so large documents may take time.

## Video evidence

Select a project and video, then choose **Index stored video annotations**.
AURA indexes the actual video metadata, non-archived annotation rows in time
order, and the latest persisted validation issues where available. Each
annotation chunk retains the actual annotation ID and half-open interval
boundaries. The content is explicitly described as a database annotation,
not as a vision-model detection.

For the preloaded synthetic demo, the video metadata status is unavailable.
There are eight synthetic annotation records, but no video bytes; no frame
was inspected or processed. Video-scoped answers only cite those records and
include the unavailable-pixels warning.

## Conversation scopes and citations

Supported scopes:

- **Selected video**: stored metadata/annotation evidence for that video.
- **Selected video + selected PDFs**: that video plus explicitly selected
  project or same-video PDFs.
- **Selected PDFs only**: explicitly selected active PDFs in the project.
- **Project knowledge**: active, indexed sources in the selected project.

The API validates selected PDF IDs against the project, requires the proper
video for video scopes, filters retrieval by the conversation's project and
scope, and rejects source IDs from another project. An unsupported question
returns `insufficient_evidence` with no citations. The no-key answer mode is
`deterministic_extractive`; citations are constructed from retrieved ORM
chunks and persisted with source IDs, title/type, page/time, annotation ID,
snippet, and checksum. The UI evidence drawer shows the selected snippet and
source location; it does not embed a PDF viewer or seek a video player.

Useful local demo questions:

1. “List the actions recorded for this video in chronological order.”
2. “According to the guideline PDF, what should be verified before a pick?”
3. “Compare the guideline with the actions recorded in the video.”
4. “What is the capital of France?” (should abstain when not present in the
   selected evidence).

Answers are returned in structured, source-cited form, but deterministic
extractive mode is not a provider-backed natural-language synthesis system.
It may present excerpts rather than compose a comparison.

## Local embedding and Chroma setup (optional, explicit)

The base install needs only the normal application dependencies plus `pypdf`.
The optional local vector extra is:

```powershell
python -m pip install -e ".[rag]"
```

This installs ChromaDB and sentence-transformers and may add substantial
CPU/ML dependencies. A model is deliberately not downloaded by AURA at
startup. If you choose to download the recommended small model explicitly,
save it to an ignored local directory:

```powershell
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2').save('data/models/all-MiniLM-L6-v2')"
$env:AURA_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
$env:AURA_EMBEDDING_MODEL_PATH = (Resolve-Path "data/models/all-MiniLM-L6-v2").Path
$env:AURA_EMBEDDING_MODEL_REVISION = "all-MiniLM-L6-v2-local-1"
$env:AURA_VECTOR_STORE_DIR = (Join-Path (Get-Location) "data/vector_store")
```

The explicit command may access the model source to download files; it is not
run by application startup. The explicit revision is stored with each index;
if omitted, AURA derives a local fingerprint from the model directory's file
names, sizes, and modification times. Keep model files and the Chroma
directory private and out of source control. Once configured, re-index existing sources with
`python manage.py aura_reindex_knowledge --source-id <source-id>`. The model
loads lazily on first indexing/retrieval and is cached for that server process.
Embedding work is CPU-first; memory/time requirements depend on the chosen
model.

Check capability mode without exposing source content:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/config/capabilities
python manage.py aura_knowledge_status
python manage.py aura_evaluate_knowledge --top-k 3
```

The current checked-out environment has `pypdf` 6.21.2 installed; ChromaDB
and sentence-transformers are absent. Therefore current operation uses
`lexical_sqlite`. The evaluation command runs a small synthetic lexical
fixture and reports computed recall@k, citation precision, and negative
abstention rate; it is not a dense-model benchmark. Dense retrieval and Chroma
restart persistence remain unverified until the optional setup above is
intentionally performed. Retrieval permissions are applied in the ORM scope
before querying and are revalidated against current ORM chunk IDs and source
hash/index versions before citation.

## Privacy, deletion and backup

PDF originals are private local files under `data/media/knowledge/`; text and
annotations are stored in SQLite, and optional vector records are derived
private data under `data/vector_store/`. No file is publicly served. API
errors and logs do not intentionally include full document text. Source
deletion invalidates ORM chunks and asks configured Chroma to remove their
vectors; retrieval also excludes deleted sources before searching.

Back up/restore the relational DB, private `data/media/`, optional
`data/vector_store/`, generated exports, and any explicitly downloaded local
model assets together. Local storage is not encrypted by AURA. A DB-only
restore or manual DB row deletion can leave orphaned derived vectors; use the
source removal/re-index commands and inspect status before relying on the
index. A dedicated orphan reconciliation command and automated Chroma
consistency check remain deferred.

## Not yet implemented or verified

- ChromaDB/sentence-transformer runtime was not installed or tested here.
- No local or external LLM, LangChain orchestration, safe tool traces, or
  generated comparative synthesis.
- No scanned-PDF OCR, visual frame extraction for chat, real detection
  outputs, video playback jump, or PDF viewer.
- No range-filtered video retrieval, reranker, RAG evaluation harness, upload
  progress meter, retention controls, or background job runner.
- No multi-user project membership ACL; role groups are global.
- No manual browser workflow was performed.

See [Implementation status](./IMPLEMENTATION_STATUS.md) for the audit,
commands, tests and remaining industrial-platform phases.
