# Novaliseo AI Quality Inspection

Agentic sheet-metal inspection and root-cause platform (vertical-slice MVP of the 8-stage flow).

| Stage | Where | Notes |
|---|---|---|
| 1 Trigger, context, capture | `graph/nodes.py` `load_context`, `capture` | image upload (no live camera yet); part master in `data/parts/`; blur/glare/exposure check |
| 2 Dimensional + Gate 1 | `dimensional.py`, `gate1` | DXF via ezdxf, OpenCV measurement, engineer confirm |
| 3 Defect detection | `cv/detector.py`, `label_review` | YOLOv8 (`models/best.pt`, NEU-DET classes); SAM/Anomalib not built; low-confidence gate |
| 4 Knowledge retrieval | `rag.py` | dense + keyword hybrid with rerank, vectors in SQLite |
| 5 RCA | `rca.py` | Ollama LLM, validated and cited; evidence-only fallback without a model |
| 6 Gate 2 | `gate2` | expert selects / edits / rejects all |
| 7 Report + Gate 3 | `report.py`, `gate3` | PDF, Excel, Word; approver sign-off |
| 8 Output, learning | `finalize`, `db.py` | case added to KB, corrective actions, feedback stored |

Loops L1-L8 are explicit graph edges with caps in `backend/app/config.py` (`MAX_RETRIES`). L9 is `db.close_action`. L10/L12 feedback is recorded in the `feedback` table; automated retraining and recalibration are not built.

## Differences from the PDF
- SQLite (stdlib) instead of PostgreSQL + pgvector; `db.py` is the only data module to swap.
- No MES/QMS/ERP calls: Stage 8 dispatch is written to the audit log as simulated.
- SAM, Anomalib, graph expansion, cross-encoder rerank and live camera are not built.

## Run
```
pip install -r requirements.txt            # fastapi is the only package not in the project venv yet
ollama pull qwen2.5:7b && ollama pull nomic-embed-text   # optional; works offline without
uvicorn backend.app.main:app --reload      # API on :8000, seeds the KB from data/kb_seed
cd frontend && npm install && npm run dev  # UI on :5173
```
Try part `SM-1001` with an image from `samples/`.

## Test
```
pytest
```
Covers each loop at its cap, all three gates, the no-defect fast path and checkpoint resume. Tests run without Ollama.
