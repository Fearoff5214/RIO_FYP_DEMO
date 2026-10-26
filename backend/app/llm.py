"""Ollama client for chat and embeddings, with an offline fallback.

Embeddings fall back to a deterministic hashed bag-of-words vector when Ollama is not
running, so ingestion, retrieval and tests work without a model server. The two vector
spaces must not be mixed: the embedding backend is recorded per chunk by vector length.
"""
import hashlib
import json
import math
import re

import requests

from . import config

HASH_DIM = 256
_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def hash_embed(text: str) -> list[float]:
    vec = [0.0] * HASH_DIM
    for tok in tokenize(text):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % HASH_DIM] += 1.0 if (h >> 8) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(text: str) -> list[float]:
    if config.LLM_PROVIDER == "ollama":
        try:
            r = requests.post(f"{config.OLLAMA_URL}/api/embeddings",
                              json={"model": config.EMBED_MODEL, "prompt": text}, timeout=30)
            r.raise_for_status()
            return r.json()["embedding"]
        except (requests.RequestException, KeyError, ValueError):
            pass
    return hash_embed(text)


def available() -> bool:
    if config.LLM_PROVIDER != "ollama":
        return False
    try:
        return requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=2).ok
    except requests.RequestException:
        return False


def chat_json(system: str, user: str) -> dict | None:
    """Ask the model for a JSON object. Returns None if unavailable or unparseable."""
    if not available():
        return None
    try:
        r = requests.post(f"{config.OLLAMA_URL}/api/chat", json={
            "model": config.LLM_MODEL, "stream": False, "format": "json",
            "options": {"temperature": 0.2},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }, timeout=180)
        r.raise_for_status()
        return json.loads(r.json()["message"]["content"])
    except (requests.RequestException, KeyError, ValueError):
        return None
