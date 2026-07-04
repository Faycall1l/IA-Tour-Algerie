# Authentication System

## Overview

Passwordless OTP auth via phone number. JWT access tokens + refresh token rotation with reuse detection.

```
Phone → /send-otp → SMS/WhatsApp OTP → /verify-otp → {access_token, refresh_token}
                                                      → /refresh → new token pair
```

## Endpoints

### `POST /api/v1/auth/send-otp`

Request:
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
- Store OTP hash in memory with TTL (deferred — currently validated directly).

### `POST /api/v1/auth/verify-otp`

Request:
```json
{ "phone": "+213555123456", "otp": "123456" }
```

Response (200):
```json
{
  "access_token": "eyJ...",
  "refresh_token": "dGhpcyBpcyBh...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": { "id": "...", "phone": "+213555123456", "role": "traveler", "is_onboarded": false }
}
```

**Logic**:
- Verify OTP (stub: check `== "123456"`).
- `get_or_create_user` — creates `User` if phone not found.
- Generate access token (1h) + refresh token (30d).
- Store refresh token hash in DB (`RefreshToken` table) with device info.
- Return user profile — if `is_onboarded` is false, client should redirect to onboarding.

### `POST /api/v1/auth/refresh`

Request:
```json
{ "refresh_token": "dGhpcyBpcyBh..." }
```

Response (200): Same as verify-otp (new token pair).

**Logic**:
- Look up refresh token hash in DB.
- **Reuse detection**: If token not found (already rotated), invalidate all tokens for that user (stolen token mitigation).
- Rotate: delete old, insert new.
- Return new access + refresh.

## JWT Format

```python
{
  "sub": user_id (UUID),
  "phone": "+213555123456",
  "role": "traveler" | "guide" | "agency" | "hotel" | "admin",
  "exp": timestamp,
  "iat": timestamp,
  "type": "access" | "refresh"
}
```

- Signed with `HS256` using `SECRET_KEY` from config.
- Access token: 1 hour expiry.
- Refresh token: 30 days expiry (the JWT itself, separate from DB record).

## Refresh Token Rotation

```
Initial: issue Token_A (stored hash)
Refresh:  Token_A found → delete Token_A, issue Token_B (stored hash)
Replay:   Token_A used again → not found in DB → delete ALL user tokens (attack detected)
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
- `get_current_user` dependency: extracts user from JWT, fetches from DB.
- `get_current_admin` dependency: wraps `get_current_user`, checks `.role == "admin"`.
- View-level checks in endpoint logic (e.g., only author can edit their experience).
- No per-object permissions system yet (deferred).

## Future
- Real Twilio Verify API integration.
- OTP rate limiting via Redis.
- Device management (list/revoke sessions).
- OAuth for Google/Apple (post-MVP).
