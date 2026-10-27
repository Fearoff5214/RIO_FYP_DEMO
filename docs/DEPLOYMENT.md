# Deployment and operations

For whoever installs and runs this on a shop-floor or test machine.

## What it is, physically

One Python process (FastAPI, port 8000) that also serves the web UI. It uses:

| Piece | Where | Notes |
|---|---|---|
| Database | `runs/data/novaliseo.db` (SQLite) | jobs, audit trail, knowledge base, feedback, actions, outbox |
| Workflow state | `runs/data/checkpoints.db` | lets a job wait days at a gate and survive restarts |
| Uploads, reports | `runs/data/uploads/<job>/`, `runs/data/reports/<job>/` | images, PDF/XLSX/DOCX |
| Models | `models/best.pt` (YOLO), `models/sam/`, `models/anomaly/`, `models/versions/` | |
| Ollama | separate process, port 11434 | optional |
| Camera | Iriun Webcam virtual camera on the same PC | Windows DirectShow |

Everything runs on **one machine**. SQLite and the camera handle make this a single-instance
design; do not run two copies against the same `runs/data`.

## Security: read before putting this on a network

The API has **no login and no access control**. Anyone who can reach port 8000 can create jobs,
approve gates (including Gate 3 sign-off), retrain and roll back models, and download reports.
The "reviewer/approver" names in the audit trail are whatever the client sends; they are not
verified.

- Default start (`scripts/run.ps1`) listens on `127.0.0.1` only: safe for single-PC use.
- `-Lan` listens on all interfaces. Use only on a trusted, isolated network, and add Windows
  Firewall rules limiting port 8000 to known PCs.
- For real multi-user use, put it behind a reverse proxy that does authentication (e.g. nginx or
  Caddy with SSO / basic auth) and add per-user identity to the gate calls. This is not built.
- `.env` holds `INTEGRATION_TOKEN`; it is git-ignored. Never commit it.

## Starting and stopping

Manual: `.\scripts\run.ps1` (runs the preflight, then the server in the foreground; Ctrl+C stops).

As a Windows service that starts at boot (example with [NSSM](https://nssm.cc)):

```powershell
nssm install Novaliseo "F:\path\to\project\.venv\Scripts\python.exe" "-m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"
nssm set Novaliseo AppDirectory "F:\path\to\project"
nssm set Novaliseo AppStdout "F:\path\to\project\runs\service.log"
nssm set Novaliseo AppStderr "F:\path\to\project\runs\service.log"
nssm start Novaliseo
```

The Iriun desktop app must be running in the logged-in session for the camera to exist, so
for live-camera use prefer a Task Scheduler "at log on" task over a pre-login service.

Ollama: install the desktop app (starts at login) or run it as a service.

## Configuration reference

All optional, in `.env` (see `.env.example`). Retry limits (L1-L8) are in `backend/app/config.py`
(`MAX_RETRIES`) and need a restart.

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `none` disables the LLM; causes then come straight from KB text |
| `LLM_MODEL` | `qwen2.5:7b` | any Ollama chat model that follows JSON instructions |
| `EMBED_MODEL` | `nomic-embed-text` | changing it re-embeds the knowledge base at next start |
| `OLLAMA_URL` | `http://localhost:11434` | |
| `YOLO_WEIGHTS` | `models/best.pt` | baseline detector; promoted retrained versions are tracked in `models/versions/registry.json` |
| `CONF_THRESHOLD` | `0.25` | YOLO minimum confidence |
| `LABEL_REVIEW_CONF` | `0.85` | below this a detection goes to human label review |
| `SAM_ENABLED` / `SAM_WEIGHTS` | `1` / `models/sam/mobile_sam.pt` | `sam_b.pt` for full SAM-B (375 MB) |
| `ANOMALY_ENABLED` | `1` | no effect until a model is fitted |
| `BLUR_MIN`, `GLARE_MAX` | `20`, `0.15` | image-quality limits; tune per camera |
| `CAMERA_DEFAULT_DEVICE`, `CAMERA_WIDTH`, `CAMERA_HEIGHT` | `1`, `1280`, `720` | |
| `WATCH_HOLD_SECONDS`, `WATCH_PRESENCE_MIN`, `WATCH_DIFF_THR` | `1.5`, `0.04`, `25` | watch mode: stillness time, minimum covered fraction of the view, pixel-change threshold |
| `MES_URL`, `QMS_URL`, `ERP_URL`, `NOTIFY_URL` | empty = off | see below |
| `INTEGRATION_TOKEN` | empty | sent as `Authorization: Bearer ...` |
| `INTEGRATION_ATTEMPTS` | `4` | attempts per message per round |
| `AUTO_RETRAIN` | `0` | `1` = retrain in background when `RETRAIN_MIN_LABELS` (20) corrections exist. Leave off until the retrain procedure below has been tried by hand |
| `RECAL_MIN_SAMPLES` | `10` | expert decisions before confidence recalibration applies |
| `DATA_DIR`, `PARTS_DIR`, `KB_SEED_DIR` | `runs/data`, `data/parts`, `data/kb_seed` | move data to another drive here |

## Connecting MES / QMS / ERP

Set the URL(s) in `.env` and restart. At the end of each signed-off job the system `POST`s JSON
to each configured URL with headers `Idempotency-Key: <job>:<system>` and (if set)
`Authorization: Bearer <INTEGRATION_TOKEN>`. Success = any 2xx. Failed sends are queued and
retried every minute and from the Outbox page. The receiver should de-duplicate on the key.

Messages (fields not shown are in the code, `backend/app/integrations.py`):

```
mes    {job_id, part_number, result: "OK"|"NG", completed_at, disposition: "release"|"hold", defect_classes[]}
qms    {job_id, part_number, result, completed_at, defects[], dimensional{}, root_cause{}, actions[], approved_by, flags[], report_files{}}
erp    {job_id, part_number, result, completed_at, quarantine: bool, scrap_review: bool}
notify {job_id, part_number, result, completed_at, text}
```

These are generic shapes. A real MES/QMS/ERP will want its own format: change `_build()` in
`integrations.py` (one branch per system) and, if needed, `_post()` for its authentication.
To test without real systems: `.\scripts\run.ps1 -Mock` starts a receiver on `:9000` and
`GET http://localhost:9000/received` lists what arrived; `POST .../fail?on=true` simulates an outage.

## Backup and restore

Stop the app, copy `runs/data/` (and `models/versions/` if you have retrained). That is the
whole state. Restore by copying it back. Do not restore only one of `novaliseo.db` and
`checkpoints.db`: jobs would show up without their workflow state.

## Upgrading

```powershell
git pull
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend; npm install; npm run build; cd ..
.venv\Scripts\python.exe -m pytest -q
```
then restart. The database schema creates missing tables on start; existing data is kept.

## Retraining procedure (do this by hand the first time)

1. Collect corrections: operators confirm or fix classes at the label-review gate. Each fix is saved.
2. Learning page shows *labels waiting*. At 20 (or lower with `force`) press **Retrain now**.
3. It builds a dataset from the corrected images (about 20% held out), measures the current model
   on the held-out part, fine-tunes, measures again, and records both numbers.
4. Status `promoted` = live now. `rejected` = worse, not used. `unvalidated` = no held-out image
   contained a labelled defect, so nothing could be measured; check by hand, then **Activate**.
5. Wrong? **Activate** an older version (always `baseline` available).

Limits you should know: the fine-tune only sees corrected images (no replay of the original
training data, which is not in this repository), so a model can get worse at classes it saw
nothing of; this is why promotion requires a held-out check, and why `AUTO_RETRAIN` is off by
default. Plan to retrain from a full dataset offline when you have one.

## Known limits

- Single machine, single instance. SQLite. About a handful of concurrent users.
- A gate answer (and starting a job) is processed inside the web request, so the call returns
  only when the next gate is reached: up to a minute or more when SAM or the LLM must load.
  The UI polls and shows *Working...*; do not click twice.
- Detector classes are the 6 NEU-DET steel-surface defects (crazing, inclusion, patches, pitted
  surface, rolled-in scale, scratches), not dent/crack/deformation. For other defects use the
  anomaly model and label corrections, or train a new model on your own data.
- Dimensional check measures the outer rectangle and round holes against the DXF using one
  `px_per_mm` scale. No lens undistortion, no perspective correction, no GD&T.
- Windows only for the camera path (DirectShow). The rest is portable.
- The knowledge base ships with 7 paragraphs of general steel-defect text. Real value needs
  your plant's RCA documents.
- Not independently load- or security-tested.
