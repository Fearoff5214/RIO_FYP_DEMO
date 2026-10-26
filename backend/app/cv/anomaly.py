"""Unseen-defect detection from defect-free images only (PatchCore-style).

Anomalib is the usual tool for this, but pip-installing it would pull in 28 packages
including a second OpenCV build into the project venv. This is the same algorithm in
~100 lines on torch + torchvision, behind the same interface (`fit`, `score`).

Fit: ResNet-18 layer2+layer3 patch features of good images -> memory bank.
Score: per-patch distance to nearest bank patch; image score = max; hotspot = region above threshold.
The threshold comes from leave-one-image-out scores on the good set, so it needs >= 3 images.
"""
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from .. import config

SIZE = 256
MAX_BANK = 40000
MIN_IMAGES = 3
_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
_STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)


def _device():
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


@lru_cache(maxsize=1)
def _backbone():
    import torchvision
    net = torchvision.models.resnet18(weights=torchvision.models.ResNet18_Weights.IMAGENET1K_V1)
    return net.eval().to(_device())


@torch.no_grad()
def _features(img_bgr: np.ndarray) -> tuple[torch.Tensor, tuple[int, int]]:
    """(patches, D) features and the (h, w) patch grid."""
    rgb = cv2.cvtColor(cv2.resize(img_bgr, (SIZE, SIZE)), cv2.COLOR_BGR2RGB)
    x = torch.from_numpy(rgb).permute(2, 0, 1).float().unsqueeze(0) / 255.0
    x = ((x - _MEAN) / _STD).to(_device())
    n = _backbone()
    x = n.maxpool(n.relu(n.bn1(n.conv1(x))))
    f2 = n.layer2(n.layer1(x))
    f3 = n.layer3(f2)
    f2, f3 = F.avg_pool2d(f2, 3, 1, 1), F.avg_pool2d(f3, 3, 1, 1)  # local neighbourhood aggregation
    f3 = F.interpolate(f3, size=f2.shape[-2:], mode="bilinear", align_corners=False)
    feat = torch.cat([f2, f3], dim=1)[0]
    d, h, w = feat.shape
    return feat.permute(1, 2, 0).reshape(-1, d), (h, w)


def _min_dist(q: torch.Tensor, bank: torch.Tensor, chunk: int = 2048) -> torch.Tensor:
    return torch.cat([torch.cdist(q[i:i + chunk], bank).min(dim=1).values for i in range(0, len(q), chunk)])


def fit(images: list[np.ndarray], out_path: Path) -> dict:
    if len(images) < MIN_IMAGES:
        raise ValueError(f"need at least {MIN_IMAGES} defect-free images, got {len(images)}")
    feats = [_features(im)[0] for im in images]
    owner = torch.cat([torch.full((len(f),), i) for i, f in enumerate(feats)])
    bank = torch.cat(feats)
    if len(bank) > MAX_BANK:  # random subsample keeps the owner mapping aligned
        idx = torch.randperm(len(bank), generator=torch.Generator().manual_seed(0))[:MAX_BANK]
        bank, owner = bank[idx.to(bank.device)], owner[idx]
    loo = []
    for i, f in enumerate(feats):  # leave-one-image-out: score each good image against the others
        keep = (owner != i).to(bank.device)
        loo.append(float(_min_dist(f, bank[keep]).max()))
    threshold = max(loo) * 1.1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"bank": bank.cpu(), "threshold": threshold, "n_images": len(images)}, out_path)
    _load.cache_clear()
    return {"threshold": threshold, "n_images": len(images), "bank_size": len(bank), "path": str(out_path)}


@lru_cache(maxsize=4)
def _load(path: str):
    d = torch.load(path, map_location="cpu")
    return d["bank"].to(_device()), float(d["threshold"])


def model_path(part_number: str | None) -> Path | None:
    for name in (part_number, "default"):
        p = config.ANOMALY_DIR / f"{name}.pt"
        if name and p.exists():
            return p
    return None


@torch.no_grad()
def score(img_bgr: np.ndarray, model: Path) -> dict:
    """{score, threshold, ratio, anomalous, bbox (original image coords) | None}"""
    bank, thr = _load(str(model))
    q, (h, w) = _features(img_bgr)
    amap = _min_dist(q, bank).reshape(1, 1, h, w)
    amap = F.interpolate(amap, size=img_bgr.shape[:2], mode="bilinear", align_corners=False)[0, 0].cpu().numpy()
    amap = cv2.GaussianBlur(amap, (0, 0), 4)
    peak = float(amap.max())
    out = {"score": round(peak, 4), "threshold": round(thr, 4), "ratio": round(peak / thr, 3),
           "anomalous": peak > thr, "bbox": None}
    if out["anomalous"]:
        mask = (amap > max(thr, 0.5 * peak)).astype(np.uint8)  # tight around the peak, not the whole halo
        n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        if n > 1:
            x, y, bw, bh, _ = stats[1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))]
            out["bbox"] = [float(x), float(y), float(x + bw), float(y + bh)]
    return out
