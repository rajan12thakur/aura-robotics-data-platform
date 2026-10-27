# AURA — Robotics Data Workspace

**An end-to-end workspace for robotics demonstration data, temporal annotation, dataset quality, evidence-grounded knowledge retrieval, and traceable data operations.**

AURA is a local-first, full-stack application designed to demonstrate how robotics data can move from raw demonstration assets to structured annotations, quality validation, human review, and reproducible dataset exports.

The platform combines a React and TypeScript frontend with a Django backend, persistent data models, a standalone Python annotation processor, and a knowledge workspace for querying available project evidence.

> **Project status:** Active development. Core data-management workflows are implemented. Advanced AI capabilities are being developed incrementally and are identified separately from verified functionality.

---

## Table of Contents

- [Overview](#overview)
- [Problem Statement](#problem-statement)
- [Project Objectives](#project-objectives)
- [Key Features](#key-features)
- [Platform Architecture](#platform-architecture)
- [Technology Stack](#technology-stack)
- [Application Modules](#application-modules)
- [Annotation Data Lifecycle](#annotation-data-lifecycle)
- [Knowledge Retrieval and RAG](#knowledge-retrieval-and-rag)
- [Data Engineering Pipeline](#data-engineering-pipeline)
- [Authentication and Security](#authentication-and-security)
- [Repository Structure](#repository-structure)
- [Installation and Setup](#installation-and-setup)
- [Running the Application](#running-the-application)
- [Creating a User Account](#creating-a-user-account)
- [API Overview](#api-overview)
- [Testing and Verification](#testing-and-verification)
- [Current Implementation Status](#current-implementation-status)
- [Limitations and Roadmap](#limitations-and-roadmap)
- [Engineering Principles](#engineering-principles)
- [Learning Outcomes](#learning-outcomes)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

Robotics systems learn from structured demonstrations, annotated observations, and carefully curated datasets. Preparing these datasets involves much more than uploading a video or drawing a bounding box.

A reliable workflow needs to support:

- Organizing projects and demonstration assets.
- Registering and managing video metadata.
- Recording time-aligned action segments.
- Importing and validating annotation datasets.
- Detecting temporal overlaps and data-quality issues.
- Reviewing and approving annotations.
- Maintaining revision history and audit events.
- Exporting structured datasets with traceability.
- Searching relevant project evidence and policy documents.
- Experimenting with task-level environments and reinforcement-learning concepts.

AURA brings these operations into one local workspace.

The application is intended both as a practical engineering project and as a demonstration of the foundations required to build larger robotics-data and AI-assisted annotation systems.

### What AURA demonstrates

| Engineering area | Demonstration |
|---|---|
| Full-stack development | React frontend connected to a Django API |
| Backend engineering | Django models, request handling, validation, and persistence |
| Data modeling | Projects, videos, annotations, revisions, and ontology labels |
| Data quality | Deterministic validation and quality summaries |
| Human-in-the-loop workflows | Annotation review and project-level review decisions |
| Data engineering | Structured ingestion, transformation, quality checks, and exports |
| Knowledge retrieval | Search over available project evidence and documents |
| Dataset traceability | Revision records, audit events, and export manifests |
| Machine learning foundations | Task-level simulation and reinforcement-learning experiments |
| Software testing | Automated backend tests and frontend build verification |

---

## Problem Statement

Robotics demonstration data can contain inconsistent timestamps, incomplete annotations, overlapping actions, missing evidence, inconsistent labels, and unclear review status.

When these problems are handled manually or across disconnected tools, dataset preparation becomes difficult to reproduce and audit.

AURA addresses this problem by providing a structured workflow in which demonstration metadata, annotations, validation results, review decisions, and export artifacts can be managed through a common application.

The long-term goal is to evolve the platform toward AI-assisted annotation, multimodal evidence retrieval, model-assisted suggestions, and measurable dataset-quality improvements.

---

## Project Objectives

The project is designed around six objectives.

### 1. Structured data management

Maintain persistent records for projects, videos, annotations, ontology labels, and associated workflow information.

### 2. Annotation quality

Validate annotation structure and temporal constraints before datasets move through review and export.

### 3. Human oversight

Keep review decisions explicit and preserve traceability instead of treating automatically generated outputs as inherently correct.

### 4. Reproducible exports

Generate structured dataset exports with associated metadata and manifests so exported artifacts can be inspected and traced back to their source data.

### 5. Evidence-grounded assistance

Provide a knowledge interface that retrieves relevant available evidence and presents source references rather than inventing answers when supporting evidence is missing.

### 6. Extensible AI architecture

Create a foundation for future integration of computer vision, embedding-based retrieval, language models, and learning-based robotics workflows.

---

## Key Features

### Project Management

- Create and manage robotics data projects.
- Associate video assets with projects.
- Inspect project-level dataset information.
- Review annotation and quality summaries.
- Access related workflow information through the application interface.

### Video Asset Management

- Register video metadata.
- Upload managed video files.
- Track metadata-only video registrations.
- Inspect available video metadata.
- Extract frame metadata when the relevant optional dependencies and workflow are available.

**Important:** Registering video metadata does not mean that the corresponding video file exists. Playback is unavailable for metadata-only registrations.

### Annotation Workspace

- Create and edit time-aligned action annotations.
- Associate annotations with videos and projects.
- Import annotation records from CSV and JSON.
- Inspect annotation revisions.
- Work with a versioned action ontology.
- Validate annotations before review or export.

### Dataset Quality

- Validate annotation structure and supported constraints.
- Detect temporal overlap issues.
- Produce quality summaries.
- Inspect validation results.
- Identify records that require correction or review.

### Review and Auditability

- Submit project data for review.
- Record review decisions.
- Preserve annotation revision snapshots.
- Maintain audit events for supported operations.
- Distinguish approved data from data that has not completed review.

### Dataset Export

- Generate CSV and JSON exports.
- Support approved-only exports by default.
- Make unapproved exports explicit where supported.
- Include export metadata and manifests.
- Preserve source traceability through associated identifiers and checksums.

### AI Assistant and Policy Workspace

- Query supported local policy and annotation guidance.
- Retrieve relevant policy sections using deterministic search.
- Provide bounded, rule-based assistance for supported requests.

The local assistant should not be confused with a fully autonomous, general-purpose LLM agent.

### Video & Document Chat

The knowledge workspace supports document and project-evidence retrieval.

Implemented functionality includes:

- PDF source ingestion.
- Source lifecycle management.
- Evidence derived from stored project and annotation records.
- Lexical retrieval.
- Extractive responses in the deterministic retrieval mode.
- Source citations for supported document pages and project evidence.
- Persistent conversations.
- Abstention when available evidence does not adequately support an answer.

An optional dense-retrieval adapter is being developed, but the active retrieval mode must be checked in the running environment before claiming that vector search is operational.

### Simulation and Reinforcement-Learning Foundations

The platform includes a task-level grid environment and tabular Q-learning foundations for experimenting with action selection and task-level rewards.

This is a controlled software environment, not a physical robotics simulator.

---

## Platform Architecture

AURA follows a layered architecture that separates the frontend, HTTP API, persistent domain models, processing logic, and generated artifacts.

```text
                         AURA ROBOTICS DATA WORKSPACE
                                      |
                 +--------------------+--------------------+
                 |                                         |
          React + TypeScript                        Vite Development
             Frontend                                 Server
                 |                                         |
                 +--------------------+--------------------+
                                      |
                              HTTP /api/v1
                                      |
                           Django Application
                                      |
                 +--------------------+--------------------+
                 |                    |                    |
            API Views             Domain Models        Authentication
                 |                    |                    |
                 +--------------------+--------------------+
                                      |
                                  Django ORM
                                      |
                                  SQLite DB
                                      |
             +------------------------+------------------------+
             |                        |                        |
       Project Records          Annotation Records       Knowledge Records
             |                        |                        |
             +------------------------+------------------------+
                                      |
                          Python Processing Components
                                      |
             +------------------------+------------------------+
             |                        |                        |
       CSV/JSON Processor      Quality Validation       Knowledge Retrieval
             |                        |                        |
             +------------------------+------------------------+
                                      |
                           Generated Data Artifacts
                                      |
                    Exports, Manifests, Reports, Pipelines
```

### Frontend

The frontend provides the user interface for project management, annotation workflows, quality inspection, policy access, knowledge retrieval, and related operations.

### Backend

The Django application provides HTTP endpoints, request validation, persistence, authentication, and workflow logic.

### Persistence

Django ORM models provide structured storage. SQLite is the default local database, with configuration options for PostgreSQL.

### Processing

The standalone annotation processor handles supported CSV/JSON processing and validation independently of the web interface.

### Artifacts

Generated exports, pipeline outputs, managed media, and other local artifacts are kept separate from the main application source code.

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React | Component-based user interface |
| Frontend language | TypeScript | Typed frontend development |
| Frontend tooling | Vite | Local development server and production builds |
| Backend | Python | Application and processing logic |
| Web framework | Django 5.x | API, models, authentication, and persistence |
| ORM | Django ORM | Database access and domain persistence |
| Default database | SQLite | Local development persistence |
| Alternative database | PostgreSQL | Configurable relational database |
| Data interchange | CSV, JSON | Annotation ingestion and exports |
| Document processing | PDF extraction | Document evidence ingestion |
| Knowledge retrieval | SQLite-backed lexical retrieval | Current deterministic retrieval path |
| Optional retrieval | ChromaDB and local embeddings | Dense-retrieval extension, subject to installation and verification |
| Testing | Django test framework | Backend checks and regression testing |
| Version control | Git | Source history and collaboration |

The table describes the architecture and optional extensions. It does not imply that every optional library is installed or active in every environment.

---

## Application Modules

### 1. Overview Dashboard

Provides a high-level view of available projects and related dataset information.

### 2. Project Management

Organizes demonstration datasets and their associated assets.

### 3. Annotation Workspace

Provides the interface for selecting videos, registering metadata, managing annotations, and importing structured records.

### 4. Dataset Quality

Displays validation information and supported quality summaries.

### 5. AI Assistant

Provides bounded assistance for supported policy and annotation queries.

### 6. Video & Document Chat

Supports knowledge-source ingestion, retrieval, citations, and persistent conversations.

### 7. Simulation

Provides access to the task-level environment and supported reinforcement-learning experiments.

### 8. Policy & Guidelines

Provides access to supported annotation policies and relevant policy sections.

### 9. Audit Trail

Exposes supported audit events to help trace workflow operations.

### 10. Settings

Provides access to the application's available configuration and workspace controls.

---

## Annotation Data Lifecycle

A central design principle is that annotations should pass through explicit quality and review stages before being treated as approved dataset records.

```text
Create Project
      |
      v
Register or Upload Video
      |
      v
Create / Import Annotations
      |
      v
Validate Dataset
      |
      +------ Issues Found ------> Correct Annotations
      |                                  |
      |                                  v
      |                              Validate Again
      |                                  |
      +<---------------------------------+
      |
      v
Submit for Review
      |
      v
Record Review Decision
      |
      +------ Changes Required ------> Update Data
      |                                   |
      |                                   v
      |                              Revalidate
      |
      v
Approved Dataset
      |
      v
Generate Export
      |
      v
Inspect Export and Manifest
```

The diagram describes the intended workflow. Exact transition rules and permissions are determined by the implemented backend behavior.

### Annotation processing principles

- Input records should be structurally valid.
- Timestamps must satisfy the supported temporal constraints.
- Overlaps should be detected and reported where applicable.
- Ontology labels should follow the available vocabulary.
- Review decisions should remain traceable.
- Exports should distinguish approved records from unreviewed records.
- Failed or invalid records should not silently disappear during processing.

---

## Knowledge Retrieval and RAG

The Video & Document Chat module is designed to answer questions using available project evidence rather than relying exclusively on model-generated knowledge.

### Current retrieval flow

```text
User Question
      |
      v
Knowledge API
      |
      v
Resolve Available Sources
      |
      +-------------------------------+
      |                               |
      v                               v
Uploaded PDF Evidence         Stored Project Evidence
      |                               |
      v                               v
Extracted Document Text        Annotation / Video Records
      |                               |
      +---------------+---------------+
                      |
                      v
              Lexical Retrieval
                      |
                      v
              Evidence Selection
                      |
                      v
          Deterministic Extractive Answer
                      |
                      v
             Source References
                      |
                      v
            Persisted Conversation
```

### Retrieval capabilities

The implemented deterministic retrieval path supports source-based retrieval and extractive answers. It is useful for demonstrating the evidence lifecycle, document ingestion, persistence, and citation handling.

### Optional dense retrieval

An optional adapter for local embeddings and ChromaDB has been introduced.

However, dense retrieval should only be considered operational after the dependencies, model configuration, vector index, and retrieval behavior have been tested successfully. The current documented environment uses lexical retrieval as its fallback and active mode.

### LLM integration

A fully operational provider-backed LLM answer-generation layer is not yet verified as part of the current implementation.

The architecture can be extended to use an LLM after evidence retrieval, but the application must preserve source grounding, handle unsupported questions, and avoid presenting unverified generated statements as facts.

---

## Data Engineering Pipeline

AURA includes a local data-pipeline foundation for processing project videos and annotation records.

The pipeline follows a medallion-style organization.

```text
              Source Project Data
                      |
                      v
               BRONZE LAYER
        Raw / Ingested Structured Records
                      |
                      v
               SILVER LAYER
       Normalization and Quality Checks
                      |
                      v
                GOLD LAYER
       Curated Data for Downstream Use
                      |
             +--------+--------+
             |                 |
             v                 v
       Dataset Exports    Quality Reports
```

### Bronze

Preserves the ingestion-oriented representation of supported source records.

### Silver

Provides the layer for normalized records and validation results.

### Gold

Provides curated records intended for downstream analysis and export.

### Pipeline considerations

The local pipeline implementation includes structured CSV/JSON outputs, quarantine handling, checksums, idempotent batch foundations, and CLI/API/UI integration as documented in the implementation status.

The pipeline is currently a local application workflow, not a production-scale distributed data platform.

It should not be described as a Spark, Kafka, or Airflow pipeline unless those components are actually implemented and verified.

---

## Authentication and Security

AURA uses Django authentication and session-based login for the local workspace.

The authentication implementation includes:

- Django user accounts.
- Session-based authentication.
- CSRF protection for applicable requests.
- Server-side role checks for supported operations.
- Login, logout, and current-user API endpoints.
- Local account provisioning.

### Local authentication setup

The frontend and backend are configured to work together through the Vite development proxy and Django API.

For local development, both services must be running, and the browser must be able to reach the configured API endpoints.

A successful login to Django administration can establish a Django session in the same browser. Whether that session also authenticates the frontend depends on the configured host, cookies, and authentication checks.

### Security boundaries

This project is intended for local development and demonstration.

Before production deployment, additional work is needed for deployment hardening, secure secret management, operational monitoring, and a comprehensive security review.

Never commit database passwords, API keys, production secrets, or private environment files.

---

## Repository Structure

```text
aura-robotics-data-platform/
|
|-- backend/
|   |-- aura_api/
|       |-- settings.py
|       |-- urls.py
|       |-- views.py
|       |-- models.py
|       |-- migrations/
|       |-- tests.py
|
|-- frontend/
|   |-- src/
|   |-- package.json
|   |-- vite.config.ts
|
|-- src/
|   |-- annotation_processor/
|
|-- data/
|   |-- examples/
|   |-- media/
|   |-- pipelines/
|   |-- aura.db
|
|-- output/
|   |-- exports/
|
|-- docs/
|   |-- system_architecture.md
|   |-- annotation_policy_v1.md
|   |-- dataset_schema.md
|   |-- AI_AGENT_AND_RAG.md
|   |-- IMPLEMENTATION_STATUS.md
|   |-- FINAL_IMPLEMENTATION_REPORT.md
|
|-- manage.py
|-- pyproject.toml
|-- requirements.txt
|-- .env.example
|-- .gitignore
|-- README.md
```

The exact files and directories may vary slightly as implementation progresses. Local databases, uploads, generated outputs, and environment-specific files should remain separate from version-controlled source code.

---

## Installation and Setup

The following instructions are for a local Windows development environment using PowerShell.

### Prerequisites

Install the following:

- Python 3.11 or another version supported by the repository's dependency configuration.
- Node.js and npm.
- Git.
- A terminal such as PowerShell.
- A browser such as Chrome or Firefox.

The existing virtual environment and Python installation should be compatible with the versions specified in `pyproject.toml` and the dependency files.

### 1. Clone the repository

```powershell
git clone https://github.com/rajan12thakur/aura-robotics-data-platform.git

cd aura-robotics-data-platform
```

If you already have the project locally, open PowerShell in the existing repository instead. Do not clone over your working directory.

### 2. Create and activate the Python environment

```powershell
python -m venv .venv

.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation for the current terminal, use:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned

.\.venv\Scripts\Activate.ps1
```

### 3. Install backend dependencies

Use the repository's declared dependency configuration.

```powershell
python -m pip install --upgrade pip

python -m pip install -e .
```

If editable installation is not supported by the current checkout, inspect `pyproject.toml` and `requirements.txt` and use the installation method specified there.

Optional RAG and database dependencies may require their corresponding extras or explicit installation. Do not assume that optional dependencies are installed simply because their adapters exist in the codebase.

### 4. Configure environment variables

Review `.env.example` and configure any required environment variables using your local development environment.

The application supports configuration for items such as:

- Application environment.
- Django secret key.
- Allowed hosts.
- Database engine.
- PostgreSQL connection settings.
- Frontend origin.
- Data, media, and output directories.

SQLite is the default database for local development.

**Do not replace an existing database path or create a fresh database over existing data.** Check the current environment configuration before changing database settings.

### 5. Apply database migrations

From the repository root:

```powershell
python manage.py migrate
```

Migrations update the database schema. They should be reviewed before applying them to a database containing important data.

For an existing installation, make a verified backup before running new migrations.

### 6. Create a Django user

```powershell
python manage.py createsuperuser
```

Follow the prompts to create a username, email address if requested, and password.

Use your own credentials. Do not put passwords in the README or source code.

If a suitable superuser already exists, you do not need to create another one.

### 7. Install frontend dependencies

Open a second PowerShell terminal and navigate to the frontend:

```powershell
cd frontend

npm install
```

If the repository contains a valid `package-lock.json`, `npm ci` is preferable for a reproducible installation.

### 8. Build the frontend

```powershell
npm run build
```

A successful build confirms that the frontend can be compiled. It does not, by itself, verify that every API workflow works correctly.

---

## Running the Application

AURA uses two development servers.

### Terminal 1: Django backend

From the repository root:

```powershell
.\.venv\Scripts\Activate.ps1

python manage.py runserver 127.0.0.1:8000
```

Backend base address:

```text
http://127.0.0.1:8000
```

Health endpoint:

```text
http://127.0.0.1:8000/api/v1/health
```

### Terminal 2: React frontend

From the frontend directory:

```powershell
npm run dev
```

The development server normally uses:

```text
http://127.0.0.1:5173
```

Check the address printed by Vite in your terminal if the port differs.

### Vite API proxy

The development configuration proxies API requests to Django:

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
```

With this configuration, the browser can send requests to paths such as `/api/v1/health` through the frontend origin.

### Accessing the workspace

Open the frontend address printed by Vite.

If authentication is enabled and no valid session exists, sign in using an account provisioned for the local installation.

Django administration is available at:

```text
http://127.0.0.1:8000/admin/
```

The frontend and Django administration use the same backend user database, but frontend authentication depends on the application's session and CSRF handling.

---

## Creating a User Account

If you need to create a new account, use the Django management command:

```powershell
python manage.py createsuperuser
```

If the frontend login screen returns a `404 Not Found`, check the request URL and response before changing user credentials.

For example, the frontend login endpoint is expected to be available at:

```text
/api/v1/auth/login
```

A `404` indicates that the requested route was not found at the responding server. It does not necessarily mean the username or password is incorrect.

Check the following:

1. Django is running on the expected port.
2. Vite is running on the expected port.
3. `vite.config.ts` contains the correct API proxy.
4. Django's root URL configuration includes the authentication route.
5. The browser request uses the expected path.
6. The Django server log shows the request and response.
7. The frontend and backend are using the intended local database.

If the request returns `401` or another authentication-related response instead, inspect the response body and the backend login implementation.

Avoid deleting the database or resetting migrations to troubleshoot login problems.

---

## API Overview

AURA exposes versioned HTTP API endpoints under `/api/v1/`.

The following table describes representative endpoint groups in the current application.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health` | Basic service health |
| `GET /api/v1/health/ready` | Readiness checks |
| `GET /api/v1/auth/csrf` | CSRF initialization |
| `POST /api/v1/auth/login` | Login |
| `POST /api/v1/auth/logout` | Logout |
| `GET /api/v1/auth/me` | Current-user information |
| `GET /api/v1/config/capabilities` | Capability information |
| `GET /api/v1/projects` | Project listing |
| `POST /api/v1/projects` | Project creation, where supported by the request contract |
| `GET /api/v1/projects/{project_id}/videos` | Project video listing |
| `POST /api/v1/projects/{project_id}/videos/register` | Register video metadata |
| `GET /api/v1/videos/{video_id}/annotations` | Video annotation listing |
| `POST /api/v1/videos/{video_id}/annotations` | Annotation creation, subject to validation and permissions |
| `POST /api/v1/videos/{video_id}/validate` | Video-level validation |
| `POST /api/v1/projects/{project_id}/validate` | Project-level validation |
| `GET /api/v1/projects/{project_id}/quality-summary` | Quality summary |
| `POST /api/v1/projects/{project_id}/submit-review` | Submit project for review |
| `POST /api/v1/projects/{project_id}/review` | Record a supported review decision |
| `GET /api/v1/projects/{project_id}/audit-events` | Project audit events |
| `GET /api/v1/projects/{project_id}/exports` | Project export listing |
| `POST /api/v1/assistant/ask` | Supported assistant queries |
| `GET /api/v1/projects/{project_id}/knowledge/sources` | Knowledge-source listing |
| `POST /api/v1/videos/{video_id}/knowledge/index` | Index supported video/project evidence |
| `GET /api/v1/projects/{project_id}/knowledge/conversations` | Knowledge conversation listing |
| `GET /api/v1/vision/status` | Vision capability status |
| `GET /api/v1/rl/environment` | Task-level reinforcement-learning environment information |

**API note:** The table is a navigation aid, not a complete API specification. Request bodies, HTTP methods, authentication requirements, validation rules, and response schemas should be confirmed from `backend/aura_api/urls.py`, `views.py`, and the corresponding frontend API client. Not every endpoint supports every HTTP method.

---

## Testing and Verification

AURA should be tested at both the backend and frontend levels.

### Django configuration check

```powershell
python manage.py check
```

### Inspect migrations

```powershell
python manage.py showmigrations
```

### Check for model changes requiring migrations

```powershell
python manage.py makemigrations --check --dry-run
```

### Run backend tests

Use the test command appropriate to the current project configuration. For the API test suite:

```powershell
python manage.py test aura_api.tests --verbosity 2
```

### Build the frontend

From the `frontend` directory:

```powershell
npm run build
```

### Check Git changes

From the repository root:

```powershell
git status --short

git diff --check
```

### Recommended end-to-end verification

Before demonstrating the application, verify the following manually:

- The frontend loads.
- The health endpoint responds successfully.
- Login and logout work.
- Projects can be created and retrieved.
- Video metadata registration works.
- Annotations can be created, edited, and retrieved.
- Validation returns understandable results.
- Review decisions persist.
- Exports can be generated and inspected.
- Knowledge-source ingestion and retrieval behave as documented.
- The browser displays useful errors when operations fail.

A passing build or test suite is not a substitute for testing the complete browser workflow.

---

## Current Implementation Status

AURA is under active development. The status below distinguishes implemented functionality from optional integrations and deferred work.

| Capability | Current status |
|---|---|
| React/TypeScript frontend | Implemented |
| Django API and ORM | Implemented |
| SQLite persistence | Implemented |
| PostgreSQL configuration | Available; deployment configuration requires verification |
| Project and video management | Implemented |
| Annotation creation and editing | Implemented |
| CSV/JSON annotation processing | Implemented |
| Deterministic annotation validation | Implemented |
| Temporal overlap checks | Implemented |
| Human review workflows | Implemented |
| Audit events | Implemented |
| Versioned annotation revisions | Implemented |
| Versioned action ontology | Implemented |
| CSV/JSON exports and manifests | Implemented |
| Session-based authentication | Implemented for the local application |
| Policy retrieval and deterministic assistance | Implemented within supported behavior |
| PDF and project-evidence retrieval | Implemented in deterministic lexical mode |
| Persistent knowledge conversations | Implemented |
| Bronze/Silver/Gold local data pipeline | Implemented for supported project data |
| Task-level grid environment | Implemented |
| Tabular Q-learning foundation | Implemented |
| ChromaDB/local embedding retrieval | Optional adapter; real runtime verification required |
| OpenCV-based processing | Optional; dependency-dependent |
| Real object detector inference | Deferred |
| YOLO inference integration | Deferred |
| Provider-backed LLM response generation | Deferred or unverified |
| Autonomous multi-step AI agents | Not yet established as an operational capability |
| Deep Q-Network training | Deferred |
| Behavior cloning | Deferred |
| Physical robot control | Out of scope |
| Production deployment hardening | Deferred |
| Complete public API documentation | Deferred |

This status describes the implementation record and should be updated whenever new capabilities are completed and verified.

---

## Limitations and Roadmap

The roadmap focuses on extending the existing application without replacing its working components.

### Phase 1 — Core workflow reliability

- Complete browser-based verification of all existing workflows.
- Improve error handling and form validation.
- Verify frontend and backend authentication behavior.
- Improve the usability of annotation editing and review.
- Expand regression tests for important workflows.

### Phase 2 — Knowledge retrieval

- Verify optional local embedding dependencies.
- Validate ChromaDB persistence and index lifecycle.
- Compare lexical and dense retrieval on a repeatable evaluation dataset.
- Measure retrieval precision and recall where suitable ground truth is available.
- Improve citation accuracy and abstention behavior.
- Document retrieval mode and model configuration clearly.

### Phase 3 — Computer vision

- Integrate an optional object detector such as YOLO.
- Provide model and dependency status in the interface.
- Support configurable inference on uploaded video frames.
- Generate reviewable annotation suggestions.
- Track confidence scores and model provenance.
- Keep human approval separate from automated suggestions.

### Phase 4 — AI-assisted annotation

- Add configurable inference and suggestion workflows.
- Introduce confidence-based review queues.
- Compare model suggestions with accepted annotations.
- Record corrections for evaluation.
- Measure quality improvements rather than relying on visual demonstrations alone.

### Phase 5 — Advanced learning workflows

- Expand the task-level simulation environment.
- Add documented evaluation baselines.
- Explore Deep Q-Network training.
- Explore behavior cloning from curated demonstrations.
- Track experiments, configuration, and evaluation results.
- Keep simulated results separate from claims about physical robotics performance.

### Phase 6 — Production-oriented engineering

- Review access control and object-level permissions.
- Improve observability and operational logging.
- Add deployment configuration and automated CI checks.
- Document database backup and recovery.
- Define file-retention and data-governance policies.
- Evaluate scalability before introducing distributed infrastructure.

Each phase should be considered complete only when its implementation, tests, and limitations have been documented.

---

## Engineering Principles

### 1. Preserve source data

Processing and migration workflows should not silently destroy original records.

### 2. Make operations traceable

Important review and export decisions should be associated with source records and relevant audit information.

### 3. Separate suggestions from approvals

An automated annotation or model prediction should not automatically become an approved training label.

### 4. Prefer deterministic validation

Structural and temporal rules should be enforced with explicit, testable logic wherever possible.

### 5. Ground knowledge answers in evidence

Knowledge retrieval should expose supporting evidence and avoid unsupported answers.

### 6. Report actual capability status

Optional integrations should not be presented as operational until they have been configured and tested.

### 7. Build incrementally

Extend the existing models, API contracts, frontend components, and migrations rather than repeatedly scaffolding a new application.

---

## Learning Outcomes

The project provides practical opportunities to study and demonstrate:

- Full-stack application development.
- REST API design and integration.
- Relational data modeling.
- Authentication and authorization.
- Data ingestion and validation.
- Annotation schemas and ontology management.
- Human-in-the-loop quality control.
- Dataset versioning and traceability.
- Local knowledge retrieval and RAG architecture.
- Computer vision integration patterns.
- Data engineering pipeline design.
- Reinforcement-learning fundamentals.
- Automated testing and incremental software delivery.

The emphasis is on understanding how these components fit together in a maintainable application, not simply collecting technology names in a stack.

---

## Contributing

Contributions should follow the existing architecture and preserve established data contracts.

Suggested workflow:

1. Inspect the current implementation and documentation.
2. Create a focused feature branch.
3. Define the expected behavior and acceptance criteria.
4. Implement the smallest coherent change.
5. Add or update tests.
6. Run backend checks and the frontend build.
7. Update the implementation-status documentation.
8. Review the diff before committing.

Avoid committing local databases, credentials, uploaded private documents, or generated artifacts that do not belong in source control.

---

## License

Refer to the repository's existing `LICENSE` file for the applicable licensing terms.

---

## Project Summary

**AURA — Robotics Data Workspace** is an evolving full-stack project focused on structured robotics data operations, temporal annotation, dataset quality, human review, traceable exports, and evidence-grounded knowledge retrieval.

Its core workflows provide a foundation for exploring how data engineering, AI-assisted annotation, and robotics learning systems can be brought together in one application.

The project's next stage is to verify and extend its advanced retrieval and AI capabilities while maintaining reliable data workflows, explicit human oversight, and accurate implementation documentation.