# NOVALISEO — AI-Driven Quality Inspection & Root Cause Intelligence Platform
## Master Implementation Guide for IDE Coding Agents

> **Audience:** an autonomous coding agent (Cursor, Claude Code, Copilot Agent, Windsurf, etc.).
> **Source of truth:** this file, plus the two spec artifacts: `Novaliseo_AI_Quality_Inspection_Flow_Editable_BW.pdf` (flow chart, loops L1–L12) and the 8-step infographic PNG. If this file and the PDF disagree, the PDF wins; flag the conflict in `docs/DECISIONS.md`.
> **Product:** sheet-metal AI quality inspection with dimensional checking, defect detection, RAG-based root-cause prediction, three human-in-the-loop gates, report generation, and continuous learning.

---

## 0. HOW THE AGENT MUST WORK (READ FIRST)

1. **Audit before building.** If a repository already exists, first inspect it completely: architecture, dependencies, entry points, tests, execution flow. Write findings to `docs/AUDIT.md` with a table mapping every spec item (Section 8 stages, Section 9 loops, Section 17 milestones) to `DONE / PARTIAL / MISSING`. If the repo is empty, write `docs/AUDIT.md` stating "greenfield" and proceed.
2. **Preserve working features.** Never delete or rewrite working code unless it blocks the spec. Prefer extending. Record any breaking change in `docs/DECISIONS.md`.
3. **Work in small vertical steps.** One milestone (Section 17) at a time. For each step: implement → write/adjust tests → run tests → fix → update docs → commit with a conventional message (`feat(stage2): ...`).
4. **Never stop at a plan.** Produce working code. If something is blocked (missing GPU, missing model weights, missing customer data, missing credentials), implement a **clean interface plus a deterministic mock/fake adapter**, mark it in `docs/BLOCKERS.md`, and continue.
5. **Everything configurable, nothing hard-coded.** Thresholds, retry limits, model names, paths come from `config/default.yaml` (Section 14) and environment variables.
6. **Every state change is auditable.** Each node writes an audit row (Section 6). Every human decision stores reviewer ID, timestamp, and reason code.
7. **Keep the app runnable at all times.** `make dev` and `make test` must pass at the end of every milestone.
8. **Update docs continuously:** `README.md`, `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/RUNBOOK.md`, `docs/DECISIONS.md`, `docs/BLOCKERS.md`.
9. **Definition of Done** is in Section 19. Do not declare completion until every item is verified.

---

## 1. PROJECT OVERVIEW

Novaliseo ("Brain Behind Intelligent Operations") delivers an end-to-end agentic workflow that:

1. Captures images of a sheet-metal part with an industrial camera (computer vision inspection).
2. Compares measured dimensions against a 2D drawing (DXF/PDF) and reports PASS/FAIL per feature. **Human Gate 1** (quality engineer) confirms.
3. Detects surface/shape defects (**Dent, Scratch, Crack, Deformation**) with YOLO + SAM + Anomalib. A **label-review gate** appears only if any confidence < 85%.
4. Retrieves customer-provided root-cause knowledge (RCA documents, historical issues, corrective/preventive actions, process and material data) via hybrid RAG.
5. Predicts the **Top 3 root causes** with effect/impact, recommended precautions and calibrated confidence (example: 92%, 78%, 71%).
6. **Human Gate 2** (quality expert) reviews, selects or edits the final root cause and actions.
7. Generates the inspection and RCA report (PDF, Excel, Word, Print) and routes it for **Human Gate 3** (approver e-signature).
8. Publishes final quality output to dashboards/MES/QMS/ERP, tracks corrective actions, and feeds a **learning hub** (retrain CV models, update knowledge base, recalibrate confidence).

**Tagline:** *Intelligent Inspection. Accurate Insights. Superior Quality.*
**Core pillars:** Computer Vision · AI Analysis & Prediction · Human Expertise Validation · Intelligent Decision Making · Continuous Quality Improvement.

**Fast path:** if Stage 3 finds **no defect**, skip Stages 4–6 and go straight to the OK report in Stage 7.

---

## 2. SCOPE, ASSUMPTIONS, NON-GOALS

**In scope:** everything in the PDF and infographic: the 8-stage runtime workflow, the offline knowledge-base ingestion plane, all human gates, loops L1–L12, report generation, audit trail, RBAC, monitoring, notifications, and a reviewer web UI.

**Assumptions (override via config if wrong):**
- Single-site deployment first; multi-site later.
- Camera access via an abstraction (`CameraAdapter`); real hardware optional. A folder-watch / file-upload adapter must work for development.
- MES/QMS/ERP integrations are webhook/REST adapters with mocks.
- Defect models are pretrained/fine-tuned weights supplied by the customer or trained from labeled data; the repo ships a training pipeline plus a tiny demo dataset and mock detector.
- LLM provider is pluggable (Anthropic, OpenAI, or local via Ollama). Default: Anthropic.

**Non-goals (v1):** real-time line-speed (<1 s) inspection, 3D point-cloud inspection, mobile native apps.

---

## 3. TECH STACK (DEFAULTS)

| Layer | Choice |
|---|---|
| Language | Python 3.11+ (backend/agents), TypeScript (frontend) |
| Orchestration | **LangGraph** (state graph, checkpoints, interrupts for human gates) |
| API | FastAPI + Pydantic v2, Uvicorn, WebSocket/SSE for live status |
| Database | **PostgreSQL 16 + pgvector** (state, audit, KB vectors); SQLAlchemy 2 + Alembic |
| Checkpointer | `langgraph-checkpoint-postgres` |
| Object storage | S3-compatible (MinIO in dev) for raw/processed images, masks, reports |
| Queue / workers | Celery or Arq + Redis (GPU jobs, ingestion, retraining) |
| CV | OpenCV, NumPy, **ezdxf** (DXF), PyMuPDF/pdfplumber (PDF drawings), Ultralytics **YOLO**, **SAM** (segment-anything), **Anomalib** |
| RAG | pgvector (dense) + Postgres FTS/BM25 (keyword) + optional graph (Postgres tables or Neo4j), cross-encoder reranker (`sentence-transformers`) |
| Doc parsing / OCR | `unstructured` or `docling`, Tesseract / PaddleOCR for scans |
| LLM | Provider abstraction; structured JSON output validated by Pydantic |
| Reports | ReportLab/WeasyPrint (PDF), openpyxl (Excel), python-docx (Word), Jinja2 templates |
| Frontend | React + Vite + TypeScript + Tailwind; image overlay via canvas/SVG |
| Auth | OIDC/JWT, role-based access (Operator, Quality Engineer, Quality Expert, Approver, Admin) |
| Observability | OpenTelemetry, Prometheus, Grafana, structured JSON logs; drift monitoring |
| MLOps | MLflow (model registry/versioning), DVC or object storage for datasets |
| Packaging | Docker, docker-compose (dev), Helm optional (prod) |
| Quality | pytest, pytest-asyncio, ruff, mypy, pre-commit, Playwright (UI e2e) |

---

## 4. ARCHITECTURE

### 4.1 Logical components

- **Orchestrator (grey, "System")** — LangGraph graph holding workflow state, checkpoints, retry counters, routing. Not an LLM; deterministic code.
- **Inspection Agent** — Stage 1 (capture) and Stage 3 (defect detection). Tools: camera, OpenCV, YOLO, SAM, Anomalib.
- **Dimensional Agent** — Stage 2. Tools: ezdxf, OpenCV, calibration.
- **Knowledge Agent** — Stage 4. Hybrid RAG.
- **Root-Cause Agent** — Stage 5. LLM + scoring + calibration.
- **Report Agent** — Stage 7. Templates, e-signature stamp, exports.
- **Human gates** — implemented as LangGraph `interrupt()` points plus UI tasks; graph resumes on API submission.
- **Learning Hub** — Stage 8 background jobs: retrain, re-index, recalibrate.
- **Offline Data Plane** — knowledge-base ingestion pipeline (runs before and independently of inspections).

### 4.2 Shape legend (from PDF; reflect it in `docs/ARCHITECTURE.md` diagrams)
Tool/CV step · AI agent step (double line) · System/orchestrator (grey) · Data store · Start/end/connector · Decision · Human gate (thick line) · Loop-back (L#, dashed) · Main flow.

### 4.3 High-level data flow
```
Trigger → [S1 Capture] → [S2 Dimensions] → H-Gate1 → [S3 Defects] → (low-conf → Label Review)
   ├─ no defect → Fast path → [S7 Report OK-part] → H-Gate3 → [S8 Output/Learning]
   └─ defect → [S4 Knowledge Retrieval] → [S5 Prediction Top-3] → H-Gate2 (Expert)
                → [S7 Report full RCA] → H-Gate3 (Approver) → [S8 Output + Actions + Learning]
Offline: Customer docs → Parse/OCR → Chunk/Tag → Embed/Index → Knowledge Base (K)
```

### 4.4 Cross-cutting (every stage)
LangGraph state + checkpoints · PostgreSQL audit trail · role-based access · monitoring and drift · notifications.

---

## 5. REPOSITORY STRUCTURE (TARGET)

Adapt to the existing repo if one exists. Do not reorganize working code needlessly; add missing modules.

```
novaliseo/
├── README.md
├── Makefile                      # dev, test, lint, migrate, seed, demo
├── docker-compose.yml            # postgres+pgvector, redis, minio, api, worker, frontend, mlflow
├── pyproject.toml
├── .env.example
├── config/
│   ├── default.yaml              # thresholds, retries, models (Section 14)
│   └── report_templates/         # jinja2 + docx/xlsx templates
├── docs/                         # AUDIT, ARCHITECTURE, API, RUNBOOK, DECISIONS, BLOCKERS
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI entry
│   │   ├── api/                  # routers: jobs, gates, kb, reports, actions, admin, auth
│   │   ├── core/                 # config, logging, security, rbac, telemetry
│   │   ├── db/                   # models, session, alembic/
│   │   ├── storage/              # object-store adapter
│   │   ├── notifications/        # email, webhook, MES/QMS/ERP adapters
│   │   ├── workflow/
│   │   │   ├── state.py          # InspectionState (Section 7)
│   │   │   ├── graph.py          # LangGraph builder
│   │   │   ├── routing.py        # conditional edges, loop counters
│   │   │   ├── nodes/
│   │   │   │   ├── s1_capture.py
│   │   │   │   ├── s2_dimensional.py
│   │   │   │   ├── s3_defects.py
│   │   │   │   ├── s4_retrieval.py
│   │   │   │   ├── s5_prediction.py
│   │   │   │   ├── s6_expert_gate.py
│   │   │   │   ├── s7_report.py
│   │   │   │   └── s8_output_learning.py
│   │   │   └── gates.py          # interrupt/resume helpers
│   │   ├── cv/
│   │   │   ├── camera/           # CameraAdapter: folder, file-upload, GenICam/GigE, mock
│   │   │   ├── preprocess.py     # undistort, px→mm, normalize
│   │   │   ├── drawing/          # dxf_parser.py, pdf_parser.py, gdt.py
│   │   │   ├── features.py       # holes, edges, contours
│   │   │   ├── measure.py        # calibrated measurement + tolerance compare
│   │   │   └── detectors/        # yolo.py, sam.py, anomalib.py, fuse.py, classify.py, mock.py
│   │   ├── rag/
│   │   │   ├── ingest/           # parse, ocr, chunk, tag, embed, index
│   │   │   ├── retrieve.py       # query build, filters, hybrid, graph expand
│   │   │   ├── rerank.py
│   │   │   └── kb_models.py
│   │   ├── llm/                  # provider abstraction, prompts/, schemas
│   │   ├── scoring/              # confidence scoring + calibration
│   │   ├── reports/              # compose, render_pdf, render_xlsx, render_docx, esign
│   │   └── learning/             # label sink, retrain, reindex, recalibrate
│   ├── workers/                  # celery/arq tasks
│   └── tests/                    # unit/, integration/, e2e/, fixtures/
├── frontend/
│   └── src/ (pages: Jobs, JobDetail, Gate1Review, LabelReview, Gate2Expert,
│            Gate3Approval, Reports, KnowledgeBase, Actions, Dashboard, Admin)
├── ml/
│   ├── training/                 # yolo/sam/anomalib training + eval scripts
│   ├── datasets/                 # DVC pointers, demo data
│   └── mlflow/
└── scripts/                      # seed_demo.py, generate_sample_drawing.py, load_kb.py
```

---

## 6. DATA MODEL (POSTGRESQL)

Create via Alembic migrations. Use UUID PKs, `created_at/updated_at`, and soft-delete only where noted.

```sql
-- Master data
CREATE TABLE part_master (
  part_number TEXT PRIMARY KEY,            -- e.g. MS-4505-001
  part_name TEXT NOT NULL,                 -- e.g. Sheet Metal Bracket
  drawing_rev TEXT NOT NULL,
  drawing_uri TEXT NOT NULL,               -- DXF/PDF in object storage
  material TEXT, process TEXT,
  tolerances JSONB,                        -- default + per-feature
  camera_recipe JSONB,                     -- lighting, angles, exposure
  calibration JSONB                        -- px_per_mm, distortion coeffs
);

-- Inspection job and workflow state
CREATE TABLE inspection_job (
  job_id UUID PRIMARY KEY, part_number TEXT REFERENCES part_master,
  status TEXT NOT NULL,                    -- see enum below
  current_stage INT, thread_id TEXT,       -- LangGraph thread
  dimensional_status TEXT,                 -- PASS|FAIL
  defect_found BOOLEAN, final_decision TEXT,
  loop_counters JSONB DEFAULT '{}',        -- {"L2":1,"L3":0,...}
  created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
);
-- status enum: CREATED, CAPTURING, DIMENSIONAL, AWAIT_GATE1, DEFECT_DETECTION,
-- AWAIT_LABEL_REVIEW, RETRIEVAL, PREDICTION, AWAIT_GATE2, REPORTING, AWAIT_GATE3,
-- OUTPUT, LEARNING, CLOSED, ON_HOLD, REJECTED_REINSPECT, FAILED

CREATE TABLE image_asset (
  image_id UUID PRIMARY KEY, job_id UUID, kind TEXT,  -- raw|processed|mask|overlay
  uri TEXT, angle TEXT, quality_score REAL, meta JSONB
);

CREATE TABLE dimension_result (
  id UUID PRIMARY KEY, job_id UUID, feature_id TEXT, feature_type TEXT,
  nominal REAL, tol_plus REAL, tol_minus REAL, measured REAL, deviation REAL,
  within_tolerance BOOLEAN, evidence_uri TEXT
);  -- e.g. 120.05 (+0.05), Ø11.70 (-0.30) OUT

CREATE TABLE gate_decision (
  id UUID PRIMARY KEY, job_id UUID, gate TEXT,        -- GATE1|LABEL|GATE2|GATE3
  reviewer_id TEXT, decision TEXT, reason_code TEXT, comments TEXT,
  payload JSONB, decided_at TIMESTAMPTZ
);

CREATE TABLE defect (
  defect_id UUID PRIMARY KEY, job_id UUID, image_id UUID,
  defect_type TEXT,                         -- dent|scratch|crack|deformation|other
  bbox JSONB, mask_uri TEXT, size_mm2 REAL, severity TEXT,
  confidence REAL, source TEXT,             -- yolo|sam|anomalib|human
  human_corrected BOOLEAN DEFAULT FALSE, original_label TEXT
);

CREATE TABLE root_cause_prediction (
  id UUID PRIMARY KEY, job_id UUID, rank INT, cause TEXT, effect TEXT,
  precautions JSONB, confidence_raw REAL, confidence_cal REAL,
  evidence JSONB,                           -- [{doc_id, chunk_id, score, uri}]
  model_version TEXT
);

CREATE TABLE final_rca (
  job_id UUID PRIMARY KEY, selected_rank INT, cause TEXT, effect TEXT,
  corrective_actions JSONB, preventive_actions JSONB,
  edited BOOLEAN, reviewer_id TEXT, finalized_at TIMESTAMPTZ
);

CREATE TABLE report (
  report_id UUID PRIMARY KEY, job_id UUID, version INT, status TEXT,  -- DRAFT|PENDING|APPROVED|REJECTED
  pdf_uri TEXT, xlsx_uri TEXT, docx_uri TEXT,
  approved_by TEXT, approved_at TIMESTAMPTZ, signature_uri TEXT
);

CREATE TABLE corrective_action (
  action_id UUID PRIMARY KEY, job_id UUID, description TEXT, owner TEXT,
  due_date DATE, status TEXT, evidence_uri TEXT, effective BOOLEAN
);

-- Knowledge base (Section 11)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE kb_document (doc_id UUID PRIMARY KEY, source_uri TEXT, doc_type TEXT,
  title TEXT, meta JSONB, ingested_at TIMESTAMPTZ, version INT);
CREATE TABLE kb_chunk (chunk_id UUID PRIMARY KEY, doc_id UUID, text TEXT,
  embedding vector(1024), tsv tsvector,
  part TEXT, material TEXT, process TEXT, defect_type TEXT, cause TEXT, section TEXT);
CREATE INDEX ON kb_chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON kb_chunk USING gin (tsv);
CREATE TABLE kb_edge (src TEXT, rel TEXT, dst TEXT, weight REAL, source_chunk UUID);
  -- relations: defect→cause, cause→action, cause→precaution, cause→material/process

-- Learning
CREATE TABLE feedback (id UUID PRIMARY KEY, job_id UUID, kind TEXT,  -- label|rca_choice|outcome
  ai_value JSONB, human_value JSONB, created_at TIMESTAMPTZ);
CREATE TABLE model_registry (model TEXT, version TEXT, stage TEXT, metrics JSONB, uri TEXT, created_at TIMESTAMPTZ);

-- Audit (append-only; revoke UPDATE/DELETE from app role)
CREATE TABLE audit_log (
  id BIGSERIAL PRIMARY KEY, job_id UUID, actor TEXT, actor_role TEXT,
  node TEXT, event TEXT, state_hash TEXT, payload JSONB, ts TIMESTAMPTZ DEFAULT now()
);
```

---

## 7. WORKFLOW STATE & GRAPH (LANGGRAPH)

### 7.1 State
```python
class InspectionState(TypedDict, total=False):
    job_id: str; part_number: str; part_master: dict
    camera_recipe: dict; images: list[dict]; image_quality_ok: bool
    drawing: dict                       # parsed dims, tolerances, GD&T
    measurements: list[dict]; dimensional_status: Literal["PASS","FAIL"]
    gate1: dict                         # decision, reviewer, reason_code
    detections: list[dict]; defects: list[dict]; defect_found: bool
    min_confidence: float; label_review: dict
    query: dict; retrieved: list[dict]; reranked: list[dict]; evidence_sufficient: bool
    evidence_pack: dict; candidates: list[dict]; top3: list[dict]; output_valid: bool
    gate2: dict; final_rca: dict
    report: dict; report_complete: bool; gate3: dict
    loops: dict[str,int]                # L1..L9 counters
    flags: list[str]                    # "low_evidence", "low_confidence", ...
    status: str
```

### 7.2 Graph skeleton
```python
g = StateGraph(InspectionState)
# Stage 1
g.add_node("read_part_id", ...); g.add_node("load_part_master", ...)
g.add_node("create_job", ...);   g.add_node("set_camera_recipe", ...)
g.add_node("capture_images", ...); g.add_node("preprocess_store", ...)
# Stage 2
g.add_node("parse_drawing", ...); g.add_node("detect_features", ...)
g.add_node("measure_mm", ...);    g.add_node("compare_drawing", ...)
g.add_node("set_dim_status", ...); g.add_node("gate1_engineer", ...)  # interrupt
g.add_node("lock_result", ...);   g.add_node("save_dim", ...)
# Stage 3
g.add_node("dispatch_detectors", ...); g.add_node("detect_segment", ...)
g.add_node("anomaly_check", ...);      g.add_node("fuse", ...)
g.add_node("classify_measure", ...);   g.add_node("label_review_gate", ...)  # interrupt
g.add_node("save_defects", ...)
# Stage 4
g.add_node("build_query", ...); g.add_node("apply_filters", ...); g.add_node("embed_query", ...)
g.add_node("graph_expand", ...); g.add_node("set_limits", ...)
g.add_node("hybrid_retrieve", ...); g.add_node("rerank", ...); g.add_node("assemble_evidence", ...)
# Stage 5
g.add_node("assemble_context", ...); g.add_node("llm_reason", ...); g.add_node("score_conf", ...)
g.add_node("rank_top3", ...); g.add_node("calibrate", ...); g.add_node("format_top3", ...)
g.add_node("save_ranked", ...)
# Stage 6
g.add_node("gate2_expert", ...)       # interrupt
g.add_node("finalize_actions", ...); g.add_node("save_decision", ...)
g.add_node("record_feedback", ...);  g.add_node("mark_rca_final", ...)
# Stage 7
g.add_node("compose_report", ...); g.add_node("draft_report", ...); g.add_node("render_files", ...)
g.add_node("gate3_approver", ...)     # interrupt
g.add_node("esign_archive", ...); g.add_node("notify_systems", ...)
# Stage 8
g.add_node("final_output", ...); g.add_node("dispatch_results", ...)
g.add_node("track_actions", ...); g.add_node("close_case", ...); g.add_node("learning_hub", ...)

# Conditional edges (see routing.py): part_found, image_ok, engineer_confirms,
# any_defect, all_conf_ge_85, evidence_sufficient, output_valid, expert_accepts,
# report_complete, approved, action_effective.
```
Compile with `PostgresSaver` checkpointer. Human-gate nodes call `interrupt({...})`; the API resumes with `Command(resume=payload)`. **Each loop-back must increment `state.loops[Lx]` and enforce its max** (Section 9) before routing; on exhaustion route to the stated fallback.

---

## 8. STAGE-BY-STAGE IMPLEMENTATION SPEC

For each stage: **Flow → Implementation → Outputs → Acceptance tests.**

### STAGE 1 — Trigger, Context & Image Capture (Inspection agent · industrial camera)

**Flow:** START (part arrives; sensor/MES trigger) → Read part ID (barcode/QR/part number) → Load part master (drawing rev, material, process, tolerances) → *Part & drawing found?* (No → **L1**) → Create inspection job (job ID, state, audit trail) → Set camera recipe (lighting, angles, exposure) → Capture images (high-res, multi-angle) → *Image quality OK?* (No → **L2**) → Preprocess (undistort, scale px→mm, normalize) → Store images (raw + processed in object storage) → Release to Stage 2.

**Implementation:**
- `POST /jobs` (manual/API trigger), plus MES webhook `POST /triggers/mes`, plus folder-watch trigger.
- Part-ID reader: `pyzbar`/OpenCV QR+barcode; fallback typed PN. Normalize and validate against `part_master`.
- `CameraAdapter` interface: `capture(recipe) -> list[Image]`. Implement `FolderCamera`, `UploadCamera`, `MockCamera`, and a stub `GenICamCamera` (harvesters/pypylon).
- Image quality scoring: blur (variance of Laplacian), glare (saturated-pixel ratio), exposure (histogram clipping). Thresholds from config. On failure auto-adjust recipe (exposure ±, angle) and recapture.
- Preprocess: undistort using `calibration` (camera matrix + distortion), compute `px_per_mm` from calibration target/fiducials, normalize illumination (CLAHE), perspective-rectify to part plane.
- Persist raw + processed to object storage; insert `image_asset` rows; create `inspection_job` and first audit entry.

**Acceptance:** unknown PN triggers L1 up to 3 times then `ON_HOLD`; blurred test image triggers L2 up to 3 recaptures then operator alert; processed images carry a valid `px_per_mm`.

---

### STAGE 2 — Dimensional Check + Human Gate 1 (Dimensional agent · ezdxf, OpenCV)

**Flow:** Parse 2D drawing (DXF/PDF → dimensions, tolerances, GD&T) → Detect features (holes, edges, contours via CV) → Measure in mm (pixel→mm via calibration) → Compare with drawing (deviation per feature vs tolerance) → Set dimensional status (PASS/FAIL + out-of-tolerance list) → **Human Gate 1: engineer reviews deviation overlay** → *Engineer confirms?* (No → **L3** re-measure, max 2, then manual measurement) → Lock result (confirmed, or overridden with reason code) → Save to DB → Release to Stage 3.

**Implementation:**
- **DXF parser (ezdxf):** extract DIMENSION entities, circles (hole Ø), lines/arcs (edges), layers; map to `feature_id`. Read tolerances from dimension text/tolerance fields or part-master defaults (e.g. ±0.10).
- **PDF drawing parser:** PyMuPDF vector extraction when vector; else rasterize + OCR (Tesseract/PaddleOCR) + regex for `Ø`, `±`, `+x/-y`, `R`, GD&T frames. Record parse confidence; low-confidence parse is flagged for Gate 1.
- **Feature detection (OpenCV):** threshold/Canny → contours; `HoughCircles` / ellipse fit for holes (sub-pixel via `cv2.fitEllipse`); polygon approximation for edges and bends; align drawing to image with homography from fiducials or ICP/feature matching (contour-to-DXF registration).
- **Measurement:** distance transforms in px × `1/px_per_mm`; report measured, nominal, deviation, within-tolerance. Example target output (from infographic): `120.05 (+0.05)` OK, `80.02 (+0.02)` OK, `Ø11.70 (-0.30)` OUT, `50.01 (+0.01)` OK, `2.15 (-0.15)` OUT-or-OK per tolerance.
- **Status rule:** `PASS` only if all features in tolerance; else `FAIL` with list.
- **Overlay generator:** annotate processed image with green (within) / red (out) labels per feature; store as `overlay` asset.
- **Gate 1 (UI + API):** `GET /gates/1/{job_id}` returns overlay, table, drawing preview. `POST /gates/1/{job_id}` body `{decision: confirm|reject|override, reason_code, comments, overrides[]}`. Reject → L3 (recalibrate then re-measure, max 2, then flag `manual_measurement`). Override requires reason code.
- Save results to `dimension_result` + `gate_decision`; audit entry.

**Acceptance:** synthetic DXF + synthetic rendered image yield measurements within 0.05 mm of nominal; out-of-tolerance feature produces FAIL and a red overlay; gate resume continues the graph; override requires reason code.

---

### STAGE 3 — Defect Detection (Inspection agent · YOLO, SAM, Anomalib)

**Flow:** Dispatch detectors (parallel on GPU) → Detect + segment (YOLO boxes, SAM masks) → Anomaly check (Anomalib flags unseen defects) → Fuse detections (merge, de-duplicate, score) → *Any defect found?* (**No → Fast path to Stage 7 OK report**) → Classify + measure (dent, scratch, crack, deformation; size, severity) → *All confidence ≥ 85%?* (No → **Human label review**; Yes → skip review) → Save defects (corrections go to training set, **L10**) → Release to Stage 4.

**Implementation:**
- `Detector` protocol: `detect(images) -> list[Detection]`. Implementations: `YoloDetector` (Ultralytics, 4 classes), `SamSegmenter` (prompted by YOLO boxes → masks), `AnomalibDetector` (PatchCore/EfficientAD trained on good parts; returns anomaly map + score), `MockDetector` (deterministic, for CI).
- Run detectors concurrently (`asyncio.gather` / Celery group); GPU if available else CPU.
- **Fusion:** class-aware NMS/WBF on boxes, mask IoU merge, anomaly-only regions become class `unknown_anomaly` (routed to label review). Fused confidence = weighted combo (config weights).
- **Classification + measurement:** geometric/area stats from masks → `size_mm2`, length, depth proxy; severity rules (config) such as crack → critical; scratch length/width; dent area; deformation deviation from nominal contour.
- **Decision:** `defect_found = len(defects)>0`. If false → set route `fast_path`.
- **Label review gate:** only when `min(confidence) < 0.85` or any `unknown_anomaly`. UI shows masks; reviewer confirms/corrects/deletes/adds. Corrections stored with `human_corrected=true`, `original_label`, and written to `feedback` (kind=label) for **L10**.
- Persist `defect`, mask assets, overlay (infographic style: red boxes labelled Scratch/Dent/Crack/Deformation).

**Acceptance:** mock detector returns 4 defect types → classification and severity correct; no-defect image takes fast path; low-confidence defect pauses for label review, corrected label is stored as training sample.

---

### STAGE 4 — Root-Cause Knowledge Retrieval (Knowledge agent · hybrid RAG)

**Flow:** Build query (defects, deviations, part, material, process) → Apply filters (part, material, process, defect type) → Embed query (dense vector + keyword terms) → Graph expand (defect→cause→action links) → Set retrieval limits (top-k, similarity threshold) → Hybrid retrieval (vector + keyword in KB) → Rerank (cross-encoder keeps best evidence) → *Evidence sufficient?* (No → **L4**: relax filters, widen query, max 2, then flag `low_evidence`) → Assemble evidence pack (causes, CAPA, precautions, sources) → Stage 5.

**Implementation:**
- Query builder: natural-language + structured (e.g. "dent + scratch + crack on sheet-metal bracket, material X, process bending, Ø11.70 undersize").
- Metadata pre-filter (SQL WHERE on part/material/process/defect_type); on L4 progressively drop the filters in order: part → process → material, then widen synonyms.
- Dense search: pgvector cosine top-k (default 30); keyword: `ts_rank_cd`/BM25 top-k (30); merge via **Reciprocal Rank Fusion**.
- Graph expansion: traverse `kb_edge` from detected defect types to candidate causes and actions (1–2 hops), add as extra evidence.
- Rerank with cross-encoder (`bge-reranker` or `ms-marco-MiniLM`), keep top 8–10.
- **Sufficiency test:** `max_score ≥ sim_threshold` AND `≥ min_chunks` (config). Failing after L4 retries sets `flags += ["low_evidence"]` and continues.
- Evidence pack JSON: `{causes[], corrective[], preventive[], precautions[], process_material_notes[], sources[{doc,chunk,uri,score}]}`.

**Acceptance:** seeded KB returns relevant cause chunks for each defect type; sufficiency failure triggers up to 2 relaxations then flags; every evidence item has a source link.

---

### STAGE 5 — AI Prediction & Recommendation (Root-cause agent · LLM + scoring)

**Flow:** Assemble context (defects, deviations, part, evidence) → LLM reasons (candidate root causes with rationale) → Score confidence (retrieval match, history, detection) → Rank top 3 (cause, effect, precautions each) → Calibrate confidence (map to calibrated % per cause) → *Valid, cited output?* (No → **L5** regenerate with more context, max 2, then send flagged `low_confidence`) → Format top 3 → Save ranked causes (+ source links) → Release to Stage 6.

**Implementation:**
- Prompt in `llm/prompts/root_cause.md`; system rules: use only provided evidence, cite chunk IDs, no invented sources, output strict JSON.
- Pydantic output schema:
```json
{"candidates":[{"cause":"Improper Bending Force / Over Bending",
  "rationale":"...", "effect":"Deformation, Dimensional Inaccuracy",
  "precautions":["Optimize bending parameters","Use proper tooling","Regular machine calibration"],
  "citations":["chunk_id", "..."]}]}
```
- Validators: JSON valid; ≥3 candidates (or fewer with flag); each has ≥1 existing citation; effect consistent with detected defects/deviations (rule-based check: e.g. over-bending ↔ deformation/Ø deviation). Failure → L5.
- **Confidence score** = weighted sum of (a) retrieval match score (rerank), (b) historical frequency of cause for same defect/part in KB/history, (c) detection confidence and dimensional agreement. Weights in config.
- **Calibration:** isotonic regression or Platt scaling on past (score, expert-accepted) pairs; before enough data, use identity mapping + conservative cap and label `uncalibrated`. Persist `confidence_raw` and `confidence_cal`.
- Rank → top 3. Reference example (infographic): Rank 1 Improper Bending Force/Over Bending (92%), Rank 2 Material Inconsistency/Hardness Variation (78%), Rank 3 Tool Wear/Die Damage (71%), each with effect and 3 precautions.
- LLM provider abstraction with retries, timeouts, token/cost logging, and prompt/version tracking.

**Acceptance:** golden test with fixed evidence yields valid JSON with citations; invalid output triggers regeneration twice then `low_confidence` flag; confidences are ordered and within [0,1].

---

### STAGE 6 — Human Gate 2: Final Decision (Quality expert)

**Flow:** Expert reviews top 3 with evidence → *Accept a cause?* (No → **L6**: reject all → request re-inspection back to Stage 1 camera recipe, or manual RCA) → Select or edit cause (rank 1–3 or free text, with reason) → Finalize actions (corrective + preventive precautions) → Save decision (final RCA, edits, reviewer ID) → Record feedback (expert choice vs AI rank → **L10–L12**) → Mark RCA final (state checkpoint + audit entry) → Release to Stage 7.

**Implementation:**
- UI card per rank: cause, effect, precautions, confidence ring, evidence snippets with source links (see infographic: checkboxes, "AI Recommended Top 3 Root Causes", "Finalized Root Cause", "Finalized Precautions", **APPROVED & FINALIZED**).
- `POST /gates/2/{job_id}`: `{decision: accept|edit|reject_all, selected_rank, edited_cause?, reason, corrective[], preventive[], next: reinspect|manual_rca}`.
- Writes `final_rca`, `gate_decision`, `feedback(kind=rca_choice)` with AI ranks vs human pick (used for recalibration, **L12**).
- `reject_all` + `reinspect` loops back to `set_camera_recipe` (new capture). `manual_rca` lets expert enter RCA freely.

**Acceptance:** each decision branch tested; feedback row captures rank vs choice; edited cause requires reason.

---

### STAGE 7 — Report & Human Gate 3: Sign-off (Report agent · PDF / Excel / Word)

**Flow:** Compose report data (OK part: summary; NG part: full RCA) → Draft report (text, tables, images, charts) → *Report complete?* (No → **L7** orchestrator adds missing data and redrafts) → Render files (PDF, Excel, Word templates) → **Human Gate 3: approver reviews report** → *Approved?* (No → **L8**: approver comments logged, redraft, repeat sign-off) → Apply e-signature (name, date, approval stamp) → Archive (files in object storage + DB) → Notify systems (MES, QMS, ERP, e-mail) → Release to Stage 8.

**Report content (match infographic "Quality Inspection Report"):**
- Part details: Part Name, PN, Date, Inspector (System AI + Human).
- Inspection summary: Dimensional Inspection (PASS/FAIL), Defect Detection (PASS/FAIL).
- Detected defects list with annotated image.
- Finalized Root Cause (rank), Potential Effect/Impact, Precautionary/Corrective/Preventive actions.
- Evidence citations, confidence, model versions, reviewer names and timestamps.
- Approval block: Approved By, Date, signature image.
- **OK-part variant:** summary only (no RCA sections).
- Export buttons: **PDF, Excel, Word, Print**.

**Implementation:** Jinja2 data model → ReportLab/WeasyPrint PDF, openpyxl workbook (sheets: Summary, Dimensions, Defects, RCA, Actions, Audit), python-docx from a branded template. Completeness validator checks required fields (L7). E-signature: capture approver identity (authenticated user), timestamp, SHA-256 of the PDF, stamp onto PDF, store signature record. Each redraft increments `report.version`; prior versions retained.

**Acceptance:** NG and OK jobs render all three formats; missing field triggers L7; rejection stores comments and creates version N+1; approved PDF contains hash/stamp.

---

### STAGE 8 — Output, Actions & Continuous Learning

**Flow:** Final quality output (status, defects, cause, effect, precautions) → Dispatch results (dashboard, alerts, MES/QMS/ERP) → Track corrective actions (owner, due date, evidence) → *Action effective?* (No → **L9** reopen and escalate to quality lead) → Close case (archive, history updated) → **Learning hub** (labels, RCA edits, outcomes) → Retrain CV models (versioned; **L10** → Stage 3) · Update knowledge base (final RCA added, **L11** → Stage 4) · Recalibrate scores (thresholds; **L12** → Stages 5–6) → END (ready for next part).

**Implementation:**
- "Final Quality Intelligence Output" payload (infographic right panel): dimensional status, detected defects, finalized root cause, effect/impact, precautionary actions, approval status ("AI + Human Approved").
- Dispatcher adapters with retry + dead-letter queue: dashboard (WebSocket), email/Teams/Slack, MES/QMS/ERP REST/webhooks.
- Action tracker: CRUD, reminders on due dates, evidence upload, effectiveness verification (re-inspection of next N parts or manual confirm); ineffective → reopen + escalate (L9).
- **Learning hub (scheduled + triggered workers):**
  - L10: export human-corrected labels to dataset; when ≥N new samples, fine-tune YOLO/SAM/Anomalib via `ml/training`, evaluate vs champion on a holdout, register in MLflow, promote only if metrics improve; new version served to Stage 3 (blue/green).
  - L11: finalized RCA becomes a new `kb_document` (type=historical_case), chunked/tagged/embedded/indexed.
  - L12: refit calibrator on (confidence, accepted?) pairs; re-tune thresholds (85% label threshold, similarity threshold) with guardrails and manual approval for threshold changes.
- Close case writes final status and emits `case_closed` event.

**Acceptance:** closing a case adds a KB document; ineffective action reopens and notifies; retrain job registers a new model version; calibrator refit changes stored mapping.

---

## 9. LOOP & DECISION REGISTER (CONFIGURABLE DEFAULTS)

| ID | Trigger (No-branch) | Action | Max | Exhaustion fallback |
|---|---|---|---|---|
| L1 | Part or drawing not found | Operator rescans or types PN, re-read ID | 3 | Job `ON_HOLD` |
| L2 | Image quality fails (blur, glare, exposure) | Auto-adjust recipe, recapture | 3 | Operator alert |
| L3 | Engineer rejects dimensional result | Recalibrate and re-measure | 2 | Manual measurement |
| L4 | Evidence insufficient (similarity < threshold) | Relax filters, widen query | 2 | Flag `low_evidence`, continue |
| L5 | Output invalid / uncited / inconsistent | Regenerate with more context | 2 | Send flagged `low_confidence` |
| L6 | Expert rejects all 3 causes | Re-inspect (Stage 1 recipe) or manual RCA | — | Expert's choice |
| L7 | Report incomplete | Orchestrator adds missing data, redraft | 3 (suggested) | Escalate to admin |
| L8 | Approver rejects | Log comments, redraft, repeat sign-off | — | Unlimited with audit |
| L9 | Corrective action not effective | Reopen action, escalate to quality lead | — | — |
| L10 | Learning | Corrected labels retrain CV models; new version returns to Stage 3 | — | — |
| L11 | Learning | Final RCA added as case, re-indexed for Stage 4 | — | — |
| L12 | Learning | Expert choice vs AI rank + outcomes recalibrate Stages 5–6 | — | — |

Other routing: "Yes · skip review" when all defect confidences ≥85%; **Fast path** for no-defect parts.

**Human gates summary:** engineer (Stage 2), label review (Stage 3, low-confidence only), expert (Stage 6), approver (Stage 7).

---

## 10. HUMAN GATE MECHANICS

- Implemented with LangGraph `interrupt()`; the job row moves to `AWAIT_GATE{1|2|3}` or `AWAIT_LABEL_REVIEW`; a task appears in the reviewer's inbox (UI + notification).
- Resume only via authenticated API by a user holding the correct role (RBAC): Gate 1 = Quality Engineer; Label review = Quality Engineer; Gate 2 = Quality Expert; Gate 3 = Approver. Separation of duties: the Gate 3 approver must differ from the Gate 2 expert (configurable).
- Timeouts/SLAs: configurable reminder and escalation (e.g. 4h reminder, 24h escalate).
- Every decision stored in `gate_decision` + `audit_log` with state hash.
- Jobs must survive process restarts (checkpoint in Postgres) — test this explicitly.

---

## 11. OFFLINE DATA PLANE — KNOWLEDGE-BASE INGESTION

**Flow:** Customer inputs (RCA docs, historical issues, corrective + preventive actions, process & material data) → Parse + OCR (PDF, Word, Excel, scanned pages) → Chunk + tag (part, material, process, defect, cause) → Embed + index (vector, keyword, graph) → **Knowledge base (K)**.

**Implementation:**
- Endpoints: `POST /kb/documents` (upload), `GET /kb/documents`, `DELETE`/re-ingest with versioning, `POST /kb/reindex`.
- Parsers: PDF text/tables (pdfplumber), scanned (OCR), DOCX (python-docx), XLSX (openpyxl, one chunk per row/case with column headers retained).
- Chunking: semantic/section-aware, 300–600 tokens with overlap; keep tables intact; attach metadata tags using rules + LLM tagger (part, material, process, defect_type, cause, doc_type). Human spot-check UI for tags.
- Graph build: extract triples (defect→cause→corrective/preventive action, cause→material/process) into `kb_edge` with `source_chunk`.
- Embeddings: configurable model (default dense 1024-dim, e.g. `bge-m3` or provider embedding); store `tsv` for keyword.
- Idempotent ingestion (hash documents), progress tracking, error report per document.
- Seed script `scripts/load_kb.py` with a sample corpus covering: over-bending, material hardness variation, tool/die wear, springback, burrs, lubrication.

**Acceptance:** ingest PDF + DOCX + XLSX + scanned sample; chunks tagged; vector and keyword queries return expected chunks; re-ingest of unchanged file is a no-op.

---

## 12. API DESIGN (FASTAPI)

All routes under `/api/v1`, JWT-protected, OpenAPI at `/docs`.

| Method | Route | Purpose | Role |
|---|---|---|---|
| POST | `/jobs` | Create job (PN, optional images) | Operator+ |
| POST | `/triggers/mes` | MES/sensor webhook trigger | Service |
| GET | `/jobs`, `/jobs/{id}` | List/detail incl. state, timeline | All |
| GET | `/jobs/{id}/events` | SSE/WebSocket live progress | All |
| POST | `/jobs/{id}/rescan` | L1 operator PN rescan/entry | Operator |
| GET/POST | `/gates/1/{id}` | Dimensional review / decision | Engineer |
| GET/POST | `/gates/label/{id}` | Low-confidence label review | Engineer |
| GET/POST | `/gates/2/{id}` | Top-3 review / final RCA | Expert |
| GET/POST | `/gates/3/{id}` | Report approval / reject with comments | Approver |
| GET | `/reports/{job_id}` , `/reports/{id}/download?fmt=pdf\|xlsx\|docx` | Reports | All |
| GET/POST/PATCH | `/actions` | Corrective-action tracking | Engineer+ |
| GET/POST/DELETE | `/kb/documents`, POST `/kb/reindex` | Knowledge base | Admin/Expert |
| GET | `/parts`, POST/PUT `/parts` | Part master + drawings + calibration | Admin |
| GET | `/dashboard/kpis` | Pass rate, defect mix, cycle time, gate backlog | All |
| GET | `/models`, POST `/models/{id}/promote` | Model registry | Admin |
| GET | `/audit?job_id=` | Audit trail | Auditor/Admin |
| GET | `/healthz`, `/readyz`, `/metrics` | Ops | — |

Document request/response schemas with Pydantic and keep `docs/API.md` generated from OpenAPI.

---

## 13. FRONTEND (REACT)

Pages and key behaviors:
1. **Jobs list / Dashboard:** live status, filters, KPIs (pass rate, defect distribution, average cycle time, backlog per gate).
2. **Job detail:** timeline of stages with loop counters, images, state, audit.
3. **Gate 1 Review:** drawing vs actual overlay, deviation table (green within / red out), Confirm / Reject / Override-with-reason.
4. **Label Review:** image with masks/boxes, class dropdown, confidence, add/delete/correct.
5. **Gate 2 Expert:** three rank cards (cause, effect, precautions, confidence ring), evidence viewer with source links, accept/edit/reject-all, finalize actions, **Approved & Finalized** state.
6. **Gate 3 Approval:** report preview, comments, approve (e-sign) or reject.
7. **Reports:** download PDF/Excel/Word, print.
8. **Knowledge Base:** upload, ingestion status, tag editor, search tester.
9. **Actions:** corrective-action board with owners/due dates/evidence/effectiveness.
10. **Admin:** parts/drawings/calibration, thresholds, users/roles, model registry.

Branding: NOVALISEO logo, "Brain Behind Intelligent Operations", "Inspired Engineering"; blue/white palette per infographic; accessible, responsive, role-aware navigation.

---

## 14. CONFIGURATION (`config/default.yaml`)

```yaml
workflow:
  retries: {L1: 3, L2: 3, L3: 2, L4: 2, L5: 2, L7: 3}
  gate_sla_hours: {reminder: 4, escalate: 24}
  separation_of_duties: true
image_quality: {blur_min_laplacian_var: 100, glare_max_ratio: 0.02, exposure_clip_max: 0.05}
dimensional:
  default_tolerance_mm: 0.10
  subpixel: true
detection:
  models: {yolo: yolov8m-defects:latest, sam: sam_vit_b, anomalib: patchcore:latest}
  label_review_confidence_threshold: 0.85
  fusion_weights: {yolo: 0.5, sam: 0.2, anomalib: 0.3}
  severity_rules: {crack: critical, deformation: major, dent: major, scratch: minor}
retrieval:
  dense_top_k: 30
  keyword_top_k: 30
  rerank_keep: 8
  similarity_threshold: 0.55
  min_chunks: 3
  filter_relax_order: [part, process, material]
prediction:
  llm: {provider: anthropic, model: configurable, temperature: 0.2, max_tokens: 2000}
  confidence_weights: {retrieval: 0.5, history: 0.3, detection: 0.2}
  calibration: {method: isotonic, min_samples: 50}
learning:
  retrain_min_new_labels: 200
  promote_requires_metric_gain: true
  threshold_change_requires_approval: true
storage: {bucket: novaliseo, retention_days_raw: 365}
```
Secrets (DB URL, LLM keys, object-store keys, SMTP, MES tokens) only via environment variables; provide `.env.example`.

---

## 15. CROSS-CUTTING REQUIREMENTS

- **Audit trail:** append-only `audit_log`; hash of state at each node; no UPDATE/DELETE for the app DB role; export endpoint for auditors.
- **RBAC:** roles Operator, Quality Engineer, Quality Expert, Approver, Admin, Auditor (read-only). Enforce at API and UI.
- **Security:** TLS, input validation, file-type/size limits on uploads, malware scan hook, secrets via env/vault, OWASP top-10 review, prompt-injection defense for RAG content (treat retrieved text as data, never instructions; strip/flag instruction-like content).
- **Monitoring and drift:** Prometheus metrics (stage latency, loop counts, gate wait times, queue depth, GPU utilization); drift checks on image statistics, detection-confidence distribution, retrieval-score distribution, and LLM output validity rate; alerts via notifications.
- **Notifications:** gate-pending, SLA breach, job on hold, defect-critical alert, report approved, action due/overdue.
- **Resilience:** idempotent nodes, retries with backoff, dead-letter queue, resume-after-crash from checkpoint, graceful degradation (e.g. no GPU → CPU or mock, LLM down → queue and flag).
- **Observability:** trace ID per job across API, workers and LLM calls (OpenTelemetry).
- **Performance targets (v1, configurable):** Stage 1–3 ≤ 60 s per part on one GPU; Stage 4–5 ≤ 30 s; report render ≤ 15 s.
- **Data retention & privacy:** configurable retention; PII limited to reviewer identity.

---

## 16. TESTING STRATEGY

1. **Unit:** parsers (DXF/PDF), measurement math, fusion/NMS, severity rules, scoring + calibration, RRF, validators, report composers.
2. **Component:** each node with fixtures; detectors via `MockDetector`; LLM via recorded/fake provider.
3. **Graph/integration:** full workflow with fakes covering every branch: PASS + no defect (fast path), FAIL dimensional, defect with high confidence, defect needing label review, each loop L1–L9 incl. exhaustion fallbacks, expert reject-all, approver reject → redraft, crash-and-resume at each gate.
4. **API:** contract tests + RBAC matrix tests.
5. **E2E (Playwright):** upload sample → gates → approval → download report.
6. **Data/ML:** evaluation scripts with metrics (mAP/IoU for defects, AUROC for anomalies, measurement MAE in mm, retrieval recall@k/MRR, calibration ECE). Fail CI if below configured floors on the demo set.
7. **Security & quality gates:** `ruff`, `mypy`, `pytest --cov` (target ≥80% on backend core), dependency audit.
8. **Golden demo:** `make demo` runs the sample part MS-4505-001 end to end and produces the three report formats, reproducing the infographic scenario (dimensional PASS/overall FAIL with Dent, Scratch, Crack, Deformation; Top-3 causes 92/78/71%).

---

## 17. PHASED IMPLEMENTATION PLAN (MILESTONES)

Mark each task `[x]` in `docs/AUDIT.md` as completed. Do milestones in order; each ends with passing tests and updated docs.

**M0 — Foundation**
- [ ] Repo audit → `docs/AUDIT.md`; scaffold missing structure; tooling (ruff, mypy, pre-commit, Makefile).
- [ ] docker-compose (Postgres+pgvector, Redis, MinIO, MLflow); config loader; logging; health endpoints.
- [ ] Alembic migrations for Section 6; seed script with sample part MS-4505-001 and synthetic DXF.
- [ ] Auth + RBAC skeleton; audit-log writer; object-storage adapter.

**M1 — Orchestrator skeleton**
- [ ] `InspectionState`, LangGraph graph with all nodes as stubs, conditional routing, loop counters with max/fallbacks, Postgres checkpointer, interrupt/resume helpers.
- [ ] Jobs API + SSE; integration test traversing every branch with stubs.

**M2 — Stage 1**
- [ ] Part-ID reader, part master load, camera adapters (folder/upload/mock), quality scoring, recipe auto-adjust (L1, L2), preprocess, storage.

**M3 — Stage 2 + Gate 1**
- [ ] DXF + PDF parsers, feature detection, registration, measurement, tolerance compare, overlay, status.
- [ ] Gate 1 API + UI; L3 re-measure/manual fallback; persistence.

**M4 — Stage 3 + label review**
- [ ] Detector interfaces, Mock + YOLO + SAM + Anomalib adapters, fusion, classify/measure, severity, fast path.
- [ ] Label-review gate API + UI; L10 feedback capture; training-set export.

**M5 — Knowledge base + Stage 4**
- [ ] Ingestion pipeline (parse/OCR/chunk/tag/embed/index/graph), KB UI + API, sample corpus.
- [ ] Retrieval (filters, hybrid, RRF, graph expand, rerank), sufficiency + L4, evidence pack.

**M6 — Stage 5**
- [ ] LLM abstraction, prompts, schema validators, scoring, calibration (identity first), top-3 formatting, L5.

**M7 — Gate 2 (Stage 6)**
- [ ] Expert review API/UI, final RCA persistence, feedback capture (L12), reject-all → re-inspect/manual RCA (L6).

**M8 — Stage 7 + Gate 3**
- [ ] Report composer (OK and NG variants), PDF/Excel/Word renderers, completeness check (L7), approval flow with e-signature + hash (L8), archive, notifications.

**M9 — Stage 8 + learning**
- [ ] Final output payload, dispatch adapters (dashboard/MES/QMS/ERP mocks), action tracker with L9, case close.
- [ ] Learning hub workers: retrain pipeline + MLflow registry (L10), KB update (L11), recalibration (L12).

**M10 — Frontend completion & dashboard**
- [ ] All pages in Section 13, role-aware navigation, KPIs dashboard.

**M11 — Hardening**
- [ ] Monitoring/drift, SLA reminders, security review, performance pass, crash-resume tests, backup/restore runbook.

**M12 — Release**
- [ ] `make demo` golden run, E2E tests, full docs, `docs/RUNBOOK.md`, `docs/BLOCKERS.md` final, version tag.

---

## 18. DEVELOPMENT ENVIRONMENT

- `make dev` → docker-compose up (db, redis, minio, mlflow, api, worker, frontend).
- `make migrate`, `make seed`, `make test`, `make lint`, `make demo`, `make ingest-sample-kb`.
- CPU-only fallback path must work (mock detectors, small embedding model, fake LLM) so CI runs without GPU or API keys. Use env switches: `NOVALISEO_MODE=mock|real`.
- Real models require: weights for YOLO/SAM/Anomalib, an LLM API key, an embedding model; document download/setup in `README.md`.

---

## 19. DEFINITION OF DONE

The project is complete only when **all** of the following are demonstrably true (record evidence in `docs/AUDIT.md`):

1. Every stage (1–8) and the offline KB plane is implemented per Section 8, with all decision points routed as in the PDF.
2. All loops L1–L12 work, enforce max counts, and use the specified fallbacks; each has an automated test.
3. All four human gates work end to end via API and UI with RBAC, reason codes, timestamps, and survive restarts.
4. Fast path (no defect) skips Stages 4–6 and produces an OK report.
5. Dimensional check compares against DXF/PDF drawings and flags out-of-tolerance features with overlay.
6. Defect detection returns Dent/Scratch/Crack/Deformation with size/severity; label review only triggers below 85% or on unknown anomalies.
7. RAG retrieval is hybrid + graph + rerank with source citations; sufficiency/L4 behaves as specified.
8. Top-3 root causes with effect, precautions and calibrated confidence are produced, validated and cited.
9. Reports render in PDF, Excel and Word (NG and OK variants), with e-signature and archive; Print works.
10. Final output dispatches to dashboard/MES/QMS/ERP adapters; corrective actions tracked with effectiveness check.
11. Learning hub functions: labels → retrain/registry, final RCA → KB, feedback → recalibration.
12. Audit trail is complete and append-only; monitoring, drift metrics and notifications are active.
13. `make test` passes (unit, integration, API, E2E) with coverage targets met; `ruff` and `mypy` clean.
14. `make demo` reproduces the infographic scenario end to end on a fresh clone with no GPU and no external keys (mock mode), and instructions exist for real-model mode.
15. Documentation is complete and accurate: README, ARCHITECTURE (with diagrams), API, RUNBOOK, DECISIONS, BLOCKERS.
16. Any genuine blockers (e.g. no customer weights/data, no camera hardware, no MES access) are listed in `docs/BLOCKERS.md` with the mock used and the exact steps to replace it.

---

## 20. FINAL INSTRUCTIONS TO THE AGENT

1. Start with **Section 0** and the audit. Then execute **Milestones M0→M12** sequentially.
2. After each milestone: run `make lint test`, fix failures, update docs, commit.
3. Do not ask the user for permission between milestones; continue until Section 19 is satisfied or a documented blocker prevents progress.
4. If the spec is ambiguous, choose the most conservative, configurable option, log it in `docs/DECISIONS.md`, and continue.
5. At the end, output a completion report: what was done, evidence per Definition-of-Done item, remaining blockers, and how to run everything.

*Novaliseo Global Tech Pvt Ltd. · Inspired Engineering · Sheet-metal AI quality inspection and root-cause intelligence*
