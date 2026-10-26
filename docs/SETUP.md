# Setup

For a new machine (Windows 10/11). About 30 minutes plus downloads.

## 1. What you need

| Item | Version used | Needed for |
|---|---|---|
| Python | 3.14 (3.11+ should work) | everything |
| Node.js + npm | 26 / 11 (any current LTS) | building the web UI |
| Git | any | getting the code |
| Ollama | current | root-cause text from a local LLM (optional, see below) |
| NVIDIA GPU | RTX 5060 used | faster detection and SAM (optional, CPU works) |
| Iriun Webcam | current, on phone and laptop | live camera (optional, uploads work without it) |

Disk: about 10 GB (Python packages with CUDA PyTorch, the 7B model, weights).

## 2. Get the code and install Python packages

```powershell
git clone https://github.com/Fearoff5214/RIO_FYP_DEMO.git
cd RIO_FYP_DEMO
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
```

Install PyTorch first, matching your GPU. For NVIDIA (CUDA 12.8 wheels, what the lock file uses):

```powershell
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```

No NVIDIA GPU: `pip install torch torchvision` (CPU build). Then the rest:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.lock.txt` is the exact set the project was developed and tested with. Use it
(`pip install -r requirements.lock.txt`) if a newer package version breaks something.

## 3. Build the web UI

```powershell
cd frontend
npm install
npm run build
cd ..
```

## 4. Language model (optional but recommended)

Without Ollama everything still runs; the root-cause candidates are then read straight from
the knowledge-base text instead of being written by the model, and the report says so.

```powershell
ollama pull qwen2.5:7b          # writes root-cause candidates (4.7 GB)
ollama pull nomic-embed-text    # embeddings for knowledge-base search (0.3 GB)
```

Ollama must be running (the desktop app, or `ollama serve`). The first root-cause step after
starting Ollama takes about a minute while the model loads into memory.

## 5. Configuration

```powershell
copy .env.example .env
```

Defaults work for a first run; do not edit anything yet. Settings are explained in
[DEPLOYMENT.md](DEPLOYMENT.md#configuration-reference). `.env` is ignored by git, so secrets
(such as `INTEGRATION_TOKEN`) stay on the machine.

## 6. Check everything

```powershell
.venv\Scripts\python.exe scripts\check_setup.py
```

Every line should say PASS, except possibly:
- `SAM weights`: WARN is fine; they download on the first job (needs internet, 40 MB).
- `anomaly model`: WARN until you fit one ([USER_GUIDE](USER_GUIDE.md#unseen-defects-the-anomaly-model)).
- `Ollama` / `cameras`: WARN if you skipped those optional parts.

## 7. Run it

```powershell
.\scripts\run.ps1                 # http://localhost:8000
```

Open http://localhost:8000. Sample images are in `samples/`; the sample part is `SM-1001`.
Run one end to end by following the [User Guide](USER_GUIDE.md#your-first-inspection).

Equivalent without the script: `.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000`.

## 8. Phone camera (Iriun Webcam)

1. Install **Iriun Webcam** on the phone (Android/iOS) and on the laptop (iriun.com).
2. Phone and laptop on the same Wi-Fi (or USB cable, per Iriun's instructions). Open the app
   on both; the laptop app should show the phone's picture.
3. In the web UI: *New inspection > Phone camera > Find cameras*. The phone usually appears as
   the highest-numbered camera (the laptop's own webcam is `#0`). Use *Live preview* to check.
4. If a camera number is wrong, set `CAMERA_DEFAULT_DEVICE` in `.env`.

Close other apps that use the camera (Zoom, the Windows Camera app); only one program can
hold it.

## 9. Run the tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

48 tests, about two minutes, no Ollama or camera needed. See [TESTING.md](TESTING.md).

## Developing the UI

```powershell
.\scripts\run.ps1                 # backend on :8000
cd frontend; npm run dev          # UI with hot reload on http://localhost:5173
```
