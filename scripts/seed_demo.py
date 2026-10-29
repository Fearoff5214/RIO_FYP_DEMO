"""
Seed script: creates demo part MS-4505-001 and default users.
Run with: python scripts/seed_demo.py
Or called from FastAPI lifespan on startup.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


async def seed_if_empty() -> None:
    """Seed database if it has no parts or users."""
    from app.db.session import get_db, create_tables
    from app.db.models import PartMaster, User
    from app.core.security import hash_password
    from sqlalchemy import select

    await create_tables()

    factory = __import__("app.db.session", fromlist=["_get_session_factory"])._get_session_factory()

    async with factory() as db:
        # Check parts
        result = await db.execute(select(PartMaster).limit(1))
        if result.scalar_one_or_none() is None:
            await _seed_parts(db)

        # Check users
        result = await db.execute(select(User).limit(1))
        if result.scalar_one_or_none() is None:
            await _seed_users(db)


async def _seed_parts(db) -> None:
    """Seed demo parts."""
    from app.db.models import PartMaster
    from app.cv.drawing.synthetic import DEMO_PART

    part = PartMaster(
        part_number=DEMO_PART["part_number"],
        part_name=DEMO_PART["part_name"],
        drawing_rev=DEMO_PART["drawing_rev"],
        drawing_uri=DEMO_PART["drawing_uri"],
        material=DEMO_PART["material"],
        process=DEMO_PART["process"],
        tolerances=DEMO_PART["tolerances"],
        camera_recipe=DEMO_PART["camera_recipe"],
        calibration=DEMO_PART["calibration"],
    )
    db.add(part)
    await db.commit()
    print(f"[seed] Created part: {DEMO_PART['part_number']}")


async def _seed_users(db) -> None:
    """Seed default users for each role."""
    from app.db.models import User
    from app.core.security import hash_password

    default_users = [
        ("operator", "operator", "operator", "Demo Operator"),
        ("engineer", "engineer", "engineer", "Demo Engineer"),
        ("expert", "expert", "expert", "Demo Expert"),
        ("approver", "approver", "approver", "Demo Approver"),
        ("admin", "admin", "admin", "Demo Admin"),
        ("auditor", "auditor", "auditor", "Demo Auditor"),
    ]

    for username, password, role, name in default_users:
        user = User(
            username=username,
            hashed_password=hash_password(password),
            role=role,
            full_name=name,
            email=f"{username}@novaliseo.demo",
        )
        db.add(user)

    await db.commit()
    print("[seed] Created demo users: operator/operator, engineer/engineer, expert/expert, approver/approver, admin/admin")


if __name__ == "__main__":
    asyncio.run(seed_if_empty())
    print("[seed] Done.")
