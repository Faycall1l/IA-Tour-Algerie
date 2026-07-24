import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.experience import Experience
from app.models.user import User


@pytest.fixture
async def provider_user(db: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        phone="+213555999999",
        role="agency",
        display_name="Test Agency",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def provider_headers(provider_user: User) -> dict[str, str]:
    from app.core.security import create_access_token
    token = create_access_token(str(provider_user.id), provider_user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def sample_experience(db: AsyncSession, provider_user: User) -> Experience:
    exp = Experience(
        provider_id=provider_user.id,
        title="Sahara Desert Tour",
        category="tour",
        wilaya_id=11,
        description="3-day tour through the Tassili n'Ajjer",
        status="active",
        price_dzd=25000,
        max_participants=12,
    )
    db.add(exp)
    await db.commit()
    await db.refresh(exp)
    return exp


# ── POST /bookings ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_booking_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/bookings",
        json={"entity_type": "experience", "entity_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_booking(
    client: AsyncClient,
    auth_headers: dict,
    sample_experience: Experience,
):
    resp = await client.post(
        "/api/v1/bookings",
        json={
            "entity_type": "experience",
            "entity_id": str(sample_experience.id),
            "participants": 3,
            "message": "We'd love to join!",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["booking"]["entity_type"] == "experience"
    assert data["booking"]["participants"] == 3
    assert data["booking"]["status"] == "pending"
    assert data["booking_title"] == "Sahara Desert Tour"


@pytest.mark.asyncio
async def test_create_booking_own_experience(
    client: AsyncClient,
    provider_headers: dict,
    sample_experience: Experience,
):
    resp = await client.post(
        "/api/v1/bookings",
        json={
            "entity_type": "experience",
            "entity_id": str(sample_experience.id),
            "participants": 1,
        },
        headers=provider_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_booking_not_found(
    client: AsyncClient,
    auth_headers: dict,
):
    resp = await client.post(
        "/api/v1/bookings",
        json={
            "entity_type": "experience",
            "entity_id": str(uuid.uuid4()),
            "participants": 1,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ── GET /bookings ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_bookings(
    client: AsyncClient,
    auth_headers: dict,
    sample_experience: Experience,
):
    await client.post(
        "/api/v1/bookings",
        json={
            "entity_type": "experience",
            "entity_id": str(sample_experience.id),
            "participants": 2,
        },
        headers=auth_headers,
    )
    resp = await client.get("/api/v1/bookings", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_list_bookings_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/bookings")
    assert resp.status_code == 401


# ── GET /bookings/{id} ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_booking(
    client: AsyncClient,
    auth_headers: dict,
    sample_experience: Experience,
):
    create_resp = await client.post(
        "/api/v1/bookings",
        json={
            "entity_type": "experience",
            "entity_id": str(sample_experience.id),
            "participants": 1,
        },
        headers=auth_headers,
    )
    booking_id = create_resp.json()["booking"]["id"]

    resp = await client.get(f"/api/v1/bookings/{booking_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["booking"]["id"] == booking_id


@pytest.mark.asyncio
async def test_get_booking_not_found(
    client: AsyncClient,
    auth_headers: dict,
):
    resp = await client.get(f"/api/v1/bookings/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_booking_forbidden(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    sample_experience: Experience,
):
    create_resp = await client.post(
        "/api/v1/bookings",
        json={
            "entity_type": "experience",
            "entity_id": str(sample_experience.id),
            "participants": 1,
        },
        headers=auth_headers,
    )
    booking_id = create_resp.json()["booking"]["id"]

    third_user = User(id=uuid.uuid4(), phone="+213555000011")
    db.add(third_user)
    await db.commit()

    from app.core.security import create_access_token
    third_token = create_access_token(str(third_user.id), "traveler")
    third_headers = {"Authorization": f"Bearer {third_token}"}
    resp = await client.get(f"/api/v1/bookings/{booking_id}", headers=third_headers)
    assert resp.status_code == 403


# ── PUT /bookings/{id}/status ──────────────────────────────────────


@pytest.mark.asyncio
async def test_provider_confirms_booking(
    client: AsyncClient,
    auth_headers: dict,
    provider_headers: dict,
    sample_experience: Experience,
):
    create_resp = await client.post(
        "/api/v1/bookings",
        json={
            "entity_type": "experience",
            "entity_id": str(sample_experience.id),
            "participants": 2,
        },
        headers=auth_headers,
    )
    booking_id = create_resp.json()["booking"]["id"]

    resp = await client.put(
        f"/api/v1/bookings/{booking_id}/status",
        json={"status": "confirmed"},
        headers=provider_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["booking"]["status"] == "confirmed"


@pytest.mark.asyncio
async def test_traveler_can_only_cancel(
    client: AsyncClient,
    auth_headers: dict,
    sample_experience: Experience,
):
    create_resp = await client.post(
        "/api/v1/bookings",
        json={
            "entity_type": "experience",
            "entity_id": str(sample_experience.id),
            "participants": 1,
        },
        headers=auth_headers,
    )
    booking_id = create_resp.json()["booking"]["id"]

    resp = await client.put(
        f"/api/v1/bookings/{booking_id}/status",
        json={"status": "confirmed"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_traveler_can_cancel(
    client: AsyncClient,
    auth_headers: dict,
    sample_experience: Experience,
):
    create_resp = await client.post(
        "/api/v1/bookings",
        json={
            "entity_type": "experience",
            "entity_id": str(sample_experience.id),
            "participants": 1,
        },
        headers=auth_headers,
    )
    booking_id = create_resp.json()["booking"]["id"]

    resp = await client.put(
        f"/api/v1/bookings/{booking_id}/status",
        json={"status": "cancelled"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["booking"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cannot_update_cancelled_booking(
    client: AsyncClient,
    auth_headers: dict,
    provider_headers: dict,
    sample_experience: Experience,
):
    create_resp = await client.post(
        "/api/v1/bookings",
        json={
            "entity_type": "experience",
            "entity_id": str(sample_experience.id),
            "participants": 1,
        },
        headers=auth_headers,
    )
    booking_id = create_resp.json()["booking"]["id"]

    await client.put(
        f"/api/v1/bookings/{booking_id}/status",
        json={"status": "cancelled"},
        headers=auth_headers,
    )

    resp = await client.put(
        f"/api/v1/bookings/{booking_id}/status",
        json={"status": "confirmed"},
        headers=provider_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_invalid_status_transition(
    client: AsyncClient,
    auth_headers: dict,
    provider_headers: dict,
    sample_experience: Experience,
):
    create_resp = await client.post(
        "/api/v1/bookings",
        json={
            "entity_type": "experience",
            "entity_id": str(sample_experience.id),
            "participants": 1,
        },
        headers=auth_headers,
    )
    booking_id = create_resp.json()["booking"]["id"]

    resp = await client.put(
        f"/api/v1/bookings/{booking_id}/status",
        json={"status": "completed"},
        headers=provider_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_provider_completes_confirmed_booking(
    client: AsyncClient,
    auth_headers: dict,
    provider_headers: dict,
    sample_experience: Experience,
):
    create_resp = await client.post(
        "/api/v1/bookings",
        json={
            "entity_type": "experience",
            "entity_id": str(sample_experience.id),
            "participants": 4,
        },
        headers=auth_headers,
    )
    booking_id = create_resp.json()["booking"]["id"]

    await client.put(
        f"/api/v1/bookings/{booking_id}/status",
        json={"status": "confirmed"},
        headers=provider_headers,
    )

    resp = await client.put(
        f"/api/v1/bookings/{booking_id}/status",
        json={"status": "completed"},
        headers=provider_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["booking"]["status"] == "completed"
