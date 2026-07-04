# Configuration & Deployment

## Configuration (`app/core/config.py`)

Uses **pydantic-settings** with nested model hierarchy:

```
Settings
├── app_name: str = "ATHAR OS"
├── debug: bool = False
├── environment: str = "development"
├── allowed_hosts: list[str] = ["*"]
│
├── database: DatabaseSettings
│   ├── host: str = "localhost"
│   ├── port: int = 5432
│   ├── user: str = "athar"
│   ├── password: str = "athar"
│   ├── name: str = "athar_db"
│   ├── pool_size: int = 20
│   └── pool_pre_ping: bool = True
│
├── qdrant: QdrantSettings
│   ├── host: str = "localhost"
│   ├── port: int = 6333
│   ├── prefer_grpc: bool = True
│   ├── collection_name_pois: str = "pois"
│   ├── collection_name_experiences: str = "experiences"
│   └── vector_size: int = 384
│
├── redis: RedisSettings
│   ├── host: str = "localhost"
│   ├── port: int = 6379
│   └── db: int = 0
│
├── minio: MinIOSettings
│   ├── endpoint: str = "localhost:9000"
│   ├── access_key: str = "minioadmin"
│   ├── secret_key: str = "minioadmin"
│   ├── bucket_name: str = "athar-media"
│   ├── use_ssl: bool = False
│   └── public_url: str = "http://localhost:9000"
│
├── auth: AuthSettings
│   ├── secret_key: str (Auto-generated in dev, required in prod)
│   ├── access_token_expire_minutes: int = 60
│   └── refresh_token_expire_days: int = 30
│
└── twilio: TwilioSettings
    ├── account_sid: str = ""
    ├── auth_token: str = ""
    └── verify_service_sid: str = ""
```

All values overrideable via environment variables:
- `DATABASE__HOST=prod-db.internal`
- `QDRANT__HOST=qdrant.internal`
- `MINIO__ACCESS_KEY=...`

### Singleton Pattern

```python
@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

---

## Docker

### Dockerfile (multi-stage)

```
Stage 1: python:3.11-slim
  - Install build deps (gcc, ...)
  - Install Python deps (pip install -r requirements.txt)
  - Cleanup

Stage 2: python:3.11-slim (non-root)
  - Copy site-packages from stage 1
  - Copy app code
  - User: appuser (non-root)
  - HEALTHCHECK: curl /health
  - CMD: uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### docker-compose.yml

```yaml
version: "3.8"
services:
  api:
    build: .
    ports: ["8000:8000"]
    depends_on: [postgres, qdrant, redis, minio]
    environment:
      - DATABASE__HOST=postgres
      - QDRANT__HOST=qdrant
      - REDIS__HOST=redis
      - MINIO__ENDPOINT=minio:9000

  postgres:
    image: postgres:16-alpine
    volumes: [pgdata:/var/lib/postgresql/data]

  qdrant:
    image: qdrant/qdrant:latest
    volumes: [qdrant_storage:/qdrant/storage]

  redis:
    image: redis:7-alpine

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    volumes: [minio_data:/data]
```

---

## CI/CD (`.github/workflows/ci.yml`)

```yaml
on: push
jobs:
  test:
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: athar
          POSTGRES_PASSWORD: athar
          POSTGRES_DB: athar_db_test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -r requirements.txt
      - run: ruff check app/
      - run: ruff format --check app/
      - run: mypy app/
      - run: pytest tests/ -v --cov=app --cov-report=term
```

Pipeline:
1. **ruff lint** — checks PEP8 + style rules (100 char lines)
2. **ruff format --check** — enforces auto-formatter consistency
3. **mypy** — strict static type checking
4. **pytest** — runs async tests against PG service container

---

## Code Quality (`pyproject.toml`)

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
select = ["ALL"]
ignore = ["D", "COM812", "ISC001", "EM101", "EM102"]

[tool.mypy]
strict = true
ignore_missing_imports = true
disallow_untyped_defs = true
disallow_any_unimported = false

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```
