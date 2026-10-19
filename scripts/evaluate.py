"""
Evaluates a trained model on the held-out NEU-DET test split and reports
overall + per-class metrics. Only prints/saves numbers that were actually
measured by Ultralytics' validator - nothing here is invented.

Usage:
    python scripts/evaluate.py [path/to/weights.pt]
Defaults to the latest training run's best.pt if no path is given.
"""
import json
import sys
from pathlib import Path

from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_YAML = PROJECT_ROOT / "data" / "yolo" / "data.yaml"
RUNS_DIR = PROJECT_ROOT / "runs"
MODELS_DIR = PROJECT_ROOT / "models"


def find_latest_best_weights() -> Path:
    candidates = sorted(RUNS_DIR.glob("*/weights/best.pt"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"No trained weights found under {RUNS_DIR}. Run scripts/train.py first.")
    return candidates[-1]


def main():
    weights_path = Path(sys.argv[1]) if len(sys.argv) > 1 else find_latest_best_weights()
    print(f"Evaluating weights: {weights_path}")

    model = YOLO(str(weights_path))
    metrics = model.val(data=str(DATA_YAML), split="test")

    class_names = metrics.names
    per_class = {}
    for idx, ap50 in enumerate(metrics.box.ap50):
        per_class[class_names[idx]] = {
            "mAP50": round(float(ap50), 4),
            "mAP50-95": round(float(metrics.box.maps[idx]), 4),
        }

    results = {
        "weights": str(weights_path),
        "overall": {
            "mAP50": round(float(metrics.box.map50), 4),
            "mAP50-95": round(float(metrics.box.map), 4),
            "precision": round(float(metrics.box.mp), 4),
            "recall": round(float(metrics.box.mr), 4),
        },
        "per_class": per_class,
    }

    print(json.dumps(results, indent=2))

    results_path = PROJECT_ROOT / "results.json"
    results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Saved metrics to {results_path}")

    MODELS_DIR.mkdir(exist_ok=True)
    best_copy = MODELS_DIR / "best.pt"
    best_copy.write_bytes(weights_path.read_bytes())
    print(f"Copied best weights to {best_copy}")


if __name__ == "__main__":
    main()
