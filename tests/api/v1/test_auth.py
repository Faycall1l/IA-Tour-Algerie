import pytest
from app.api.v1.endpoints.auth import _otp_store
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_send_otp(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/send-otp",
        json={"phone": "+213555123456"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "OTP sent successfully"
    assert "+213555123456" in _otp_store


@pytest.mark.asyncio
async def test_verify_otp_creates_user(client: AsyncClient):
    phone = "+213555999999"
    await client.post("/api/v1/auth/send-otp", json={"phone": phone})
    code = _otp_store[phone]["code"]
    resp = await client.post(
        "/api/v1/auth/verify-otp",
        json={"phone": phone, "code": code},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["phone"] == phone


@pytest.mark.asyncio
async def test_verify_otp_bad_code(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/verify-otp",
        json={"phone": "+213555000000", "code": "000000"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "bad_request"


@pytest.mark.asyncio
async def test_debug_otp_rejected_when_debug_off(client: AsyncClient):
    # The fixed debug OTP must NOT grant access unless debug=True.
    resp = await client.post(
        "/api/v1/auth/verify-otp",
        json={"phone": "+213555777001", "code": "000000"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "bad_request"


@pytest.mark.asyncio
async def test_debug_otp_granted_when_debug_on(client: AsyncClient, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "debug_otp", "000000")
    resp = await client.post(
        "/api/v1/auth/verify-otp",
        json={"phone": "+213555777002", "code": "000000"},
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["phone"] == "+213555777002"


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    phone = "+213555888888"
    await client.post("/api/v1/auth/send-otp", json={"phone": phone})
    code = _otp_store[phone]["code"]
    login = await client.post(
        "/api/v1/auth/verify-otp",
        json={"phone": phone, "code": code},
    )
    refresh_token = login.json()["refresh_token"]

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_refresh_reuse_revokes_family(client: AsyncClient):
    phone = "+213555444444"
    await client.post("/api/v1/auth/send-otp", json={"phone": phone})
    code = _otp_store[phone]["code"]
    login = await client.post(
        "/api/v1/auth/verify-otp",
        json={"phone": phone, "code": code},
    )
    original_refresh = login.json()["refresh_token"]

    rotated = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert rotated.status_code == 200
    new_refresh = rotated.json()["refresh_token"]

    replay = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert replay.status_code == 401

    family_peer = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh},
    )
    assert family_peer.status_code == 401


@pytest.mark.asyncio
async def test_verify_otp_locks_after_attempts(client: AsyncClient):
    phone = "+213555777777"
    await client.post("/api/v1/auth/send-otp", json={"phone": phone})
    assert phone in _otp_store
    code = _otp_store[phone]["code"]

    for _ in range(5):
        resp = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": phone, "code": "000000"},
        )
        assert resp.status_code == 400

    assert phone not in _otp_store

    resp = await client.post(
        "/api/v1/auth/verify-otp",
        json={"phone": phone, "code": code},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_send_otp_throttled_per_phone(client: AsyncClient):
    phone = "+213555666666"
    for _ in range(3):
        resp = await client.post("/api/v1/auth/send-otp", json={"phone": phone})
        assert resp.status_code == 200

    resp = await client.post("/api/v1/auth/send-otp", json={"phone": phone})
    assert resp.status_code == 400

    other = await client.post("/api/v1/auth/send-otp", json={"phone": "+213555555555"})
    assert other.status_code == 200
