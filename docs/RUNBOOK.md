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
py -m uvicorn backend.app.main:app --reload --port 8000

# 4. Load sample knowledge base (in another terminal)
py scripts/load_kb.py

# 5. Open browser
# API: http://localhost:8000/docs
# Frontend: cd frontend && npm install && npm run dev → http://localhost:5173
```

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
