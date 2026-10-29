# NOVALISEO — AI-Driven Quality Inspection & Root Cause Intelligence Platform

> *Intelligent Inspection. Accurate Insights. Superior Quality.*

Built on top of an existing YOLOv8 sheet-metal defect detection demo, Novaliseo is a full
end-to-end agentic quality inspection platform with:

- **8-stage workflow** (capture → dimensional → defect → RAG retrieval → AI prediction → expert review → report → learning)
- **4 human gates** with LangGraph `interrupt()` — all resumable after restarts
- **12 control loops** (L1–L12) with configurable retry limits and fallbacks
- **Hybrid RAG** (dense + keyword + graph + cross-encoder rerank) for root-cause knowledge
- **3 report formats** (PDF, Excel, Word) with e-signature and archival
- **Continuous learning** (label correction → retrain, RCA → KB, feedback → calibration)
- **React + Vite + Tailwind** frontend with 10 role-aware pages
- **Mock mode** — runs entirely without GPU, API keys, or camera hardware

---

## Quick Start (Mock Mode)

```powershell
# Install deps
py -m pip install -r backend/requirements.txt

# Start API
$env:NOVALISEO_MODE="mock"
py -m uvicorn app.main:app --app-dir backend --reload --port 8000
# → Open http://localhost:8000/docs

# Load sample knowledge base
py scripts/load_kb.py

# Run golden demo (reproduces infographic scenario)
py scripts/run_demo.py
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
# → Open http://localhost:5173
```

---

## Running Tests

```powershell
$env:NOVALISEO_MODE="mock"
$env:DATABASE_URL="sqlite+aiosqlite:///./novaliseo_test.db"
py -m pytest backend/tests/ -v
# → 43 passed
```

---

## Default Demo Users

| Username | Password | Role |
|----------|----------|------|
| operator | operator | Operator |
| engineer | engineer | Quality Engineer (Gate 1, Label Review) |
| expert | expert | Quality Expert (Gate 2) |
| approver | approver | Approver (Gate 3) |
| admin | admin | Admin |

---

## Infographic Demo Scenario (MS-4505-001 Sheet Metal Bracket)

The mock mode reproduces the spec infographic exactly:
- **Dimensional:** 120.05(+0.05)✓, 80.02(+0.02)✓, Ø11.70(-0.30)✗, 50.01(+0.01)✓
- **Defects:** Scratch, Dent, Crack (76% confidence → triggers label review), Deformation
- **Top-3 causes:** Improper Bending Force (92%), Material Inconsistency (78%), Tool Wear (71%)
- **Report:** generated in PDF, Excel, Word with e-signature

---

## Architecture

See `docs/ARCHITECTURE.md` for diagrams. Key components:
- `backend/app/workflow/graph.py` — LangGraph state machine
- `backend/app/workflow/nodes/` — 8 stage node implementations
- `backend/app/cv/` — Camera adapters, drawing parsers, detectors, measurement
- `backend/app/rag/` — Ingestion pipeline, hybrid retrieval, reranking
- `backend/app/llm/` — Provider abstraction (fake/Anthropic/OpenAI)
- `backend/app/reports/` — PDF/Excel/Word generation + e-signature
- `frontend/src/pages/` — 10 React pages

---

## Switching to Real Mode

See `docs/RUNBOOK.md` and `docs/BLOCKERS.md` for instructions on:
- Using real YOLO weights (`models/best.pt` from the original demo works)
- Connecting Anthropic/OpenAI for LLM-powered root cause analysis
- Using a PostgreSQL database instead of SQLite
- Connecting to real camera hardware (GenICam stub provided)

---

## Original Demo (Phase 1-2)

The original YOLOv8 Streamlit demo is preserved at `src/`. Run it with:
```
streamlit run src/app.py
```

## Repo Layout

```
RIO_FYP/
├── backend/          ← Novaliseo FastAPI + LangGraph backend
├── frontend/         ← React + Vite + Tailwind frontend
├── config/           ← default.yaml (all thresholds)
├── docs/             ← AUDIT, ARCHITECTURE, API, RUNBOOK, DECISIONS, BLOCKERS
├── scripts/          ← seed_demo.py, load_kb.py, run_demo.py
├── src/              ← Original Streamlit demo (preserved)
├── models/best.pt    ← Trained YOLOv8 weights
└── samples/          ← Sample images and demo video
```


## Status

- **Phase 1 (model)** and **Phase 2 (software demo)**: done, see metrics below.
- **Phase 3 (ESP32-CAM hardware)**: not yet built — hardware hasn't arrived.
- **PLC/SCADA/OPC integration**: explicitly out of scope. `src/alert.py`'s
  `send_plc_fail_signal()` only logs what it *would* send — there is no real
  integration, and it must never be changed to claim otherwise without
  actually building and testing one.

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cu128   # or the CUDA build matching your GPU
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in `KAGGLE_USERNAME` / `KAGGLE_KEY`
(from kaggle.com → Account → Create New API Token) if you want to re-run the
dataset download.

## Running the demo

Trained weights are already in `models/best.pt`, so you can go straight to:

```
streamlit run src/app.py
```

In the sidebar, pick a frame source:
- **Upload image/video** — upload your own file and see the verdict.
- **Sample image/video** — bundled samples in `samples/` (see `samples/README.md`):
  3 real NEU-DET defect images (should FAIL) and 2 synthetic defect-free
  plates (should PASS), plus a short demo video cycling through both.
- **Image/video file** — a local path (single image, folder of images, or video).
- **Webcam** — your machine's camera.
- **ESP32-CAM (Phase 3)** — not usable until the hardware is flashed and wired up.

## Re-running the pipeline from scratch

```
python scripts/convert_neudet_to_yolo.py   # downloads NEU-DET, converts to YOLO format, splits 70/15/15
python scripts/train.py                     # fine-tunes yolov8n, ~100 epochs
python scripts/evaluate.py                  # evaluates on the held-out test split, writes results.json + models/best.pt
python scripts/make_samples.py              # rebuilds samples/
```

## Measured results (NEU-DET test split, 270 images)

| Class | mAP50 | mAP50-95 |
|---|---|---|
| **Overall** | **0.734** | **0.412** |
| scratches | 0.931 | 0.556 |
| patches | 0.920 | 0.586 |
| inclusion | 0.828 | 0.456 |
| pitted_surface | 0.793 | 0.456 |
| rolled-in_scale | 0.582 | 0.280 |
| crazing | 0.350 | 0.136 |

Full numbers in `results.json`. Crazing is the weakest class — it's a subtle
texture defect and is the hardest class in published NEU-DET work generally.

## Caveats (real, not hedging)

- **Dataset**: NEU-DET is hot-rolled steel strip, not stamped sheet metal,
  brackets, or gaskets — it's a stand-in, not real production data.
- **Camera**: the OV2640 on the ESP32-CAM is low-resolution and sensitive to
  lighting. A fixed mount and even lighting will matter a lot; small defects
  may be missed. Not yet tested, since there's no hardware yet.
- **Metric transfer**: the numbers above are measured on NEU-DET's own test
  split. They will not be claimed to transfer to ESP32-CAM captures without
  separately measuring on real captures from that camera.
- **Samples**: NEU-DET has no defect-free images (every image has an
  annotated defect), so the "clean" samples in `samples/` are synthetic
  brushed-metal textures generated by `scripts/make_samples.py`, not real
  photographed clean steel.

## Repo layout

```
defect-demo/
  data/                 # NEU-DET, gitignored (regenerate with convert_neudet_to_yolo.py)
  models/best.pt         # trained weights
  samples/               # small bundled samples for trying the dashboard
  scripts/                # dataset conversion, training, evaluation, sample generation
  src/                    # sources.py, detector.py, decision.py, alert.py, app.py
  firmware/esp32_cam/     # Phase 3, not yet built
  results.json            # measured evaluation metrics
```
