"""Preflight check: run this first on a new machine.  python scripts/check_setup.py

Prints PASS / WARN / FAIL per item and exits 1 if anything FAILs. WARN means a feature is
degraded but the system still runs (for example no Ollama: root causes come from the
knowledge-base text instead of the LLM).
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

results: list[tuple[str, str, str]] = []


def check(name: str, status: str, detail: str = "") -> None:
    results.append((status, name, detail))


def main() -> int:
    from backend.app import config

    check("Python", "PASS" if sys.version_info >= (3, 11) else "FAIL", sys.version.split()[0])

    for mod in ("fastapi", "uvicorn", "langgraph", "langgraph.checkpoint.sqlite", "ultralytics", "cv2", "numpy",
                "ezdxf", "reportlab", "openpyxl", "docx", "requests", "torch", "torchvision", "multipart"):
        try:
            importlib.import_module(mod)
            check(f"package {mod}", "PASS")
        except ImportError as e:
            check(f"package {mod}", "FAIL", f"{e} -> pip install -r requirements.txt")

    try:
        import torch
        check("GPU (CUDA)", "PASS" if torch.cuda.is_available() else "WARN",
              torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU only: works, but slower")
    except ImportError:
        pass

    w = config.YOLO_WEIGHTS
    check("YOLO weights", "PASS" if w.exists() else "FAIL", str(w))
    sam = Path(config.SAM_WEIGHTS)
    check("SAM weights", "PASS" if sam.exists() else "WARN",
          str(sam) if sam.exists() else "downloaded automatically on the first job (needs internet, ~40 MB)")
    check("part master data", "PASS" if any(config.PARTS_DIR.glob("*.json")) else "FAIL", str(config.PARTS_DIR))
    check("KB seed documents", "PASS" if any(config.KB_SEED_DIR.glob("*.md")) else "WARN", str(config.KB_SEED_DIR))
    anomaly = list(config.ANOMALY_DIR.glob("*.pt")) if config.ANOMALY_DIR.exists() else []
    check("anomaly model", "PASS" if anomaly else "WARN",
          "fitted" if anomaly else "not fitted: unseen-defect detection is off until you fit one (see USER_GUIDE)")

    import requests
    try:
        tags = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=3).json()["models"]
        names = {m["name"] for m in tags}
        for need in (config.LLM_MODEL, f"{config.EMBED_MODEL}:latest"):
            ok = need in names or need.split(":")[0] in {n.split(":")[0] for n in names if need.endswith(":latest")}
            check(f"Ollama model {need}", "PASS" if ok else "WARN", "" if ok else f"ollama pull {need.replace(':latest', '')}")
    except Exception:
        check("Ollama", "WARN", f"not reachable at {config.OLLAMA_URL}: root causes will come straight from KB text")

    try:
        import cv2
        found = []
        for i in range(4):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
            if cap.isOpened() and cap.read()[0]:
                found.append(f"#{i} {int(cap.get(3))}x{int(cap.get(4))}")
            cap.release()
        check("cameras", "PASS" if found else "WARN",
              ", ".join(found) if found else "none found: upload mode still works; for the phone open Iriun on both devices")
    except Exception as e:
        check("cameras", "WARN", str(e))

    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        probe = config.DATA_DIR / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        check("data directory writable", "PASS", str(config.DATA_DIR))
    except OSError as e:
        check("data directory writable", "FAIL", str(e))

    ui = config.ROOT / "frontend" / "dist" / "index.html"
    check("web UI built", "PASS" if ui.exists() else "WARN", "" if ui.exists() else "cd frontend && npm install && npm run build")

    width = max(len(n) for _, n, _ in results)
    for status, name, detail in results:
        print(f"{status:5} {name:<{width}}  {detail}")
    fails = sum(s == "FAIL" for s, _, _ in results)
    warns = sum(s == "WARN" for s, _, _ in results)
    print(f"\n{len(results) - fails - warns} passed, {warns} warnings, {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
