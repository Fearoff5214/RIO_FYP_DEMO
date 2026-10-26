"""Continuous learning (loops L10-L12).

L10  Label corrections from the Stage 3 review gate -> YOLO dataset -> fine-tune -> versioned
     model, promoted only if it is not worse than the active one on the same held-out images.
L12  Expert choices vs AI rank -> per-rank acceptance rates -> confidence recalibration used by
     rca.calibrate. L11 (finalized RCA re-indexed into the KB) lives in graph/nodes.finalize.

Nothing here is a free-running agent: each function is triggered by an API call or, when
AUTO_RETRAIN=1, by a finished job, and all steps are fixed.
"""
import hashlib
import json
import shutil
import threading
import time
from pathlib import Path

from . import config, db

_registry_lock = threading.RLock()
_train_lock = threading.Lock()
_state = {"running": False, "last_error": None, "last_result": None}


# --- model registry ----------------------------------------------------------------------

def _registry_path() -> Path:
    return config.MODEL_VERSIONS_DIR / "registry.json"


def registry() -> dict:
    with _registry_lock:
        p = _registry_path()
        if p.exists():
            return json.loads(p.read_text())
    return {"active": "baseline", "versions": {"baseline": {"path": str(config.YOLO_WEIGHTS), "status": "baseline"}},
            "labels_used": []}


def _save(reg: dict) -> None:
    with _registry_lock:
        config.MODEL_VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
        _registry_path().write_text(json.dumps(reg, indent=2))


def active_weights() -> Path:
    reg = registry()
    return Path(reg["versions"][reg["active"]]["path"])


def set_active(version: str) -> None:
    """Promote or roll back. Drops cached detector weights so the next job uses them."""
    from .cv import detector
    reg = registry()
    if version not in reg["versions"]:
        raise KeyError(f"unknown model version {version!r}")
    reg["active"] = version
    _save(reg)
    detector.reload_model()


# --- L10: labels -> dataset -> retrain ----------------------------------------------------

def correction_rows() -> list[dict]:
    """Corrections not yet used by an earlier retrain: [{id, image, after:[defects]}]."""
    used = set(registry().get("labels_used", []))
    rows = []
    for fb in db.get_feedback("label_correction"):
        p = fb["payload"]
        if fb["id"] in used or p["after"] == p["before"]:
            continue
        image = next((d["image"] for d in p["after"] + p["before"] if d.get("image")), None)
        if image and Path(image).exists():
            rows.append({"id": fb["id"], "image": image, "after": p["after"]})
    return rows


def export_dataset(rows: list[dict], dest: Path, class_names: list[str]) -> dict:
    """YOLO layout with a deterministic ~20% validation split. Returns {yaml, n_train, n_val, names}."""
    import cv2
    names = list(class_names)
    for r in rows:
        for d in r["after"]:
            if d["cls"] not in names:
                names.append(d["cls"])
    if dest.exists():
        shutil.rmtree(dest)
    for split in ("train", "val"):
        (dest / "images" / split).mkdir(parents=True)
        (dest / "labels" / split).mkdir(parents=True)

    def split_of(row):
        return "val" if int(hashlib.md5(row["image"].encode()).hexdigest(), 16) % 5 == 0 else "train"

    assigned = [(r, split_of(r)) for r in rows]
    if len(rows) >= 2 and not any(s == "val" for _, s in assigned):
        assigned[-1] = (assigned[-1][0], "val")
    if not any(s == "train" for _, s in assigned) and assigned:
        assigned[0] = (assigned[0][0], "train")
    counts = {"train": 0, "val": 0}
    for r, split in assigned:
        img = cv2.imread(r["image"])
        h, w = img.shape[:2]
        stem = f"{r['id']}_{Path(r['image']).stem}"
        cv2.imwrite(str(dest / "images" / split / f"{stem}.jpg"), img)
        lines = []
        for d in r["after"]:  # an empty list is a valid negative (false alarm)
            x1, y1, x2, y2 = d["bbox"]
            lines.append(f"{names.index(d['cls'])} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} "
                         f"{(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
        (dest / "labels" / split / f"{stem}.txt").write_text("\n".join(lines))
        counts[split] += 1
    if counts["val"] == 0:  # single sample: validate on the training image (weak, flagged in metrics)
        for f in (dest / "images" / "train").iterdir():
            shutil.copy(f, dest / "images" / "val" / f.name)
            shutil.copy(dest / "labels" / "train" / f"{f.stem}.txt", dest / "labels" / "val" / f"{f.stem}.txt")
        counts["val"] = counts["train"]
    yaml = dest / "data.yaml"
    yaml.write_text(f"path: {dest.as_posix()}\ntrain: images/train\nval: images/val\nnames:\n" +
                    "".join(f"  {i}: {n}\n" for i, n in enumerate(names)))
    val_instances = sum(1 for f in (dest / "labels" / "val").glob("*.txt")
                        for line in f.read_text().splitlines() if line.strip())
    return {"yaml": str(yaml), "n_train": counts["train"], "n_val": counts["val"], "names": names,
            "val_instances": val_instances,
            "val_is_train": counts["val"] == counts["train"] and len(rows) < 2}


def _map50(weights: Path, data_yaml: str) -> float:
    from ultralytics import YOLO
    return float(YOLO(str(weights)).val(data=data_yaml, verbose=False, plots=False, workers=0).box.map50)


def retrain(epochs: int = 30, force: bool = False, min_gain: float = -0.02, trainer=None) -> dict:
    """Fine-tune on new corrections. `trainer(base_weights, yaml, out_dir)->weights_path` and the
    metric function are injectable so the promote/reject logic is testable without a GPU run."""
    if not _train_lock.acquire(blocking=False):
        return {"status": "already_running"}
    _state.update(running=True, last_error=None)
    try:
        rows = correction_rows()
        if len(rows) < config.RETRAIN_MIN_LABELS and not force:
            return {"status": "not_enough_labels", "have": len(rows), "need": config.RETRAIN_MIN_LABELS}
        if not rows:
            return {"status": "no_labels"}
        reg = registry()
        base = Path(reg["versions"][reg["active"]]["path"])
        from ultralytics import YOLO
        base_names = list(YOLO(str(base)).names.values())
        version = f"v{len([v for v in reg['versions'] if v != 'baseline']) + 1}"
        out_dir = config.MODEL_VERSIONS_DIR / version
        ds = export_dataset(rows, out_dir / "dataset", base_names)
        base_map = _map50(base, ds["yaml"])
        if trainer is None:
            def trainer(base_w, yaml, out):
                model = YOLO(str(base_w))
                model.train(data=yaml, epochs=epochs, imgsz=320, lr0=0.001, freeze=10, workers=0, batch=8,
                            project=str(out), name="train", exist_ok=True, verbose=False, plots=False)
                return Path(model.trainer.best)
        best = Path(trainer(base, ds["yaml"], out_dir))
        final = out_dir / "best.pt"
        shutil.copy(best, final)
        new_map = _map50(final, ds["yaml"])
        # mAP is undefined without labelled objects in the held-out set, so such a model is
        # registered but never promoted on its own say-so (activate it by hand after checking).
        validated = ds["val_instances"] >= 1
        promote = validated and new_map - base_map >= min_gain
        reg = registry()
        reg["versions"][version] = {"path": str(final), "created": time.time(), "base": reg["active"],
                                    "n_labels": len(rows), "map50_base": round(base_map, 4),
                                    "map50_new": round(new_map, 4), "classes": ds["names"],
                                    "weak_validation": ds["val_is_train"] or ds["val_instances"] < 10,
                                    "val_instances": ds["val_instances"],
                                    "status": "promoted" if promote else ("rejected" if validated else "unvalidated")}
        reg["labels_used"] = sorted(set(reg.get("labels_used", [])) | {r["id"] for r in rows})
        _save(reg)
        if promote:
            set_active(version)
        result = {"status": reg["versions"][version]["status"], "version": version,
                  **{k: reg["versions"][version][k] for k in ("map50_base", "map50_new", "n_labels")}}
        _state["last_result"] = result
        return result
    except Exception as e:
        _state["last_error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        _state["running"] = False
        _train_lock.release()


def retrain_async(**kw) -> bool:
    if _state["running"]:
        return False
    threading.Thread(target=lambda: _safe(retrain, **kw), daemon=True).start()
    return True


def _safe(fn, **kw):
    try:
        fn(**kw)
    except Exception:
        pass  # recorded in _state["last_error"]


def maybe_auto_retrain() -> bool:
    return config.AUTO_RETRAIN and len(correction_rows()) >= config.RETRAIN_MIN_LABELS and retrain_async()


# --- L12: confidence recalibration ----------------------------------------------------------

def _calibration_path() -> Path:
    return config.DATA_DIR / "calibration.json"


def load_calibration() -> dict | None:
    p = _calibration_path()
    return json.loads(p.read_text()) if p.exists() else None


def recalibrate() -> dict:
    """Acceptance rate per AI rank from expert decisions. An edited pick counts as half an accept."""
    hits, seen = {1: 0.0, 2: 0.0, 3: 0.0}, {1: 0, 2: 0, 3: 0}
    for fb in db.get_feedback("expert_choice"):
        p = fb["payload"]
        for r in range(1, len(p["confidences"]) + 1):
            seen[r] += 1
        if p.get("chosen_rank") in hits:
            hits[p["chosen_rank"]] += 0.5 if p.get("edited") else 1.0
    for fb in db.get_feedback("rca_rejected_all"):
        for r in range(1, min(3, len(fb["payload"]["candidates"])) + 1):
            seen[r] += 1
    n = max(seen.values())
    cal = {"n": n, "rank_acc": {str(r): round(hits[r] / seen[r], 3) for r in hits if seen[r]}, "updated": time.time(),
           "active": n >= config.RECAL_MIN_SAMPLES}
    _calibration_path().parent.mkdir(parents=True, exist_ok=True)
    _calibration_path().write_text(json.dumps(cal))
    return cal


def apply_calibration(rank: int, raw_pct: float) -> float:
    """Blend the model's raw confidence with how often experts actually accepted this rank."""
    cal = load_calibration()
    if not cal or not cal.get("active") or str(rank) not in cal["rank_acc"]:
        return raw_pct
    return round(0.5 * raw_pct + 0.5 * 100 * cal["rank_acc"][str(rank)], 1)


def status() -> dict:
    reg = registry()
    return {"active": reg["active"], "versions": reg["versions"], "pending_labels": len(correction_rows()),
            "retrain_min_labels": config.RETRAIN_MIN_LABELS, "auto_retrain": config.AUTO_RETRAIN,
            "training": dict(_state), "calibration": load_calibration()}
