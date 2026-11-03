# Novaliseo Demo Script (about 10 minutes)

Speaker script for presenting the AI sheet-metal inspection demo. Lines in
*italics* are spoken; **bold** lines are actions on screen.

## Before you go on (do this 15 minutes early)

1. Terminal 1 (backend):
   ```powershell
   .\.venv\Scripts\Activate.ps1
   $env:NOVALISEO_MODE = "mock"
   py -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
   ```
2. Terminal 2 (frontend): `cd frontend; npm run dev`
3. Load the knowledge base once: `py scripts\load_kb.py`
4. Check `http://localhost:8000/healthz` returns OK and `http://localhost:5173` loads.
5. Optional AI root cause: `GEMINI_API_KEY` in `.env`, then `py scripts\check_gemini.py`.
   The free tier has a small daily quota. Without it the offline template is used
   and the UI says so. Decide beforehand which you will show.
6. Browser: full screen, zoom 100-110%, log in once as `operator` to confirm it works.
7. Backup: `docs\demo\novaliseo_demo.mp4` open in another window in case anything fails.

Logins (all password = username): `operator`, `engineer`, `expert`, `approver`.

---

## 1. The problem (1 min)  - slide or Dashboard

*"Inspecting sheet-metal parts by hand is slow and inconsistent. A bracket can
fail on a 0.1 mm hole error or a hairline crack, and when it fails, the question
is why. Novaliseo does three things: it finds defects and measures dimensions
from a camera image, it retrieves knowledge to propose root causes, and it keeps
a human in the loop to review and approve every decision."*

**Show:** Dashboard (`/`). Point at job counts and charts.

## 2. The part (30 s)

*"Our test part is bracket MS-4505-001: SPCC steel, 2 mm thick, 120 by 80 mm base,
50 mm flange, six 12 mm holes at plus or minus 0.05 mm, and a 90 degree bend at
plus or minus 0.5 degrees."*

**Show:** `docs\drawings\` PNG or the 3D render from `docs\models\bracket\`.

## 3. Live defect marking (3 min)  - the headline moment

**Action:** Log in as `operator`, open **New Job**, press **Start simulated camera**,
tick **Mark defects live**.

*"The browser is playing images as a camera feed. About once a second a frame goes
to our API, and defects are drawn directly on the feed."*

Walk the 6-second frames in this order and say one line for each:

| Frame | Say |
|---|---|
| `clean_bracket_good` | *"Good part. Nothing flagged. A system that cries wolf is useless, so this matters."* |
| `defect_bracket_surface` | *"Dent in orange, scratch in yellow, and the flange bend measured at 93 degrees against a 90 degree spec."* |
| `defect_bracket_crack` | *"Cracks at the hole edges, in red."* |
| `defect_bracket_size` | *"Short length and an oversize, shifted hole. The label shows the measurement: hole dia 12.75 against nominal 12.00 plus or minus 0.05."* |
| steel texture (e.g. `defect_scratches`) | *"A different material. This goes to a trained YOLO model instead."* |

*"Two detectors work together. A classical measurement pipeline handles the
bracket with sub-pixel edge and circle fitting. A YOLO model trained on steel
surface defects handles textures. The system picks the right one per frame."*

**Optional (if a webcam is on hand):** press **Use live camera** and show it
working. Warn first: *"The bracket inspector is calibrated for this part only; an
arbitrary scene will be unreliable."*

**Action:** pause on a defect frame and press **Capture frame**.

## 4. AI root cause analysis (2 min)

**Action:** with the defects marked, press **Analyse root cause (AI)**.

*"Now the question is why. The system retrieves evidence from a knowledge base of
process documents and sends only that evidence to the language model. It returns
three ranked causes, each with the reason, a corrective action, a prevention step
and citations. Any citation that is not in the evidence is dropped, and the
confidence score is computed by our code, not by the model."*

**Show:** the cause, reason, solution and prevention, then the Word/PDF download.

**If the AI is unavailable:** *"This panel states when the model was not used. We
fall back to an offline template instead of failing, and it is labelled as such."*

## 5. Human review gates (2 min)

*"The AI never makes the final decision. There are three gates."*

**Action:** open the job from **Jobs** and walk through, switching users:

1. `engineer` - **Gate 1** (`/jobs/:id/gate1`): confirms or corrects dimensions and defects.
2. `expert` - **Gate 2** (`/jobs/:id/gate2`): reviews the ranked causes with reason
   and solution; can edit or choose another cause. *"Expert edits are recorded
   and feed back into learning."*
3. `approver` - **Gate 3** (`/jobs/:id/gate3`): approves the report.

**Show:** **Reports** (`/jobs/:id/reports`): the inspection report and the
Root Cause Analysis document. *"Everything is traceable: model version,
expert edits, audit log."*

## 6. Honest numbers (1 min)

*"Here is what we measured, and the limits."*

- YOLO on held-out NEU-DET (270 images): precision 65.6%, recall 73.0%, mAP50 73.4%.
  Strong on scratches (93%) and patches (92%), weak on crazing (35%).
- Bracket inspector on a randomised synthetic benchmark (320 frames): precision
  77.1%, recall 90.0%, 55 ms per frame. Hole diameter F1 97%.
- Known weaknesses: a 20% false-alarm rate on good frames, and scratch/dent false
  positives.
- *"These are synthetic frames, not real production parts. Next step is
  validating on real photographs."*

## 7. Close (30 s)

*"To summarise: live defect and dimension marking, evidence-grounded root cause
analysis, human approval at every decision point, and a full audit trail. Next:
real-part validation, a calibrated camera rig, and more of the knowledge base.
Thank you. Questions?"*

---

## Likely questions

| Question | Answer |
|---|---|
| Is the camera real? | Simulated from `samples/` by default; a real camera also works (Use live camera). |
| Does the LLM decide the cause? | No. It drafts from retrieved evidence; the expert decides; confidence is computed by code. |
| What if the LLM is down or out of quota? | Falls back to an offline template, clearly labelled. |
| Why two detectors? | YOLO was trained on steel textures and raises false alarms on the bracket; the measurement pipeline gives mm-level values. |
| How accurate is it? | See section 6. Synthetic benchmark only; not validated on real parts. |
| Can it handle other parts? | The bracket inspector is calibrated to MS-4505-001 (4.6 px/mm at 640 px). Other parts need new calibration and rules. |

## If something breaks

- **Blank page / 500 on login:** `py -m pip install "bcrypt<5"`, restart the API.
- **No highlights on the feed:** check Terminal 1 for errors on `/api/v1/parts/live-detect`.
- **AI panel says model not used:** quota or key; continue with the offline output and say so.
- **Anything else:** switch to `docs\demo\novaliseo_demo.mp4` and narrate over it.
