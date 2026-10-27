# Architecture

Reference for developers. Source of truth for the flow: `Novaliseo_AI_Quality_Inspection_Flow_Editable_BW.pdf`.

## Principle

The workflow is a **fixed graph** (LangGraph). Nothing decides its own next step. The LLM is
called in exactly one place (writing root-cause candidates in Stage 5). Humans decide at the
gates. Every retry loop has a hard cap.

## Stage to code map

| Stage | Graph node(s) | Code |
|---|---|---|
| 1 Trigger, context, capture | `load_context`, `capture`, `quality_alert` | `graph/nodes.py`, `camera.py`, `cv/quality.py` |
| 2 Dimensional + Gate 1 | `dimensional`, `gate1` | `dimensional.py` (ezdxf + OpenCV) |
| 3 Defect detection | `detect`, `label_review` | `cv/detector.py` (YOLO), `cv/segmenter.py` (SAM), `cv/anomaly.py` |
| 4 Knowledge retrieval | `retrieve` | `rag.py` |
| 5 Root cause | `rca` | `rca.py`, `llm.py` |
| 6 Gate 2 | `gate2` | `graph/nodes.py` |
| 7 Report + Gate 3 | `report`, `gate3` | `report.py` |
| 8 Output, learning | `finalize` | `integrations.py`, `learning.py`, `rag.ingest_text` |

Wiring: `graph/workflow.py`. State schema: `graph/state.py`. Settings: `config.py`.

## Graph

```
load_context -> capture -> dimensional -> gate1 -> detect -> label_review
                                                                 |-- no defects ----------------------------> report
                                                                 `-- defects --> retrieve -> rca -> gate2 --> report
report -> gate3 -> finalize -> END

Loops back:  load_context -> load_context (L1)      capture -> capture (L2) -> quality_alert -> capture | dimensional | END
             gate1 -> dimensional (L3)              retrieve -> retrieve (L4)    rca -> rca (L5)
             gate2 -> capture (L6)                  report -> report (L7)        gate3 -> report (L8) | END when exhausted
```

Each node returns a `_route` string that its conditional edge reads. Gates call `interrupt()`;
the API resumes with `Command(resume=answer)`. On resume the node function runs again from
the top, so work before `interrupt()` must be repeatable and side effects (audit rows,
feedback) come after it. Checkpoints are in SQLite (`runs/data/checkpoints.db`).

## Loops

| Loop | Trigger | Cap (`config.MAX_RETRIES`) | Then |
|---|---|---|---|
| L1 | part not found | 3 | job on hold |
| L2 | image quality fails | 3 | operator alert gate |
| L3 | engineer rejects dimensions | 2 | flag `manual_measurement_required` |
| L4 | too few evidence hits | 2 (relax filters, then lower threshold) | flag `low_evidence` |
| L5 | LLM output invalid / uncited | 2 | evidence-only causes, flag `low_confidence` |
| L6 | expert rejects all causes | 1 | manual RCA |
| L7 | report incomplete | 1 | |
| L8 | approver rejects | 5 | job on hold |
| L9 | corrective action ineffective | n/a | `db.close_action` marks it escalated |
| L10 | label corrections | | `learning.retrain` |
| L11 | final RCA | | re-indexed into KB in `finalize` |
| L12 | expert choice vs AI rank | | `learning.recalibrate` |

## Data (SQLite, `db.py`)

`jobs`, `audit_log`, `kb_chunks` (text, tags, embedding JSON), `feedback` (kind = label_correction,
expert_choice, rca_rejected_all, dimension_rejected), `actions`, `outbox` (unique per job+system).
`db.py` is the only module that touches SQL; replace it to move to PostgreSQL.
Retrieval is a Python scan over chunks (dense cosine + keyword overlap + rerank boosts); for
thousands of chunks, replace `rag.search` with a pgvector query.

## Detection details

- YOLO weights: `learning.active_weights()` (registry in `models/versions/registry.json`, default baseline).
- SAM prompts with YOLO boxes. On any failure it sets `segmenter.sam_error` and detections continue without masks.
- Anomaly: ResNet-18 layer2+3 patch features, memory bank from good images, nearest-neighbour distance, leave-one-image-out threshold
  (`cv/anomaly.py`). Hotspots whose centre lies in no YOLO box become `unknown_anomaly` with
  confidence capped below `LABEL_REVIEW_CONF` so a human always sees them.

## HTTP API (all under `/api`)

| Method + path | Purpose |
|---|---|
| `GET /health` | app, Ollama and KB status |
| `POST /jobs` (multipart: `part_number`, `files[]`) | start from uploads |
| `POST /jobs/from-camera` `{part_number, device, frames, recipe}` | start from camera |
| `GET /jobs`, `GET /jobs/{id}` | list; detail = job row + graph state + pending gate + audit |
| `POST /jobs/{id}/gate` (answer JSON) | resolve the pending gate (409 if none) |
| `GET /jobs/{id}/report/{pdf\|xlsx\|docx}` | download |
| `POST /watch/start` `{part_number, device, live_boxes}`, `POST /watch/stop`, `GET /watch`, `GET /watch/stream` | watch mode: auto-inspect when a part is shown (`watcher.py`) |
| `GET /camera/devices`, `GET /camera/stream?device=`, `POST /camera/release` | camera |
| `POST /kb/upload` | add a document to the knowledge base |
| `GET /actions`, `POST /actions/{id}/close` `{effective, evidence}` | corrective actions (L9) |
| `GET /learning`, `POST /learning/retrain`, `/learning/activate`, `/learning/recalibrate` | learning |
| `POST /anomaly/fit` `{part_number}` | fit the anomaly model from `data/good/<part>/` |
| `GET /outbox`, `POST /outbox/retry` | integrations |

Gate answers (what the UI sends):

```
part_number   {part_number}
operator      {action: retake|accept|abort, image_paths?}
engineer      {confirm: bool, scale_override?, reviewer?, note?}
label_review  {defects: [...corrected list...], reviewer?}
expert        {action: select|edit|reject_all, rank?, text?, reason?, reviewer?}
approver      {approved: bool, approver?, comments?}
```

Interactive docs while running: http://localhost:8000/docs.

## Extending

- **New defect class from the detector**: retrain; class names come from the weights. KB paragraphs
  are tagged by `rag.DEFECT_TERMS`; add the new name there.
- **New output system**: add to `integrations._urls()` / `_build()` and `config.py`.
- **New gate**: write a node that calls `_gate(state, name, payload)`, add it and its edges in
  `workflow.build`, add a case in `frontend/src/App.jsx` `Gate`, add a test using `run_to_gate`.
- **Different LLM**: `llm.chat_json` and `llm.embed` are the only two functions to change.
