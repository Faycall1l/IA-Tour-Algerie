# Feature: POIs & Reviews

## Points of Interest

ATHAR's core content layer — a crowdsourced directory of places to visit in Algeria.

### Categories

| Category | Examples |
|----------|---------|
| `historical` | Roman ruins (Timgad, Djemila), Casbah |
| `natural` | Tassili n'Ajjer, Gouffre de Ghar Boumaza |
| `cultural` | M'Zab Valley, traditional festivals |
| `religious` | Ketchaoua Mosque, Notre-Dame d'Afrique |
| `museum` | Bardo Museum, MAMO |
| `beach` | Sidi Fredj, Les Andalouses |
| `mountain` | Djurdjura, Hoggar |
| `park` | El-Kala National Park, Tlemcen National Park |
| `market` | Souk El Djemâa, Marché Malakoff |
| `other` | Anything else |

### CRUD

| Endpoint | Auth | Notes |
|----------|------|-------|
| `POST /pois` | User | Create new POI. Also indexes in Qdrant. |
| `GET /pois` | Public | Filters: `wilaya_id`, `category`, `search`. Sort: `name`, `created_at`, `rating`. Search falls through Qdrant if `?search=` param given. |
| `GET /pois/{id}` | Public | Returns with `average_score` + `total_reviews` from Review aggregation. |
| `DELETE /pois/{id}` | Admin | Also removes from Qdrant. |
| `POST /pois/{id}/photo` | Admin | Upload image via MinIO. |

### Search Behaviour

When `?search=` query param is present:
1. If Qdrant is available → vector search via EmbeddingService + VectorSearchService.
2. If Qdrant is down → SQL `ILIKE` on name and description.
3. Results are enriched with rating stats.

When `?search=` is absent → standard SQL filtering + sorting.

### Ratings Enrichment

Every POI list item and detail response includes:

```python
# Single query for all POIs in the list
ratings_query = text("""
    SELECT poi_id, AVG(rating)::float as avg_rating, COUNT(*) as cnt
    FROM reviews WHERE poi_id = ANY(:ids) GROUP BY poi_id
""")
```

Attached as `average_score` (float) and `total_reviews` (int).

---

## Reviews

### Rules

- **One review per user per POI** — enforced at DB level with UNIQUE(user_id, poi_id).
- **Rating 1–5** — enforced with CHECK constraint.
- **Comment optional** — up to 2000 chars.

### Endpoints

| Endpoint | Auth | Notes |
|----------|------|-------|
| `POST /reviews` | User | Create. Rejects if user already reviewed this POI. |
| `GET /reviews` | Public | Filters: `poi_id`, `user_id`. Sorted by created_at desc. |
| `GET /reviews/ratings/{poi_id}` | Public | Rating distribution: {1: count, 2: count, ..., 5: count}. |
| `DELETE /reviews/{id}` | Author/Admin | Author can delete own, admin can delete any. |

### Review Response Format

```json
{
  "id": "uuid",
  "poi_id": "uuid",
  "user_id": "uuid",
  "user_name": "Yasmine B.",
  "rating": 5,
  "comment": "Absolutely stunning Roman ruins. The guide was fantastic.",
  "poi_name": "Timgad",
  "wilaya_name": "Batna",
  "created_at": "2026-07-04T18:30:00Z"
}
```

### Rating Distribution

`GET /reviews/ratings/{poi_id}`

```json
{
  "poi_id": "uuid",
  "average": 4.6,
  "total": 12,
  "distribution": {
    "1": 0,
    "2": 0,
    "3": 1,
    "4": 3,
    "5": 8
  }
}
```
