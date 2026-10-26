# AURA system architecture

## Components and request flow

The browser-hosted React/TypeScript/Vite UI calls the versioned Django
application through `frontend/src/api/client.ts`. Vite proxies `/api` to
loopback port 8000 during development. Django views own request validation,
SQLite persistence through the Django ORM, file boundaries, and workflow
operations. They delegate annotation checks and file parsing to the
framework-independent `annotation_processor` Python package.

```text
Browser → typed API client → Django views → Django ORM → SQLite
                                  ├→ annotation_processor
                                  ├→ canonical policy document retrieval
                                  ├→ aura_rag parsing/chunking + optional Chroma adapter
                                  ├→ data/media (managed upload only)
                                  └→ output/exports (downloadable artifact)
```

## Domain and storage

The database schema is created/updated by Django migrations
(`python manage.py migrate`).
Entities include projects, videos, annotations, validation snapshots,
append-oriented review/audit events, exports, assistant interactions, and
simulation runs, plus project-scoped knowledge sources/chunks/jobs and
user-owned conversations/messages/citation snapshots. IDs are UUIDs except
for the stable synthetic demo fixture.
SQLite foreign keys are enabled. Managed uploads use generated random storage
keys and are streamed only from the configured media root. The browser never
receives the internal storage key.

## Annotation processing

The processor reads CSV and JSON into record mappings. Validation reports
stable issue codes, source row/record references, severity, and suggested
actions; it does not normalize incorrect timestamps or labels. Overlap
analysis uses half-open intervals `[start,end)` and a sorted active-set scan.
Validation runs persist immutable issue JSON snapshots. Quality summaries are
computed from persisted records and the latest stored run.

## Assistant and policy retrieval

The existing assistant retrieves the canonical `docs/annotation_policy_v1.md`
and answers supported project/quality intents deterministically. A separate
Video & Document Chat indexes actual database-backed video metadata,
annotations and persisted validation findings, plus text PDFs parsed with
`pypdf`. It stores source provenance/chunks in Django and returns persisted
page/time/annotation citations. Current verified retrieval is a lexical
SQLite fallback with deterministic extractive answers and explicit
abstention. Optional local sentence-transformer and persistent Chroma
adapters are lazy and not enabled unless dependencies and local model files
are configured. No external LLM or LangChain agent is implemented.

Project and source scopes are applied before scoring; conversations belong to
the authenticated user. The current application uses global Django role
groups rather than per-project membership ACLs, which is a deployment
limitation. Video annotations are not visual observations. Missing video
pixels produce a capability warning.

## Upload, CV and exports

Uploads allow a short video extension list, enforce size limits, generate
non-user-controlled keys, and store a SHA-256 checksum. OpenCV is optional for
metadata and bounded frame metadata. No preview files/detector adapter are
provided. Exports are deterministic-order CSV/JSON files with a lineage
manifest and content checksum; default export includes approved records only.

## Simulation

Simulation task JSON maps actual annotation action labels and source IDs into
phases. The stored run advances one phase at a time. This is a task-level UI
visualization, not a physics or robot-control simulation.

## Trust boundaries and future work

Imported notes and file names are untrusted; filenames are reduced to a
basename for display and not used as storage paths. API errors have a stable
public envelope. PDF originals are stored below the private media root using
generated names. Chroma data, when configured, is private derived content
below `data/vector_store/`; it is not encrypted by AURA. This local
trusted-user application has no project-membership ACL, rate limiting,
production upload scanning, or cloud deployment hardening.
