"""Pytest fixtures for Novaliseo tests."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

# Set mock mode before any imports
os.environ["NOVALISEO_MODE"] = "mock"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


@pytest_asyncio.fixture(scope="session")
async def db():
    """In-memory SQLite database session for tests."""
    from app.db.session import create_tables, _get_session_factory
    await create_tables()
    factory = _get_session_factory()
    async with factory() as session:
        yield session


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for all tests in the session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_part():
    """Return demo part master dict."""
    from app.cv.drawing.synthetic import generate_synthetic_part_master
    return generate_synthetic_part_master("MS-4505-001")


@pytest.fixture
def sample_defects():
    """Return mock defect detections."""
    return [
        {"defect_id": "d1", "defect_type": "scratch", "confidence": 0.92, "severity": "minor",
         "bbox": {"x1": 100, "y1": 80, "x2": 240, "y2": 120}, "size_px": 3200, "source": "yolo"},
        {"defect_id": "d2", "defect_type": "dent", "confidence": 0.88, "severity": "major",
         "bbox": {"x1": 300, "y1": 200, "x2": 380, "y2": 280}, "size_px": 6400, "source": "yolo"},
        {"defect_id": "d3", "defect_type": "crack", "confidence": 0.76, "severity": "critical",
         "bbox": {"x1": 450, "y1": 100, "x2": 520, "y2": 180}, "size_px": 5600, "source": "yolo"},
        {"defect_id": "d4", "defect_type": "deformation", "confidence": 0.91, "severity": "major",
         "bbox": {"x1": 150, "y1": 300, "x2": 350, "y2": 420}, "size_px": 40000, "source": "yolo"},
    ]


@pytest.fixture
def sample_measurements():
    """Return sample measurements matching the infographic."""
    return [
        {"feature_id": "L1", "feature_type": "edge", "nominal": 120.0, "measured": 120.05,
         "deviation": 0.05, "tol_plus": 0.10, "tol_minus": 0.10, "within_tolerance": True},
        {"feature_id": "L2", "feature_type": "edge", "nominal": 80.0, "measured": 80.02,
         "deviation": 0.02, "tol_plus": 0.10, "tol_minus": 0.10, "within_tolerance": True},
        {"feature_id": "H1", "feature_type": "hole", "nominal": 12.0, "measured": 11.70,
         "deviation": -0.30, "tol_plus": 0.05, "tol_minus": 0.05, "within_tolerance": False},
        {"feature_id": "L3", "feature_type": "edge", "nominal": 50.0, "measured": 50.01,
         "deviation": 0.01, "tol_plus": 0.10, "tol_minus": 0.10, "within_tolerance": True},
    ]
