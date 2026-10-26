# AURA implementation gap analysis

**Audit date:** 2026-10-27  
**Branch inspected:** `feature/1-initialize-aura-platform`

## Baseline inspected

- The current branch is the issue-named feature branch. Git history has the
  initial repository, prompt, and merge commits; no upgrade commit was made.
- The current worktree contains implementation-phase uncommitted changes. The
  repository's `.dist` directory and existing SQLite database were preserved.
- `data/aura.db` contains project `synthetic-demo-project`, video
  `demo-video-001`, and eight annotation rows. They are persisted Django ORM
  records, not frontend-only fixtures. The demo video is deliberately
  unavailable and synthetic. `data/media/` contained only `.gitkeep` at audit.
- The existing stack is Django 5.2 + Django ORM + SQLite, with React 18,
  TypeScript, and Vite. The initial ORM migration is present and applied.
- Prior implementation report and README were compared with source and
  manually verified API behavior. The report disclosed important omissions
  but overstated some implementation boundaries; this audit supersedes those
  claims where noted below.

## Existing behavior verified from code

- Project list/create/update/archive; registration/upload/listing of videos;
  annotation CRUD and CSV/JSON import; project/video validation; quality
  summary; project/annotation review; audit events; CSV/JSON export with
  checksum manifest; policy search; deterministic assistant; and
  annotation-derived simulation routes exist in `backend/aura_api/urls.py`.
- The UI is connected to the API for the main project, annotation, quality,
  assistant, audit, export, policy, and simulation screens.
- Django migration, configuration checks, Vite TypeScript/production build,
  API CRUD, a synthetic demo run, an approval-blocking check, and CLI sample
  validation were previously executed; see the final report for exact results.
- Uploads use generated names, a size cap and an extension/MIME allowlist;
  stream/download paths are resolved under configured roots.
- Demo data is created only on explicit request and `get_or_create` preserves
  the existing project. The actual local demo was inspected and left intact.

## Gaps and risks found in the pre-upgrade source

1. All API views were `csrf_exempt`; there was no Django session
   authentication, authorization, login flow, or server-side role enforcement.
2. API handlers in `views.py` contain domain, validation, persistence,
   export, file, and assistant logic in a single large module. Multi-step
   project review and export writes need explicit atomicity.
3. Collections lacked standard pagination, filters, and stable paging metadata.
4. Labels were duplicated as constants; there was no persisted ontology.
5. Annotation constraints were primarily in request handlers. Approved
   records had no immutable revision history.
6. Review transitions did not enforce maker-checker or a clear submit/review
   sequence, and project decisions were not captured as individual revision
   snapshots.
7. Validation snapshots record issue JSON and counts but do not bind to input
   revisions/checksums. A source video metadata update/archive is not expressed
   as a staleness condition.
8. Exports wrote artifacts before creating DB metadata/audit rows and did not
   verify files on download. They had no immutable version/source snapshot.
9. Import validation is atomic but there is no separate preview endpoint,
   source checksum, stable duplicate-resolution policy, or persisted rejected
   row summary. The upload handler has no explicit request ID or processing
   state.
10. OpenCV support returns frame metadata but no persisted sample job,
    thumbnails, or retry/status model. Detector and provider-backed LLM are
    not implemented and are honestly reported as unavailable.
11. Frontend still contains `any`-typed API results and hard-coded label
    options; a full annotation-level review queue, ontology editor, box
    annotation UI, and simulation reload remain absent.
12. Operations diagnostics were missing. There was no PostgreSQL profile.
13. There were no automated tests in the initial implementation.

## Architecture decision record: retain Django

The running code, migrations, and local data use Django ORM and SQLite. The
upgrade brief explicitly requires continuing this stack. Replacing it would
add data migration risk without solving a demonstrated problem. Django ORM is
retained as a modular monolith, forward migrations preserve all existing
project/video/annotation IDs, SQLite remains the quick-start database, and an
optional PostgreSQL profile is available via environment configuration.

## Ordered implementation plan

1. **Implemented:** Django session authentication, CSRF mutations, role
   gates/account commands, readiness diagnostics, request IDs, pagination,
   and boundary validation.
2. **Implemented baseline:** Annotation snapshots, review transitions,
   maker-checker approval, and transactional review/audit writes.
3. **Implemented baseline:** Versioned v1 ontology and atomic import label
   validation. Ontology editor, upload checksum workflow enhancements, and
   import preview remain deferred.
4. **Implemented baseline:** Immutable release numbers/source snapshots,
   atomic artifact/metadata write handling, deterministic CSV/JSON bytes,
   manifests, and download checksum verification.
5. **Partially implemented:** Operations/docs and auth UI were updated;
   full typed API modeling, filters, and remaining workflows are still gaps.
6. **Implemented:** Focused Django tests, migration/system checks, frontend
   build, CLI validation, and data-preservation checks were completed. A
   browser walkthrough was documented but not manually run.

## Upgrade implementation and verification

The upgrade now provides Django session login/logout and CSRF-protected
mutations, server-side role groups with a provisioning command, request IDs,
health/readiness checks, paginated core collections, a seeded versioned
ontology, immutable annotation revision snapshots, submit/review state
transitions, maker-checker approval, atomic versioned CSV/JSON releases, and
download checksum verification. The focused Django tests cover these flows;
exact commands/results and the database-preservation check are in
`docs/FINAL_IMPLEMENTATION_REPORT.md`.

## Full expansion prompt progress (2026-10-27)

The current follow-on request expands AURA beyond the earlier security and
release upgrade. In this implementation pass, one complete vertical slice was
added: a deterministic 3×3 pick-and-place task environment, tabular
Q-learning, separate fixed-seed baseline evaluation, persisted experiment and
Q-table records, a role-gated API, a management command, the Simulation-page
controls/metrics, and focused tests. The policy checksum and evaluation
results are persisted; this is simulator learning only, not a physical robot
policy and not learning from annotations.

The remaining expansion phases are not silently represented as completed:

- Ontology administration, object instances/boxes/tracks, and the full
  annotation-level review queue remain incomplete.
- Bronze/Silver/Gold pipeline processing, durable job/retry records,
  quarantined rows, and pipeline artifact lineage are not implemented.
- No detector inference, YOLO weights, frame browser, or CV evaluation ran.
- No supervised ML baseline, DQN, model registry, or MLflow integration exists.
- The current assistant is deterministic local policy search; document
  ingestion, vector retrieval, provider LLM, and a tool-using agent are absent.
- No isolated BFSI document-intelligence domain pack exists.
- The PostgreSQL runtime, browser UX, and deployment security are not verified.

## Remaining limitations

The app is suitable for local use and controlled evaluation, not an
unreviewed public deployment. Authentication exists, but deployment security
hardening, rate limiting, OpenAPI, ontology editing, full filters/import
preview, durable vision-processing jobs, detector/LLM adapters, COCO/YOLO
export, object-level annotation UI, and physical robot simulation remain
deferred. The original demo project ID and records remain intact. A database
backup was made before applying these forward migrations.
