# Authentication System

## Overview

Passwordless OTP auth via phone number. JWT access tokens (EdDSA/Ed25519) + refresh token rotation with reuse detection.

```
Phone → /send-otp → SMS/WhatsApp OTP → /verify-otp → {access_token, refresh_token}
                                                      → /refresh → new token pair
```

All auth endpoints are rate-limited via slowapi middleware.

## Endpoints

### `POST /api/v1/auth/send-otp`

Rate limited: **10/minute**.

```json
{ "phone": "+213555123456" }
```

Response (200):
```json
{ "message": "OTP sent", "expires_in": 300 }
```

**Logic**:
- Validate phone format (starts with `+213`, 10-13 chars).
- **Stub**: Always uses `"123456"` as OTP. Production would call Twilio Verify API.
- Rate limited to 10 requests per minute per IP.

### `POST /api/v1/auth/verify-otp`

Rate limited: **20/minute**.

```json
{ "phone": "+213555123456", "otp": "123456" }
```

Response (200):
```json
{
  "access_token": "eyJ...",
  "refresh_token": "dGhpcyBpcyBh...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": { "id": "...", "phone": "+213555123456", "role": "traveler", "is_onboarded": false }
}
```

**Logic**:
- Verify OTP (stub: check `== "123456"`).
- `get_or_create_user` — creates `User` if phone not found.
- Generate EdDSA-signed access token (15 min) + refresh token (30 days).
- Store refresh token SHA-256 hash in DB (`RefreshToken` table) with family UUID.
- Return user profile — if `is_onboarded` is false, client should redirect to onboarding.

### `POST /api/v1/auth/refresh`

Rate limited: **20/minute**.

```json
{ "refresh_token": "dGhpcyBpcyBh..." }
```

Response (200): Same as verify-otp (new token pair).

**Logic**:
- Look up refresh token SHA-256 hash in DB.
- **Reuse detection**: If token not found (already rotated), invalidate all tokens for that user (stolen token mitigation).
- Rotate: revoke old hash, insert new with same family.
- Return new access + refresh.

## JWT Format

```python
{
  "sub": user_id (UUID),
  "role": "traveler" | "guide" | "agency" | "hotel" | "admin",
  "type": "access" | "refresh",
  "iss": "ATHAR OS (أثر)",
  "aud": "ATHAR OS (أثر)",
  "iat": timestamp,
  "exp": timestamp,
  "jti": UUID (unique per token)
}
```

- **Algorithm**: EdDSA (Ed25519) — asymmetric, per RFC 8725bis (June 2026 BCP).
- **Key**: Ed25519 private key loaded from `AUTH__JWT_PRIVATE_KEY` env var. Auto-generated at startup if not set (tokens invalidated on restart).
- **Access token**: 15 minutes.
- **Refresh token**: 30 days.

### Why EdDSA over HS256

| | HS256 | EdDSA (Ed25519) |
|---|-------|-----------------|
| Key type | Symmetric (shared secret) | Asymmetric (key pair) |
| Verification speed | Fast | **8× faster** |
| Signature size | 32 bytes | 64 bytes |
| Key size | Any | 32 bytes |
| Key distribution | Must share secret | Only public key for verification |
| Standard | RFC 7518 | RFC 8037 |
| BCP status | Allowed but not recommended | **Recommended** by RFC 8725bis |

## Refresh Token Rotation

```
Initial: issue Token_A (stored hash, family=X)
Refresh:  Token_A found → revoke Token_A, issue Token_B (family=X)
Replay:   Token_A used again → not found in DB → revoke ALL family=X tokens
```

## Role-Based Access Control

| Role | Can |
|------|-----|
| `traveler` | Create reviews, book experiences, create live posts |
| `guide` | All traveler + create own experiences |
| `agency` | All traveler + create experiences |
| `hotel` | All traveler + create experiences |
| `admin` | All + delete any content, moderate price reports |

**Enforcement**:
- `get_current_user` dependency: extracts user from JWT, validates EdDSA signature + all claims (`exp`, `iat`, `iss`, `aud`, `jti`), fetches from DB.
- `get_current_admin` dependency: wraps `get_current_user`, checks `.role == "admin"`.
- View-level checks in endpoint logic (e.g., only author can edit their experience).

## Future
- Real Twilio Verify API integration.
- Redis-backed rate limiting (currently in-memory).
- Device management (list/revoke sessions).
- OAuth for Google/Apple (post-MVP).
