"""Settings read from .env. Retry caps mirror the loop register (L1-L9) in the flow PDF."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _env(name: str, default: str) -> str:
    return os.environ.get(name) or default


DATA_DIR = Path(_env("DATA_DIR", str(ROOT / "runs" / "data")))
DB_PATH = Path(_env("DB_PATH", str(DATA_DIR / "novaliseo.db")))
CHECKPOINT_PATH = Path(_env("CHECKPOINT_PATH", str(DATA_DIR / "checkpoints.db")))
UPLOAD_DIR = DATA_DIR / "uploads"
REPORT_DIR = DATA_DIR / "reports"
PARTS_DIR = Path(_env("PARTS_DIR", str(ROOT / "data" / "parts")))
KB_SEED_DIR = Path(_env("KB_SEED_DIR", str(ROOT / "data" / "kb_seed")))

YOLO_WEIGHTS = Path(_env("YOLO_WEIGHTS", str(ROOT / "models" / "best.pt")))
CONF_THRESHOLD = float(_env("CONF_THRESHOLD", "0.25"))
LABEL_REVIEW_CONF = float(_env("LABEL_REVIEW_CONF", "0.85"))
INSPECTION_MODE = _env("INSPECTION_MODE", "yolo")  # yolo | manifest

LLM_PROVIDER = _env("LLM_PROVIDER", "ollama")  # ollama | none
LLM_MODEL = _env("LLM_MODEL", "qwen2.5:7b")
EMBED_MODEL = _env("EMBED_MODEL", "nomic-embed-text")
OLLAMA_URL = _env("OLLAMA_URL", "http://localhost:11434")

# Retry caps (L1..L8). A cap of N means N retries after the first attempt.
MAX_RETRIES = {
    "L1": 3,  # part / drawing not found: rescan, then job on hold
    "L2": 3,  # image quality: recapture
    "L3": 2,  # engineer rejects dimensions: re-measure
    "L4": 2,  # evidence insufficient: relax filters
    "L5": 2,  # RCA output invalid: regenerate
    "L6": 1,  # expert rejects all causes: re-inspect
    "L7": 1,  # report incomplete: add missing data
    "L8": 5,  # approver rejects: redraft
}

# Image-quality thresholds
BLUR_MIN = float(_env("BLUR_MIN", "20"))  # variance of Laplacian
GLARE_MAX = float(_env("GLARE_MAX", "0.15"))  # fraction of saturated pixels
EXPOSURE_RANGE = (40.0, 220.0)  # mean gray level

# Retrieval
RETRIEVE_TOP_K = 5
RETRIEVE_MIN_SIM = 0.15
RETRIEVE_MIN_HITS = 2
