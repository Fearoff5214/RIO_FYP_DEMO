"""Integration tests for the FastAPI endpoints."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture(scope="module")
async def client():
    """Shared async client with lifespan support."""
    from app.db.session import create_tables
    from app.main import app
    # Create tables before tests
    await create_tables()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readyz(client):
    resp = await client.get("/readyz")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_jobs(client):
    resp = await client.get("/api/v1/jobs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_parts(client):
    resp = await client.get("/api/v1/parts")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_kpis(client):
    resp = await client.get("/api/v1/dashboard/kpis")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_jobs" in data
    assert "pass_rate" in data


@pytest.mark.asyncio
async def test_kb_search(client):
    resp = await client.get("/api/v1/kb/search?q=bending+force+deformation")
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data


@pytest.mark.asyncio
async def test_auth_register_and_login(client):
    # Register
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "testuser_int2", "password": "Pass1234", "role": "operator"},
    )
    assert resp.status_code in (201, 409)

    # Login
    resp = await client.post(
        "/api/v1/auth/token",
        data={"username": "testuser_int2", "password": "Pass1234"},
    )
    if resp.status_code == 200:
        assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_create_part_and_job(client):
    """Create a part, then create an inspection job for it."""
    # Create part via admin (mock mode skips auth)
    resp = await client.post(
        "/api/v1/parts",
        json={
            "part_number": "TEST-001",
            "part_name": "Test Part",
            "drawing_rev": "A",
            "drawing_uri": "synthetic://TEST-001.dxf",
        },
    )
    assert resp.status_code in (201, 422)  # may already exist

    # Create job
    resp = await client.post(
        "/api/v1/jobs",
        json={"part_number": "TEST-001"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "job_id" in data


@pytest.mark.asyncio
async def test_job_rejects_unknown_part_verification(client):
    part_number = "VERIFY-GUARD-001"
    await client.post(
        "/api/v1/parts",
        json={
            "part_number": part_number,
            "part_name": "Verification Guard Test",
            "drawing_rev": "A",
            "drawing_uri": "synthetic://VERIFY-GUARD-001.dxf",
        },
    )

    response = await client.post(
        "/api/v1/jobs",
        json={"part_number": part_number, "verification_id": "not-a-valid-verification"},
    )

    assert response.status_code == 409
    assert "verification" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_part_reference_upload_and_capture_verification(client, monkeypatch, tmp_path):
    import cv2
    import numpy as np

    class TestConfig:
        project_root = tmp_path

        @staticmethod
        def get(*keys):
            return 0.55 if keys == ("part_verification", "score_threshold") else None

    monkeypatch.setattr("app.api.parts.get_config", lambda: TestConfig())
    part_number = "VERIFY-CV-ENDPOINT"
    created = await client.post(
        "/api/v1/parts",
        json={
            "part_number": part_number,
            "part_name": "Verification Endpoint Test",
            "drawing_rev": "A",
            "drawing_uri": "synthetic://VERIFY-CV-ENDPOINT.dxf",
        },
    )
    assert created.status_code == 201

    image = np.full((400, 400, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (50, 50), (350, 350), (0, 0, 0), 5)
    cv2.circle(image, (120, 120), 24, (0, 0, 0), 4)
    cv2.circle(image, (280, 180), 18, (0, 0, 0), 4)
    encoded, buffer = cv2.imencode(".png", image)
    assert encoded
    image_bytes = buffer.tobytes()

    uploaded = await client.put(
        f"/api/v1/parts/{part_number}/references",
        files={
            "cad_image": ("cad.png", image_bytes, "image/png"),
            "reference_image": ("part.png", image_bytes, "image/png"),
        },
    )
    assert uploaded.status_code == 200

    verification = await client.post(
        f"/api/v1/parts/{part_number}/verify",
        files={"image": ("capture.png", image_bytes, "image/png")},
    )

    assert verification.status_code == 200
    assert verification.json()["status"] == "Match"
    assert verification.json()["verification_id"]
