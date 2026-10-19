"""
Fine-tunes a pretrained YOLOv8 model on the converted NEU-DET dataset.
Run scripts/convert_neudet_to_yolo.py first to produce data/yolo/data.yaml.
"""
from pathlib import Path

from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_YAML = PROJECT_ROOT / "data" / "yolo" / "data.yaml"
RUNS_DIR = PROJECT_ROOT / "runs"

# yolov8n (nano) - fastest to train, fits comfortably on an 8GB GPU, plenty
# for a 6-class / 1800-image dataset like NEU-DET.
BASE_WEIGHTS = "yolov8n.pt"
EPOCHS = 100
IMGSZ = 320  # NEU-DET images are 200x200; upscaled slightly for YOLO's stride requirements
BATCH = 16


def main():
    if not DATA_YAML.exists():
        raise FileNotFoundError(
            f"{DATA_YAML} not found. Run scripts/convert_neudet_to_yolo.py first."
        )

    model = YOLO(BASE_WEIGHTS)
    model.train(
        data=str(DATA_YAML),
        epochs=EPOCHS,
        imgsz=IMGSZ,
        batch=BATCH,
        project=str(RUNS_DIR),
        name="neu_det_yolov8n",
        patience=20,  # early stop if val metrics plateau
        seed=42,
    )


if __name__ == "__main__":
    main()
