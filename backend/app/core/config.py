"""
Application configuration: loads from config/default.yaml + environment variables.
Secrets come only from env vars; all thresholds/paths from YAML.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings

# Project root is three levels up from this file: backend/app/core/config.py
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"


def _load_yaml() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


class Settings(BaseSettings):
    # ── App ────────────────────────────────────────────────────────────────
    app_name: str = "Novaliseo"
    version: str = "0.1.0"
    novaliseo_mode: str = "mock"  # mock | real

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str = f"sqlite+aiosqlite:///{PROJECT_ROOT}/novaliseo_dev.db"

    # ── Object storage ─────────────────────────────────────────────────────
    storage_endpoint_url: str = "http://localhost:9000"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_bucket: str = "novaliseo"

    # ── Auth ───────────────────────────────────────────────────────────────
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # ── LLM ───────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # ── Redis ─────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Notifications ─────────────────────────────────────────────────────
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    notification_from_email: str = "noreply@novaliseo.com"

    # ── External integrations ─────────────────────────────────────────────
    mes_url: str = ""
    qms_url: str = ""
    erp_url: str = ""

    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @field_validator("novaliseo_mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("mock", "real"):
            raise ValueError("NOVALISEO_MODE must be 'mock' or 'real'")
        return v


class AppConfig:
    """Merged config: YAML defaults + env overrides."""

    def __init__(self) -> None:
        self._yaml = _load_yaml()
        self.settings = Settings()

    def get(self, *keys: str, default: Any = None) -> Any:
        """Navigate nested YAML keys with dot-path support."""
        node: Any = self._yaml
        for key in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(key, default)
        return node

    @property
    def mode(self) -> str:
        return self.settings.novaliseo_mode

    @property
    def is_mock(self) -> bool:
        return self.mode == "mock"

    @property
    def database_url(self) -> str:
        return self.settings.database_url

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig()
