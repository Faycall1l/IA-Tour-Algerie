# ATHAR OS — Technical Specifications

[Architecture & Tech Stack](./architecture.md)
: Overall system design, stack decisions, tradeoffs

[Authentication](./auth.md)
: Passwordless OTP, JWT with refresh rotation, role-based access

[Database](./database.md)
: PostgreSQL schema, all models, alembic migrations, constraints

[API Layer](./api.md)
: Route index, conventions, pagination, error handling, middleware

[Storage Service](./services-storage.md)
: MinIO file uploads, bucket policies, validation

[Embeddings & Vector Search](./services-vector.md)
: sentence-transformers, Qdrant collections, semantic search

[Configuration & Deployment](./config-deployment.md)
: pydantic-settings, Docker, docker-compose, CI/CD

[Security & Data Sovereignty](./security.md)
: Loi 18-07 compliance, data flow, PII handling
