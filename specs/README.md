# ATHAR OS — Technical Specifications

[Architecture & Tech Stack](./architecture.md)
: Overall system design, stack decisions, tradeoffs

[Authentication](./auth.md)
: Passwordless OTP, JWT with refresh rotation, role-based access

[Database](./database.md)
: PostgreSQL schema, all models, alembic migrations, constraints

[API Layer](./api.md)
: Route index, conventions, pagination, error handling, middleware

[Services](./services.md)
: MinIO storage, sentence-transformers embeddings, Qdrant vector search, startup auto-indexing

[Configuration & Deployment](./config-deployment.md)
: pydantic-settings, Docker, docker-compose, CI/CD

[Security & Data Sovereignty](./security.md)
: Loi 18-07 compliance, data flow, PII handling

[Admin Dashboard](./admin.md)
: Admin endpoints, moderation, human-in-the-loop oversight

[Agentic Traveler](./agentic-traveler.md)
: AI trip planning, multi-agent orchestration, conversational travel companion
