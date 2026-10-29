# NOVALISEO — Architecture Decisions

## DEC-001: Preserve existing Streamlit demo
**Decision:** Keep `src/` Streamlit app intact. Novaliseo backend lives in `backend/`.  
**Rationale:** Working code must not be deleted. The Streamlit demo serves as a Phase-2 deliverable.

## DEC-002: Mock-first, real-later pattern
**Decision:** All external dependencies (camera, LLM, GPU detectors, MES/QMS/ERP, e-mail) have a mock adapter 
controlled by `NOVALISEO_MODE=mock|real`. CI always runs in mock mode.  
**Rationale:** No GPU, no API keys, no hardware in CI; spec requires CI to pass on any machine.

## DEC-003: Conservative confidence thresholds
**Decision:** Default label-review threshold 0.85, similarity threshold 0.55 per Section 14.  
**Rationale:** Most conservative option; configurable via `config/default.yaml`.

## DEC-004: SQLite in development mode
**Decision:** When `DATABASE_URL` is not set, use SQLite at `./novaliseo_dev.db` for local development 
without Docker.  
**Rationale:** Allows contributors to run without a full Postgres stack.

## DEC-005: LangGraph interrupt() for all human gates
**Decision:** All four human gates (Gate1, LabelReview, Gate2, Gate3) use LangGraph `interrupt()`.  
**Rationale:** Spec requirement; ensures graph is resumable after restarts.

## DEC-006: Calibration identity mapping until 50 samples
**Decision:** Confidence calibration uses identity mapping (confidence_cal = confidence_raw) until 
`≥50` expert-accepted pairs exist, per spec Section 8 Stage 5.  
**Rationale:** Isotonic regression requires sufficient data; conservative fallback avoids overfit.

## DEC-007: OpenAPI-first API documentation
**Decision:** FastAPI auto-generates OpenAPI at `/docs`; `docs/API.md` is a summary pointing to `/docs`.  
**Rationale:** Single source of truth; avoids drift between code and docs.
