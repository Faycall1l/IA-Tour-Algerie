# Security & Data Sovereignty

## Loi 18-07 Compliance

Algeria's Law 18-07 (July 2018) mandates that:
- Personal data of Algerian citizens must be processed and stored within Algeria.
- Cross-border transfer requires explicit consent or legal basis.
- Data controllers must register with ANPDP (National Authority for Personal Data Protection).

### How ATHAR OS Complies

| Requirement | Implementation |
|-------------|---------------|
| Data stored in-country | All services self-hosted (PostgreSQL, Qdrant, MinIO, Redis) — no foreign cloud storage |
| PII not exported externally | PII stripped before any external API calls (see data flow below) |
| User consent | Implicit via account creation; explicit consent collected during onboarding |
| Data minimization | Only essential fields collected (phone, optional display name) — no email, no address |
| Right to deletion | DELETE endpoints for reviews, live posts, bookings; user account deletion planned |

### Data Flow Diagram

```
                    ┌──────────────┐
                    │  In-Country  │
                    │  (Self-Host) │
                    │              │
  User Data ──────► │  PostgreSQL  │
  (phone, name)     │  Qdrant      │
                    │  MinIO       │
                    │  Redis       │
                    └──────┬───────┘
                           │
                           │ Non-PII only
                           ▼
                    ┌──────────────┐
                    │  External    │
                    │  APIs        │
                    │              │
                    │  Twilio API  │  (OTP sending, future)
                    └──────────────┘
```

**Rule**: Before any external API call, all PII fields (phone, name) are stripped. Only anonymous content (text, embeddings) leaves the server.

## Authentication Security

| Measure | Detail |
|---------|--------|
| Passwordless | No passwords to leak or brute-force |
| JWT algorithm | **EdDSA (Ed25519)** — asymmetric, per RFC 8725bis (June 2026) |
| Access token | 15 min expiry — 5× faster verification than RS256 |
| Refresh rotation | Each refresh invalidates previous token (token family) |
| Reuse detection | Stolen token play → all user tokens revoked |
| Rate limiting | 10/min OTP send, 20/min verify+refresh via slowapi |
| Token storage | SHA-256 hash in DB, never raw |
| Claims validation | `exp`, `iat`, `iss`, `aud`, `jti` all required on decode |

## API Security

| Measure | Detail |
|---------|--------|
| CORS | Explicit origins (`localhost:3000`, `localhost:5173`) — no wildcard |
| Security headers | X-Content-Type-Options, X-Frame-Options, Permissions-Policy, Referrer-Policy |
| TrustedHostMiddleware | Prevents host header injection |
| Rate limiting | slowapi with in-memory backend (Redis planned) |
| Role-based access | `get_current_admin` guards admin endpoints |
| Ownership checks | Only author/admin can delete/modify resources |
| Input validation | Pydantic schemas with strict types, field constraints |
| SQL injection | Impossible with SQLAlchemy ORM + parameterized queries |

## Docker Security

| Measure | Detail |
|---------|--------|
| Non-root containers | All services run as non-root (postgres UID 999, app UID 1000) |
| Capability drop | `cap_drop: ALL` on every container |
| No new privileges | `security_opt: no-new-privileges:true` everywhere |
| Resource limits | Memory + CPU limits prevent DoS from runaway containers |
| No exposed internals | PostgreSQL, Redis, Qdrant, MinIO have no external ports |
| Image pinning | All images pinned to specific versions (no `:latest`) |
| Secrets via files | DB password mounted at `/run/secrets/db_password` |
| Network isolation | All services on isolated `backend` bridge network |

## File Upload Security

| Measure | Detail |
|---------|--------|
| File type whitelist | Only `.jpg`, `.jpeg`, `.png`, `.webp` accepted |
| Size limit | 10 MB max — prevents disk fill |
| UUID filenames | No user-controlled filenames (no path traversal) |
| Non-root container | Docker runs as `appuser` |
| Public-read only | No write access from outside the API |

## Data Privacy

- **Phone numbers**: The only required PII. Not exposed in any list endpoint. Only returned to the owner via `GET /users/me`.
- **Display names**: Optional. Used in public contexts (review author, live post author).
- **Avatar URLs**: Optional. Public MinIO URLs.
- **No email**: Deliberately omitted. Phone is the identifier.
- **No location tracking**: Latitude/longitude are for POI coordinates, not user tracking.
- **Minimal logging**: structlog logs correlation IDs and request paths, not request bodies or PII. OTP code never logged.

## Future Security Items

1. **Redis-backed rate limiting** — replace slowapi's in-memory backend.
2. **Honeypot tokens** for refresh reuse detection with alerting.
3. **ANPDP registration** documentation.
4. **Data export endpoint** for GDPR-style user data requests.
5. **Account deletion** cascade (remove user + all associated data).
6. **Audit log** for admin actions (delete content, verify reports).
7. **TLS everywhere** — reverse proxy (Caddy/Traefik) for HTTPS termination, MinIO TLS, PostgreSQL SSL.
