# Admin Dashboard

## Implementation

7 endpoints under `/api/v1/admin/`, protected by `get_current_admin` dependency (role check).

### Users

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/admin/users` | List all users (filter: `?role=`, `?verified=true/false`) |
| PUT | `/api/v1/admin/users/{id}/role` | Change role (`traveler`/`guide`/`agency`/`hotel`/`admin`), auto-creates/deletes ProviderProfile |
| PUT | `/api/v1/admin/users/{id}/verify` | Toggle `is_verified` |

### Provider Profiles

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/admin/providers` | List all provider profiles (filter: `?verified=true/false`, `?provider_type=`) |
| PUT | `/api/v1/admin/providers/{id}/approve` | Set `is_verified=true` |

### Content Moderation

| Method | Path | Description |
|--------|------|-------------|
| DELETE | `/api/v1/admin/experiences/{id}` | Delete any experience |

### Stats

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/admin/stats` | Dashboard stats: user count, POI count, experience count, stay count, recent activity |

### Schemas

```python
class UserAdminRead(BaseModel):
    # Includes id, phone, role, language, is_active, is_verified, display_name,
    # avatar_url, created_at

class UserAdminFeed(BaseModel):
    # Standard pagination wrapper

class AdminRoleUpdate(BaseModel):
    role: str  # Validated against USER_ROLES regex

class ProviderProfileAdminRead(BaseModel):
    # Includes id, user_id, provider_type, is_verified, company_name,
    # property_name, experience_years

class ProviderAdminFeed(BaseModel):
    # Standard pagination wrapper

class AdminActionResponse(BaseModel):
    message: str
```

### Test Coverage

Tests in `tests/api/v1/test_admin.py`:
- Non-admin gets 403
- Users: list, set role, toggle verification
- Providers: list, approve
- Content: delete experience

Fixtures in `tests/conftest.py`: `admin_user`, `admin_token`, `admin_headers`.

---

## Admin as Human-in-the-Loop

The admin dashboard is the **human oversight layer** for the [Agentic Traveler system](./agentic-traveler.md). When the traveler-facing AI agents encounter edge cases, they escalate to an admin through the existing endpoints:

| Traveler Agent | Escalation to Admin |
|---------------|-------------------|
| Trip Planner | Unclear destination mapping → admin reviews wilaya categorization |
| POI Scout | Low-confidence POI matches → admin reviews POI metadata |
| Provider Screener | Provider claims unverifiable → admin reviews documents |

The existing admin endpoints cover the human-in-the-loop surface. Future additions would be an **escalation queue** that aggregates items requiring admin attention, sorted by priority and agent confidence score.
