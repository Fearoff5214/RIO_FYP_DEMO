# User guide

For the people who run inspections and review results. Setup is in [SETUP.md](SETUP.md).

## What the system does

You give it a photo (or a live phone picture) of a part and the part number. It checks the
image quality, measures the part against its drawing, finds defects, looks up similar past
cases and documents, proposes the three most likely root causes, and produces a signed-off
report. **People make every decision that matters** at the review points ("gates") below;
the software only prepares the evidence and waits.

```
Capture -> Measure -> [Gate 1: engineer] -> Detect -> [label review if unsure]
        -> Find evidence -> Propose causes -> [Gate 2: expert] -> Report -> [Gate 3: approver]
        -> Send to MES/QMS/ERP, save the case for future jobs
```

No defect found: it skips the cause steps and goes straight to an OK report (still needs Gate 3).

## Your first inspection

1. Open http://localhost:8000.
2. Left panel, **Upload** tab. Part number `SM-1001`. Choose `samples/defect_scratches.jpg`. **Start**.
3. **Gate 1 (engineer)** appears with a table of measured vs drawing sizes. For the sample,
   some rows are red: the sample is a steel texture, not a cut plate, so the numbers are
   meaningless. Click **Confirm**.
4. Wait. The first job loads the models (SAM, YOLO) and takes up to a minute. A dashed
   *Working...* box shows it is busy; the page refreshes itself.
5. **Label review** appears if any detection is under 85% confident. Check the class,
   then **Confirm** (or **No defect** for a false alarm).
6. **Gate 2 (expert)** shows three ranked causes with confidence, effect and precautions.
   Tick one, optionally add a reason, **Finalize**.
7. **Gate 3 (approver)**: open the PDF/XLSX/DOCX links to read the report, then
   **Approve and sign** (or **Reject, redraft** with a comment).
8. Status becomes *completed*. The *Reports* box has the three files.

## Starting a job from the phone camera

1. Iriun Webcam open on phone and laptop ([SETUP.md section 8](SETUP.md#8-phone-camera-iriun-webcam)).
2. **Phone camera** tab > **Find cameras** > pick the phone > **Live preview** to frame the part.
3. Light the part evenly, avoid glare, keep it in focus.
4. **Capture and inspect** takes one frame and starts the job.

If the picture is too dark, bright or blurry the system changes the camera settings and takes
up to 3 new pictures by itself. If that fails you get the **operator alert**: fix the lighting
or focus, then **Retake** (for a camera job this takes new pictures; for an upload it re-checks
the same photo, so start a new job with a better photo instead). **Accept as is** is recorded in the report; **Abort job** puts the
job on hold. An unusable image never becomes an automatic OK.

## Watch mode: inspect without pressing anything

*New inspection > Phone camera > Watch mode > Start watching.* Fix the phone on a stand
pointing at a plain surface, then:

1. Keep the view empty for about a second ("Learning the empty view").
2. Place a part in view and let go. The banner says "Hold still..." with a progress bar; after
   about 1.5 seconds of no movement the sharpest frame is taken and a normal inspection starts.
3. The job appears in the *Started* list under the video; click it to open the review gates.
4. Remove the part. When the view is empty again the next part can be shown.

Live red boxes on the video are a quick YOLO preview only (a few per second). The recorded
result comes from the full pipeline (quality check, SAM, anomaly model). The part number is fixed
for the whole watching session: stop and restart to change it. Watching holds the camera, so
*Live preview* and *Capture and inspect* are unavailable until you stop.

Tips: fixed mount, steady light, plain background, no shadows moving. A part larger than half the
view, or a background that changes, will cause missed or false triggers. Tune with
`WATCH_HOLD_SECONDS`, `WATCH_PRESENCE_MIN`, `WATCH_DIFF_THR` ([DEPLOYMENT](DEPLOYMENT.md#configuration-reference)).

## The review points

| Gate | Who | What to check | Your options |
|---|---|---|---|
| Operator alert | operator | image still bad after 3 automatic retries | Retake / Accept as is / Abort |
| Gate 1 | engineer | measured vs nominal sizes, red = out of tolerance | Confirm, or Reject and re-measure (type a corrected px/mm scale first if the scale is wrong; up to 2 re-measures, then it is flagged *manual measurement required*) |
| Label review | reviewer | defect classes under 85% confidence, or anything the anomaly model found that YOLO could not name (`unknown_anomaly`) | Confirm (optionally type the right class for all rows), or No defect. Corrections are saved as training data |
| Gate 2 | quality expert | which cause is right | pick one (+ reason), or edit the text, or **Reject all** (see below) |
| Gate 3 | approver | the report itself | Approve and sign, or Reject with comments (report is redrafted; the 6th rejection puts the job on hold) |

**Reject all** at Gate 2 sends the job back to capture once (a new picture at default camera
settings, or the same images for uploads). Rejecting all a second time lets you type the
cause yourself and the report is marked *manual RCA*.

If the part number is not found, you are asked to retype it (3 tries, then the job is on hold).

## Reading the results

- **Confidence %** on a cause mixes how well the evidence matched, how sure the detector was,
  and (after enough decisions) how often experts actually picked that rank. It is a guide, not
  a probability.
- **Flags** (red text on the job) tell you what was not ideal: `low_evidence` (few matching
  documents), `llm_unavailable` (causes copied from documents because Ollama was off),
  `low_confidence`, `manual_measurement_required`, `manual_rca`, `accepted_poor_image`,
  `camera_error`, `approval_loop_exhausted`. They are also printed in the report.
- **Audit trail** (expandable on every job) lists every stage and gate answer with times. It is
  the record of who decided what.
- Report files are also on disk in `runs/data/reports/<job id>/`.

## Learning and integrations page

Left panel button **Learning and integrations**.

- **Detector model**: the YOLO version in use, how many label corrections are waiting, and
  past retrains. **Retrain now** fine-tunes on corrections (needs 20 by default). A new version
  goes live only if it is not worse on held-out images that contain labelled defects.
  **Activate** on any row switches back (rollback). Retraining takes minutes and uses the GPU.
- **Confidence recalibration**: how often experts picked rank 1/2/3. Used automatically once
  there are 10 decisions.
- **Anomaly model**: see next section.
- **Outbox**: delivery status of messages to MES / QMS / ERP / notification. `failed` rows
  retry every minute; **Retry failed** forces it. A down plant system never blocks an inspection.

## Unseen defects: the anomaly model

YOLO only knows its 6 trained classes. The anomaly model learns what a *good* part looks like
and flags anything else as `unknown_anomaly` (always sent to label review).

1. Photograph 20-50 known-good parts with the same camera, lighting and distance as production.
2. Put the images in `data/good/default/` (or `data/good/<part number>/` for one specific part).
3. Learning page > **Fit from data/good/default** (takes about 15 seconds).

Do not use `scripts/make_good_images.py` output for real work; it makes fake plates for demos,
and a model fitted on it flags real photos as anomalous.

## Adding a part

Create `data/parts/<PART-NUMBER>.json`:

```json
{
  "name": "Bracket 3 mm",
  "material": "mild steel",
  "process": "laser cutting",
  "drawing_rev": "C",
  "dxf": "BRACKET-3.dxf",
  "px_per_mm": 4.2,
  "tolerance_mm": 0.3
}
```

and put the DXF drawing beside it. Notes:
- `px_per_mm` is how many image pixels are one millimetre **for your camera setup**; measure a
  known object (a ruler) and calibrate. Wrong scale = wrong measurements.
- The drawing parser reads `LINE`, `LWPOLYLINE` and `CIRCLE` entities (outline and round holes).
  The part should be photographed flat, light on a dark background.
- Without `dxf`, the dimensional step is skipped (shown as NOT_CHECKED).
- No restart needed.

## Adding knowledge

The cause suggestions come from documents in the knowledge base. Add `.md`, `.txt`, `.docx`
or `.xlsx` files to `data/kb_seed/` before first start, or POST a file to `/api/kb/upload`
at any time. Write paragraphs the way the seed file does, one defect per paragraph with
`Cause:`, `Effect:` and `Precautions:` lines; that is what makes them easy to find and quote.
Finished jobs add their own approved cause back into the knowledge base automatically.

## Problems

| Symptom | Likely cause and fix |
|---|---|
| Page blank / "Loading" forever | backend not running, or UI not built: `npm run build` in `frontend/` |
| "Working..." for minutes | first run loading models, or Ollama loading the 7B model; check the terminal running the app |
| Cause cards say "(no LLM available)" in the rationale, flag `llm_unavailable` | Ollama not running. Start it; later jobs are fine |
| *Camera not available* | Iriun not open on both devices, or another program holds the camera; close it, press Find cameras |
| Camera picture black | Iriun not streaming, or wrong camera number |
| Gate 1 always red | wrong `px_per_mm`, part not on a dark background, or drawing does not match the photographed side |
| Every photo gets `unknown_anomaly` | anomaly model was fitted on photos unlike production; refit with real good parts |
| Outbox rows `failed` | the URL in `.env` is wrong or the system is down; fix, then **Retry failed** |
| Job stuck *on_hold* | part not found 3 times, approval rejected 6 times, or operator abort; start a new job |

More operational detail: [DEPLOYMENT.md](DEPLOYMENT.md).
