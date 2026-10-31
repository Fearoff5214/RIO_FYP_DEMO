# Novaliseo Project Guide

This guide describes the main technology stack and how to set up, run, test, and
demo the project on Windows using PowerShell.

## Project overview

Novaliseo is an AI-assisted manufacturing quality-inspection application. It
contains a FastAPI backend and a React frontend, plus a preserved Streamlit
demo from the earlier project phase.

The main workflow covers image capture, dimensional inspection, defect
detection, knowledge retrieval, root-cause analysis, human review, report
generation, and learning feedback. Mock mode is the recommended way to explore
the application locally; it does not require GPU hardware or external AI API
keys.

## Technology stack

### Backend and workflow

- **Python 3.11 or newer** — runtime (`pyproject.toml`).
- **FastAPI** — HTTP API, request validation, and OpenAPI documentation.
- **Uvicorn** — local ASGI development server.
- **Pydantic 2 and pydantic-settings** — data validation and environment-based
  configuration.
- **SQLAlchemy 2 async** — database models and asynchronous data access.
- **SQLite with aiosqlite** — default local development database.
- **PostgreSQL with asyncpg/psycopg2** — supported database dependencies for
  non-local deployments.
- **Alembic** — database migration tooling.
- **LangGraph and LangChain** — inspection workflow orchestration, human gates,
  retrieval, and LLM integrations.
- **OpenCV, NumPy, Pillow, and Ultralytics** — image processing and computer
  vision / YOLO-based detection.
- **Sentence Transformers and rank-bm25** — text embeddings and keyword
  retrieval for the knowledge base.
- **ReportLab, openpyxl, and python-docx** — PDF, Excel, and Word reports.
- **python-jose and passlib** — JWT and password hashing support.
- **pytest and pytest-asyncio** — automated backend testing.
- **Ruff and mypy** — backend linting and type checking.

The pinned backend dependencies are listed in
[`backend/requirements.txt`](./backend/requirements.txt).

### Frontend

- **React 18** — component-based user interface.
- **TypeScript** — static type checking.
- **Vite** — development server and production bundler.
- **Tailwind CSS** — utility styling, alongside project-specific CSS.
- **React Router** — page navigation.
- **TanStack Query** — API request and server-state management.
- **Axios** — HTTP client.
- **Recharts** — dashboard charts.
- **Lucide React** — interface icons.
- **ESLint** — frontend lint script.

The frontend scripts and dependencies are listed in
[`frontend/package.json`](./frontend/package.json).

### Preserved original demo

The earlier defect-detection application is kept in `src/` and uses
**Streamlit**, **Ultralytics**, and OpenCV. Its dependencies are separate from
the main backend and are listed in the root [`requirements.txt`](./requirements.txt).

## Requirements

- Windows 10 or later with PowerShell.
- Python 3.11+ available through the Windows `py` launcher.
- Node.js and npm.
- Internet access for the initial dependency installation.

The main app runs locally in mock mode. You do not need PostgreSQL, Redis,
MinIO, a camera, a GPU, or an LLM API key for the standard local demo.

## First-time setup

Open PowerShell in the project root:

```powershell
cd "C:\Users\rcdt0\OneDrive\Documents\RIO FYP\RIO_FYP"
```

Create and activate a Python virtual environment, then install the backend
dependencies:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r backend\requirements.txt
```

If PowerShell prevents environment activation, allow it for the current
terminal only, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Install the frontend dependencies:

```powershell
Set-Location frontend
npm install
Set-Location ..
```

These installation steps are normally needed once. Repeat them if you recreate
the virtual environment or change the dependency manifests.

## Run the application

Run the backend and frontend in two separate PowerShell terminals. In both
terminals, start from the project root.

### Terminal 1: backend API

```powershell
cd "C:\Users\rcdt0\OneDrive\Documents\RIO FYP\RIO_FYP"
.\.venv\Scripts\Activate.ps1
$env:NOVALISEO_MODE = "mock"
py -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

The API creates the local database tables and seeds demo users on startup.
Useful endpoints:

- API documentation: <http://localhost:8000/docs>
- API health: <http://localhost:8000/healthz>
- API readiness: <http://localhost:8000/readyz>

### Terminal 2: frontend

```powershell
cd "C:\Users\rcdt0\OneDrive\Documents\RIO FYP\RIO_FYP\frontend"
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` requests to the backend at
`http://localhost:8000`.

To stop either development server, press **Ctrl+C** in its terminal.

## Demo and sample knowledge base

With the backend dependencies installed and the project root as the current
directory, load the bundled knowledge-base samples:

```powershell
.\.venv\Scripts\Activate.ps1
$env:NOVALISEO_MODE = "mock"
py scripts\load_kb.py
```

Run the golden workflow demo:

```powershell
.\.venv\Scripts\Activate.ps1
$env:NOVALISEO_MODE = "mock"
py scripts\run_demo.py
```

The original Streamlit demo is separate. To install its additional
dependencies, install PyTorch appropriate for your machine first if required,
then install the root requirements:

```powershell
py -m pip install -r requirements.txt
streamlit run src\app.py
```

The project README documents optional CUDA-specific PyTorch installation and
model training.

## Tests and checks

Run the backend tests from the project root:

```powershell
.\.venv\Scripts\Activate.ps1
$env:NOVALISEO_MODE = "mock"
$env:DATABASE_URL = "sqlite+aiosqlite:///./novaliseo_test.db"
py -m pytest backend\tests\ -v
$env:NOVALISEO_MODE = "mock"
py -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Build the frontend:

```powershell
Set-Location frontend
npm run build
```

The frontend lint command is:

```powershell
npm run lint
```

If ESLint reports that it cannot find `eslint.config.js`, the repository's
current ESLint 9 installation needs a compatible flat configuration before
that lint script can run.

## Configuration and local data

- `config/default.yaml` — workflow thresholds, model settings, camera adapter,
  and other application defaults.
- `.env` — optional local environment overrides and API secrets. Do not commit
  credentials.
- `novaliseo_dev.db` — default SQLite database at the project root.
- `data/part_references/` — registered CAD and part-reference images.
- `tmp/part_verification/` — locally saved part-verification captures.
- `tmp/overlays/` and `tmp/reports/` — generated overlays and reports.
- `models/` and `samples/` — included model weights and demo media.

By default, the database URL points to the project-root SQLite database.
`NOVALISEO_MODE` defaults to `mock`; setting it in PowerShell applies only to
that terminal session.

## Demo users

The application seeds these development accounts:

| Username | Password | Role |
|---|---|---|
| `operator` | `operator` | Operator |
| `engineer` | `engineer` | Quality engineer and dimensional review |
| `expert` | `expert` | Quality expert |
| `approver` | `approver` | Report approver |
| `admin` | `admin` | Administrator |

These are development credentials only. Change them before any deployment
outside a local demo.

## Useful project locations

- `backend/app/main.py` — FastAPI application entry point.
- `backend/app/api/` — API route modules.
- `backend/app/workflow/` — inspection workflow and stages.
- `backend/app/cv/` — computer-vision components.
- `backend/app/rag/` — knowledge ingestion and retrieval.
- `backend/app/llm/` — LLM provider abstraction.
- `backend/app/reports/` — report creation and signatures.
- `frontend/src/pages/` — React application pages.
- `scripts/` — demo, seeding, sample, and model utilities.
- `docs/RUNBOOK.md` and `docs/ARCHITECTURE.md` — deeper operating and design
  documentation.
