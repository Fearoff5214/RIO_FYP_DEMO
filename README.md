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

## Added after the first slice
| Feature | Where | Notes |
|---|---|---|
| Live phone camera | `camera.py`, `/api/jobs/from-camera` | Iriun Webcam shows the phone as a laptop webcam; live MJPEG preview, capture, camera recipe changes on quality failure (L2) and on reject-all |
| Operator alert | `quality_alert` node | after the L2 cap an unusable image stops at an operator gate (retake / accept / abort); it never becomes an automatic OK |
| SAM masks | `cv/segmenter.py` | MobileSAM (`models/sam/mobile_sam.pt`, auto-downloaded) outlines each YOLO box; severity uses mask area |
| Unseen-defect detection | `cv/anomaly.py` | PatchCore-style model fitted on defect-free photos (`POST /api/anomaly/fit`); hotspots YOLO does not explain become `unknown_anomaly` and always go to label review |
| MES / QMS / ERP / notify | `integrations.py`, `mock_systems.py` | REST connectors set by `MES_URL` etc. in `.env`; DB outbox with retry and idempotency keys; a down system never fails a signed-off job |
| Retraining (L10) | `learning.py` | label corrections -> YOLO dataset -> fine-tune -> versioned model, promoted only if mAP50 holds on held-out images that contain labelled objects; manual rollback in the Learning tab |
| Recalibration (L12) | `learning.py` | expert choice vs AI rank sets per-rank acceptance rates that adjust shown confidence |

## Not what the PDF says
- SQLite (stdlib) instead of PostgreSQL + pgvector; `db.py` is the only data module to swap.
- The anomaly model is a PatchCore-style implementation on torch/torchvision, not the `anomalib` package: installing it would have added 28 packages including a second OpenCV build to the venv. The interface (`fit`, `score`) is the same, so it can be swapped.
- SAM is MobileSAM by default (40 MB); set `SAM_WEIGHTS` to `sam_b.pt` for full SAM-B.
- MES/QMS/ERP message shapes are generic JSON. Mapping to a specific product is done in `integrations._build`.
- Retraining is a fine-tune on corrected images only. With no replay set it can forget classes, which is why promotion needs a validation set with labelled objects and why `AUTO_RETRAIN` is off by default.
- The flow is fixed. The LLM only writes root-cause candidates; there is no agent choosing its own steps.

## Run
```
pip install -r requirements.txt            # fastapi is the only package not in the project venv yet
ollama pull qwen2.5:7b && ollama pull nomic-embed-text   # optional; works offline without
uvicorn backend.app.main:app --reload      # API on :8000, seeds the KB from data/kb_seed
cd frontend && npm install && npm run dev  # UI on :5173
```
Try part `SM-1001` with an image from `samples/`.

Phone camera: install Iriun Webcam on the phone and laptop, open it on both, then use *Phone camera > Find cameras* in the UI.

Plant systems (optional): `uvicorn backend.mock_systems:app --port 9000`, then set in `.env`
`MES_URL=http://localhost:9000/mes`, `QMS_URL=.../qms`, `ERP_URL=.../erp`, `NOTIFY_URL=.../notify`.

Anomaly model: put 20-50 defect-free photos (same camera and lighting as production) in `data/good/default/`, then use *Fit* in the Learning tab. `scripts/make_good_images.py` makes synthetic ones for a demo only: a model fitted on them will flag real steel photos as anomalous.

## Test
```
pytest
```
Covers each loop at its cap, all three gates, the no-defect fast path and checkpoint resume. Tests run without Ollama.
