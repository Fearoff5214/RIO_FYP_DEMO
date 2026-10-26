# Testing and handover

## 1. Automated tests

```powershell
.venv\Scripts\python.exe -m pytest -q          # all, ~1 minute
.venv\Scripts\python.exe -m pytest -q -k l3    # one loop
```

They need no Ollama, no camera, no internet (except that SAM weights must already be in
`models/sam/`; one test skips itself if not). Each test uses a temporary database.

What is covered, by file (`backend/tests/`):

| File | Covers |
|---|---|
| `test_workflow.py` | full graph through all gates; fast path (no defect); loops L1, L2, L3, L4, L5, L6, L7, L8; label review (L10 signal); operator alert (abort / retake / accept); resume after restart |
| `test_stage3_extras.py` | anomaly model fit/score/localisation; unseen defect -> `unknown_anomaly` below review threshold; no duplicate when YOLO already explains it; SAM failure degrades safely; real SAM mask |
| `test_camera_integrations_learning.py` | camera recipe changes and recapture (fake camera); camera failure fallback; MES/QMS/ERP/notify message shapes; outage -> outbox -> retry with no duplicates; job survives connector outage; recalibration; dataset export; retrain promote/reject/unvalidated; rollback |
| `test_units.py` | image quality, detection fusion, dimensional measurement, root-cause validation, KB chunking/search, re-embedding on embedder change, corrective-action loop L9 |

**Not covered by automated tests** (needs a human, see section 2): the web UI, a real phone
camera, real Ollama output quality, real MES/QMS/ERP endpoints, a real GPU retrain run on
meaningful data (one 2-epoch smoke run was done by hand), and every FastAPI route except by
manual use.

## 2. Manual acceptance checklist

Start the app (`.\scripts\run.ps1 -Mock`) and open http://localhost:8000. Tick as you go.
"Sample" = `samples/defect_scratches.jpg`, part `SM-1001`.

### Core flow
- [ ] **Happy path.** Upload the sample, confirm Gate 1, confirm label review, pick cause #1 at
      Gate 2, approve at Gate 3. Expect: status *completed*; PDF, XLSX, DOCX open and show the
      defect, the chosen cause, reviewer and reason.
- [ ] **Resume after restart.** Start a job, stop the app at Gate 2 (Ctrl+C), start again,
      open the job. Expect: still waiting at Gate 2, answer works.
- [ ] **No-defect fast path.** Upload `samples/clean_synthetic_1.jpg`. Expect: no cause step; goes to
      report and Gate 3 only; report says OK. (It may trip the image-quality alert because the
      synthetic plate is very smooth: choose Accept as is.)
- [ ] **Audit trail.** Expand it on a finished job: every stage and gate answer present, times increasing.

### Loops and limits
- [ ] **L1.** Part number `NOPE`. Expect a "Part not found" box 3 times, then status *on_hold*.
- [ ] **L2 + operator alert.** Make a flat grey image:
      `.venv\Scripts\python.exe -c "import cv2,numpy as n; cv2.imwrite('flat.png', n.full((200,200,3),128,'uint8'))"`
      and upload it. Expect the operator alert (blur problem). Abort -> *on_hold*; Retake on an upload re-checks
      the same photo (so it alerts again); Accept as is -> continues with flag `accepted_poor_image`.
- [ ] **L3.** At Gate 1 press *Reject and re-measure* three times (it shows Gate 1 again after each of
      the first two). Expect the third rejection to let the job continue with flag `manual_measurement_required`.
- [ ] **L6.** At Gate 2 press *Reject all*. Expect the job to run again; reject all a second time,
      type a cause in the text box, Expect flag `manual_rca` and your text in the report.
- [ ] **L8.** At Gate 3 reject with a comment. Expect a new report revision (`report_rev2`) containing the comment.
- [ ] **Label correction -> training data.** At label review, type a class and Confirm. Learning
      page > *labels waiting* goes up by 1.
- [ ] **L4/L5/L7** are only reachable with an empty knowledge base, a misbehaving LLM, or a broken
      report; they are covered by automated tests only.

### Camera
- [ ] Find cameras lists the phone; Live preview shows the picture; Capture and inspect starts a job.
- [ ] Cover the lens (dark picture): expect automatic recaptures, then the operator alert.
- [ ] Unplug/close Iriun mid-job: expect flag `camera_error` and no crash.

### Integrations
- [ ] With `-Mock` and the four URLs set in `.env`: finish a job; Outbox shows 4 `sent`;
      `http://localhost:9000/received` shows 4 messages (`mes` disposition `hold` for NG).
- [ ] `POST http://localhost:9000/fail?on=true`, finish a job: job still *completed*, Outbox
      rows `failed`. `POST .../fail?on=false`, press *Retry failed*: all `sent`, no duplicates at the receiver.

### Learning
- [ ] Recalibration: after 10+ Gate 2 decisions the page shows the calibration as *active*.
- [ ] Retrain (try once on purpose): `RETRAIN_MIN_LABELS=2` in `.env`, make two label corrections,
      press *Retrain now*. Expect a new row with before/after mAP and a status. Press *Activate*
      on `baseline` to roll back, then run another job to confirm detection still works.
- [ ] Anomaly: fit on 3+ good photos, then upload a photo with an obvious mark YOLO misses.
      Expect an `unknown_anomaly` row at label review.

### Acceptance with real data (do this before relying on it)
- [ ] Calibrate `px_per_mm` with a ruler; measure 3 known parts; compare with calipers.
- [ ] Run 20+ real known-good and 20+ known-bad parts; note false alarms and misses; adjust
      `LABEL_REVIEW_CONF`, `BLUR_MIN`, lighting; fit the anomaly model on real good parts.
- [ ] Review the knowledge base answers with a quality engineer: are the three causes sensible
      for your defects? Add your RCA documents (`/api/kb/upload`) and repeat.

## 3. What a tester should expect to find broken or weak

Honest list from development, so you do not report these as surprises:

1. **The detector is trained on NEU-DET** (hot-rolled steel surface texture, 200x200 px
   photos, 6 classes). It has not seen your parts, your camera or your lighting. Expect
   missed and mislabelled defects on real sheet-metal parts. Bring labelled photos.
2. **Sample dimensional results are meaningless** (a texture photo, not a plate); real value
   needs a real plate on a dark background and a calibrated scale.
3. **Confidence numbers are heuristic**, not statistical, until enough expert decisions accumulate.
4. **Root-cause quality depends on the knowledge base**; the shipped 7 paragraphs are generic.
   The 7B local model is adequate for structured output, not for deep metallurgy.
5. **Slow first job** (model loading), and every gate answer blocks until the next gate.
6. **No login, no roles**: see [DEPLOYMENT.md](DEPLOYMENT.md#security-read-before-putting-this-on-a-network).
7. **Retraining with few corrections can overfit**; see the retraining notes.
8. **Verified only on one machine** (Windows 11, RTX 5060 laptop GPU, Python 3.14). The phone
   camera path was exercised on the laptop's cameras, not with a phone streaming Iriun.

## 4. Reporting a bug

Include: what you did, what you expected, the **job id**, the job's *Audit trail* text, the last
~50 lines of the terminal running the app, and `python scripts\check_setup.py` output. Job data
is under `runs/data/` (zip it if the issue depends on the images).
