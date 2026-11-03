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

The demo input is **simulated by default**: the New Job screen plays the images in
`samples/` as a camera feed and marks defects live. A **live camera** can be used
instead (see
[Simulated demo and live defect marking](#simulated-demo-and-live-defect-marking)).

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

### Known installation problems

The pinned versions in `backend
equirements.txt` do not install cleanly on every
machine. These were hit when setting the project up on Python 3.14:

| Symptom | Cause | Fix |
|---|---|---|
| `psycopg2-binary` fails to build | No wheel for the Python version | Skip it; mock mode uses SQLite. Install it only for PostgreSQL. |
| `ResolutionImpossible` on `numpy==2.1.3` | `langchain==0.3.7` requires `numpy<2` | Install the packages without version pins, or use Python 3.11 as documented. |
| Login returns HTTP 500, log says `password cannot be longer than 72 bytes` | `passlib` 1.7.4 is incompatible with `bcrypt` 5 | `py -m pip install "bcrypt<5"` |

Extra packages used by the demo scripts (not in `requirements.txt`):
`py -m pip install trimesh shapely mapbox-earcut manifold3d matplotlib imageio-ffmpeg`.

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

## Simulated demo and live defect marking

The demo input comes from the `samples/` folder by default. A real camera can be
used as an alternative (see "Live camera" below).

1. Open <http://localhost:5173>, go to **New Job** and press **Start simulated
   camera**. The browser plays every image in `samples/` as a looping camera
   feed, **6 seconds per frame** (`DEMO_SECONDS_PER_FRAME` in
   `frontend/src/pages/NewJob.tsx`).
2. Tick **Mark defects live**. About once a second a frame is sent to
   `POST /api/v1/parts/live-detect`, and the defects that come back are drawn on
   the feed: a **wireframe outline** around each defect and a **colour fill only
   inside the defect area**, with a label and, where measured, a note such as
   `hole dia 12.75 (nom 12.00 ±0.05)`.
3. **Use live camera** (next to the simulated button) connects a real camera
   instead; see below. Both sources use the same marking, capture and
   verification.
4. **Capture frame** takes a still; the same highlighting is applied to the
   "Latest capture" image.

Colours: crack red, dent orange, scratch yellow, deformation cyan, size
mismatch magenta.

### Live camera

Press **Use live camera** on New Job. The browser asks for camera permission
(allow it); the camera feed then replaces the simulation, an Iriun Webcam is
selected automatically if present, and a device list appears when the machine has
several cameras. Requirements: `localhost` or HTTPS, permission granted, and no
other application holding the camera. Marking works the same way: frames go to
`POST /api/v1/parts/live-detect`. The bracket inspector only recognises the
MS-4505-001 bracket at its calibration (4.6 px/mm at 640 px wide); anything else
is analysed by the YOLO model, which was trained on steel textures and will not
be reliable on arbitrary scenes. The stage is 16:9 for a live camera and square
for the simulation.

### Frontend styling note

`frontend/postcss.config.cjs` is **missing on this branch**, so Tailwind's `@tailwind`
directives are never processed and Tailwind utility classes (`absolute`, `inset-0`,
`aspect-video`, ...) have no effect. The redesign branch added the file
(commit "Add missing postcss.config.cjs"). Until that is merged, write new UI
styles as plain CSS in `frontend/src/index.css`: the camera stage, capture stage
and `.defect-overlay` are done this way. Do not rely on utility classes for
positioning. Adding the PostCSS config would change how the whole existing UI is
styled, so test every page if you do.

### Behaviour of the live overlay

- The overlay is cleared every time the simulated camera moves to the next image,
  and a detection that arrives for a frame that is no longer on screen is
  dropped, so highlights never sit on the wrong image.
- Labels and notes are kept inside the image (shifted left near the right edge).
- The stage is square because the simulated frames are square.

### Sample set

| File | Content | Detector |
|---|---|---|
| `clean_bracket_good_top/front.jpg` | Good bracket MS-4505-001 | bracket inspector (no defects) |
| `defect_bracket_surface_top.jpg` | Dent, scratch, bend 93° | bracket inspector |
| `defect_bracket_crack_top/front.jpg` | Cracks at hole edges | bracket inspector |
| `defect_bracket_size_top/front.jpg` | Short length, oversize and shifted holes | bracket inspector |
| `clean_synthetic_*.jpg`, `defect_*.jpg` (NEU-DET) | Steel texture samples | YOLO (`models/best.pt`) |

The frames carry **no markings or annotation files**. Defects are found from the
pixels at demo time.

### How live detection chooses a detector

`backend/app/api/parts.py` (`live_detect`) first runs
`backend/app/cv/bracket_inspector.py`. It returns `None` unless the frame shows
the MS-4505-001 bracket (a bright rectangle of about 120 x 80 mm or 120 x 50 mm),
in which case the frame goes to the trained YOLO model. This split exists because
YOLO was trained on NEU-DET steel textures and raises false alarms on bracket
frames.

### What the bracket inspector measures

| Check | Method | Flagged when |
|---|---|---|
| Length, width/height | Sub-pixel edge (steepest gradient) | outside 120 / 80 / 50 mm by more than 0.10 mm (+0.04 guard) |
| Hole diameter | Ray-based sub-pixel circle fit | outside 12.00 mm by more than 0.05 mm (+0.04 guard) |
| Hole position | Circle centre vs nominal, from the part edges | more than 0.10 mm (+0.04 guard) off |
| Flange bend (top view) | Visible flange strip height | outside 90 deg by more than 0.5 deg (+0.2 guard) |
| Crack | Dark thin ridge (black top-hat), elongated | always |
| Scratch | Bright thin line (top-hat), at least 12 mm long | always |
| Dent | Smooth shading anomaly (band-pass), 7-32 mm | always |

Calibration is fixed: **4.6 px/mm for a 640 px wide frame**, scaled with frame
width (the browser sends 480 px JPEG frames, so about 3.45 px/mm). Measured and
tested at both sizes with deviations injected into otherwise perfect frames:
length +0.15 mm, hole diameter +0.10 mm, hole position +0.15 mm and bend +1 deg
are caught; 0.05 mm length and 0.03 mm diameter changes (inside tolerance) are
ignored. This is a simulation result on synthetic frames, not a measured
accuracy on real photographs.

### Measured accuracy

**YOLO (`models/best.pt`)**, held-out NEU-DET test split of 270 images
(`results.json`): precision 65.6%, recall 73.0%, mAP50 73.4%, mAP50-95 41.2%.
Per class mAP50: scratches 93.1%, patches 92.0%, inclusion 82.8%, pitted surface
79.3%, rolled-in scale 58.2%, crazing 35.0%. Valid for hot-rolled steel strip only.

**Bracket inspector**, randomised synthetic benchmark
(`py scripts\eval_bracket_inspector.py 40 2026`, result in
`docs\demo\bracket_inspector_eval.json`): 320 frames, random defect type, size,
position, lighting gain, sensor noise and JPEG quality at 480 px.

| Class | Precision | Recall | F1 | Localisation |
|---|---|---|---|---|
| crack | 94.3% | 82.5% | 88.0% | 97% |
| scratch | 56.9% | 82.5% | 67.3% | 94% |
| dent | 69.0% | 100% | 81.6% | 100% |
| deformation (bend) | 100% | 72.5% | 84.1% | n/a |
| length | 72.2% | 97.5% | 83.0% | n/a |
| hole diameter | 100% | 95.0% | 97.4% | 100% |
| hole position | 72.7% | 100% | 84.2% | 100% |
| **All classes** | **77.1%** | **90.0%** | | |

In-tolerance good frames reported clean: 32 of 40 (20% false-alarm rate).
Measurement error (mean / 95th percentile): length 0.055 / 0.079 mm, hole
diameter 0.039 / 0.056 mm, hole position 0.052 / 0.095 mm, bend 0.53 / 0.64 deg.
Speed: 55 ms per frame (95th percentile 62 ms).

This is a synthetic benchmark, not a measurement on real parts. The thresholds
were tuned on the demo frames before this benchmark was written, and the demo
frames themselves are all handled correctly; the weaker numbers come from the
random lighting and noise. Known weak spots: scratch and dent false alarms, bend
recall, and false length / hole-position alarms on the synthetic under-bent
flanges (the frame renderer draws bends below 90 deg poorly, so this is probably
partly a renderer artifact).

### Regenerating the demo assets

Run from the project root with the API running where noted.

```powershell
py scripts\make_bracket_frames.py            # samples\*bracket*.jpg camera frames
py scripts\make_bracket_models.py            # docs\models\bracket\ STL, GLB, DXF, 3D/2D renders
py scripts\make_bracket_drawing.py           # docs\drawings\ engineering drawing (PNG, PDF, SVG)
py scripts\make_demo_video.py                # docs\demo\novaliseo_demo.mp4 (API must be running): drawing, 3D/2D models, inspection, summary
```

The geometry of the four bracket variants (good, defect, crack, size mismatch)
lives in `scripts\bracket_variants.py`; the frames, 3D models and DXF files all
read it, so change a dimension there and regenerate.

## Bracket MS-4505-001

Sheet-metal L-bracket, SPCC steel, 2.0 mm thick: base 120 x 80 mm, flange 50 mm
high, inside bend radius 3 mm, four Ø12.00 +/-0.05 base holes at (15/105, 15/65)
with axis along Z, two Ø12.00 flange holes at X = 30/90, Z = 30 with axis along
Y. General tolerance +/-0.10 mm, bend 90 +/-0.5 deg. Drawings and models are in
`docs\drawings\` and `docs\models\bracket\`.

## AI root cause analysis (Gemini)

Root cause analysis (stages 4 to 6) can use Google Gemini instead of the built-in
offline template.

**Enable it**

1. Create an API key in Google AI Studio (<https://aistudio.google.com/apikey>).
2. Put it in `.env` at the project root (this file is git-ignored; never commit a key):

   ```
   GEMINI_API_KEY=your-key-here
   GEMINI_MODEL=gemini-3.1-flash-lite
   ```

3. Check it: `py scripts\check_gemini.py` (lists the models your key can call and
   makes one test call; it never prints the key). If `GEMINI_MODEL` is not in the
   list, set it to one that is.
4. Restart the API.

`prediction.llm.provider` in `config/default.yaml` is `auto`: Gemini when
`GEMINI_API_KEY` is set, otherwise the offline fake. Force a choice with
`NOVALISEO_LLM_PROVIDER=gemini|anthropic|openai|fake`. The choice no longer
depends on `NOVALISEO_MODE`. Tests always use the fake provider.

**Model and quota (found by testing a real key).**
- The Gemini 2.5 family returns HTTP 404 "no longer available to new users" for new keys, even though
  it appears in the model list. `scripts\check_gemini.py` makes a real call and suggests a model that works.
- `gemini-3.1-flash-lite` is the default because it is kind to the free tier. `gemini-3.5-flash` gives
  better quality but the free tier allows only a small number of requests per day **per model**; the
  limit was used up during testing and resets after about 14 hours.
- A daily-quota 429 is not retried; the result falls back to the offline template and says
  "daily free-tier quota used up for this model". Change `GEMINI_MODEL` or enable billing.

**What it does.** The retrieved knowledge-base evidence is sent to Gemini with a
prompt that allows only that evidence. It returns three ranked causes, each with
the **reason** (rationale), effect, **solution** (corrective actions), prevention
(preventive actions), precautions, a verification step and chunk citations.
Citations that are not in the evidence are dropped. Confidence is still computed
by the scoring code, not by the model.

**If the AI call fails** (no key, network, quota, bad model name, unparseable
answer) the result falls back to the offline template and is clearly labelled:
`model_version` starts with `fallback-fake (gemini failed: ...)` and the RCA
document opens with a warning. The key is sent in a header and never logged.

**The RCA document.** Word, PDF and Markdown with: 1 Problem (defects and
out-of-tolerance measurements), 2 Root cause (cause, **reason**, effect,
confidence, supporting evidence), 3 Solution (corrective actions, preventive
actions, precautions, how to verify), 4 Other causes considered, 5 Traceability
(model, expert edits, disclaimer).

- **From a job:** generated automatically when the report is rendered (stage 7)
  with the expert's final decision; download with
  `GET /api/v1/reports/{job_id}/rca?fmt=docx|pdf|md`. Gate 2 now shows the reason
  and solution on each cause card.
- **From any list of defects:** `POST /api/v1/rca/analyze` with
  `{"defects":[{"defect_type":"crack","confidence":0.9,"note":"..."}]}` returns the
  analysis and download links (`GET /api/v1/rca/{id}/download?fmt=...`).
  `GET /api/v1/rca/status` shows which provider is active.
- **From the demo:** on New Job, capture a frame (or mark defects live) and press
  **Analyse root cause (AI)**. The panel shows the cause, reason, solution and
  prevention, with the document download buttons, and says clearly when the AI
  model was not used.

**Workflow fixes made while testing end to end** (the full inspection had never completed on the
newer package versions installed here):
- Node outputs are converted to plain Python so the LangGraph checkpointer can store them
  (numpy floats from the measurement stage crashed it).
- The L4 (retry evidence) and L5 (regenerate) counters are now stored by nodes
  (`workflow/nodes/loops.py`). Counters changed inside routing functions were lost, so the loops never ended.
  The other loops (L1, L2, L3, L7) still use the old pattern.
- Retrieval reads the knowledge base itself and its filters are tolerant (any word of the material,
  case-insensitive process, generic chunks always allowed). Before, it always fell back to the 4 built-in
  snippets. Re-ranker scores are turned into 0..1 relevance so confidence is no longer a flat 95%.
- `scripts\run_demo.py` asks the graph which gate is waiting, so it now runs through all gates to CLOSED.
- Gemini's JSON output is forced with a response schema, with a larger output limit and one retry;
  placeholder candidates such as "Insufficient evidence" are dropped.

**Database connection.** Workflow nodes are now given a database session (`workflow/graph.py` injects one
into every node that takes `db`), so the workflow persists everything it produces: `inspection_job`
(CLOSED at the end), `image_asset`, `dimension_result`, `defect`, `gate_decision`,
`root_cause_prediction` (with the reason and solution), `final_rca`, `feedback`, `corrective_action`,
`report` and `audit_log`. A database error inside a node is logged and the node is re-run without
persistence, so a storage problem never aborts an inspection. `create_job` no longer inserts a second
row when the jobs API has already created it. `tests/integration/test_workflow_persistence.py` runs the
whole workflow and checks the stored rows. Loops L1, L2, L3 and L7 still keep their counters inside
routing functions and need the same fix as L4 / L5.

**Where the RCA document is**

| What | Where |
|---|---|
| From an inspection job | `tmp\reports\<job_id>_rca.docx`, `.pdf`, `.md` |
| From `POST /api/v1/rca/analyze` | `tmp\reports\rca_<rca_id>.docx`, `.pdf`, `.md` |
| Recorded in the database | `report.rca_docx_uri`, `rca_pdf_uri`, `rca_md_uri` (returned by `GET /api/v1/reports/{job_id}`) |
| Download (job) | `GET /api/v1/reports/{job_id}/rca?fmt=docx|pdf|md` |
| Download (standalone) | `GET /api/v1/rca/{rca_id}/download?fmt=docx|pdf|md` |
| In the UI | **Reports** page of a job (`/jobs/<id>/reports`), section "Root Cause Analysis Document"; New Job, "Analyse root cause (AI)" panel |
| Samples | `C:\Users\param\Downloads\Novaliseo_RCA_samples\` |

Existing databases are upgraded automatically on start-up (new nullable columns
for the reason and solution). Gemini output is a draft for a quality expert, not a
decision.

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
- `backend/app/cv/bracket_inspector.py` — image-based bracket inspection used by
  live defect marking.
- `backend/app/api/demo.py` — serves the simulated camera inputs from `samples/`.
- `backend/app/rag/` — knowledge ingestion and retrieval.
- `backend/app/llm/` — LLM provider abstraction.
- `backend/app/reports/` — report creation and signatures.
- `frontend/src/pages/` — React application pages.
- `scripts/` — demo, seeding, sample, and model utilities, plus the bracket
  frame, model, drawing and video generators.
- `docs/drawings/`, `docs/models/bracket/`, `docs/demo/` — engineering drawing,
  3D/2D models and renders, and the demo video and stills.
- `docs/RUNBOOK.md` and `docs/ARCHITECTURE.md` — deeper operating and design
  documentation.
