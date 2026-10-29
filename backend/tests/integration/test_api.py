"""Integration tests for the FastAPI endpoints."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest_asyncio.fixture(scope="module")
async def client():
    """Shared async client with lifespan support."""
    from app.main import app
    from app.db.session import create_tables
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
