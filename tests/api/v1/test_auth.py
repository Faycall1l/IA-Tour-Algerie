import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_send_otp(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/send-otp",
        json={"phone": "+213555123456"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["otp"] == "123456"
    assert data["message"] == "OTP sent successfully"


@pytest.mark.asyncio
async def test_verify_otp_creates_user(client: AsyncClient):
    phone = "+213555999999"
    await client.post("/api/v1/auth/send-otp", json={"phone": phone})
    resp = await client.post(
        "/api/v1/auth/verify-otp",
        json={"phone": phone, "code": "123456"},
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
async def test_refresh_token(client: AsyncClient):
    phone = "+213555888888"
    await client.post("/api/v1/auth/send-otp", json={"phone": phone})
    login = await client.post(
        "/api/v1/auth/verify-otp",
        json={"phone": phone, "code": "123456"},
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
