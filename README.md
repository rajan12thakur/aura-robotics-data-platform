# AURA — Robotics Data Workspace

AURA (AI-assisted Understanding, Review and Action for Robotics Data) is a
local-first web workspace for managing demonstration-video metadata,
time-aligned action annotations, deterministic quality validation, human
review, traceable dataset exports, policy-grounded assistance, and a
scripted task-level visualization.

## Honest feature status

| Capability | Status |
|---|---|
| Persistent projects, video registration/upload, annotation CRUD | Implemented |
| CSV/JSON processor, CLI, validation, overlap checks, quality summaries | Implemented |
| Review decisions, audit events, CSV/JSON exports and manifests | Implemented |
| React workspace, project dashboard, timeline, quality, policy, audit | Implemented |
| Local deterministic assistant and policy-section retrieval | Implemented; bounded intent handling |
| Video & Document Chat | Implemented in deterministic extractive + lexical SQLite mode; PDF/page and annotation/time citations persist |
| ChromaDB / local sentence-transformer retrieval | Optional adapter implemented; not installed/configured in this environment; current capability reports lexical fallback |
| Synthetic demonstration fixture | Implemented; explicitly loaded, no real video |
| OpenCV video metadata and frame metadata | Optional; requires OpenCV |
| Managed-video playback | Implemented; codec/browser support varies |
| Django session login, CSRF protection, and server-side role checks | Implemented; local accounts must be provisioned |
| Versioned action ontology and annotation revision snapshots | Implemented; v1 vocabulary is seeded by migration |
| Versioned CSV/JSON releases with manifest/source checksums | Implemented; approved records only by default |
| Task-level grid environment, tabular Q-learning, baseline evaluation | Implemented; not a physical robot policy |
| Object detector inference / real LLM provider | Deferred; not implemented |
| Physical robot control or physics simulation | Out of scope; scripted visualization only |
| DQN, behavior cloning, policy deployment | Deferred |
| Production deployment hardening, OpenAPI, object-level annotation | Deferred |
| Automated Django API checks | Implemented; see final report for exact scope |

## Product flow

```text
React/Vite UI ── HTTP /api/v1 ── Django views ── Django ORM ── SQLite
       │                            │
       │                            ├── annotation_processor (CSV/JSON, validation)
       │                            ├── local policy retrieval + deterministic assistant
       │                            ├── managed media (data/media/)
       │                            └── export artifacts + manifests (output/exports/)
       └── Upload/register → annotate → validate → review → export → simulate
```

The Python processor is independent of HTTP/database code. The API persists
projects and annotations. Video & Document Chat builds evidence from actual
stored video/annotation/validation records and private PDF uploads; the UI
does not emulate persisted workflows with frontend-only state.

## Repository structure

```text
backend/aura_api/          Django settings, API views, ORM models
src/annotation_processor/  Framework-independent import, validation, CLI
frontend/                  React + TypeScript + Vite application
docs/                      Policy, schema, architecture, feature limitations
data/examples/              Clearly synthetic CSV sample
data/media/                 Ignored local uploads
output/exports/             Ignored generated export files
```

## Prerequisites and Windows setup

Use Python 3.11+ and Node.js/npm. From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python manage.py migrate
python manage.py createsuperuser
```

`.env.example` documents supported environment variables. This build does not
load a `.env` file automatically; set overrides in PowerShell, for example
`$env:AURA_DEFAULT_REVIEWER = "Reviewer"`.

In one PowerShell window, start the Django API:

```powershell
python manage.py runserver 127.0.0.1:8000
```

In another, start the frontend:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. API health is at
`http://127.0.0.1:8000/api/v1/health`; the API index is at
`http://127.0.0.1:8000/api/v1/`; readiness is at
`http://127.0.0.1:8000/api/v1/health/ready`. Sign in with the Django
superuser created above; superusers have the AURA Administrator role. To
create a least-privilege account, run:

```powershell
python manage.py aura_create_user annotator
python manage.py aura_assign_role annotator Annotator
```

Available roles are `Administrator`, `Project Manager`, `Annotator`,
`Reviewer`, `Dataset Manager`, `ML Engineer`, and `Read-only Auditor`. Django
ORM schema migrations are run with `python manage.py migrate`. An interactive
OpenAPI/Swagger page is not included in this Django build. The frontend Vite
server proxies `/api` to the local API.

If startup fails with `ModuleNotFoundError: No module named 'aura_rag'`,
reinstall the editable project into the same active virtual environment used
to launch Django, from the repository root:

```powershell
python -m pip install -e .
python -c "import aura_rag; print(aura_rag.__file__)"
python manage.py runserver 127.0.0.1:8000
```

Installing only `requirements.txt` installs third-party dependencies; it does
not install the project's `src` packages. Keep the virtual environment
activated in the PowerShell window where these commands run.

For a PostgreSQL profile, install the optional driver with
`python -m pip install -e ".[postgres]"`, set `AURA_DB_ENGINE=postgresql` and
`AURA_DB_NAME`, `AURA_DB_USER`, and `AURA_DB_PASSWORD` (optionally
`AURA_DB_HOST` and `AURA_DB_PORT`), then run the same migrations. SQLite
remains the default local quick-start database.

## Local workflow

1. Create a project from **Projects**, or select **Load synthetic demo**.
   The demo action is idempotent and clearly labels its records synthetic.
2. In **Annotation Workspace**, upload a supported video file or register
   metadata for an external video. Metadata-only video has no playback.
3. Select a video and create/edit/delete action segments. For a managed video,
   use the player and **Set start / Set end** shortcuts.
4. Run deterministic validation from **Dataset Quality**. Use **Submit drafts
   for review** to move draft records into the reviewer queue. Reviewers can
   approve only submitted records; hard validation errors block approval.
5. Ask supported questions in **AI Assistant**; answers cite actual local
   validation or canonical policy sections.
6. Approve records and create default approved-only CSV/JSON exports. An
   unapproved export is a separate explicit action, recorded in the audit log.
7. Prepare a task-level run in **Simulation**, then advance through annotation
   phases and inspect missing/unmapped actions.
8. In the Simulation page's reinforcement-learning lab, train a bounded
   Q-learning policy or evaluate the deterministic baseline and compare
   separate fixed-seed evaluation results.
9. Open **Video & Document Chat**, index the selected video's stored
   annotation evidence, upload
   `data/examples/synthetic_robot_operating_guideline.pdf`, select the PDF
   scope, and ask a question. Citations point to actual annotation intervals
   or extracted PDF pages. In this checkout, retrieval is explicitly
   `lexical_sqlite`; no local embedding model is configured.

The synthetic example is `data/examples/sample_annotations.csv`. It has no
corresponding video. It is not automatically seeded at startup.
The one-page `data/examples/synthetic_robot_operating_guideline.pdf` is a
fictional retrieval fixture, not an approved robot safety procedure.

For setup, privacy boundaries, RAG API details, optional local embeddings and
known limitations, see [docs/AI_AGENT_AND_RAG.md](./docs/AI_AGENT_AND_RAG.md).
The RAG dependency group can be installed with
`python -m pip install -e ".[rag]"`; installing it does not download a model.

## Data contracts and CLI

Canonical CSV fields:

```csv
video_id,start_time,end_time,action_label,object_label,actor_id,confidence,notes
```

JSON accepts an annotation array or `{"schema_version":"1.0","annotations":[]}`.
Timestamps are seconds; intervals are half-open `[start,end)`. See
[docs/dataset_schema.md](docs/dataset_schema.md) and
[docs/annotation_policy_v1.md](docs/annotation_policy_v1.md).

After editable installation, use:

```powershell
annotation-processor --help
annotation-processor validate data/examples/sample_annotations.csv
annotation-processor report data/examples/sample_annotations.csv --output output/reports/quality_report.json
annotation-processor export data/examples/sample_annotations.csv --format json --output output/exports/annotations.json
```

The CLI does not require the API/database. `validate` exits nonzero for
deterministic errors and prints issue details. Unknown CSV columns are
reported as warnings. The API import is atomic and returns a validation error
instead of silently importing a subset.

## Configuration, storage and privacy

Defaults: loopback host `127.0.0.1`, port `8000`, SQLite at `data/aura.db`,
managed video under `data/media/`, exports/reports under `output/`, upload
limit 250 MB, and frontend origin `http://localhost:5173`. See
[.env.example](.env.example). `.env`, DB files, uploads, frontend dependencies,
and generated exports are ignored by Git.

Supported settings: `AURA_APP_NAME`, `AURA_ENV`,
`AURA_DATABASE_PATH`, `AURA_DB_ENGINE`, `AURA_DB_NAME`, `AURA_DB_USER`,
`AURA_DB_PASSWORD`, `AURA_DB_HOST`, `AURA_DB_PORT`, `AURA_ALLOWED_HOSTS`,
`DJANGO_SECRET_KEY`, `AURA_DATA_DIR`,
`AURA_MEDIA_DIR`, `AURA_OUTPUT_DIR`, `AURA_MAX_UPLOAD_MB`,
`AURA_FRONTEND_ORIGIN`, `AURA_DEFAULT_REVIEWER`, and
`AURA_FRAME_SAMPLE_LIMIT`. The Django development server's bind address and
port are passed as `runserver` command arguments. `DJANGO_SECRET_KEY` may be
left blank for a process-random local-development key; configure a persistent
secret via environment for deployments. `AURA_VISION_ENABLED`,
`AURA_VISION_MODEL`, and `AURA_VISION_WEIGHTS_PATH` are status/configuration
hints; no detector adapter is implemented. `AURA_LLM_*` is reserved and no
LLM adapter is implemented. Capability responses never reveal credentials.

The application uses Django session authentication, CSRF protection, and
server-side role gates. Create/provision accounts locally; client-supplied
actor names are not trusted for reviewer decisions. This is not a
production-hardening or security-review sign-off: do not expose the Django
development server to untrusted networks. Uploads remain local; no video or
dataset is sent to an AI provider.

## Assistant, CV and simulation boundaries

The assistant uses deterministic intent routing, local annotation/policy facts,
and bounded policy-section retrieval; unsupported questions disclose the
limitation. A real provider adapter is deferred.

OpenCV is optional. When available, AURA can extract basic metadata and bounded
frame metadata. Frame previews and object detection are not implemented.
Manual annotation works without OpenCV; codec support depends on OpenCV and the
browser.

Simulation is an annotation-derived phase visualization only. Labels such as
`grasp`/`lift` do not provide coordinates, trajectories, forces, or collision
plans and cannot train/control a physical robot. See
[docs/simulation.md](docs/simulation.md).

The separate learning lab uses rewards and transitions from a deterministic
3×3 grid environment; annotations are not used as training transitions. It
does not model physical robotics or provide a deployable robot policy. See
[docs/REINFORCEMENT_LEARNING.md](docs/REINFORCEMENT_LEARNING.md).

## Developer checks

Run the focused backend suite and frontend typecheck/build with:

```powershell
python manage.py test aura_api.tests
Set-Location frontend
npm run build
```

## Documentation

- [System architecture](docs/system_architecture.md)
- [Annotation policy](docs/annotation_policy_v1.md)
- [Dataset schema](docs/dataset_schema.md)
- [Assistant behavior](docs/ai_assistant.md)
- [CV pipeline](docs/cv_pipeline.md)
- [Simulation scope](docs/simulation.md)
- [Implementation status](docs/implementation_status.md)
- [Final implementation report](docs/FINAL_IMPLEMENTATION_REPORT.md)
