# AURA --- Master Implementation Prompt

## Single-file specification for the AI coding agent in VS Code

**Use this entire document as the master prompt.** Inspect the existing
repository, preserve useful work and the current Git branch, then
implement the product end to end. Do not merely return a plan or create
empty scaffolding.

**Owner's explicit constraint:** Do not create test cases or run tests
in this phase. Testing will happen later. You may perform non-test
checks if useful, but report exactly what was checked. Never claim tests
passed.

------------------------------------------------------------------------

# 0. Role and mission

Act as the lead architect and engineer for **AURA --- AI-assisted
Understanding, Review and Action for Robotics Data**.

Build a coherent, local-first web application that manages human
demonstration videos, creates/imports temporal action annotations,
validates data quality, supports human review, provides policy-grounded
AI assistance, exports traceable datasets, and demonstrates a task-level
pick-and-place simulation.

This must be a working product, not a collection of static mockup pages.
Core workflows must work without cloud credentials, an LLM key, or
downloaded model weights.

## Non-negotiable rules

1.  Inspect the repository before changing it. Review the current
    branch, files, README, `pyproject.toml`, requirements, existing
    `src/annotation_processor/`, and current Git status.
2.  Preserve user work. Do not reset, force-push, rename branches,
    delete useful files, or commit/push automatically. Keep the
    issue-generated branch naming convention.
3.  Reuse and extend the existing Python annotation processor and CLI
    configuration where practical.
4.  Do not create or run tests. Do not create test files. Do not run
    `pytest`, another test suite, or test commands.
5.  Do not fabricate behavior, metrics, records, model results, or
    successful verification. A button must work or clearly explain why
    it is disabled/unavailable.
6.  Do not hard-code secrets. Use environment variables and
    `.env.example` placeholders.
7.  Core workflows must run locally without API keys. AI/vision are
    optional integrations with graceful fallbacks.
8.  The deterministic validator is the source of truth for validation
    facts. AI explains real results; it must not invent them.
9.  AI suggestions must never silently modify or approve annotations. A
    human must make review decisions.
10. Mark synthetic demo data as synthetic. Never present it as real
    human-labelled data.
11. Do not claim that video action labels alone train/control a physical
    robot. The initial simulation is task-level/scripted unless real
    physics/control is implemented.
12. Prefer a complete vertical workflow over superficial integrations.
    Do not add Redis, Kafka, Kubernetes, multiple agents, vector DBs, or
    other technologies merely for résumé keywords.
13. If something cannot be implemented, create the best safe fallback,
    document the limitation, and mention it in the final report.
14. Do not stop after writing architecture documents or scaffolding.
    Implement the application.
15. Keep README and feature status honest: distinguish implemented,
    optional, partial, and deferred capabilities.

# 1. Product definition

## Problem

Robotics datasets need structured, time-aligned action labels,
consistent annotation rules, quality checks, human review, versioning,
and reproducible exports. Raw videos are not enough. Human annotations
can contain invalid timestamps, unknown labels, duplicates, suspicious
overlaps, or missing metadata. AI can assist, but model suggestions are
not automatically ground truth.

## Main user journey

1.  Open the dashboard.
2.  Create a project, e.g. **Bottle Pick-and-Place Demonstration**.
3.  Upload a supported video or register external/local video metadata.
4.  Create or import action segments.
5.  View the video, timeline, and annotation table.
6.  Edit labels, timestamps, objects, and notes.
7.  Run validation; inspect specific errors/warnings and affected
    records.
8.  Ask the AURA assistant why validation failed, what the policy says,
    or which records need attention.
9.  Review the dataset and explicitly approve or reject it.
10. Export approved data to CSV/JSON with a manifest, schema version,
    policy version, and validation lineage.
11. Open a task-level simulation based on the selected annotations.
12. Inspect the audit trail.

Persist core state in a database. Do not fake the workflow using
frontend-only state.

## Scope boundaries

AURA is a dataset engineering and review platform, not automatically a
production robot controller, a custom-trained CV model, or a
multi-tenant cloud service. Human video labels such as `grasp` and
`lift` do not contain joint trajectories, gripper commands, object pose,
force, or collision-free motion plans. Explain this in the UI and
documentation.

# 2. Architecture and technology choices

Use a **modular monolith**, not microservices.

## Backend

-   Python 3.11+.
-   FastAPI, Uvicorn, Pydantic, SQLAlchemy 2.x.
-   SQLite as the zero-configuration default.
-   Use Alembic if it can be set up cleanly; otherwise implement
    reliable schema initialization and document it.
-   Standard-library CSV/JSON parsing.
-   Reuse `src/annotation_processor/` as the framework-independent
    domain/processing package.
-   Python logging; safe, consistent API errors.
-   `python-multipart` for uploads.
-   Keep route handlers thin and place logic in services.

## Frontend

-   React + TypeScript + Vite.
-   A consistent, accessible, professional interface.
-   Reuse any sensible existing UI dependencies; otherwise use a small
    CSS design system.
-   Centralize HTTP calls in `frontend/src/api/client.ts`.
-   Use typed frontend models that align with backend schemas.
-   Real loading, error, empty, and success states.
-   All normal workflows must call the backend and persist.

## CV

-   OpenCV is optional for metadata and frame extraction.
-   An optional pretrained detector adapter may use Ultralytics YOLO,
    but do not download weights on startup.
-   If dependencies or weights are unavailable, manual annotation must
    still work and capability status must say the detector is not
    configured.
-   Detections are suggestions, not approved action annotations.

## AI

-   A provider-neutral assistant service.
-   Deterministic local assistant required, even with no key.
-   Optional LLM provider configured only through environment variables.
-   Policy retrieval works locally and deterministically using
    keyword/TF-IDF/BM25-like retrieval or a similarly simple method.
-   Explicit typed tools only. No arbitrary shell, Python, SQL, or
    unrestricted filesystem execution.
-   Do not send video bytes or complete datasets to a provider by
    default.

## Storage

-   SQLite file under `data/`, e.g. `data/aura.db`.
-   Managed uploads under `data/media/`.
-   Reports/exports under `output/reports/` and `output/exports/`.
-   Ignore local DBs, uploaded videos, secrets, and generated private
    data in Git.
-   Never return host absolute paths to the browser.

## Suggested repository structure

Adapt to the existing repository; do not create empty placeholders just
to match this tree.

``` text
.github/
data/
  .gitkeep
  examples/
  media/                 # ignored local uploads
docs/
  system_architecture.md
  annotation_policy_v1.md
  dataset_schema.md
  ai_assistant.md
  cv_pipeline.md
  simulation.md
  implementation_status.md
output/
  .gitkeep
  reports/
  exports/
src/
  annotation_processor/
    __init__.py
    models.py
    schema.py
    validation.py
    overlap.py
    dataset.py
    reports.py
    policy.py
    service.py
    cli.py
backend/
  aura_api/
    __init__.py
    main.py
    config.py
    database.py
    db_models.py
    schemas.py
    dependencies.py
    api/
    services/
frontend/
  package.json
  index.html
  vite.config.ts
  src/
    main.tsx
    App.tsx
    api/client.ts
    components/
    layouts/
    pages/
    types/
    hooks/
    styles/
.env.example
.gitignore
pyproject.toml
requirements.txt
README.md
docs/FINAL_IMPLEMENTATION_REPORT.md
```

If the backend package is in `backend/`, ensure launch/import commands
work from the repository root. Do not patch `sys.path` arbitrarily. Keep
dependencies coherent between `pyproject.toml` and `requirements.txt`.

# 3. Domain model

Use UUID/stable IDs, foreign keys, sensible indexes, UTC audit
timestamps, and typed Pydantic schemas. Avoid unnecessary sensitive
data.

## Project

-   `id`, `name` (required, max 120 chars), `description`, `task_type`.
-   `status`: `active` or `archived`.
-   `created_at`, `updated_at`.
-   `annotation_policy_version` (default `1.0`).

## Video asset

-   `id`, `project_id`.
-   `original_filename`, generated safe storage key/path (internal
    only).
-   `mime_type`, `file_size_bytes`, `duration_seconds`, `width`,
    `height`, `fps`, `checksum_sha256`.
-   `status`: `uploaded`, `metadata_ready`, `metadata_partial`,
    `unavailable`, `archived`.
-   `created_at`, optional source/licensing notes.
-   Distinguish managed uploads from metadata-only registrations.
-   Restrict extensions/MIME, set upload-size limit, generate filenames,
    prevent path traversal, handle unsupported codecs gracefully, and
    never expose arbitrary paths.

## Annotation

-   `id`, `project_id`, `video_id`.
-   `start_time`, `end_time` as finite seconds from video start.
-   `action_label`, optional `object_label`, `actor_id`, `confidence`
    (0--1), `notes`.
-   `source`: `human`, `imported`, `model_suggestion`, `synthetic_demo`.
-   `status`: `draft`, `needs_review`, `approved`, `rejected`.
-   `created_at`, `updated_at`, `created_by`, `updated_by`, `revision`.
-   Optional bounded JSON metadata.
-   Use one documented interval convention consistently. Prefer
    half-open intervals `[start, end)`, so intervals touching at a
    boundary are not overlapping.

Default action vocabulary: `approach`, `reach`, `grasp`, `lift`, `move`,
`place`, `release`, `withdraw`, `inspect`, `other`.

This is AURA's default vocabulary, not a universal robotics standard.

## Annotation policy

Versioned policy with `version`, `title`, `status`, `created_at`,
content/rules, and change note. Include labels, timestamp convention,
overlap guidance, unknown/ambiguous actions, hard errors vs warnings, AI
suggestion provenance, and human approval expectations. Keep the
canonical policy in `docs/annotation_policy_v1.md`; if stored in the DB,
seed it from the canonical document or avoid silent duplication.

## Validation run

-   `id`, project/video IDs, timestamp, policy version.
-   total/valid record counts, error/warning counts, status (`passed`,
    `passed_with_warnings`, `failed`), structured issue results,
    triggering actor.
-   Historical runs are snapshots; annotation edits must not rewrite
    prior results.

## Review/audit event

-   `id`, project ID, optional video/annotation/export IDs.
-   `event_type`, actor, timestamp, summary, bounded JSON details.
-   Record consequential events. Audit history is append-only in the
    ordinary UI.

## Dataset export

-   `id`, project/video IDs, format, timestamp, actor, policy/schema
    versions, record count, validation run ID, approval state, safe
    filename/key, manifest JSON.

## Assistant interaction

-   `id`, optional project ID, timestamp, question, answer, mode,
    tool-call summary, evidence references, status.
-   Never store API keys or hidden reasoning.

Suggested tables: `projects`, `videos`, `annotations`,
`annotation_policies`, `validation_runs`, `review_events`,
`dataset_exports`, `assistant_interactions`.

# 4. Annotation processor and CLI

The domain engine must work independently of HTTP, UI, and database so
it can be reused by the CLI and API.

## Input formats

CSV canonical columns:

``` csv
video_id,start_time,end_time,action_label,object_label,actor_id,confidence,notes
```

Required: `video_id`, `start_time`, `end_time`, `action_label`. Optional
values may be blank. Define blank handling.

JSON: accept an array of objects or documented envelope:

``` json
{"schema_version":"1.0","annotations":[]}
```

Do not silently drop unknown columns; report a warning or preserve
permitted metadata.

## Validation checks

Implement stable issue codes and return `code`, `severity`, `message`,
record ID or source row, field, suggested action, and policy reference
where relevant.

Required checks: - missing/empty required fields. - non-numeric, NaN,
infinite, or malformed timestamps. - start \< 0. - end \<= start. - end
beyond known video duration (with documented tolerance). - action label
not in vocabulary. - confidence outside `[0,1]`. - duplicate records
based on a documented key. - malformed CSV rows/JSON objects. - unknown
video references or project/video mismatch. - overlap analysis per
video. - unknown input columns. - empty dataset. - unavailable video
duration (report that boundary checking could not be done). - suspicious
duration only if a documented policy threshold exists.

Issue codes to use consistently: `MISSING_REQUIRED_FIELD`,
`INVALID_START_TIME`, `INVALID_END_TIME`, `NEGATIVE_START_TIME`,
`NON_POSITIVE_INTERVAL`, `END_EXCEEDS_VIDEO_DURATION`,
`UNKNOWN_ACTION_LABEL`, `INVALID_CONFIDENCE`, `DUPLICATE_ANNOTATION`,
`OVERLAPPING_INTERVAL`, `UNKNOWN_VIDEO_REFERENCE`,
`VIDEO_PROJECT_MISMATCH`, `UNKNOWN_COLUMNS`, `EMPTY_DATASET`,
`VIDEO_DURATION_UNAVAILABLE`, `SUSPICIOUS_INTERVAL_DURATION`.

Do not silently repair timestamps/labels. Overlaps are warnings unless
active policy says otherwise. Report both records involved. Use
sort-and-sweep analysis where reasonable; exact boundary contact is not
overlap under `[start,end)`.

## Quality report

Compute real values: - annotation count, unique videos, unique labels. -
counts by label, source, and review status. - validation issues from a
specific run. - valid-record percentage with its definition and nonzero
denominator. - segment duration min/mean/max for valid intervals. -
missing metadata counts where relevant.

Do not invent a quality score. Any composite score must have a disclosed
formula and be described as a heuristic.

## CLI

`pyproject.toml` may already define:
`annotation-processor = "annotation_processor.cli:main"`

Make it work. Use `argparse` or a lightweight equivalent. Support
validate/report/export commands with helpful `--help`. Examples:

``` powershell
annotation-processor validate data/examples/sample_annotations.csv
annotation-processor validate data/examples/sample_annotations.json --format json
annotation-processor report data/examples/sample_annotations.csv --output output/reports/quality_report.json
annotation-processor export data/examples/sample_annotations.csv --format json --output output/exports/annotations.json
```

Adjust commands if needed, but document the actual interface. CLI file
validation must not require the API server or database.

# 5. Backend API

Use `/api/v1`, thin routes, service methods, Pydantic schemas, correct
HTTP status codes, safe errors, configured CORS, and proper DB session
handling. Add a health endpoint and OpenAPI docs. Do not expose secrets,
stack traces, local paths, or video bytes in JSON.

## Required endpoint capabilities

Health/config: - `GET /api/v1/health` -
`GET /api/v1/config/capabilities`

Projects: - `GET/POST /api/v1/projects` -
`GET/PATCH /api/v1/projects/{project_id}` -
`POST /api/v1/projects/{project_id}/archive`

Videos: - `GET /api/v1/projects/{project_id}/videos` -
`POST /api/v1/projects/{project_id}/videos` (multipart upload) -
`POST /api/v1/projects/{project_id}/videos/register` -
`GET /api/v1/videos/{video_id}` -
`GET /api/v1/videos/{video_id}/stream` -
`GET /api/v1/videos/{video_id}/metadata` -
`POST /api/v1/videos/{video_id}/extract-frames` -
`POST /api/v1/videos/{video_id}/archive`

Annotations: - `GET/POST /api/v1/videos/{video_id}/annotations` -
`GET/PATCH/DELETE /api/v1/annotations/{annotation_id}` -
`POST /api/v1/videos/{video_id}/annotations/import` -
`GET /api/v1/videos/{video_id}/annotations/export-preview`

Validation/quality: - `POST /api/v1/projects/{project_id}/validate` -
`POST /api/v1/videos/{video_id}/validate` -
`GET /api/v1/validation-runs/{run_id}` -
`GET /api/v1/projects/{project_id}/quality-summary` -
`GET /api/v1/videos/{video_id}/overlaps`

Review/audit: - `POST /api/v1/projects/{project_id}/review` -
`POST /api/v1/annotations/{annotation_id}/review` -
`GET /api/v1/projects/{project_id}/audit-events`

Exports: - `POST /api/v1/projects/{project_id}/exports` -
`GET /api/v1/projects/{project_id}/exports` -
`GET /api/v1/exports/{export_id}` -
`GET /api/v1/exports/{export_id}/download`

Policy/assistant: - `GET /api/v1/policy/active` -
`GET /api/v1/policy/search?q=...` - `POST /api/v1/assistant/ask` -
`GET /api/v1/assistant/interactions` -
`GET /api/v1/assistant/interactions/{interaction_id}`

Vision: - `GET /api/v1/vision/status` -
`POST /api/v1/videos/{video_id}/vision/suggest` -
`POST /api/v1/videos/{video_id}/vision/sample-frames`

Simulation: -
`GET /api/v1/projects/{project_id}/simulation/available-actions` -
`POST /api/v1/projects/{project_id}/simulation/prepare` -
`GET /api/v1/simulation-runs/{run_id}` -
`POST /api/v1/simulation-runs/{run_id}/start` -
`POST /api/v1/simulation-runs/{run_id}/reset`

The exact router grouping can vary, but the capabilities and workflows
must be real and documented. If a capability cannot be completed, return
a clear unavailable response and document it, rather than a fake
success.

Use a consistent error shape:

``` json
{"error":{"code":"ANNOTATION_NOT_FOUND","message":"The requested annotation does not exist.","details":{}}}
```

Validation findings are normal domain results, not necessarily HTTP
errors.

# 6. Frontend screens and interactions

## Visual design

Clean industrial AI workspace: neutral backgrounds, readable typography,
restrained accents, consistent spacing, useful density, accessible
status badges, keyboard focus, semantic HTML. Avoid excessive gradients,
decorative fake charts, random emoji, and nonfunctional buttons.
Desktop-first, usable at laptop/tablet widths.

## Navigation

-   Overview
-   Projects
-   Annotation Workspace
-   Dataset Quality
-   AI Assistant
-   Simulation
-   Policy & Guidelines
-   Audit Trail
-   Settings/Capabilities

## Dashboard

Real API data: project/video/annotation counts, latest validation, items
needing review, recent audit events, and quick actions. Provide a
meaningful empty state. If demo data is loadable, make it explicit,
idempotent, and labelled synthetic.

## Projects and videos

Create/edit/archive projects; show associated videos and annotation
totals. Video library shows filename, metadata, annotation count,
readiness, date, and managed-vs-registered state. Managed video has a
player; metadata-only registered video must clearly indicate that
playback is unavailable.

## Annotation workspace (priority)

-   Video player or explicit no-video state.
-   Current time and a simple time-scaled timeline of intervals.
-   Annotation list/table and create/edit form.
-   Label dropdown, start/end seconds, object, actor, notes,
    source/status badges.
-   Create/edit/delete through API.
-   Click a record to seek the video if playback is available.
-   Optional mark-start/mark-end from current video time if practical.
-   Immediate client-side validation, with backend authoritative.
-   Persist across refresh.
-   Distinguish human/imported/model suggestion/synthetic data.
-   Do not auto-approve suggestions.

If a sophisticated timeline is too costly, implement a correct interval
visualization and accessible table.

## Quality and review

Show latest validation run, policy version, errors/warnings/info grouped
by issue code, affected records, label/source distributions, durations,
overlap analysis, review states, and actions to validate/open
record/export. Explain percentages and scores. Block approval if hard
errors remain unless a documented override exists; any override requires
a reason and audit event. Warnings can be acknowledged.

## AI assistant

Real API-backed chat panel. Display mode (deterministic or configured
provider), cited policy sections, validation/annotation references, tool
activity, and supported next actions. Unsupported questions should
receive an honest limitation message. Do not show fabricated AI answers.

## Policy and audit

Display active policy version and rules. Audit page shows timestamp,
actor, event type, related record, and concise details. Do not expose
secrets or raw private media.

## Simulation

Show selected project/video, action sequence, visual task state, current
phase/progress, start/reset, missing action warnings, and limitations.
Use real annotation-derived phases.

# 7. Human review, audit, and exports

## Review

Support `draft`, `needs_review`, `approved`, and `rejected`. Record
actor/display name, timestamp, decision, comment, and audit event. A
local display name is not authentication; document that this is a
trusted local demo. Approval should be blocked while hard validation
errors exist, unless a carefully documented override is implemented.

## Audit

Record consequential actions: project creation/update/archive,
upload/registration, annotation create/update/delete, validation, review
decision, export, policy change, and assistant tool call where useful.
Append-only in ordinary UI.

## CSV export

Stable columns:
`annotation_id,project_id,video_id,start_time,end_time,action_label,object_label,actor_id,confidence,source,status,revision,notes`

Use standard CSV writer and UTF-8.

## JSON export

Use a documented envelope:

``` json
{
  "schema_version":"1.0",
  "exported_at":"UTC ISO-8601 timestamp",
  "project":{"id":"project-id","name":"Project name"},
  "policy":{"version":"1.0"},
  "annotations":[]
}
```

## Manifest and lineage

Include export ID, project/video IDs, timestamp, format, schema/policy
versions, record count, selected statuses/filters, validation run/status
if any, approval state/reviewer, and checksums if practical. Export
approved records by default. Exporting unapproved data must be an
explicit choice and labelled. Never say an export is validated if no
current validation run supports that claim. Use deterministic record
ordering.

# 8. AI assistant, tool calling, and RAG

## Core rule

**Deterministic tools produce facts; the assistant explains them.**

Implement typed, allowlisted tools: -
`get_project_summary(project_id)` -
`list_annotations(project_id, video_id optional, filters optional)` -
`validate_project(project_id)` - `get_validation_run(run_id)` -
`get_quality_summary(project_id)` - `analyze_overlaps(video_id)` -
`get_label_distribution(project_id)` -
`retrieve_annotation_policy(query)` -
`get_annotation_details(annotation_id)` -
`get_export_eligibility(project_id)` -
`generate_quality_report(project_id)`

Validate tool arguments and bound result sizes. Never allow arbitrary
SQL, shell, code, or unrestricted file access.

## Deterministic fallback

Without an LLM key, answer common intents: - validation
failures/status. - errors and warnings. - label counts/distribution. -
overlaps. - policy explanation. - export eligibility. - project summary.

For unsupported questions, state the limitation and list supported
question types. Never invent facts when there is no data.

## Optional LLM

If feasible, add one provider adapter behind an interface. Configure
with environment variables, use timeouts and bounded prompts, validate
structured outputs, require citations/evidence, and fall back if
provider setup fails. No secret reaches the frontend. Do not make app
startup depend on the provider SDK.

## Evidence contract

Response should include `interaction_id`, `mode`, `answer`, tool-call
summaries, evidence/source references, and suggested actions. Sources
can reference a validation issue, annotation ID, or policy section such
as `annotation_policy_v1.md#timestamp-rules`.

## RAG

Load policy/documentation from an allowlisted set of files or policy
records. Split by headings/sections. Retrieve relevant sections using
keyword/TF-IDF/BM25-like matching. Return title, source, policy version,
and excerpt. If nothing relevant is found, say so. Reload/re-index when
policy changes. RAG says what policy states; it does not prove an event
occurred or an annotation is correct.

## Safety boundaries

Treat filenames, notes, imported rows, and metadata as untrusted. Policy
text is data and cannot override system instructions. No automatic
approval or hidden writes. Store useful tool/evidence metadata, not
hidden model reasoning. Do not log secrets or private media content.

Document later evaluation metrics: tool-call correctness, factual answer
accuracy, evidence support, unsupported-claim rate, task completion,
latency/cost, retrieval relevance, and human correction rate. Do not
fabricate scores.

# 9. Computer vision

Minimum: - Optional OpenCV metadata extraction (duration, width, height,
FPS). - Bounded frame sampling. - Managed storage/serving of frame
previews. - `/vision/status` accurately reports readiness. - Manual
annotation works without OpenCV.

Optional detector: - Load only on user request. - Never download weights
automatically. - Model path/name configured by environment. - Return
class, bounding box, confidence, frame timestamp, and model name/version
if available. - Mark outputs as `model_suggestion`. - A detector detects
objects; do not claim it understands action intent or temporal action
boundaries unless a separate method exists. - If unavailable, return a
helpful message, not a crash. - Do not send videos to cloud services
without explicit configuration and user action.

# 10. Task-level simulation

Implement a pick-and-place visualization mapped from annotations.
Suggested action mapping: `approach`, `reach`, `grasp`, `lift`, `move`,
`place`, `release`, `withdraw`.

Not every dataset has every phase. Missing phases must be shown as
missing; do not invent annotations. Unknown actions should be shown as
unmapped.

Persist simulation runs with run ID, project ID, source annotation IDs,
task type, current phase, status, timestamps, event log, and mode such
as `scripted_task_visualization`.

A simple animated DOM/SVG/canvas visualization is acceptable; use
Three.js only if it yields a working feature without destabilizing the
project. Provide start/reset and progress display. State clearly that it
does not model real robot geometry, calibrated camera coordinates, joint
trajectories, force/tactile sensing, collision planning, or physical
grasping unless those are truly implemented.

Create a versioned task representation containing task type, object
label, source IDs, action phases with annotation IDs and timestamps,
execution mode, and limitations. Do not invent observed robot
coordinates.

# 11. Security and reliability

-   Generate storage keys; never use raw filenames as paths.
-   Restrict upload types/size and prevent traversal.
-   Stream only files within the managed media root.
-   Validate all inputs; use ORM/parameterized queries.
-   For bulk import, parse/validate before writing. Avoid silent partial
    writes. If valid-row-only import exists, make it an explicit option.
-   Handle empty files, headers-only CSV, missing columns, malformed
    numbers, NaN/Infinity, invalid UTF-8, malformed JSON, unknown
    columns, duplicate IDs, and project/video mismatch.
-   Never convert invalid numbers to zero silently.
-   `.env`, API keys, databases, uploads, and generated private data
    must be ignored by Git.
-   Capability endpoints report status but never credential values.
-   Avoid tracebacks/secrets in client errors.
-   Do not log full private notes/video content.
-   Do not claim public-deployment safety without authentication,
    authorization, upload hardening, and operational review.
-   Do not expose the dev server publicly by default.
-   Document where uploads and exports are stored.

# 12. Configuration and local development

Create `.env.example` with safe defaults such as:

``` dotenv
AURA_APP_NAME=AURA
AURA_ENV=development
AURA_API_HOST=127.0.0.1
AURA_API_PORT=8000
AURA_DATABASE_URL=sqlite:///./data/aura.db
AURA_DATA_DIR=./data
AURA_MEDIA_DIR=./data/media
AURA_OUTPUT_DIR=./output
AURA_MAX_UPLOAD_MB=250
AURA_FRONTEND_ORIGIN=http://localhost:5173
AURA_DEFAULT_REVIEWER=Local Reviewer

# Optional AI provider; blank means deterministic mode.
AURA_LLM_PROVIDER=
AURA_LLM_API_KEY=
AURA_LLM_MODEL=
AURA_LLM_BASE_URL=

# Optional vision; never download weights at startup.
AURA_VISION_ENABLED=false
AURA_VISION_MODEL=
AURA_VISION_WEIGHTS_PATH=
AURA_FRAME_SAMPLE_LIMIT=100
```

Use one consistent configuration naming scheme and document actual
supported variables. Ensure data/output directories are created when
needed. Handle SQLite paths correctly on Windows.

Document Windows PowerShell commands that match the actual project:

``` powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Update packaging if needed so this install command includes actual
backend runtime dependencies. If the command changes, document the
working alternative.

Frontend:

``` powershell
cd frontend
npm install
npm run dev
```

A likely local setup is: - Frontend `http://localhost:5173` - API
`http://127.0.0.1:8000` - FastAPI docs `http://127.0.0.1:8000/docs`

Use these only if they match actual launch configuration. Implement a
coherent backend launch command, for example
`uvicorn aura_api.main:app --reload --app-dir backend`, or package the
backend properly and document that path. Do not leave commands that
cannot work.

# 13. Documentation deliverables

Create/update all documents so they match code.

## `README.md`

Purpose, scope, feature status (implemented/optional/partial/deferred),
architecture diagram, workflow, stack, structure, prerequisites, Windows
setup, backend/frontend commands, env config, demo data, CSV/JSON
schema, CLI, API docs, security/privacy caveats, assistant modes, CV
setup, simulation limitations, troubleshooting, roadmap.

## `docs/system_architecture.md`

Component boundaries, request/data flow, domain model, storage,
validation, assistant tools/RAG, CV, exports, simulation, trust
boundaries, implemented versus future parts.

## `docs/annotation_policy_v1.md`

Concrete policy with label definitions/examples, timestamp convention,
overlap rules, unknown actions, confidence interpretation, provenance,
severity, review rules, AI suggestions, version/change log.

## `docs/dataset_schema.md`

CSV/JSON contract, required/optional fields, types/bounds, timestamp
convention, source labels, synthetic examples, issue codes, versioning.

## `docs/ai_assistant.md`

Tool allowlist, deterministic mode, optional LLM config,
retrieval/citations, safety, limitations, later evaluation plan.

## `docs/cv_pipeline.md`

Metadata, frame sampling, optional detector, configuration, review,
privacy and limitations.

## `docs/simulation.md`

Action mapping, task schema, simulation mode, limitations, requirements
for real robot control.

## `docs/implementation_status.md`

Honest matrix of implemented, optional/configuration-dependent, partial,
deferred, and not tested.

# 14. Synthetic demo data

Provide a small synthetic CSV for quick exploration:

``` csv
video_id,start_time,end_time,action_label,object_label,actor_id,confidence,notes
demo-video-001,0.0,1.0,approach,water_bottle,human_1,,Synthetic demonstration record
demo-video-001,1.0,2.1,reach,water_bottle,human_1,,Synthetic demonstration record
demo-video-001,2.1,2.8,grasp,water_bottle,human_1,,Synthetic demonstration record
demo-video-001,2.8,3.6,lift,water_bottle,human_1,,Synthetic demonstration record
demo-video-001,3.6,4.7,move,water_bottle,human_1,,Synthetic demonstration record
demo-video-001,4.7,5.5,place,water_bottle,human_1,,Synthetic demonstration record
demo-video-001,5.5,5.9,release,water_bottle,human_1,,Synthetic demonstration record
demo-video-001,5.9,6.6,withdraw,water_bottle,human_1,,Synthetic demonstration record
```

These records do not correspond to a real video. Label them
`Synthetic Demo`. Do not auto-seed duplicate demo projects every
startup. Allow the user to explicitly load demo data, or support
annotation-only examples that do not claim to have a video file.

# 15. Implementation order

Work through these phases without asking the user to approve every
routine step.

### A. Inspect and define

-   Inspect repository, branch, Git status, package config, README,
    existing code.
-   Preserve useful work.
-   Resolve dependency/package structure.
-   Write policy/schema docs before encoding the rules.

### B. Domain engine

-   Schema and vocabulary.
-   CSV/JSON import.
-   Validation and issue codes.
-   Overlap analysis.
-   Quality reports.
-   CLI. 
-   No tests.

### C. Database and API

-   Configuration and DB initialization.
-   Project/video/annotation CRUD.
-   Safe upload and metadata extraction.
-   Validation integration.
-   Reviews/audit.
-   Exports and manifests.

### D. Frontend

-   Shell/navigation.
-   Dashboard/projects.
-   Video library.
-   Annotation workspace.
-   Quality/review.
-   Policy and audit.
-   Real API calls, real loading/error/empty states.

### E. AI and retrieval

-   Policy retrieval.
-   Typed allowlisted tools.
-   Deterministic intent routing.
-   Evidence-backed responses and assistant UI.
-   Optional LLM adapter only if it does not destabilize local mode.

### F. CV and simulation

-   Optional metadata/frame extraction.
-   Detector adapter only if robust without startup fragility.
-   Task representation and action mapping.
-   Task-level visual simulation with start/reset.

### G. Finish

-   Reconcile docs with code.
-   Remove dead/unused placeholders and obvious broken links.
-   Perform only allowed non-test checks if useful
    (syntax/import/startup/frontend build), and record results.
-   Do not create or run tests.
-   Write the final report.

### If time becomes constrained, prioritize:

1.  Processor and CLI.
2.  Persistent API.
3.  Frontend annotation/validation/review flow.
4.  CSV/JSON export and lineage.
5.  Policy retrieval and deterministic assistant.
6.  Simulation.
7.  Optional CV detector.
8.  Optional real LLM.

Do not destabilize the working core to add an optional integration.

# 16. Definition of done

The report must identify any unmet criteria, but aim to deliver: -
Repository inspected and existing work preserved. - Runnable backend and
frontend with documented commands. - Local DB initializes
automatically. - Core works without API keys. - Projects persist. -
Video upload/registration and metadata work or limitation is explicit. -
Annotations can be created, edited, imported, and persisted. -
Validation returns stable issue codes and record references. - Overlap
analysis follows the documented interval convention. - Quality summaries
use actual data. - Review decisions and audit history persist. -
CSV/JSON exports and manifest work. - CLI entry point works or exact
blocker is documented. - Assistant uses actual tool outputs and policy
references. - Optional CV status is accurate, with no automatic model
download. - Simulation phases come from actual annotations and
limitations are explicit. - Documentation matches behavior. - No tests
created or run. - Final report saved to
`docs/FINAL_IMPLEMENTATION_REPORT.md`. - No hard-coded secrets, unsafe
paths, fake metrics, or fake success states.

# 17. Mandatory final implementation report

Create `docs/FINAL_IMPLEMENTATION_REPORT.md` and then return a concise
user-facing summary.

Use this structure:

## Executive summary

What works end to end and what remains incomplete.

## Repository changes

Table of important paths, created/modified state, purpose, and status.

## Architecture delivered

Backend/frontend entry points, database/storage, processing engine,
assistant/retrieval, CV, simulation.

## Features implemented

For each feature: behavior, key files/endpoints, how to access it,
configuration/dependencies, limitations.

## Exact setup and launch

Working commands for Python setup, backend, frontend, optional
configuration, and demo data. Do not provide commands that have not been
reconciled with actual files.

## Dependency/configuration changes

Packages, environment variables, optional integrations, compatibility
concerns.

## Verification performed

Include this exact statement:

> **Testing was intentionally not performed in this implementation
> phase, as requested. No new test cases were created and no test suite
> was run.**

Then list only non-test checks actually performed (syntax/import check,
frontend build, API startup/health, manual UI inspection, etc.) with
passed/failed/not performed and evidence. Never invent results. If none
were performed, say so.

## Known limitations and risks

Include real issues such as local-only identity, optional weights,
deterministic assistant only, scripted simulation, no test coverage yet,
codec limitations.

## Deferred items

List intentional deferrals and reasons.

## Recommended next steps

Ordered plan for the owner to run the app, create a project,
upload/register a video, annotate, validate, review, inspect audit,
export, ask the assistant, run simulation, and later add tests and
evaluate AI.

## Recruiter demo script

A short 30--60 second explanation phrased only in terms of features
actually implemented. Do not claim physical robot control or custom
model training unless present.

## Outstanding blockers

Exact missing configuration, unresolved issues, and user actions
required.

# 18. Final instructions to the agent

Start by inspecting the current repository and Git status. Then
implement AURA end to end according to this document. Preserve the
current branch and user work. Do not merely repeat this prompt or
produce scaffolding only. Do not create or run tests. Keep the code
modular and the UI connected to real APIs. If a feature is blocked,
implement an honest fallback and report it. Finish by saving
`docs/FINAL_IMPLEMENTATION_REPORT.md` and telling the user where to find
it.
