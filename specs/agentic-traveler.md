# Agentic Traveler Layer

Make the **traveler experience** AI-powered — not the admin panel. The admin dashboard is the human-in-the-loop for edge cases. The agentic layer lives on the customer-facing side, turning ATHAR from a CRUD API into a conversational travel companion.

## Vision

```
"Plan a 5-day trip to Algeria. I love Roman ruins and beach days. Budget ~50,000 DZD."
  ↓
AI Agent orchestrates: POI search → Experience matching → Price intelligence →
Itinerary building → Booking suggestions → WhatsApp-ready trip dossier
  ↓
Refine conversationally: "Swap Day 3 afternoon for a cooking workshop"
  ↓
Agent re-plans, re-prices, re-balances. Instantly.
```

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Traveler (WhatsApp / Chat UI)            │
└──────────────────────────┬─────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────┐
│              Agent Orchestrator (LangGraph / Haystack)      │
│                                                             │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │ Trip     │  │ Itinerary    │  │ Concierge          │   │
│  │ Planner  │  │ Builder      │  │ (live trip)        │   │
│  └────┬─────┘  └──────┬───────┘  └─────────┬──────────┘   │
│       │               │                     │              │
│  ┌────▼───────────────▼─────────────────────▼──────────┐   │
│  │           Specialized Sub-Agents (parallel)          │   │
│  │                                                      │   │
│  │  POI       Experience  Price       Review    Local   │   │
│  │  Scout     Matcher     Intel       Analyst   Expert  │   │
│  └────┬──────────┬──────────┬──────────┬──────────┬─────┘   │
│       │          │          │          │          │         │
└───────┼──────────┼──────────┼──────────┼──────────┼─────────┘
        │          │          │          │          │
  ┌─────▼──────────▼──────────▼──────────▼──────────▼───────┐
  │                    ATHAR API Layer                       │
  │  /pois  /experiences  /prices/estimate  /reviews  /live  │
  └──────────────────────────────────────────────────────────┘
```

## Agent Modules

### 1. Trip Planner Agent

**Input**: Natural language → structured `TripRequest`:
```python
class TripRequest(BaseModel):
    destination: str           # Wilaya name or "Algeria"
    duration_days: int
    travel_style: str          # "history", "beach", "adventure", "culture", "mixed"
    budget_dzd: float | None
    with_guide: bool = False
    interests: list[str]       # "Roman ruins", "hiking", "local food", "workshops"
    month: str | None          # Time of year for weather-aware planning
```

**Flow**:
1. Parse intent via LLM (Claude/GPT/Mistral — no PII)
2. Map destination to wilaya IDs
3. Fan-out to sub-agents in parallel (`asyncio.gather`)
4. Synthesize into structured `TripPlan`
5. Return itinerary with POI visits, experiences, transport price estimates

**Output**:
```python
class TripDay(BaseModel):
    day: int
    morning: Activity | None
    afternoon: Activity | None
    evening: Activity | None
    estimated_cost_dzd: float
    wilaya: str

class TripPlan(BaseModel):
    days: list[TripDay]
    total_estimated_cost: float
    tips: list[str]             # Local advice from LLM + review analysis
    booking_links: dict         # Pre-filled booking URLs
```

### 2. POI Scout Agent

Given a wilaya and traveler interests:
1. Query Qdrant for nearest-vector POIs (semantic search, not just keyword)
2. Filter by category, rating, price range
3. Enrich with review sentiment summary (LLM aggregates top reviews)
4. Score each POI for match with traveler preferences
5. Return top N with rationales

**Key**: Uses existing `GET /api/v1/pois/search` + review average + LLM synthesis. No new infra needed.

### 3. Experience Matcher Agent

Matches traveler profile to available experiences:
1. Query Qdrant for experiences matching interest keywords
2. Filter by wilaya, status=active, price range
3. Match by language (traveler's languages vs experience language)
4. Score: price reasonableness, provider rating, date availability

### 4. Price Intel Agent

When an itinerary involves moving between wilayas:
1. Call `GET /api/v1/prices/estimate` for each route+mode
2. Flag routes with no data → suggest most common mode
3. Summarize: "A taxi from Algiers to Tipaza typically costs 1,500–2,500 DZD"
4. Add "Don't pay more than X" advice from existing endpoint

### 5. Review Analyst Agent

Before suggesting a POI or experience:
1. Fetch top 10 reviews
2. LLM summarizes: "Guests love the guided tour but note the site is crowded by 10 AM"
3. Extract practical tips: "Bring water, no shade, entrance is 200 DZD"
4. Tie back to traveler interests: "Matches your interest in Roman architecture"

### 6. Local Expert Agent (RAG-enhanced)

Ground answers in ATHAR's own data + curated local knowledge:
1. Traveler asks: "What should I wear in Constantine in December?"
2. Agent searches:
   - Live posts tagged with that wilaya (real traveler photos = real context)
   - Reviews mentioning weather/dress
   - POI descriptions with location context
   - Wilaya metadata (GPS → climate inference)
3. LLM synthesizes answer with citations back to ATHAR content

### 7. Concierge Agent (In-Trip)

Active during the traveler's trip:
1. Re-routing: "Getting late at Timgad → suggest moving evening activity"
2. Re-booking: "Your guide cancelled" → find replacement
3. Q&A: "Where's the nearest good couscous in Setif?"
4. SOS: "I lost my wallet" → nearest embassy/hospital (future)

Runs over WhatsApp integration (future). Uses same agent pipeline but with shorter context windows and faster models.

## Implementation Phases

### Phase 1 — Trip Planning Agent (MVP)
- Single LLM call with tool access (function calling)
- No multi-agent orchestration yet
- Tools: `search_pois`, `search_experiences`, `estimate_price`, `get_wilaya_info`
- Simple day-by-day: morning/afternoon/evening slots
- Structured JSON output to chat UI

**Effort**: 3-5 days
**New files**: `app/agents/trip_planner.py`, `app/agents/tools.py`

### Phase 2 — Multi-Agent Orchestration
- LangGraph or Haystack pipeline
- Fan-out: POI Scout + Experience Matcher + Price Intel run in parallel
- Itinerary Builder agent synthesizes results
- Streaming response (SSE or WebSocket)
- Conversational refinement: "Swap Day 2 for beach"

**Effort**: 5-7 days
**New deps**: `langgraph` or `haystack-ai`
**New files**: `app/agents/orchestrator.py`, `app/agents/poi_scout.py`, `app/agents/experience_matcher.py`, `app/agents/price_intel.py`

### Phase 3 — Review Analyst + Local Expert
- RAG pipeline over reviews + live posts + POI descriptions
- ChromaDB or pgvector for local embeddings
- Review summarization on demand

**Effort**: 3-5 days
**New deps**: `chromadb` or use pgvector (existing PostgreSQL)
**New files**: `app/agents/review_analyst.py`, `app/agents/local_expert.py`, `app/services/rag_service.py`

### Phase 4 — Concierge (In-Trip)
- WhatsApp integration
- Real-time re-routing
- GPS-aware context

**Effort**: 5-7 days (depends on WhatsApp integration)
**New files**: `app/agents/concierge.py`

### Phase 5 — Voice & Immersive
- Voice interface (Whisper STT → agent → TTS)
- GPS-aware audio guide (Waivoo pattern): "As you walk through the Roman arches of Timgad..."
- Offline-capable itinerary in Flutter app

**Effort**: 7-10 days (depends on Flutter)
**New deps**: Whisper (already have), TTS engine

## Technical Design Principles

### Zero PII to External APIs
```
User message → PII scrubber (regex phone/name/email) → LLM API → Response
```
Loi 18-07: All personal data stays in ATHAR's PostgreSQL. External LLMs only see trip preferences, never phone numbers, names, or emails.

### Graceful Degradation
Every agent has a fallback:
- Qdrant unavailable → SQL ILIKE search (already implemented)
- LLM API down → Rule-based template responses
- External API fails → Mock/synthetic data with disclaimer

### Confidence-Based Escalation
```
Agent confidence > 0.9 → Auto-execute (book, suggest, answer)
Agent confidence 0.5-0.9 → Include disclaimers, suggest human review
Agent confidence < 0.5 → "I'm not sure. Let me connect you with a local expert."
```

### Structured Outputs
Every agent returns typed Pydantic models, not free text. The chat UI renders structured data (maps, cards, buttons) from JSON — not markdown.

### Streaming
Agent reasoning streams via SSE while parallel sub-agents run. Traveler sees:
```
┌─────────────────────────────────────┐
│ 🤔 Thinking...                      │
│ ✓ POI Scout: 8 matches in Algiers   │
│ ✓ Experience Matcher: 3 workshops   │
│ ⏳ Price Intel: checking routes...  │
│                                     │
│ ┌─ Your Trip Plan ────────────────┐ │
│ │ Day 1: Algiers — Casbah + Museum│ │
│ │ Day 2: Tipaza — Roman ruins     │ │
│ │ ...                             │ │
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

### Memory
Across sessions, the agent remembers:
- Previous trips planned → refine recommendations
- Liked categories → bias future searches
- Budget preferences → default to known range
- Language preference → always respond in traveler's language

Stored in a `traveler_preferences` JSON field on the User model (no new table).

## Data Flow

```
1. Traveler types: "Plan 3 days in Oran"
2. POST /api/v1/agent/plan → AgentOrchestrator
3. Orchestrator extracts TripRequest via LLM
4. Parallel fan-out:
   ├── POI Scout → Qdrant + PostgreSQL → scored POIs
   ├── Experience Matcher → Qdrant + PostgreSQL → matched experiences
   ├── Price Intel → PriceReport query → fair prices
   └── Review Analyst → Review query → sentiment summary
5. Itinerary Builder agent synthesizes → TripPlan JSON
6. Response streams back to traveler via SSE
7. Traveler refines: "Can you add a cooking workshop on Day 2?"
   → Agent re-plans from existing context (no full re-run)
```

## What Stays In-House vs External

| Capability | Where | Why |
|-----------|-------|-----|
| POI/Experience vector search | Qdrant (local) | Data sovereignty, low latency |
| Price estimate engine | PostgreSQL (local) | Own data, no external dependency |
| Review aggregation | PostgreSQL + LLM | PII in reviews stays local |
| Natural language understanding | Claude/GPT/Mistral API | No budget for fine-tuning |
| Trip plan generation | Claude/GPT/Mistral API | General capability, no training data leaked |
| Itinerary optimization | LLM + local logic | Route optimization via code, not AI |
| Image moderation | External API (future) | Specialized, not core |

## New API Endpoints

```
POST /api/v1/agent/plan              # Plan a trip from NL description
POST /api/v1/agent/plan/{id}/refine  # Refine existing plan conversationally
GET  /api/v1/agent/plan/{id}         # Retrieve saved plan
POST /api/v1/agent/ask               # One-shot travel question ("What to wear in Tamanrasset?")
POST /api/v1/agent/explore/{wilaya_id} # "What's interesting near X?"
```

## Integration with Existing System

The agent layer is an additive module — it doesn't replace existing endpoints. It's a **composer** that calls the existing API internally:

```python
class TripPlannerAgent:
    async def plan(self, request: TripRequest) -> TripPlan:
        pois = await self.poi_scout.search(
            wilaya_ids=request.wilaya_ids,
            interests=request.interests,
        )
        experiences = await self.experience_matcher.match(
            wilaya_ids=request.wilaya_ids,
            interests=request.interests,
            budget=request.budget_dzd,
        )
        prices = await self.price_intel.estimate_routes(
            routes=self._build_routes(pois, experiences),
        )
        return await self.itinerary_builder.synthesize(
            pois=pois,
            experiences=experiences,
            prices=prices,
            request=request,
        )
```

Each sub-agent calls existing ATHAR endpoints internally (or directly queries the database for performance). The agent doesn't duplicate business logic — it orchestrates it.

## Why This Works for Algeria

1. **Low connectivity areas**: Agents cache results → fallback gracefully → Flutter app works offline
2. **WhatsApp native**: Most Algerians use WhatsApp as primary internet tool → agent over WhatsApp = massive reach
3. **Multi-language**: LLM handles AR/FR/EN/TZ natively → no separate translation layer
4. **No GPUs needed**: sentence-transformers for embeddings (CPU), LLMs via API → no GPU spend
5. **Data moat**: ATHAR's POI + price + review data is unique to Algeria → LLM can't replicate it → agents add value on top of proprietary data
