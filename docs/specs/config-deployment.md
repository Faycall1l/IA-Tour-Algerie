# Configuration & Deployment

## Configuration (`app/core/config.py`)

Uses **pydantic-settings** with nested model hierarchy:

```
Settings
├── app_name: str = "ATHAR OS"
├── app_version: str = "0.3.0"
├── debug: bool = False
├── allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
│
├── database: DatabaseSettings
│   ├── url: str = "postgresql+asyncpg://athar:athar_pass@localhost:5432/athar_db"
│   ├── pool_size: int = 10          │   ├── max_overflow: int = 5
│   ├── pool_pre_ping: bool = True   │   ├── pool_recycle: int = 1800
│   └── pool_timeout: int = 30
│
├── qdrant: QdrantSettings
│   ├── host: str = "localhost"
│   ├── port: int = 6333
│   ├── grpc_port: int = 6334
│   ├── prefer_grpc: bool = True      │   └── api_key: str = ""               │
├── redis: RedisSettings
│   ├── host: str = "localhost"
│   ├── port: int = 6379
│   ├── db: int = 0
│   ├── password: str = ""
│   └── otp_ttl_seconds: int = 300
│
├── minio: MinIOSettings
│   ├── endpoint: str = "localhost:9000"
│   ├── access_key: str = "minioadmin"
│   ├── secret_key: str = "minioadmin"
│   ├── bucket: str = "athar-uploads"
│   ├── secure: bool = False
│   └── public_url: str = ""
│
├── auth: AuthSettings
│   ├── jwt_private_key: str = ""      # Ed25519 PEM — generated at startup if empty
│   ├── jwt_public_key: str = ""
│   ├── jwt_algorithm: str = "EdDSA"
│   ├── access_token_expire_minutes: int = 15
│   └── refresh_token_expire_days: int = 30
│
└── twilio: TwilioSettings
    ├── account_sid: str = ""
    ├── auth_token: str = ""
    └── verify_service_sid: str = ""
```

All values overrideable via environment variables with double-underscore nesting:
- `DATABASE__URL=postgresql+asyncpg://...`
- `QDRANT__HOST=qdrant.internal`
- `QDRANT__API_KEY=my-key`
- `AUTH__JWT_PRIVATE_KEY=...` (Ed25519 PEM)

### Singleton Pattern

```python
# app/core/config.py
settings = Settings()
```
Imported directly: `from app.core.config import settings`.

---

## Docker

### Dockerfile (multi-stage, Python 3.14)

```
Stage 1: python:3.14-slim (builder)
  - Install build deps (gcc, libpq-dev)
  - pip install --user -r requirements.txt

Stage 2: python:3.14-slim (non-root)
  - Create appuser (UID 1000) with group
  - Copy site-packages from stage 1
  - Copy app code as appuser
  - HEALTHCHECK: curl /health
  - CMD: uvicorn with --proxy-headers --forwarded-allow-ips
```

### docker-compose.yml (hardened)

```yaml
services:
  api:
    build: .
    ports: ["127.0.0.1:8000:8000"]     # Localhost only
    secrets: [db_password]
    networks: [backend]
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 512M

  db:
    image: postgres:16.4-alpine
    user: "999:999"                      # Non-root
    expose: ["5432"]                     # Internal only
    tmpfs: [/tmp, /var/run/postgresql]
    cap_drop: [ALL]
    secrets: [db_password]               # Password via file, not env

  qdrant:
    image: qdrant/qdrant:1.18.2
    environment:
      QDRANT__SERVICE__API_KEY: "${QDRANT_API_KEY:-}"

  redis:
    image: redis:7.4-alpine
    command: ["redis-server", "--requirepass", "${REDIS_PASSWORD:-redispass}"]

  minio:
    image: minio/minio:RELEASE.2026-04-17T00-00-00Z
    expose: ["9000", "9001"]             # Internal only
```

Key security measures:
- All internal services use `expose:` not `ports:` — only reachable via Docker DNS
- API port bound to `127.0.0.1` only (not `0.0.0.0`)
- All containers: `cap_drop: ALL`, `no-new-privileges`, non-root user
- DB password via Docker secrets mounted at `/run/secrets/db_password`
- Resource limits (CPU + memory) on every container
- Isolated `backend` network (no external access)
- Pinned image tags (no `:latest`)

---

## CI/CD (`.github/workflows/ci.yml`)

```yaml
on: push
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.14" }
      - run: pip install ruff
      - run: ruff check app/
      - run: ruff format --check app/

  types:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.14" }
      - run: pip install mypy
      - run: mypy app/

  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env: { POSTGRES_USER: athar, POSTGRES_PASSWORD: athar_pass, POSTGRES_DB: athar_test }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.14" }
      - run: pip install -r requirements.txt pytest httpx pytest-asyncio
      - run: pytest --cov=app --cov-report=term-missing -v
        env:
          DATABASE__URL: postgresql+asyncpg://athar:athar_pass@localhost:5432/athar_test
          DEBUG: "false"
```

Pipeline:
1. **ruff lint** — PEP8 + style rules (100 char lines)
2. **ruff format --check** — auto-formatter consistency
3. **mypy** — strict static type checking
4. **pytest** — async tests against PG service container

---

## Code Quality (`pyproject.toml`)

```toml
[project]
requires-python = ">=3.14"

[tool.ruff]
target-version = "py314"
line-length = 100

[tool.mypy]
python_version = "3.14"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## Dependency Versions (as of July 2026)

| Package | Version | Notes |
|---------|---------|-------|
| Python | 3.14.6 | JIT compiler, Android support |
| FastAPI | 0.139.0 | Requires Python ≥3.10 |
| SQLAlchemy | 2.0.38 | `[asyncio]` extra for async |
| asyncpg | 0.30.0 | Native async Postgres driver |
| Alembic | 1.15.0 | Async migration runner |
| PyJWT | 2.13.0 | `[cryptography]` extra for EdDSA |
| Qdrant | 1.18.2 | gRPC, audit logging, API key auth |
| sentence-transformers | 3.4.0 | `[onnx]` extra for 2-3x speedup |
| MinIO | 2026-04-17 | OIDC/LDAP hardening |
| Redis | 7.4 | Password auth |
| Uvicorn | 0.34.0 | `[standard]` includes websockets |
