# NOVALISEO — Architecture

## Logical Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                     NOVALISEO PLATFORM                               │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   FastAPI (backend/app/main.py)              │   │
│  │  /api/v1: jobs · gates · kb · reports · actions · parts     │   │
│  │           dashboard · audit · auth                          │   │
│  └──────────────────────────┬──────────────────────────────────┘   │
│                              │                                        │
│  ┌───────────────────────────▼──────────────────────────────────┐  │
│  │              LangGraph Workflow (workflow/graph.py)           │  │
│  │                                                               │  │
│  │  START → S1(Capture) → S2(Dimensional) → GATE1              │  │
│  │       → S3(Defects) → [LABEL_REVIEW] → S4(Retrieval)        │  │
│  │       → S5(Prediction) → GATE2 → S7(Report) → GATE3         │  │
│  │       → S8(Output+Learning) → END                           │  │
│  │  Fast path: S3(no defect) → S7(OK) → GATE3 → S8 → END       │  │
│  │  Loops: L1-L9 with max counts and fallbacks                  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────────────┐  │
│  │  CV Module   │ │  RAG Module  │ │  LLM Module                │  │
│  │  camera/     │ │  ingest/     │ │  providers/: fake/          │  │
│  │  drawing/    │ │  retrieve.py │ │  anthropic/openai           │  │
│  │  detectors/  │ │  rerank.py   │ │  prompts/root_cause.md      │  │
│  │  measure.py  │ │  embed.py    │ │  validators.py              │  │
│  └──────────────┘ └──────────────┘ └────────────────────────────┘  │
│                                                                      │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────────────┐  │
│  │  Reports     │ │  Learning    │ │  DB (SQLAlchemy + SQLite/   │  │
│  │  compose.py  │ │  hub.py      │ │  PostgreSQL)                │  │
│  │  esign.py    │ │  L10/L11/L12 │ │  models.py + audit.py       │  │
│  └──────────────┘ └──────────────┘ └────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘

                    ┌───────────────────────┐
                    │   React Frontend       │
                    │   Vite + TypeScript    │
                    │   Tailwind CSS         │
                    │   Pages: 10 screens    │
                    └───────────────────────┘
```

## Data Flow (spec Section 4.3)

```
Trigger (POST /api/v1/jobs)
  → S1: read_part_id → load_part_master → create_job → set_camera_recipe
        → capture_images → preprocess_store
  → S2: parse_drawing → detect_features → measure_mm → compare_drawing
        → set_dim_status → [GATE1 interrupt] → lock_result → save_dim
  → S3: dispatch_detectors (YOLO+SAM+Anomalib) → fuse → classify_measure
        → [LABEL_REVIEW interrupt if conf<0.85] → save_defects
        [no defect → fast_path_report]
  → S4: build_query → apply_filters → embed_query → graph_expand
        → hybrid_retrieve (dense+BM25+RRF) → rerank → assemble_evidence
  → S5: assemble_context → llm_reason → score_conf → rank_top3
        → calibrate → format_top3 → save_ranked
  → S6: [GATE2 interrupt] → finalize_actions → save_decision
        → record_feedback → mark_rca_final
  → S7: compose_report → draft_report → render_files (PDF/Excel/Word)
        → [GATE3 interrupt] → esign_archive → notify_systems
  → S8: final_output → dispatch_results → track_actions
        → close_case → learning_hub (L10+L11+L12)
  → END

Offline: POST /api/v1/kb/documents → parse → chunk → tag → embed → index
```

## Loop Register

| Loop | Trigger | Max | Fallback |
|------|---------|-----|----------|
| L1 | Part not found | 3 | ON_HOLD |
| L2 | Image quality fail | 3 | Operator alert |
| L3 | Engineer rejects Gate 1 | 2 | manual_measurement flag |
| L4 | Evidence insufficient | 2 | low_evidence flag, continue |
| L5 | LLM output invalid | 2 | low_confidence flag, continue |
| L6 | Expert rejects all causes | — | Expert's choice (reinspect/manual) |
| L7 | Report incomplete | 3 | Escalate to admin |
| L8 | Approver rejects | — | Unlimited redraft |
| L9 | Action not effective | — | Reopen + escalate |
| L10 | Learning: labels | — | Retrain CV on new samples |
| L11 | Learning: RCA → KB | — | Add finalized case to KB |
| L12 | Learning: calibration | — | Refit isotonic regression |

## Key Design Decisions

- See `docs/DECISIONS.md` for full list
- Mock-first: all external deps have deterministic fakes (BLK-001 to BLK-007)
- SQLite in dev, PostgreSQL in production
- LangGraph `interrupt()` for all 4 human gates
- Identity calibration until ≥50 expert samples

## Repository Structure

```
RIO_FYP/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry
│   │   ├── api/                 # routers: jobs, gates, kb, reports, actions, parts, dashboard, audit, auth
│   │   ├── core/                # config, logging, security
│   │   ├── db/                  # models.py, session.py, audit.py
│   │   ├── workflow/            # state.py, graph.py, routing.py, gates.py
│   │   │   └── nodes/           # s1_capture → s8_output_learning
│   │   ├── cv/                  # camera/, drawing/, detectors/, features.py, measure.py, preprocess.py
│   │   ├── rag/                 # ingest/, retrieve.py, rerank.py, embed.py
│   │   ├── llm/                 # factory.py, providers/, validators.py, prompts/
│   │   ├── scoring/             # confidence.py, calibration.py
│   │   ├── reports/             # compose.py, esign.py
│   │   ├── notifications/       # dispatcher.py
│   │   └── learning/            # hub.py
│   └── tests/
│       ├── unit/                # test_routing, test_detection, test_scoring, test_measurement, test_retrieval
│       └── integration/         # test_api
├── frontend/
│   └── src/
│       ├── App.tsx              # Router + nav
│       ├── api.ts               # Typed API client
│       └── pages/               # Dashboard, Jobs, JobDetail, Gate1-3, LabelReview, Reports, KB, Actions, NewJob
├── config/default.yaml          # All thresholds and settings
├── docs/                        # AUDIT, ARCHITECTURE, DECISIONS, BLOCKERS
└── scripts/                     # seed_demo.py, load_kb.py, run_demo.py
```
