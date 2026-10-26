"""One function per stage of the flow. Loops L1-L8 are explicit: a node bumps its counter in
`retries` and its router sends control back, until the cap in config.MAX_RETRIES is reached.

Human gates use langgraph `interrupt()`. On resume the node re-runs from its top, so every
gate node does only deterministic work before the interrupt and side effects after it.
"""
import functools
import json
import shutil
import time
from pathlib import Path

import cv2
from langgraph.types import interrupt

from .. import camera, config, db, dimensional, integrations, learning, rag, rca, report
from ..cv import detector, quality

CAP = config.MAX_RETRIES


def stage(name):
    """Audit a node's completion and mirror its status onto the job row."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(state):
            update = fn(state) or {}
            db.audit(state["job_id"], name, "done", {k: v for k, v in update.items()
                                                      if k in ("retries", "flags", "status", "_route")})
            db.update_job(state["job_id"], status=update.get("status") or name)
            return update
        return wrapper
    return deco


def _gate(state, name: str, payload: dict):
    db.update_job(state["job_id"], status=f"awaiting_{name}")
    answer = interrupt({"gate": name, **payload})
    db.audit(state["job_id"], f"gate_{name}", "resolved", answer if isinstance(answer, dict) else {"answer": answer})
    return answer


def _retries(state) -> dict:
    return {**{k: 0 for k in CAP}, **(state.get("retries") or {})}


def load_part(part_number: str) -> dict | None:
    p = config.PARTS_DIR / f"{part_number}.json"
    if not p.exists():
        return None
    part = json.loads(p.read_text())
    dxf = part.get("dxf")
    if dxf and not Path(dxf).is_absolute():
        part["dxf"] = str(config.PARTS_DIR / dxf)
    return {"part_number": part_number, **part}


# --- Stage 1 -----------------------------------------------------------------------------

@stage("load_context")
def load_context(state):
    r = _retries(state)
    part = load_part(state["part_number"])
    if part:
        return {"part": part, "retries": r, "_route": "ok"}
    r["L1"] += 1
    if r["L1"] > CAP["L1"]:
        return {"retries": r, "status": "on_hold", "flags": [*state.get("flags", []), "part_not_found"],
                "_route": "hold"}
    answer = _gate(state, "part_number", {"message": f"Part {state['part_number']!r} not found. Rescan or type the part number.",
                                          "attempt": r["L1"]})
    db.update_job(state["job_id"], part_number=answer["part_number"])
    return {"part_number": answer["part_number"], "retries": r, "_route": "retry"}


@stage("capture")
def capture(state):
    r = _retries(state)
    src = state.get("source") or {}
    live = src.get("type") == "camera"
    extra, flags = {}, list(state.get("flags", []))
    sources = state.get("working_paths") or state["image_paths"]
    if live and state.get("recapture"):  # expert rejected all causes: back to the default camera recipe
        try:
            sources = _grab(state, camera.DEFAULT_RECIPE)
            extra.update(recapture=False, recipe=dict(camera.DEFAULT_RECIPE), image_paths=sources)
        except camera.CameraError as e:
            flags.append(f"camera_error:{e}")
            extra["recapture"] = False
    reports, adjusted, all_ok, problems = [], [], True, set()
    for p in sources:
        img = cv2.imread(p)
        if img is None:
            raise ValueError(f"cannot read image {p}")
        q = quality.assess(img)
        reports.append({"path": p, **q})
        if not q["ok"]:
            all_ok = False
            problems.update(q["problems"])
            out = Path(p).with_name(f"{Path(p).stem}_adj{r['L2'] + 1}.png")
            cv2.imwrite(str(out), quality.auto_adjust(img, q["problems"]))
            adjusted.append(str(out))
        else:
            adjusted.append(p)
    if all_ok:
        return {**extra, "quality": reports, "working_paths": sources, "retries": r, "flags": flags, "_route": "ok"}
    if r["L2"] < CAP["L2"]:
        r["L2"] += 1
        if live:  # L2 for real: change the camera recipe and take new frames
            recipe = camera.adjust_recipe(state.get("recipe") or {}, sorted(problems))
            try:
                return {**extra, "quality": reports, "working_paths": _grab(state, recipe), "recipe": recipe,
                        "retries": r, "flags": flags, "_route": "retry"}
            except camera.CameraError as e:
                flags.append(f"camera_error:{e}")
        return {**extra, "quality": reports, "working_paths": adjusted, "retries": r, "flags": flags, "_route": "retry"}
    return {**extra, "quality": reports, "working_paths": sources, "retries": r, "_route": "alert",
            "flags": [*flags, f"image_quality_unresolved:{','.join(sorted(problems))}"]}


@stage("quality_alert")
def quality_alert(state):
    """Retries exhausted: an unusable image must never turn into an OK verdict by default."""
    flags = [f for f in state.get("flags", []) if not f.startswith("image_quality_unresolved")]
    answer = _gate(state, "operator", {"message": "Image quality could not be fixed automatically.",
                                       "quality": state.get("quality", []), "flags": state.get("flags", [])})
    action = answer.get("action", "abort")
    if action == "abort":
        return {"status": "on_hold", "flags": [*state.get("flags", []), "aborted_by_operator"], "_route": "hold"}
    if action == "retake":
        r = _retries(state)
        r["L2"] = 0
        update = {"retries": r, "flags": flags, "_route": "retry"}
        if answer.get("image_paths"):  # operator supplied replacement photos
            update.update(image_paths=answer["image_paths"], working_paths=None)
        elif (state.get("source") or {}).get("type") == "camera":
            update.update(recapture=True, working_paths=None)
        return update
    return {"flags": [*state.get("flags", []), "accepted_poor_image"], "_route": "ok"}  # operator accepts it


def _grab(state, recipe: dict) -> list[str]:
    return camera.capture(state["source"]["device"], Path(state["image_paths"][0]).parent,
                          len(state["image_paths"]), recipe)


# --- Stage 2 -----------------------------------------------------------------------------

@stage("dimensional")
def dimensional_check(state):
    part = state["part"]
    if not part.get("dxf") or not Path(part["dxf"]).exists():
        return {"dimensional": {"status": "NOT_CHECKED", "reason": "no drawing for part"}}
    scale = state.get("scale_override") or part.get("px_per_mm", 1.0)
    nominal = dimensional.parse_drawing(Path(part["dxf"]))
    measured = dimensional.measure_image(cv2.imread(state["working_paths"][0]), scale)
    result = dimensional.compare(nominal, measured, part.get("tolerance_mm", 0.5))
    return {"dimensional": {**result, "nominal": nominal, "measured": measured, "px_per_mm": scale}}


@stage("gate1_engineer")
def gate1(state):
    dim = state["dimensional"]
    r = _retries(state)
    if dim["status"] == "NOT_CHECKED":
        return {"_route": "ok"}
    answer = _gate(state, "engineer", {"dimensional": dim, "attempt": r["L3"]})
    if answer.get("confirm"):
        return {"_route": "ok"}
    db.add_feedback(state["job_id"], "dimension_rejected", {"dimensional": dim, "note": answer.get("note")})
    if r["L3"] < CAP["L3"]:
        r["L3"] += 1
        return {"retries": r, "scale_override": answer.get("scale_override"), "_route": "retry"}
    return {"retries": r, "flags": [*state.get("flags", []), "manual_measurement_required"], "_route": "ok"}


# --- Stage 3 -----------------------------------------------------------------------------

@stage("detect")
def detect(state):
    dets = []
    for p in state["working_paths"]:
        img = cv2.imread(p)
        for d in detector.fuse(detector.detect(Path(p), state["part_number"])):
            dets.append({**d, "image": p, "severity": detector.severity(d, img.shape)})
    return {"defects": dets}


@stage("label_review")
def label_review(state):
    dets = state.get("defects", [])
    if any(d["conf"] < config.LABEL_REVIEW_CONF for d in dets):
        answer = _gate(state, "label_review", {"defects": dets, "threshold": config.LABEL_REVIEW_CONF})
        corrected = answer.get("defects", dets)
        if corrected != dets:  # L10: corrections feed the next training set
            db.add_feedback(state["job_id"], "label_correction", {"before": dets, "after": corrected,
                                                                    "reviewer": answer.get("reviewer")})
        dets = corrected
    return {"defects": dets, "_route": "retrieve" if dets else "report"}


# --- Stage 4 -----------------------------------------------------------------------------

@stage("retrieve")
def retrieve(state):
    r = _retries(state)
    part, dets = state["part"], state["defects"]
    types = sorted({d["cls"] for d in dets})
    query = " ".join([*types, part.get("material", ""), part.get("process", ""), "root cause corrective preventive"])
    level = r["L4"]  # 0 = strict, 1 = drop tag filter, 2 = also halve the similarity threshold
    hits = rag.search(query, defect_types=types, material=part.get("material"),
                      min_sim=config.RETRIEVE_MIN_SIM / (2 if level >= 2 else 1),
                      top_k=config.RETRIEVE_TOP_K + 3 * level, filter_tags=level == 0)
    if len(hits) >= config.RETRIEVE_MIN_HITS:
        return {"evidence": hits, "low_evidence": False, "_route": "ok"}
    if level < CAP["L4"]:
        r["L4"] += 1
        return {"retries": r, "evidence": hits, "_route": "retry"}
    return {"evidence": hits, "low_evidence": True, "_route": "ok",
            "flags": [*state.get("flags", []), "low_evidence"]}


# --- Stage 5 -----------------------------------------------------------------------------

@stage("rca")
def run_rca(state):
    from .. import llm
    r = _retries(state)
    ev, flags = state["evidence"], list(state.get("flags", []))
    causes = None
    if ev and llm.available():
        causes = rca.generate(state["defects"], state["dimensional"].get("status", "?"), state["part"], ev)
        if causes is None and r["L5"] < CAP["L5"]:
            r["L5"] += 1
            return {"retries": r, "_route": "retry"}
    if causes is None:
        causes = rca.from_evidence(ev)
        if ev:
            flags.append("low_confidence" if llm.available() else "llm_unavailable")
    ranked = rca.calibrate(causes, ev, state["defects"], state.get("low_evidence", False))
    return {"rca": ranked, "retries": r, "flags": flags, "_route": "ok"}


# --- Stage 6 -----------------------------------------------------------------------------

@stage("gate2_expert")
def gate2(state):
    r = _retries(state)
    cands = state["rca"]
    answer = _gate(state, "expert", {"candidates": cands, "defects": state["defects"], "attempt": r["L6"]})
    action = answer.get("action")
    reviewer = answer.get("reviewer", "unknown")
    if action == "reject_all":
        db.add_feedback(state["job_id"], "rca_rejected_all", {"candidates": cands, "reason": answer.get("reason")})
        if r["L6"] < CAP["L6"]:
            r["L6"] += 1
            for k in ("L3", "L4", "L5"):
                r[k] = 0
            return {"retries": r, "working_paths": None, "recapture": True, "flags": state.get("flags", []),
                    "_route": "reinspect"}
        sel = {"cause": answer.get("text") or "Manual RCA required", "effect": "", "precautions": [],
               "reviewer": reviewer, "reason": answer.get("reason", ""), "manual": True}
        return {"retries": r, "selected_cause": sel, "flags": [*state.get("flags", []), "manual_rca"], "_route": "ok"}
    if action == "edit":
        base = next((c for c in cands if c["rank"] == answer.get("rank")), {})
        sel = {**base, "cause": answer.get("text") or base.get("cause", ""), "edited": True}
    else:
        sel = next((c for c in cands if c["rank"] == answer.get("rank")), None)
        if sel is None:
            raise ValueError(f"no candidate with rank {answer.get('rank')}")
    sel = {**sel, "reviewer": reviewer, "reason": answer.get("reason", "")}
    db.add_feedback(state["job_id"], "expert_choice", {"chosen_rank": sel.get("rank"), "edited": sel.get("edited", False),
                                                      "confidences": [c["confidence"] for c in cands]})
    return {"selected_cause": sel, "_route": "ok"}


# --- Stage 7 -----------------------------------------------------------------------------

@stage("report")
def make_report(state):
    r = _retries(state)
    data = report.compose(state)
    gaps = report.missing(data)
    if gaps and r["L7"] < CAP["L7"]:
        r["L7"] += 1
        # orchestrator fills what it can from state before redrafting
        return {"retries": r, "part": state.get("part") or {"part_number": state["part_number"]},
                "dimensional": state.get("dimensional") or {"status": "NOT_CHECKED"}, "_route": "retry"}
    paths = report.render({**data, "revision": state.get("report_revision", 1)})
    return {"report_data": data, "report_paths": paths, "retries": r, "_route": "ok"}


@stage("gate3_approver")
def gate3(state):
    r = _retries(state)
    answer = _gate(state, "approver", {"report_paths": state["report_paths"], "result": state["report_data"]["result"]})
    if answer.get("approved"):
        return {"approver": answer.get("approver", "unknown"), "_route": "approved"}
    comments = [*state.get("approver_comments", []), answer.get("comments", "")]
    r["L8"] += 1
    if r["L8"] > CAP["L8"]:
        return {"retries": r, "approver_comments": comments, "status": "on_hold",
                "flags": [*state.get("flags", []), "approval_loop_exhausted"], "_route": "hold"}
    return {"retries": r, "approver_comments": comments,
            "report_revision": state.get("report_revision", 1) + 1, "_route": "redraft"}


# --- Stage 8 -----------------------------------------------------------------------------

@stage("finalize")
def finalize(state):
    job_id, dets, sel = state["job_id"], state["defects"], state.get("selected_cause")
    if dets and sel:
        text = (f"Case {job_id}. Defects: {', '.join(sorted({d['cls'] for d in dets}))}. "
                f"Material: {state['part'].get('material', '')}\nCause: {sel['cause']}\n"
                f"Effect: {sel.get('effect', '')}\nPrecautions: {'; '.join(sel.get('precautions', []))}")
        rag.ingest_text(f"case-{job_id}", text, {"case": True})  # L11: finalized RCA becomes knowledge
        for p in sel.get("precautions", [])[:3]:
            db.add_action(job_id, p)
    db.update_job(job_id, status="completed", result={"report_paths": state["report_paths"],
                                                      "result": state["report_data"]["result"],
                                                      "flags": state.get("flags", [])})
    try:  # delivery problems are queued for retry and must not fail a signed-off job
        integrations.dispatch(job_id, {
            "part_number": state["part_number"], "result": state["report_data"]["result"],
            "completed_at": time.time(), "defects": dets, "dimensional": state.get("dimensional", {}),
            "selected_cause": sel, "actions": [a["description"] for a in db.list_actions(job_id)],
            "approver": state.get("approver"), "flags": state.get("flags", []),
            "report_paths": state["report_paths"]})
    except Exception as e:
        db.audit(job_id, "dispatch", "error", {"error": f"{type(e).__name__}: {e}"})
    learning.recalibrate()  # L12
    learning.maybe_auto_retrain()  # L10, only when AUTO_RETRAIN=1 and enough new labels
    return {"status": "completed"}


def copy_upload(src: str, dest_dir: Path) -> str:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / Path(src).name
    if Path(src).resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return str(dest)
