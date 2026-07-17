# Feature: Fair Price Engine

## Endpoint

`GET /api/v1/prices/estimate?origin={wilaya_id}&dest={wilaya_id_or_poi_id}&transport={mode}`

## Algorithm

Aggregates all price reports for a given origin ↔ destination + transport mode and returns:

```json
{
  "transport_mode": "taxi",
  "origin_name": "Alger Centre",
  "dest_name": "Tizi Ouzou",
  "min": 1200,
  "max": 2500,
  "median": 1800,
  "report_count": 42,
  "advice": "The typical fare for this route is around 1800 DZD. Prices range from 1200 to 2500 DZD depending on negotiation and time of day."
}
```

### Computation

```python
amounts = [report.amount for report in reports]
minimum = min(amounts)
maximum = max(amounts)
median = statistics.median(amounts)
```

- `statistics.median` returns the middle value for odd counts, average of two middle values for even.
- Pure Python, no SQL aggregation — portable across DB backends.
- `origin_name` and `dest_name` are resolved from the POI's wilaya name or from the wilaya table directly.

### Advice Generation

Template-based (rule-based, no LLM):

```python
f"The typical fare for this route is around {median} DZD. "
f"Prices range from {min} to {max} DZD depending on "
f"negotiation and time of day."
```

For `report_count < 3`:
```python
f"Not enough price reports for this route yet."
f" The available {report_count} report(s) show prices "
f"between {min} and {max} DZD."
```

### No Reports Case

```json
{
  "transport_mode": "taxi",
  "origin_name": "Alger Centre",
  "dest_name": "Tizi Ouzou",
  "min": null,
  "max": null,
  "median": null,
  "report_count": 0,
  "advice": "No price reports available for this route yet."
}
```

## Route Resolution

| `dest` param | Resolution |
|-------------|-----------|
| POI UUID | Uses POI's wilaya_id → wilaya name |
| Wilaya ID | Direct wilaya name lookup |

## Price Report Creation

`POST /api/v1/prices`

```json
{
  "poi_id": "uuid",
  "transport_mode": "taxi",
  "amount": 1500
}
```

Constraints:
- `transport_mode` must be one of: `taxi`, `bus`, `train`, `walk`, `car`, `plane`.
- `amount` is in DZD, stored as integer.
- `is_verified` defaults to false — admin moderation for accuracy.
