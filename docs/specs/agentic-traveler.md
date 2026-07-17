# Agentic Traveler Layer

Not a chatbot. Not a conversation. A travel platform that happens to be AI-powered behind the scenes — proactive, ambient, invisible.

The agents work in the background. The user sees a polished product: itinerary builder, map, booking flow. The AI never announces itself. It Just Works.

## Core Principle: Invisible, Not Absent

```
❌ "Hi! I'm your AI travel assistant. How can I help you today?"
   → Chatbot. User must type. Breaks flow.

✅ User opens a wilaya → sidebar shows "Other travelers paired this with..."
   → AI surfaces contextually. No chat. No prompt.

✅ User adds 3 POIs → system auto-sorts by geography, estimates travel time
   → AI acts. User sees a smarter itinerary, not a thinking animation.

✅ User books a guided tour → notification: "Your guide speaks French & Arabic"
   → AI informs. User didn't ask, didn't need to.
```

The interface is the product — cards, maps, timelines, buttons. AI works in the data layer, shaping what users see without ever demanding to be seen.

## UX Patterns

### 1. Ambient Trip Brief (No Prompt Required)

When a traveler opens a wilaya page (e.g. `/wilayas/16`), the system auto-generates a trip brief as part of the page:

```
┌─────────────────────────────────────────────────────────┐
│ 🇩🇿 Tizi Ouzou                             ┌────────────┐│
│                                                        │ │  Plan Trip │
│ Top 5 POIs · 3 experiences · Sunny 24°C                │ └────────────┘│
├─────────────────────────────────────────────────────────┤
│ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────┐ │
│ │ ⛰️ Djurdjura    │ │ 🏛️ Roman ruins  │ │ 🍯 Oil      │ │
│ │ ★ 4.5 · 2km     │ │ ★ 4.2 · 15km    │ │ workshop    │ │
│ │ 45 min hike     │ │ Guided tour avail│ │ ★ 4.8 · 5km │ │
│ └─────────────────┘ └─────────────────┘ └─────────────┘ │
│                                                          │
│ Transport from Algiers: 1,200–1,800 DZD (bus)           │
│ Best time: April–June, September–November                │
│ "Don't miss the Saturday market" — 12 reviews mention it │
└─────────────────────────────────────────────────────────┘
```

**AI work**: POI Scout + Price Intel + Review Analyst run when the page loads. User never sees them. Results render directly into page sections.

### 2. Proactive Trip Dashboard

```
┌─────────────────────────────────────────────────────────┐
│ 🧳 My Trip — Algeria, 5 days         [📅 Export] [📎 Share] │
├─────────────────────────────────────────────────────────┤
│ Day 1 — Algiers                                         │
│ ┌───┐ ┌───┐ ┌───┐                                      │
│ │AM │ │PM │ │PM │ ← Drag to reorder                     │
│ │   │ │   │ │   │  Agent re-optimizes routes            │
│ │Cas│ │Mu │ │Ma │  automatically                       │
│ │bah│ │seu│ │rke│                                      │
│ └───┘ └───┘ └───┘                                      │
│                                                          │
│ ⚡ Agent note: Casbah → Museum is 800m walk (10 min)    │
│ ⚡ Agent note: Market closes at 1 PM on Fridays         │
│                                                          │
├─────────────────────────────────────────────────────────┤
│ Day 2 — Tipaza (50 min from Algiers)                    │
│ ┌───┐ ┌───┐                                             │
│ │AM │ │PM │                                             │
│ │Ro │ │Bea│                                             │
│ │man│ │ch │                                             │
│ └───┘ └───┘                                             │
│                                                          │
│ 🚌 Transport: 500–800 DZD · last bus back at 6 PM      │
│ 🎟️ Book guided tour with Youssef ★ 4.9 — 3 spots left │
└─────────────────────────────────────────────────────────┘
```

**AI work**: Itinerary Builder + Price Intel + Experience Matcher run when user adds items. Re-runs on drag. Zero user-facing agent UI.

### 3. Smart Defaults (Generative UI)

User fills a booking form → AI pre-fills intelligently:

```
Book: "Kabyle Cooking Workshop"
┌────────────────────────────────────┐
│ 📅 Date     │ [April 15] ← AI picks │
│             │   best day based on   │
│             │   existing itinerary  │
├────────────────────────────────────┤
│ 👥 People   │ [2] ← AI defaults     │
│             │   to trip size        │
├────────────────────────────────────┤
│ 🚐 Transport│ [Add from hotel]      │
│             │   800 DZD — suggested │
│             │   because workshop is │
│             │   5km from your hotel │
├────────────────────────────────────┤
│ 💰 Total    │ 3,500 DZD             │
│             │ ✓ Fits your daily     │
│             │   budget of 5,000 DZD │
└────────────────────────────────────┘
```

**AI work**: Trip Planner + Price Intel run on form mount. User sees smarter defaults, not a chatbot.

### 4. Contextual Whisper (Notifications, Not Chat)

The agent never writes a message. It surfaces **cards** and **badges** in the existing UI:

| Trigger | Surface | Example |
|---------|---------|---------|
| Price drops | Badge on POI card | "↓ 20% this week" |
| Booking conflict | Tooltip on date picker | "You already have a tour at 2 PM" |
| Weather change | Banner on trip dashboard | "Rain expected Thursday — indoor activities suggested" |
| New experience in saved wilaya | Notification bell | "New guided tour in Tipaza" |
| Optimal route found | Toast on itinerary | "Reordering your day saves 40 min walking" |
| Provider approved | Card in explore feed | "New guide: Fatima — specializes in Roman sites" |

**Design rule**: Never more than 1 proactive surface per page load. The agent has an interrupt budget — it chooses the single most valuable thing to surface and stays silent otherwise.

### 5. One-Click Actions

Every AI-generated suggestion is actionable with one click:

```
┌────────────────────────────────────┐
│ ⚡ Optimize my route                │
│ Reorder 3 activities to save       │
│ 40 min walking time                │
│                                    │
│ [Apply] [Show me] [Not now]        │
└────────────────────────────────────┘
```

No typing. No "Yes, please optimize my route." One click, the agent executes, the UI updates.

### 6. Feedback Loop (Implicit, Not Explicit)

The agent never asks "Was this helpful?" It watches behavior:

| User action | Signal | Agent learns |
|-------------|--------|-------------|
| Adds 3 historical POIs | Interest in history | Bias future searches toward historical |
| Skips all beach POIs | Disinterest in beach | Filter out beach suggestions |
| Always picks cheapest transport | Budget-conscious | Default to economy mode |
| Books guided tours repeatedly | Prefers guided | Surface guide-included options first |
| Views a POI but doesn't add | Interested but not convinced | Offer more details, show similar |

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    User-facing UI (PWA / Flutter)             │
│  Cards · Maps · Timelines · Forms · Notifications · Buttons  │
└────────────────────────────┬─────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│                   ATHAR API Layer (existing)                  │
│  /pois  /experiences  /prices  /reviews  /bookings  /live     │
└────────────────────────────┬─────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│              Background Agent Layer (invisible)               │
│                                                               │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │ Trip       │  │ Intent       │  │ Recommendation     │   │
│  │ Optimizer  │  │ Detector     │  │ Engine             │   │
│  │ (re-routes,│  │ (reads user  │  │ (collaborative     │   │
│  │  re-sorts) │  │  behavior)   │  │  + semantic)       │   │
│  └────────────┘  └──────────────┘  └────────────────────┘   │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │ Brief      │  │ Alert        │  │ Trip Dashboard     │   │
│  │ Generator  │  │ Engine       │  │ (itinerary state)  │   │
│  └────────────┘  └──────────────┘  └────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

The Background Agent Layer:
- **No endpoints** — not callable by users
- **No chat** — not a conversational interface
- **Triggered by** user actions (page load, search, add to trip, book)
- **Outputs** structured data that the frontend renders as native UI components

## Agent Modules

### 1. Brief Generator

**Trigger**: User opens a wilaya page or POI detail.
**Work**: Runs POI Scout + Price Intel + Review Analyst in parallel.
**Output**: Structured `WilayaBrief` — top POIs, transport costs, review highlights, tips.
**Frontend**: Renders as the wilaya hero section. No agent UI.

### 2. Intent Detector

**Trigger**: Any user action (search, click, add, scroll time, skip).
**Work**: Builds a behavioral profile across the session:
```python
class UserIntent(BaseModel):
    preferred_categories: list[str]     # ["historical", "natural"]
    budget_tier: str                     # "economy" | "mid" | "premium"
    pace: str                            # "packed" | "relaxed"
    prefers_guides: bool
    language: str
    travel_party_size: int | None
```
**Output**: Updated session context, stored in Redis with TTL.
**Frontend**: Nothing visible. Agent shapes downstream results.

### 3. Trip Dashboard (Itinerary State Machine)

**Trigger**: User adds first POI/experience to a trip.
**Work**: Maintains a persistent `TripState`:
```python
class TripState(BaseModel):
    days: list[DayPlan]
    budget_spent: float
    budget_remaining: float
    gaps: list[TimeGap]          # Free time slots → suggest filling
    alerts: list[Alert]          # Conflicts, weather, price changes
    optimization_score: float     # How efficient the current route is
```
**Output**: On every change — re-optimizes route, recalculates budget, identifies gaps.
**Frontend**: Trip dashboard auto-updates. "You have 3 free hours on Day 2" appears as a card.

### 4. Recommendation Engine

**Trigger**: Page load, search, or idle after 3s.
**Work**: Combines:
- Collaborative: "Travelers who liked this also liked..."
- Semantic: Qdrant vector similarity
- Behavioral: Intent Detector profile
- Contextual: Time of day, weather, season
**Output**: `RecommendationFeed` — sorted cards with rationale.
**Frontend**: Renders as "You might also like" grid. Never as a chat bubble.

### 5. Alert Engine

**Trigger**: Background cron (every 30 min) + event-driven (on booking, on price report).
**Work**: Checks for:
- Price drops on saved POIs
- New experiences in saved wilayas
- Weather conflicts with outdoor plans
- Booking conflicts (overlapping times)
- Provider availability changes
**Output**: `AlertBatch` — max 1 per hour per user (interrupt budget).
**Frontend**: Notification badge + optional toast. Never a chat message.

### 6. Trip Optimizer

**Trigger**: User adds, removes, or reorders items on the trip dashboard.
**Work**: 
- Re-sort by geography (nearest-first to minimize walking)
- Check opening hours (no museum visits at 7 PM)
- Estimate travel time between consecutive POIs
- Detect gaps → suggest filler
- Recalculate budget
**Output**: Updated `TripState` + `OptimizationSuggestion` if improvement found.
**Frontend**: Auto-applies if improvement > 20%. Otherwise shows a one-click suggestion card.

## Data Flow (No Chat)

```
User lands on /wilayas/16
  → BriefGenerator: parallel POI Scout + Price Intel + Review Analyst
  → IntentDetector: "First visit, no history yet"
  → RecommendationEngine: "Popular with first-time visitors:..."
  → Frontend renders:
       ┌─────────────────────────────────────┐
       │ Tizi Ouzou — Trip Brief             │
       │ Top 5 POIs · 3 experiences          │
       │ ┌───┐───┐───┐                     │
       │ │   │   │   │ ← Cards, not chat   │
       │ └───┘───┘───┘                     │
       │ "Popular with history lovers:"      │
       │ ┌───┐───┐───┐                     │
       │ │   │   │   │ ← Recommendations    │
       │ └───┘───┘───┘                     │
       └─────────────────────────────────────┘

User clicks "Add to trip" on 3 POIs
  → Trip Dashboard initializes
  → TripOptimizer: sorts by geography
  → IntentDetector: "Interested in history + nature"
  → AlertEngine: nothing urgent yet
  → Frontend renders:
       ┌─────────────────────────────────────┐
       │ 🧳 My Trip                          │
       │ Day 1: 3 activities, 2.5 km walk    │
       │ ⚡ 1 free hour in the afternoon      │
       │ [Suggest activity] ← one click      │
       └─────────────────────────────────────┘

User clicks [Suggest activity]
  → RecommendationEngine: "Nearby POI you haven't added"
  → One card appears. No chat. No loading spinner.
  → User clicks [+] → Added. Trip re-optimizes.
```

## New API Endpoints (Structured, Not Conversational)

```
GET  /api/v1/trip/brief?wilaya_id=16
     → WilayaBrief (top POIs, transport costs, tips, review highlights)

GET  /api/v1/trip/state
     → TripState (current itinerary, budget, gaps, alerts)

POST /api/v1/trip/items
     → Add POI/experience → returns updated TripState

DELETE /api/v1/trip/items/{id}
     → Remove → returns updated TripState with gap detection

POST /api/v1/trip/optimize
     → Re-sort, fill gaps → returns updated TripState + suggestions

GET  /api/v1/recommendations?context=wilaya_detail&item_id=xxx
     → RecommendationFeed (cards with rationale)

GET  /api/v1/alerts
     → AlertBatch (interrupt-budgeted, max 1/hour)

POST /api/v1/alerts/{id}/dismiss
     → User dismissed → agent learns
```

No `POST /agent/plan`. No `POST /agent/ask`. No chat endpoints. Every endpoint maps to a visual UI component, not a conversation turn.

## Implementation Plan

| Phase | What | User Sees | Backend Work |
|-------|------|-----------|--------------|
| 1 | Trip Dashboard | Drag-drop itinerary, auto-sort, budget calc | `TripState` model, `TripOptimizer` agent, `/trip/*` endpoints |
| 2 | Brief Generator | Wilaya pages auto-populate with brief | `BriefGenerator` agent, parallel POI/Price/Review queries |
| 3 | Smart Defaults | Forms pre-fill intelligently | Intent Detector, form-context agents |
| 4 | Recommendations | "You might also like" on every page | Recommendation Engine + Qdrant + behavior signals |
| 5 | Alert Engine | Price drops, conflicts, weather | Background cron + Alert Engine + notifications |

## Anti-Patterns (Will Not Build)

| Anti-pattern | Why |
|-------------|-----|
| Chat interface | User must type = friction. Not ambient. |
| "Ask me anything" input | Implies empty state. User doesn't know what to ask. |
| Streaming "thinking" animation | Signals uncertainty. Agent should be confident or silent. |
| "Was this helpful?" feedback | Users lie or ignore. Behavior is truth. |
| Agent自我介绍 | If the user doesn't notice the AI, it's working. |
| Loading spinners for agent work | Agents run async. UI renders from cache → updates when ready. |

## Relationship to Admin

The admin dashboard is the **control surface** for the agentic layer:

| Agent Action | Admin Escalation |
|-------------|-----------------|
| Recommendation had low confidence | Admin reviews the POI/experience data quality |
| Price intel found conflicting reports | Admin verifies flagged price reports |
| Intent detector confused | Admin reviews user's provider profile |
| Alert engine fired false positive | Admin dismisses → agent learns |

The agentic traveler layer never escalates to the user. It escalates silently to the admin, who fixes the root cause (bad data, missing info). The traveler never sees the seam.
