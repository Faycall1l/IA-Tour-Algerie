# Feature: Bookings & Notifications

## Booking Lifecycle

```
Pending ──→ Confirmed ──→ Completed
    │                       │
    └──→ Cancelled ←────────┘
```

### State Transitions

| From | To | Who | Note |
|------|----|-----|------|
| `pending` | `confirmed` | Provider | Accept the booking |
| `pending` | `cancelled` | Traveler or Provider | Withdraw request |
| `confirmed` | `completed` | Provider | Mark as done |
| `confirmed` | `cancelled` | Traveler or Provider | Cancel after confirmation |
| `completed` | — | — | Terminal state |
| `cancelled` | — | — | Terminal state |

### Business Rules

1. **Travelers** can only `cancel` (cannot confirm/complete their own booking).
2. **Providers** can transition `pending → confirmed`, `confirmed → completed`, and `cancel`.
3. Everyone sees their own bookings via `GET /bookings` — both as traveler and as provider.
4. A provider cannot book their own experience.

## Booking Endpoints

### `POST /api/v1/bookings`

Creates a booking request. Generates a `Notification` for the provider.

```json
{
  "experience_id": "uuid",
  "message": "I'd love to join this tour!",
  "participants": 2,
  "requested_date": "2026-07-15"
}
```

### `PUT /api/v1/bookings/{id}/status`

```json
{ "status": "confirmed" }
```

Generates a `Notification` for the other party.

## Notification Types

| `type` | Trigger | Sent To |
|--------|---------|---------|
| `booking_request` | New booking created | Provider |
| `booking_confirmed` | Booking confirmed | Traveler |
| `booking_completed` | Booking completed | Traveler |
| `booking_cancelled` | Booking cancelled | Both parties |

## Notification Endpoints

### `GET /api/v1/notifications`

Returns paginated notifications for current user, with `unread_count`.

| Param | Default | Effect |
|-------|---------|--------|
| `unread_only` | false | Filter to unread only |
| `page` | 1 | Pagination |
| `page_size` | 20 | Max 50 |

### `PUT /api/v1/notifications/{id}/read`

Mark single notification as read.

### `PUT /api/v1/notifications/read-all`

Mark ALL notifications as read for current user (204 No Content).

## How Notifications Are Created

In the booking endpoints, a helper `_notify()` is called before `db.commit()`:

```python
async def _notify(db, user_id, type, title, message, reference_type, reference_id):
    notif = Notification(user_id=user_id, type=type, title=title,
                         message=message, reference_type=reference_type,
                         reference_id=reference_id)
    db.add(notif)
```

This ensures notifications are transactional with the booking change — if the booking commit fails, the notification is rolled back too.

## Future Enhancements

- **Push notifications** via Firebase/MQTT for mobile.
- **WhatsApp notification** as alternative channel (critical for Algeria).
- **Notification preferences** (opt-in/out per type, per channel).
- **In-app notification center** badge count for unread.
- **Booking calendar** — providers see all bookings in a date range.
- **Payment integration** — booking status linked to payment status.
