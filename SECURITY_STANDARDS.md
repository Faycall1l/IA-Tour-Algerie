# ATHAR Security Standards

This document is the security baseline for the ATHAR API. It is derived from the
following trusted, widely-adopted sources:

| Source | Version | Scope |
| --- | --- | --- |
| [OWASP API Security Top 10](https://owasp.org/API-Security/editions/2023/en/) | 2023 | Top API risks |
| [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) | 4.0.x | Detailed app verification requirements |
| [OWASP Cheat Sheets](https://cheatsheetseries.owasp.org/) | current | Password storage, authentication, REST, headers, CORS, CSRF, JWT, injection prevention |
| [OWASP Top 10](https://owasp.org/www-project-top-ten/) | 2021 | Web app risks (CWE mapping) |
| [CWE Top 25](https://cwe.mitre.org/top25/) | 2023 | Most dangerous CWEs |
| [NIST SP 800-63B](https://pages.nist.gov/800-63-3/sp800-63b.html) | 3 | Digital identity guidelines (password/authenticator policy) |
| [RFC 9106](https://www.rfc-editor.org/info/rfc9106) | — | Argon2 parameter guidance |
| [RFC 7519 / 8725](https://www.rfc-editor.org/rfc/rfc8725) | — | JWT best practices / JSON Web Token |
| FastAPI / Starlette docs | current | Framework-specific hardening |

Compliance target: **OWASP ASVS Level 1 + API Security Top 10**, i.e. the
controls a stateless, JSON-only, bearer-token API must meet for production.

---

## 1. Authorization (API1 BOLA / API5 BFLA, CWE-639)

- Every handler that resolves an object from a user-supplied ID must check the
  caller may access **that** object — not just that they are authenticated
  (OWASP API Top 10 #1).
- Resource ownership checks: a user may only read/update/delete their own
  favorites, collections, trips, sessions, memories, profiles.
- Role-gated endpoints (`provider`, `admin`) must use a dedicated dependency
  (`get_provider_or_admin`, `get_current_admin`), applied at the route level —
  never left to a check inside the handler body.
- Use non-sequential identifiers (UUIDs) everywhere; do not expose DB row IDs.
- Object property level: response models must be explicit (Pydantic `model_config
  = ConfigDict(from_attributes=True)`) so no field is serialized by accident.
  Never return ORM objects directly.

## 2. Authentication (API2, ASVS V2, CWE-287)

- **Password policy**: minimum 12 characters; no upper bound truncation;
  printable Unicode allowed (no composition rules). Reject a blocklist of the
  1000+ most common breached passwords (OWASP ASVS 2.1.1 / 2.1.7).
- **Password storage** (ASVS 2.4.1, OWASP Password Storage Cheat Sheet):
  salted + hashed with **Argon2id** — minimum `m=19456 (19 MiB), t=2, p=1`
  (preferred `m=47104 (46 MiB), t=1, p=1`). Random salt ≥ 32 bits, stored in the
  hash string. Never MD5/SHA-*/plaintext.
- **Login**: identical error for unknown user vs wrong password; verify against a
  dummy hash when the user does not exist (timing-attack / user-enumeration
  protection, ASVS 2.1.1 note in FastAPI docs).
- **Anti-automation** (ASVS 2.2.1): rate-limit auth endpoints (`/login`, OTP
  issue/verify, registration) harder than general endpoints. No more than
  ~100 failed attempts per hour per account. OTP store: TTL + size cap.
- **One-time codes** generated with `secrets`/CSPRNG only; returned in body
  **only** for a non-production build; short TTL; constant-time comparison.
- **Sensitive changes require re-authentication** (password change, email
  change) — current password prompt.
- **JWT** (RFC 7519 / 8725):
  - Verify with a pinned `algorithms=["HS256"]` list (or asymmetric set). Never
    trust the `alg` header (rejects `alg:none` and algorithm-confusion).
  - Validate `exp` (library default); require `sub` present and a string.
  - Access tokens short-lived (≤ 60 min; 15–30 recommended). Refresh tokens
    opaque, server-stored (hashed), rotated on use, revocable.
  - Never put passwords/emails/secrets in the payload.
  - Signing key: high-entropy, from environment, persisted (multi-worker stable),
    file mode 0600, never committed.
  - Use a single vetted auth mechanism for all pathways (ASVS 1.2.3).

## 3. Session & Tokens (ASVS V3)

- Tokens travel in `Authorization: Bearer <jwt>` header, never in URLs.
- No cookies used today ⇒ CSRF formally N/A (browser cannot auto-attach a bearer
  header; see §9). If cookies are ever introduced, they must be
  `__Host-`-prefixed, `Secure; HttpOnly; SameSite=Lax|Strict`, and CSRF defense
  (signed double-submit or synchronizer) becomes mandatory.
- No secrets in logs, URLs, or error bodies.

## 4. Input Validation, Injection, SSRF (ASVS V5, API6, CWE-79/89/918)

- All request bodies validated by Pydantic models (types, lengths, `EmailStr`).
- All DB access via SQLAlchemy ORM / bound parameters. No string-concatenated SQL.
- Search terms and other free text are treated as data (parameterized, escaped).
- If any server-side URL fetch is added: allowlist schemes/hosts, reject private
  IP ranges, never follow user-supplied URLs to internal services (SSRF).
- XML parsing: reject external entities (XXE) if XML is ever accepted.
- Untrusted files: validate magic bytes + allowlisted content types, randomize
  stored names, size limits (see §7).

## 5. Cryptography (ASVS V6, CWE-327)

- Password hashing: Argon2id (§2). No custom crypto.
- JWT signing: HS256 with ≥ 256-bit key, or Ed25519 (persisted key).
- Secrets: environment variables / `.env` (gitignored); a secrets manager for
  production. No hardcoded credentials in code or committed config.
- Hash refresh tokens with SHA-256 at rest (they are high-entropy).

## 6. Rate Limiting & Resource Consumption (API4, API8, CWE-400/770)

- Rate limit ALL endpoints; stricter limits on auth endpoints and on object
  creation (POI/photo upload).
- Limit keys: client IP (trusted reverse-proxy handling) and, for auth, account.
- In-memory fallback is acceptable for single-process dev; production must use
  the shared Redis store so limits hold across workers.
- `FORWARDED_ALLOW_IPS` must default to loopback-only so a forged
  `X-Forwarded-For` cannot bypass per-IP limits.
- Response payloads paginated and capped (limit ≤ 50).
- No unbounded loops/aggregations over user-controlled counts.

## 7. File Upload / Storage (CWE-434, CWE-79)

- Magic-byte sniffing (JPEG/PNG/WebP) + content-type allowlist before storing.
- Random object keys; serve with `Content-Type` set from the stored metadata.
- Reject SVG/HTML that could be used for stored XSS unless explicitly allowed
  and sanitized.
- Size caps; storage in a private MinIO bucket; public URLs only for intended
  content (POI photos).
- Never reflect file content into responses as HTML.

## 8. Security Headers & Transport (OWASP REST Security, HSTS)

Sent on **every** HTTP response (browsers and non-browser clients alike):

| Header | Value | Purpose |
| --- | --- | --- |
| `X-Content-Type-Options` | `nosniff` | Prevent MIME sniffing |
| `X-Frame-Options` | `DENY` | Clickjacking (legacy) |
| `Content-Security-Policy` | `frame-ancestors 'none'; default-src 'none'` | Clickjacking (modern) |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Leak reduction |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` | Feature restriction |
| `Cache-Control` | `no-store` | Prevent sensitive caching |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` (production only) | Force HTTPS |

- HTTPS (TLS 1.2+) is mandatory in production; HSTS sent only over HTTPS.
- `Content-Type: application/json` explicitly on JSON responses.

## 9. CORS & CSRF (OWASP CORS/CSRF)

- CORS: explicit origin allowlist from settings; **never** `*` with
  `allow_credentials=True`; enumerate methods/headers; `max_age` capped.
- Bearer-header auth ⇒ CSRF not applicable today (§3). Documented exception:
  if cookie-based auth is ever enabled, add signed double-submit / synchronizer
  tokens and `SameSite` on all cookies.
- Always set `Vary: Origin` when CORS depends on origin.
- Treat `Origin: null` as hostile.

## 10. Errors, Logging & Monitoring (ASVS V7, API7, CWE-209)

- Return generic error messages to clients; never leak stack traces, SQL, or
  dependency details.
- Log security-relevant events (login success/failure, OTP issuance, role
  escalation, rate-limit hits, failed auth, object deletions) with a
  structured logger. No passwords/tokens/secrets in logs.
- Do not expose `/docs` or `/openapi.json` in production (API9 improper asset
  management, and recon aid). Gate behind a config flag.
- Unique correlation/request IDs in logs.

## 11. Configuration & Secrets Management (API7, ASVS V1)

- `Settings` sourced from environment with a unique prefix (`ATHAR_`).
- All secrets referenced from env; `.env` gitignored; `.env.example` contains
  only placeholders.
- No default credentials; no hardcoded keys; DB/Redis/MinIO creds set per env.
- Container: run as non-root (`user: "70:70"` for postgres); healthchecks
  without shell binaries absent from images; no service binds to the public
  interface unless intended.

## 12. Dependencies & Supply Chain (CWE-1104, CWE-937)

- Pin direct dependencies to exact versions in `requirements.txt` /
  `requirements-dev.txt` (repeatable builds).
- Keep a lock/SBOM of the transitive set; scan for known CVEs regularly.
- Prefer widely-maintained libraries (PyJWT, pwdlib/argon2-cffi, SQLAlchemy,
  Pydantic). No unmaintained or vendored crypto.

## 13. Application-level checks that are NOT in scope (N/A)

- **CSRF tokens**: N/A while auth is bearer-only (see §9). Revisit if cookies.
- **HTML/XSS (reflected/stored)**: the API returns JSON only; no HTML rendering.
  Still enforced via headers (§8) and upload allowlist (§7).
- **Client-side CSP/TLS termination**: handled by the deployment (reverse
  proxy/WAF); the app still emits headers and enforces transport via settings.

---

## 14. Audit Findings & Remediation (2026-08)

Full code audit against the sections above, plus fixes. Commit hashes in `git log`.

### Fixed

| # | Severity | Finding | Fix |
| --- | --- | --- | --- |
| 1 | **Critical** | `PUT /users/me/role` accepted any `USER_ROLES` value incl. `admin` → any authenticated user could escalate to admin (BFLA, §1). | Restricted to `SELF_ASSIGNABLE_ROLES = (traveler, guide, agency, hotel)` in the schema **and** defensively in the endpoint (403); `admin`/`artisan` not self-assignable. Tests added. |
| 2 | **High** | Fallback OTP `verify-otp` had no per-phone attempt limit (only 20/min per IP → brute-forceable with rotated IPs) and non-constant-time code comparison (§2). | Per-phone lockout (5 wrong attempts invalidates the code), `secrets.compare_digest` constant-time compare, and a per-phone send throttle (3/10 min) on the fallback to blunt SMS bombing. Tests added. |
| 3 | **High** | Replaying a revoked (previously used) refresh token only got 401; the token family kept rotating → stolen-token replay not detected (§2/§3). | Presenting a revoked token now revokes the **entire family**, invalidating rotated peers (OWASP token-reuse detection). Tests added. |
| 4 | **Medium** | `get_current_user` / optional never checked `is_active`, so a deactivated account could keep using tokens (§2). | Mandatory path → 401; optional path → treated as anonymous. Test added. |
| 5 | **Medium** | `/docs` + `/openapi.json` always exposed (API9, §10); `allowed_hosts` defaulted to `["*"]` (DNS rebinding / Host injection, §11); no CSP/HSTS/Cache-Control headers on responses (§8). | Docs/Redoc/OpenAPI gated behind `settings.debug`. `allowed_hosts` defaults to loopback only (`ATHAR_ALLOWED_HOSTS` JSON override; tests pre-set it). Headers now include `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`, HSTS (prod only), and `Cache-Control: no-store` on `/auth/*` and `/users/me`. |
| 6 | **Medium** | Method-level sliding-window rate limit was per-process in-memory even when Redis was up → limits multiplied by worker count (§6). | `SlidingWindowCounter` now uses a Redis sorted set per key when Redis is reachable (shared across workers, pruning + TTL), in-memory fallback, fail-open on Redis errors. Tests added. |

### Reviewed and confirmed OK

- **Mass assignment**: `UserUpdate` (PUT /users/me) only exposes benign profile
  fields — no `role`/`is_active`/`phone` (schema-level, §1). Locked in by test.
- **`register-provider`**: `provider_type` is schema-restricted to
  `guide|agency|hotel` and requires authentication — no escalation path.
- **Uploads** (§7): magic-byte sniffing, content-type allowlist, 10 MB cap,
  random object keys, MinIO public policy limited to `GetObject`.
- **JWT** (§2/§5): `decode_token` pins algorithms, validates `type`/`exp`;
  Ed25519 key persisted mode-0600; refresh tokens SHA-256 hashed at rest.
- **SQL**: all ORM / bound parameters; no string-concatenated queries.
- **Secrets**: no hardcoded creds in `app/` or `scripts/`; `.env` gitignored.
- **Errors** (§10): generic 500 body, no stack/SQL leakage; `admin.py` fully
  gated by `get_current_admin`.

---

## Compliance Checklist

Run before every release. Each item maps to a section above.

- [ ] All `/api/v1/.../{id}` handlers enforce ownership/role (1)
- [ ] No self-assignable privileged roles; role changes validated at schema +
      endpoint level (1)
- [ ] Passwords: Argon2id, ≥ 12-char policy, breached-blocklist (2)
- [ ] Auth endpoints rate-limited; OTP TTL+capped+attempt-locked, constant-time
      compare, per-phone send throttle; dummy-hash verify (2)
- [ ] `jwt.decode` pins `algorithms`; `exp` + `sub` validated (2)
- [ ] Inactive accounts rejected at auth boundary (2)
- [ ] Refresh tokens hashed at rest, rotated, family revoked on replay (2, 3)
- [ ] No secrets in code, logs, or commits; `.env` gitignored (5, 11)
- [ ] All SQL is parameterized (4)
- [ ] Uploads: magic-byte + content-type allowlist (7)
- [ ] Security headers on all responses, incl. CSP + HSTS (8)
- [ ] CORS explicit allowlist, no `*` + credentials (9)
- [ ] `/docs` + `/openapi.json` disabled in production (10)
- [ ] Trusted hosts allowlisted (no `*`) (11)
- [ ] Rate limiter shared across workers (Redis) (6)
- [ ] Dependencies pinned; `pip-audit`/`pip check` clean (12)
