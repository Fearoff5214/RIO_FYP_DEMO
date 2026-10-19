"""
Downloads NEU-DET (Kaggle: kaustubhdikshit/neu-surface-defect-database),
converts its Pascal VOC XML annotations to YOLO .txt labels, and writes a
seeded train/val/test split plus a data.yaml for Ultralytics training.

Requires a Kaggle API token. Get one at kaggle.com -> Account -> Create New
API Token, then put KAGGLE_USERNAME and KAGGLE_KEY in defect-demo/.env
(see .env.example) before running.

The raw dataset's exact folder layout varies between Kaggle re-uploads, so
rather than hardcoding paths, this script walks the whole download looking
for (xml, image) pairs by filename stem.
"""
import os
import random
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from dotenv import load_dotenv
import kagglehub

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

KAGGLE_DATASET = "kaustubhdikshit/neu-surface-defect-database"

# Canonical NEU-DET classes, fixed order -> fixed class indices.
CLASSES = [
    "crazing",
    "inclusion",
    "patches",
    "pitted_surface",
    "rolled-in_scale",
    "scratches",
]
# Some NEU-DET re-uploads spell/abbreviate class names differently in the
# XML <name> tags. Map known variants to the canonical name above.
CLASS_ALIASES = {
    "crazing": "crazing",
    "inclusion": "inclusion",
    "patches": "patches",
    "pitted_surface": "pitted_surface",
    "pitted surface": "pitted_surface",
    "rolled-in_scale": "rolled-in_scale",
    "rolled-in scale": "rolled-in_scale",
    "rolled_in_scale": "rolled-in_scale",
    "scratches": "scratches",
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
SPLIT_RATIOS = (0.70, 0.15, 0.15)  # train, val, test
SEED = 42

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "data" / "yolo"


def find_annotation_image_pairs(root: Path) -> list[tuple[Path, Path]]:
    """Walk `root`, pair every .xml annotation with its image by stem name."""
    images_by_stem: dict[str, Path] = {}
    for p in root.rglob("*"):
        if p.suffix.lower() in IMAGE_EXTS:
            images_by_stem.setdefault(p.stem, p)

    pairs = []
    for xml_path in root.rglob("*.xml"):
        img = images_by_stem.get(xml_path.stem)
        if img is not None:
            pairs.append((xml_path, img))
    return pairs


def parse_voc_annotation(xml_path: Path) -> tuple[int, int, list[tuple[str, float, float, float, float]]]:
    """Returns (width, height, [(class_name, xmin, ymin, xmax, ymax), ...])."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    size = root.find("size")
    width = int(size.findtext("width"))
    height = int(size.findtext("height"))

    boxes = []
    for obj in root.findall("object"):
        raw_name = obj.findtext("name").strip().lower()
        name = CLASS_ALIASES.get(raw_name)
        if name is None:
            raise ValueError(f"Unrecognized class '{raw_name}' in {xml_path}")
        bnd = obj.find("bndbox")
        xmin = float(bnd.findtext("xmin"))
        ymin = float(bnd.findtext("ymin"))
        xmax = float(bnd.findtext("xmax"))
        ymax = float(bnd.findtext("ymax"))
        boxes.append((name, xmin, ymin, xmax, ymax))
    return width, height, boxes


def voc_box_to_yolo_line(class_idx: int, width: int, height: int, xmin, ymin, xmax, ymax) -> str:
    x_center = ((xmin + xmax) / 2) / width
    y_center = ((ymin + ymax) / 2) / height
    box_w = (xmax - xmin) / width
    box_h = (ymax - ymin) / height
    return f"{class_idx} {x_center:.6f} {y_center:.6f} {box_w:.6f} {box_h:.6f}"


def main():
    if not os.environ.get("KAGGLE_USERNAME") or not os.environ.get("KAGGLE_KEY"):
        raise RuntimeError(
            "KAGGLE_USERNAME / KAGGLE_KEY not set. Fill them in defect-demo/.env "
            "(see .env.example) with a token from kaggle.com -> Account -> Create New API Token."
        )

    print(f"Downloading {KAGGLE_DATASET} via kagglehub...")
    dataset_root = Path(kagglehub.dataset_download(KAGGLE_DATASET))
    print(f"Dataset cached at: {dataset_root}")

    pairs = find_annotation_image_pairs(dataset_root)
    if not pairs:
        raise RuntimeError(
            f"No (xml, image) pairs found under {dataset_root}. "
            "The dataset layout may have changed - inspect the folder manually."
        )
    print(f"Found {len(pairs)} annotated images.")

    random.Random(SEED).shuffle(pairs)
    n = len(pairs)
    n_train = int(n * SPLIT_RATIOS[0])
    n_val = int(n * SPLIT_RATIOS[1])
    splits = {
        "train": pairs[:n_train],
        "val": pairs[n_train:n_train + n_val],
        "test": pairs[n_train + n_val:],
    }

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    for split_name, split_pairs in splits.items():
        img_dir = OUT_DIR / split_name / "images"
        lbl_dir = OUT_DIR / split_name / "labels"
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        for xml_path, img_path in split_pairs:
            width, height, boxes = parse_voc_annotation(xml_path)
            lines = [
                voc_box_to_yolo_line(CLASSES.index(name), width, height, xmin, ymin, xmax, ymax)
                for name, xmin, ymin, xmax, ymax in boxes
            ]

            dest_img = img_dir / img_path.name
            shutil.copy2(img_path, dest_img)
            (lbl_dir / f"{img_path.stem}.txt").write_text("\n".join(lines), encoding="utf-8")

        print(f"{split_name}: {len(split_pairs)} images")

    data_yaml = OUT_DIR / "data.yaml"
    data_yaml.write_text(
        "path: " + str(OUT_DIR).replace("\\", "/") + "\n"
        "train: train/images\n"
        "val: val/images\n"
        "test: test/images\n"
        f"nc: {len(CLASSES)}\n"
        "names: " + str(CLASSES) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {data_yaml}")


if __name__ == "__main__":
    main()
