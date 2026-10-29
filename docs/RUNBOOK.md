# NOVALISEO Runbook

## Quick Start (Mock Mode — no GPU, no API keys)

```powershell
# 1. Install Python deps
cd "c:\Users\rcdt0\OneDrive\Documents\RIO FYP\RIO_FYP"
py -m pip install -r backend/requirements.txt

# 2. Set environment
copy .env.example .env
# Edit .env: NOVALISEO_MODE=mock

# 3. Start API server
$env:NOVALISEO_MODE="mock"
py -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000

# 4. Load sample knowledge base (in another terminal)
py scripts/load_kb.py

# 5. Open browser
# API: http://localhost:8000/docs
# Frontend: cd frontend && npm install && npm run dev → http://localhost:5173
```

## Live Iriun Capture and Part Verification

1. Install and start Iriun Webcam on the phone and computer, connect them to the
   same network, and confirm that **Iriun Webcam** appears as a camera in Windows.
2. Start the API and frontend as above, open **New Job**, enter the registered
   part number, and allow the browser to use the camera. The capture screen
   automatically selects Iriun when the browser reports it; otherwise select it
   from the camera list.
3. Before the first inspection of a part, an administrator must upload its
   matching raster CAD export and reference photograph in the reference section
   on the New Job screen. Export a clear 2D view of the drawing as PNG or JPG.
   The pair is stored with that part number under
   `data/part_references/<part-number>/`; the existing part drawing URI is kept.
4. Capture manually, or enable automatic capture to take an image after the
   camera view is steady and detailed. Compare the captured image to the CAD
   reference. Only a **Match** enables **Continue to Inspection**; mismatch and
   inconclusive results require recapture or manual review. A passing capture
   is sent to the existing inspection workflow rather than replaced by the mock
   camera.

The comparison uses contrast normalization, ORB visual features, RANSAC
geometric alignment, and aligned edge overlap. It is an initial verification
aid, not a calibrated metrology result: camera angle, lighting, focus, and CAD
view should be controlled and the threshold validated against real parts.
Adjust `part_verification.score_threshold` in `config/default.yaml` (default
`0.55`) after testing. Each part's CAD and photograph must be the correct
matching reference pair; the API selects them by the entered part number.

Automatic capture checks that the frame is stable and has image detail; it does
not identify the part or guarantee its physical placement. Keep the whole part
inside the on-screen guide. Camera capture requires browser camera permission
and a secure context (localhost is supported).

## Running Tests

```powershell
$env:NOVALISEO_MODE="mock"
$env:DATABASE_URL="sqlite+aiosqlite:///./novaliseo_test.db"
py -m pytest backend/tests/ -v
```

## Running the Demo (Golden Scenario)

```powershell
$env:NOVALISEO_MODE="mock"
py scripts/run_demo.py
```
This reproduces the infographic scenario: MS-4505-001 bracket, Dent+Scratch+Crack+Deformation,
Top-3 causes (Improper Bending Force 92%, Material Inconsistency 78%, Tool Wear 71%),
all three human gates, PDF+Excel+Word reports generated.

## Switching to Real Mode

1. Edit `config/default.yaml`:
   - `prediction.llm.provider: anthropic` (or `openai`)
   - `detection.models.yolo: path/to/weights.pt`
   - `camera.adapter: folder` (or `upload`)

2. Set env vars in `.env`:
   ```
   NOVALISEO_MODE=real
   ANTHROPIC_API_KEY=sk-...
   DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/novaliseo
   ```

3. Run migrations:
   ```powershell
   cd backend && py -m alembic upgrade head
   ```

## Default Users (seeded on startup)

| Username | Password | Role |
|----------|----------|------|
| operator | operator | operator |
| engineer | engineer | engineer |
| expert | expert | expert |
| approver | approver | approver |
| admin | admin | admin |

**Change all passwords before any non-dev deployment.**

## Environment Variables

See `.env.example` for full list. Critical vars:
- `NOVALISEO_MODE` — `mock` or `real`
- `DATABASE_URL` — SQLite (dev) or PostgreSQL (prod)
- `JWT_SECRET_KEY` — must be changed in production
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` — for real LLM mode
