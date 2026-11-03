"""Check that the Gemini key and model configured in .env work.

Run: py scripts/check_gemini.py
Reads GEMINI_API_KEY and GEMINI_MODEL through the app settings (.env). Never prints the key.
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.config import get_config  # noqa: E402

BASE = "https://generativelanguage.googleapis.com/v1beta"


def main() -> int:
    s = get_config().settings
    key, model = (s.gemini_api_key or "").strip(), s.gemini_model
    if not key:
        print("GEMINI_API_KEY is empty. Put your key in .env (GEMINI_API_KEY=...) and run this again.")
        return 1
    headers = {"x-goog-api-key": key}
    try:
        r = httpx.get(f"{BASE}/models", headers=headers, params={"pageSize": 200}, timeout=30)
    except httpx.HTTPError as exc:
        print(f"Could not reach the Gemini API: {type(exc).__name__}")
        return 1
    if r.status_code != 200:
        print(f"Listing models failed: HTTP {r.status_code} (key rejected or API not enabled?)")
        return 1
    usable = sorted(m["name"].split("/")[-1] for m in r.json().get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", []) and "gemini" in m["name"])
    print(f"Key accepted. {len(usable)} Gemini models can generate content, for example: {', '.join(usable[:8])}")
    if model not in usable:
        print(f"WARNING: GEMINI_MODEL={model} is not in that list. Set GEMINI_MODEL in .env to one of the names above.")
        return 1
    body = {"contents": [{"role": "user", "parts": [{"text": "Reply with the single word: ready"}]}],
            "generationConfig": {"maxOutputTokens": 256}}

    def try_model(name: str) -> tuple[bool, str]:
        try:
            r = httpx.post(f"{BASE}/models/{name}:generateContent", headers=headers, json=body, timeout=40)
        except httpx.HTTPError as exc:
            return False, type(exc).__name__
        if r.status_code == 200:
            return True, ""
        try:
            return False, f"HTTP {r.status_code}: {r.json().get('error', {}).get('message', '')[:140]}"
        except ValueError:
            return False, f"HTTP {r.status_code}"

    ok, why = try_model(model)
    if ok:
        print(f"OK: {model} answered. AI root cause analysis will use it.")
        return 0
    print(f"Test call to {model} failed: {why}")
    print("Trying other models from your list ...")
    for name in [m for m in usable if m.startswith("gemini-") and not any(t in m for t in ("image", "tts", "audio", "transcribe", "robotics", "computer-use", "customtools", "nano", "omni", "argon", "latest"))
                 and "flash" in m][::-1][:8]:
        ok, why = try_model(name)
        print(f"  {name}: {'works' if ok else why}")
        if ok:
            print(f"Set GEMINI_MODEL={name} in .env and restart the API.")
            return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
