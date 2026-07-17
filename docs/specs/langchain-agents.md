# LangChain Agent Layer Architecture

## Rationale

Current custom services (`TripOptimizer`, `TripBriefGenerator`) are hand-rolled with no common framework — each has its own patterns for retries, error handling, and observability. This doesn't scale.

LangChain 1.0 (2026) provides a production-grade agent framework built around `create_agent` + composable middleware. It replaces two custom services out of the box (`langchain-qdrant`, `langchain-huggingface`).

**vLLM** (external, self-hosted) provides inference via OpenAI-compatible API — no data leaves Algeria.

## LangChain Packages

Only four packages, cherry-picked:

```
langchain               # core: create_agent, middleware, tools, structured output
langchain-openai        # vLLM via OpenAI-compatible API (no cloud dependency)
langchain-qdrant        # Qdrant vector store → replaces custom VectorSearchService
langchain-huggingface   # HuggingFaceEmbeddings → replaces custom EmbeddingService
```

No `langchain-community` (200+ unused integrations). No LangSmith/LangHub (cloud-dependent).

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      FastAPI Endpoints                        │
│  /trips/optimize  /discover/wilayas/16  /recommendations     │
└────────────────────────┬─────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────┐
│                    LangChain Agent Layer                      │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  create_agent(model, tools, system_prompt,            │    │
│  │               response_format=TripState,              │    │
│  │               middleware=[PII, Summarization, ...],   │    │
│  │               checkpointer=PostgresCheckpointer)      │    │
│  └────────────────────────┬─────────────────────────────┘    │
│                           │                                    │
│  ┌────────────────────────▼─────────────────────────────┐    │
│  │                Tool Registry (8-10 tools)              │    │
│  │  search_pois | get_price_estimate | find_nearby       │    │
│  │  get_experience | get_stay | geocode | review_summary │    │
│  └────────────────────────┬─────────────────────────────┘    │
│                           │                                    │
└───────────────────────────┼──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                    Existing Services                          │
│  POI CRUD · Price Reports · Experience Finder · Stay DB      │
│  Booking Engine · Trip CRUD · MinIO · PostgreSQL             │
└──────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                    LangChain Integrations                     │
│  ┌───────────────┐  ┌──────────────────┐                     │
│  │ langchain-    │  │ langchain-       │                      │
│  │ qdrant:       │  │ huggingface:     │                      │
│  │ vector store  │  │ embeddings       │                      │
│  │ retriever     │  │ model cache      │                      │
│  └───────────────┘  └──────────────────┘                     │
└──────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                    vLLM (external, self-hosted)               │
│  OpenAI-compatible API · GPU-backed · no data exfiltration   │
└──────────────────────────────────────────────────────────────┘
```

## LLM Configuration

```python
# app/core/agent.py
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url=settings.VLLM_BASE_URL,   # http://vllm.internal:8000/v1
    api_key=settings.VLLM_API_KEY or "",
    model=settings.VLLM_MODEL,          # "Qwen2.5-7B-Instruct"
    temperature=0.1,
    timeout=settings.VLLM_TIMEOUT,      # 30s
    max_retries=2,
)
```

Single shared instance. vLLM handles batching. No per-request LLM creation.

## Agent Definition

```python
from langchain.agents import create_agent
from langchain.agents.middleware import PIIMiddleware, SummarizationMiddleware
from langchain.agents.checkpointer import PostgresCheckpointer

agent = create_agent(
    model=llm,
    tools=trip_tools,
    system_prompt=TRIP_AGENT_PROMPT,
    response_format=TripState,           # Pydantic model → typed output
    context_schema=AgentContext,         # per-request: user_id, trip_id, etc.
    middleware=[
        PIIMiddleware(pattern=r"\+213\d{8,9}", strategy="redact"),
        SummarizationMiddleware(
            model=llm,
            trigger={"tokens": 4000},    # compress history at 4K tokens
        ),
        RetryMiddleware(max_retries=2),  # custom: retry on tool failures
    ],
    checkpointer=PostgresCheckpointer(
        connection_string=settings.DATABASE__URL,
    ),
    name="trip_agent",
)
```

### Structured output (`response_format=`)

LangChain 1.0 generates structured output in the main agent loop (no extra LLM call):

```python
# Returns typed Pydantic model, not free text
result = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Optimize trip 123"}]},
    config={"configurable": {"thread_id": str(trip_id)}},
    context=AgentContext(user_id=user_id, trip_id=trip_id),
)
trip_state: TripState = result["structured_response"]
```

Two strategies available:
- **`ToolStrategy`** — artificial tool calling (works with any model)
- **`ProviderStrategy`** — provider-native (if vLLM supports it)

Default is `ToolStrategy` which is universal. We start there.

### Context injection (`context_schema=`)

```python
class AgentContext(BaseModel):
    user_id: str
    trip_id: str | None = None
    locale: str = "en"

# Available in tool functions via runtime.context
@tool
async def search_pois(query: str, runtime: ToolRuntime) -> list[dict]:
    user_id = runtime.context.user_id  # no thread-local hacks
    ...
```

### Checkpointer

Postgres-based checkpointer means agent state survives server restarts. Supports horizontal scaling — any instance can resume any agent session. Threaded by `thread_id`.

## Middleware Stack

Middleware is the defining feature of `create_agent`. Each piece handles one concern, hooks into the agent loop at the right moment.

### Prebuilt middleware (use directly)

| Middleware | Purpose | We need it? |
|-----------|---------|-------------|
| `PIIMiddleware` | Redact phone numbers, emails, addresses before model call | ✅ Yes — Loi 18-07 compliance |
| `SummarizationMiddleware` | Compress conversation history when context window fills | ✅ Yes — prevents context overflow |
| `HumanInTheLoopMiddleware` | Require approval for sensitive tool calls (e.g., book) | ⏸️ Later — Phase 2 |
| `ToolRetryMiddleware` | Retry failed tool calls with backoff | ✅ Yes — production reliability |

### Custom middleware

Build via `AgentMiddleware` hooks:

```python
from langchain.agents.middleware import AgentMiddleware

class AtharLoggingMiddleware(AgentMiddleware):
    async def before_model(self, state, runtime):
        logger.info("model_call", tool_count=len(state.messages))
    async def after_tool(self, state, runtime, tool_call, result):
        logger.info("tool_complete", tool=tool_call.name, duration=result.duration)
    async def after_agent(self, state, runtime):
        logger.info("agent_done", response=state.structured_response)
```

| Hook | When | Use |
|------|------|-----|
| `before_agent` | Agent starts | Validate input, load session |
| `before_model` | Each LLM call | Inject context, trim messages |
| `wrap_model_call` | Around LLM call | Intercept/modify request |
| `wrap_tool_call` | Around tool call | Retry, timeout, circuit break |
| `after_model` | After LLM response | Validate output, guardrails |
| `after_tool` | After each tool | Logging, metrics increment |
| `after_agent` | Agent completes | Persist results, cleanup |

## Tool Design

### Principles

1. **All tools are async** — LangChain 1.0 supports native async tools. No sync workers needed.
2. **Every tool returns structured dicts** — never free text. Agent consumes typed data.
3. **Tools are stateless** — state lives in DB or Redis. Tools are pure functions of their inputs.
4. **Tools have timeouts** — each tool sets `timeout=10` to prevent blocking the agent loop.

### Tool Registry (~10 tools)

```python
# app/services/agent/registry.py
from langchain.tools import tool

@tool(timeout=10)
async def search_pois(
    query: str,
    wilaya_id: int | None = None,
    category: str | None = None,
    limit: int = 10,
    runtime: ToolRuntime = None,
) -> list[dict]:
    """Search points of interest by semantic query.
    Optionally filter by wilaya_id, category, or limit results."""
    store = langchain_qdrant.QdrantVectorStore(...)
    results = await store.asimilarity_search_with_score(query, k=limit)
    return [{"id": str(r.id), "name": r.name, ...} for r, score in results]

@tool(timeout=5)
async def get_price_estimate(
    item_type: str, item_id: str, runtime: ToolRuntime = None,
) -> dict:
    """Get fair price estimate for a POI or experience."""
    ...

@tool(timeout=5)
async def get_review_summary(
    item_type: str, item_id: str, runtime: ToolRuntime = None,
) -> dict:
    """Get aggregated review scores and recent highlights."""
    ...

@tool(timeout=10)
async def find_nearby(
    lat: float, lng: float, radius_km: float = 1.0,
    types: list[str] = ["poi", "experience", "stay"],
    runtime: ToolRuntime = None,
) -> list[dict]:
    """Find nearby POIs, experiences, or stays within radius."""
    ...

@tool(timeout=5)
async def geocode(address: str, runtime: ToolRuntime = None) -> dict:
    """Convert address to lat/lng coordinates."""
    ...

@tool(timeout=5)
async def estimate_travel_time(
    origin_lat: float, origin_lng: float,
    dest_lat: float, dest_lng: float,
    mode: str = "walking",
    runtime: ToolRuntime = None,
) -> dict:
    """Estimate travel time between two points."""
    ...

@tool(timeout=5)
async def get_opening_hours(
    poi_id: str, day: str | None = None,
    runtime: ToolRuntime = None,
) -> dict:
    """Get opening hours for a POI."""
    ...

@tool(timeout=5)
async def get_seasonal_context(
    wilaya_id: int, month: int, runtime: ToolRuntime = None,
) -> dict:
    """Get weather, events, and seasonal tips for a wilaya in a given month."""
    ...

@tool(timeout=5)
async def calculate_budget(
    items: list[dict], daily_budget: float | None = None,
    runtime: ToolRuntime = None,
) -> dict:
    """Calculate total cost, breakdown by day, and remaining budget."""
    ...
```

## Agents

### 1. TripAgent (immediate — replaces TripOptimizer + TripBriefGenerator)

```
Trigger: add/remove/reorder trip items, optimize request, brief request
Model: 0.1 temperature, deterministic
Tools: search_pois, get_price_estimate, find_nearby, geocode,
       estimate_travel_time, get_opening_hours, calculate_budget,
       get_review_summary, get_seasonal_context
Output: TripState (typed Pydantic)
```

**TripBriefGenerator** is not a separate agent — it's `TripAgent` with a different prompt:

```python
brief_agent = create_agent(
    model=llm,
    tools=trip_tools,
    system_prompt=BRIEF_AGENT_PROMPT,  # "Generate a trip brief for wilaya X"
    response_format=WilayaBrief,        # different output schema
    middleware=[PIIMiddleware(...)],
)
```

Both share the same tools. Different system prompt + response format.

### 2. RecommendAgent (Phase 2)

```
Trigger: page load, search results
Model: 0.3 temperature, creative
Tools: search_pois, find_nearby, get_seasonal_context, get_review_summary
Output: RecommendationFeed
```

Runs parallel to page render. Frontend gets results asynchronously.

### 3. AlertAgent (Phase 2)

```
Trigger: background cron (30 min), event-driven on booking/price report
Model: 0.0 temperature, deterministic classification
Tools: check_price_drops, check_booking_conflicts, check_weather_conflict,
       check_new_content, check_provider_availability
Output: AlertBatch (max 1 per user per hour)
```

### 4. IntentAgent (Phase 3)

```
Trigger: every user action (fire-and-forget)
Model: May not need LLM — keyword classifier first, upgrade later
Output: Updated UserIntent in Redis
```

This one might just be a lightweight classifier. No LLM cost.

## Structured Output Schemas

```python
from pydantic import BaseModel
from typing import Literal

class TripState(BaseModel):
    days: list[DayPlan]
    budget_spent: float
    budget_remaining: float
    gaps: list[TimeGap]
    optimization_score: float
    suggestions: list[Suggestion]

class DayPlan(BaseModel):
    day_number: int
    date: str
    items: list[PlannedItem]
    total_walk_km: float
    total_cost: float
    free_hours: float

class PlannedItem(BaseModel):
    item_id: str
    item_type: Literal["poi", "experience", "stay", "restaurant", "transport"]
    name: str
    start_time: str | None
    duration_minutes: int
    cost_dzd: float
    rationale: str | None  # why the agent placed it here

class TimeGap(BaseModel):
    day_number: int
    start_time: str
    duration_minutes: int
    suggestion: str | None

class Suggestion(BaseModel):
    type: Literal["reorder", "add", "remove", "replace"]
    rationale: str
    impact: str  # e.g., "Saves 30 min walking"

class WilayaBrief(BaseModel):
    wilaya_id: int
    name: str
    top_pois: list[dict]
    top_experiences: list[dict]
    typical_transport_cost: dict
    best_months: list[str]
    review_highlights: list[str]
    tips: list[str]
```

## Observability

### Prometheus metrics (via middleware)

```python
class MetricsMiddleware(AgentMiddleware):
    async def before_model(self, state, runtime):
        MODEL_CALLS.inc()
        state._start = time.monotonic()
    async def after_agent(self, state, runtime):
        AGENT_DURATION.observe(time.monotonic() - state._start)
```

Metrics:

```
athar_agent_calls_total{agent="trip", status="ok"} 142
athar_agent_duration_seconds{agent="trip"} 1.42
athar_tool_calls_total{tool="search_pois", status="ok"} 89
athar_tool_duration_seconds{tool="search_pois"} 0.23
athar_llm_tokens_total{agent="trip"} 45200
athar_middleware_execution{middleware="pii"} 0.0003
```

### Logging

`AtharLoggingMiddleware` logs every agent step as structured JSON. Each run is traceable by `thread_id`.

## State Management

### Conversation history

LangChain agents maintain a message list. Without management, it grows unbounded and hits context limits.

- `SummarizationMiddleware` compresses history at 4000 tokens
- `checkpointer` persists state to PostgreSQL — survives restarts
- No in-memory state — horizontal scaling works out of the box

### User Session (Redis)

```python
# app/services/agent/session.py
class UserSession:
    """Short-lived user context stored in Redis with TTL."""
    intent: UserIntent | None
    recent_interactions: list[str]
    locale: str
```

Set by `IntentAgent` (or classifier), read by `RecommendAgent` via tool context.

## Endpoint Integration

Existing endpoints stay. Agent calls are **inline** from the endpoint:

```python
# app/api/v1/endpoints/trips.py — Before
@router.post("/{trip_id}/optimize")
async def optimize_trip(trip_id: UUID, current_user: User = Depends(get_current_user)):
    trip = await trip_service.get_trip(trip_id, current_user.id)
    result = await trip_optimizer.optimize(trip)
    return result

# After
@router.post("/{trip_id}/optimize")
async def optimize_trip(trip_id: UUID, current_user: User = Depends(get_current_user)):
    if not settings.AGENT_ENABLED:
        return await trip_optimizer.optimize(...)  # fallback to old path
    result = await trip_agent.ainvoke(
        {"messages": [{"role": "user", "content": f"Optimize trip {trip_id}"}]},
        config={"configurable": {"thread_id": str(trip_id)}},
        context=AgentContext(user_id=str(current_user.id), trip_id=str(trip_id)),
    )
    return result["structured_response"]
```

Feature flag (`AGENT_ENABLED`) lets us land alongside existing code, switch when stable.

## Migration Strategy

### Phase 1 — Foundation (this sprint)

- Add `langchain`, `langchain-openai`, `langchain-qdrant`, `langchain-huggingface` to deps
- Add `VLLMSettings` + `AgentSettings` to config
- Create `app/services/agent/` package:
  - `llm.py` — ChatOpenAI client
  - `middleware.py` — AtharLoggingMiddleware, MetricsMiddleware
  - `registry.py` — tool definitions wrapping existing services
  - `prompts/trip_agent.py` — system prompt
  - `agents/trip_agent.py` — create_agent call
  - `session.py` — Redis-backed UserSession
- Wire into `main.py` lifespan
- Feature flag `AGENT_ENABLED=False` — existing code path unchanged

### Phase 2 — TripAgent live

- Enable TripAgent behind flag in staging
- Compare outputs with old TripOptimizer side-by-side
- Remove old TripOptimizer when stable

### Phase 3 — RecommendAgent + AlertAgent

- Build RecommendAgent, wire into discover/wilaya endpoints
- Build AlertAgent with cron trigger
- Wire alerts into notification feed

### Phase 4 — IntentAgent + remove flag

- Build behavioral profile system
- Feed into RecommendAgent
- Remove `AGENT_ENABLED` flag, remove old code

## Config Additions

```python
# app/core/config.py
class VLLMSettings(BaseModel):
    base_url: str = "http://localhost:8000/v1"
    api_key: str = ""
    model: str = "Qwen2.5-7B-Instruct"
    timeout: int = 30

class AgentSettings(BaseModel):
    enabled: bool = False
    max_iterations: int = 5
    vllm: VLLMSettings = VLLMSettings()

class Settings(BaseSettings):
    ...
    agent: AgentSettings = AgentSettings()
```

## Dependency Additions

```toml
# pyproject.toml
langchain = ">=1.0.0"
langchain-openai = ">=0.3.0"
langchain-qdrant = ">=0.2.0"
langchain-huggingface = ">=0.1.0"
```

## File Structure

```
app/services/agent/
├── __init__.py
├── llm.py              # ChatOpenAI client
├── registry.py         # Tool definitions (8-10 tools)
├── middleware.py        # Custom middleware (logging, metrics)
├── session.py          # Redis-backed UserSession
├── prompts/
│   ├── __init__.py
│   ├── trip_agent.py   # TripAgent system prompt
│   ├── brief_agent.py  # BriefGenerator system prompt
│   └── recommend.py    # RecommendAgent system prompt
└── agents/
    ├── __init__.py
    ├── trip_agent.py   # TripAgent: create_agent + tools
    ├── brief_agent.py  # BriefAgent: create_agent + tools (shares tools)
    └── recommend.py    # RecommendAgent (Phase 2)
```

## Key Anti-Patterns

| Anti-pattern | Why we avoid it |
|-------------|----------------|
| LangSmith / LangHub | Cloud-dependent, data sovereignty violation |
| `langchain-community` | 200+ unused dependencies, security surface |
| Agent-as-chatbot | Against invisible-agent design principle |
| LLM calling LLM | Agents call Tools → Services → DB, never another LLM |
| Prompt engineering in endpoint code | All prompts in `prompts/`, version-controlled |
| Agent-in-the-loop for CRUD | Agents only for optimization/recommendation/alert |
| Sync tools in async agent | Blocks the event loop — all tools are async |
| In-memory state | Prevents scaling — use Postgres checkpointer |
