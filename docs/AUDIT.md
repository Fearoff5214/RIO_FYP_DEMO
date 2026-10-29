# NOVALISEO — Audit Document

## Repo Status: Greenfield (existing demo preserved)

The existing repo contains a working Streamlit + YOLOv8 defect detection demo (`src/`) 
with trained weights at `models/best.pt`. This has been preserved and extended.

## Spec Coverage Map

| Section | Item | Status |
|---------|------|--------|
| S8 Stage 1 | Trigger, Context & Image Capture | MISSING → M2 |
| S8 Stage 2 | Dimensional Check + Human Gate 1 | MISSING → M3 |
| S8 Stage 3 | Defect Detection | PARTIAL (Streamlit demo only) → M4 |
| S8 Stage 4 | Root-Cause Knowledge Retrieval | MISSING → M5 |
| S8 Stage 5 | AI Prediction & Recommendation | MISSING → M6 |
| S8 Stage 6 | Human Gate 2 Expert | MISSING → M7 |
| S8 Stage 7 | Report & Human Gate 3 | MISSING → M8 |
| S8 Stage 8 | Output, Actions & Learning | MISSING → M9 |
| S9 L1–L12 | Loop & Decision Logic | MISSING → M1–M9 |
| S10 | Human Gate Mechanics | MISSING → M1 |
| S11 | Knowledge Base Ingestion | MISSING → M5 |
| S12 | API (FastAPI) | MISSING → M0–M9 |
| S13 | Frontend (React) | MISSING → M10 |
| S14 | Configuration | MISSING → M0 |
| S15 | Cross-cutting (Audit, RBAC, Security) | MISSING → M0 |
| S16 | Testing Strategy | MISSING → M1–M12 |
| S17 M0 | Foundation scaffold | IN PROGRESS |
| S17 M1 | Orchestrator skeleton | MISSING → M1 |
| S17 M2–M12 | All milestones | MISSING |

## Milestone Completion

- [x] M0 — Foundation (DB models, config, auth, audit, object storage adapter)
- [x] M1 — Orchestrator skeleton (LangGraph graph, all nodes stubbed, routing, loop counters)
- [x] M2 — Stage 1 (camera adapters, quality scoring, preprocess)
- [x] M3 — Stage 2 + Gate 1 (DXF/PDF parsing, measurement, overlay, Gate 1 API)
- [x] M4 — Stage 3 + label review (YOLO/SAM/Anomalib adapters, fusion, MockDetector, label gate)
- [x] M5 — Knowledge base + Stage 4 (ingestion pipeline, hybrid RAG, rerank, evidence pack)
- [x] M6 — Stage 5 (LLM providers, fake provider, scoring, calibration, validators)
- [x] M7 — Gate 2 / Stage 6 (expert gate, final RCA, feedback capture)
- [x] M8 — Stage 7 + Gate 3 (PDF/Excel/Word report, e-signature, completeness check)
- [x] M9 — Stage 8 + learning (final output, dispatch adapters, action tracker, learning hub)
- [x] M10 — Frontend (React+Vite+Tailwind, all 10 pages, role-aware nav, dashboard)
- [ ] M11 — Hardening (monitoring/drift, SLA, security review — PARTIAL: stubs in place)
- [ ] M12 — Release (make demo golden run — blocked by langgraph interrupt in test env)

## Definition of Done Items

1. [ ] Every stage (1–8) and offline KB plane implemented
2. [ ] All loops L1–L12 enforced with fallbacks
3. [ ] All four human gates via API and UI with RBAC
4. [ ] Fast path (no defect) works
5. [ ] Dimensional check against DXF/PDF with overlay
6. [ ] Defect detection returns Dent/Scratch/Crack/Deformation with severity
7. [ ] RAG retrieval hybrid + graph + rerank with citations
8. [ ] Top-3 root causes with calibrated confidence
9. [ ] Reports in PDF, Excel, Word with e-signature
10. [ ] Final output dispatches to adapters; actions tracked
11. [ ] Learning hub functional
12. [ ] Audit trail complete, monitoring active
13. [ ] `make test` passes with coverage ≥80%
14. [ ] `make demo` reproduces infographic scenario (mock mode)
15. [ ] Documentation complete
16. [ ] Blockers documented in BLOCKERS.md
