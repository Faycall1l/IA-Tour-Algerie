# Feature: POIs

## Points of Interest

ATHAR's core content layer — 52,997 real places to visit in Algeria, extracted from OpenStreetMap.

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
| `cafe` | Cafés with cultural significance |
| `restaurant` | Traditional restaurants |
| `other` | Anything else |

### CRUD

| Endpoint | Auth | Notes |
|----------|------|-------|
| `POST /pois` | User | Create new POI. Also indexes in Qdrant. |
| `GET /pois` | Public | Filters: `wilaya_id`, `category`, `neighborhood`, `search`. Sort: `name`, `created_at`. |
| `GET /pois/search` | Public | Semantic search via Qdrant vector similarity. Falls through to SQL ILIKE if Qdrant is down. |
| `GET /pois/{id}` | Public | POI detail with TripAdvisor-style fields. |
| `DELETE /pois/{id}` | Admin | Also removes from Qdrant. |
| `POST /pois/{id}/photo` | Admin | Upload image via MinIO. |

### Search Behaviour

When `?search=` query param is present:
1. If Qdrant is available → vector search via EmbeddingService + VectorSearchService.
2. If Qdrant is down → SQL `ILIKE` on name and description.

When `?search=` is absent → standard SQL filtering + sorting.

### POI Response Fields

Every POI includes TripAdvisor-style enrichment:

```json
{
  "id": "uuid",
  "name": "Timgad",
  "category": "historical",
  "wilaya_id": 5,
  "latitude": 35.48,
  "longitude": 6.47,
  "description": "Roman ruins...",
  "entry_fee_dzd": 300,
  "ranking": 1,
  "price_level": "$$",
  "suggested_duration_min": 90,
  "photo_urls": ["https://..."],
  "subtype": "archaeological_site",
  "name_ar": "تيمقاد",
  "name_en": "Timgad",
  "is_featured": true,
  "featured_order": 1,
  "average_score": null,
  "total_reviews": 0,
  "has_parking": true,
  "has_accessibility": false,
  "fun_fact": "Built by Emperor Trajan around 100 AD..."
}
```

### POI Graph Service

Networkx-based tourist routing with 34,787 tourism POIs and 535,237 walking edges within 5km.

- **Tour optimization**: Density-based cluster detection with category diversity penalty
- **Cluster detection**: Oran 9 POIs (4.1km), Tlemcen 10 (2.3km), Algiers 10 (3.2km)
- **API**: `GET /pois/tour/optimize`, `/tour/clusters`, `/tour/hubs`

### Fun Facts

583 POIs have fun facts sourced from:
- Wikidata (16)
- OSM tags (304)
- Category templates (263)
- AI-generated via vLLM Gemma 4 (planned: 4,182 eligible)
