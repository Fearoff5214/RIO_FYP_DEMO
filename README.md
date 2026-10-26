# Novaliseo AI Quality Inspection

Sheet-metal inspection and root-cause platform built from the Novaliseo flow
(`Novaliseo_AI_Quality_Inspection_Flow_Editable_BW.pdf`): capture a part photo (upload or live
phone camera), measure it against its drawing, detect defects (YOLO + SAM masks + anomaly model),
retrieve similar cases from a knowledge base, propose three root causes with a local LLM, and
produce a signed-off PDF/Excel/Word report. People decide at three review gates; every retry
loop is capped; results are pushed to MES / QMS / ERP; corrections feed retraining and
confidence recalibration.

The workflow is a fixed LangGraph graph, not a free-running agent. The LLM only writes the
root-cause candidates.

## Documents

| Read this | If you want to |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | install it on a new PC and run it |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | run inspections, use the review gates, add parts and knowledge |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | configure, run as a service, connect MES/QMS/ERP, back up, understand the limits and security |
| [docs/TESTING.md](docs/TESTING.md) | run the automated tests, do the manual acceptance checklist, know the weak spots |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | change the code: stage map, loops, data, HTTP API |

## Quick start (Windows)

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend; npm install; npm run build; cd ..
ollama pull qwen2.5:7b; ollama pull nomic-embed-text      # optional
copy .env.example .env
.\scripts\run.ps1                                         # http://localhost:8000
```

Details and the Iriun phone-camera setup are in [docs/SETUP.md](docs/SETUP.md). Try part
`SM-1001` with an image from `samples/`. Run `pytest -q` to check the install (48 tests).

## Status and limits (short version)

Working and tested: all 8 stages, 3 human gates plus label review and operator alert, loops
L1-L8, live camera path, SAM, anomaly model, MES/QMS/ERP connectors with retry outbox, retraining
and recalibration, web UI. The full list of known weak spots is in
[docs/TESTING.md](docs/TESTING.md#3-what-a-tester-should-expect-to-find-broken-or-weak).
The main ones: the detector is trained on a public steel-surface dataset, not your parts; there
is **no login** (keep it on localhost or a trusted network); SQLite, single machine; tested on one
Windows laptop and not yet with a phone streaming through Iriun.

Not the same as the PDF: SQLite instead of PostgreSQL/pgvector; a PatchCore-style anomaly model
instead of the `anomalib` package; MobileSAM by default; generic MES/QMS/ERP message formats.
