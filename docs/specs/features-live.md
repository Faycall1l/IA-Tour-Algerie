# Feature: Photographic Content (Algeria Live)

## Overview

A real-time photo feed — travelers and locals post photos of Algeria as they explore. Think "Instagram for Algerian travel".

## Endpoints

### `POST /api/v1/live/posts`

Auth required. Multipart form upload.

| Field | Type | Max |
|-------|------|-----|
| `caption` | String | 500 |
| `image` | UploadFile (jpg/png/webp) | 10 MB |
| `wilaya_id` | Integer | — |

Response includes `user_name` + `user_avatar` of the author.

### `GET /api/v1/live/posts`

Public. Paginated feed.

| Param | Effect |
|-------|--------|
| `wilaya_id` | Filter by location |
| `user_id` | Filter by author |
| `page` / `page_size` | Pagination |

Response includes `user_name` + `user_avatar` for each post.

### `DELETE /api/v1/live/posts/{post_id}`

Auth required. Only the post author or an admin can delete.

## Photo Upload Flow

```
1. Client sends multipart/form-data with image + caption
2. API validates file type and size
3. StorageService.upload(file, folder="live") → MinIO URL
4. LivePost created with image_url
5. Response includes the post with author info
```

## Feed Response Format

```json
{
  "items": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "user_name": "Yasmine B.",
      "user_avatar": "http://minio:9000/athar-media/avatars/yasmine.jpg",
      "caption": "Sunset over Tipaza Roman ruins",
      "image_url": "http://minio:9000/athar-media/live/abc123.jpg",
      "wilaya_id": 42,
      "created_at": "2026-07-04T18:30:00Z"
    }
  ],
  "total": 5,
  "page": 1,
  "page_size": 10,
  "total_pages": 1,
  "has_prev": false,
  "has_next": false
}
```

## User Info in Live Posts

The `user_name` and `user_avatar` fields are populated by joining the `users` table on `user_id`. This is done via a single `SELECT` after fetching posts (N+1 avoided by batch query).

```python
# After fetching posts, fetch all referenced users in one query
user_ids = {post.user_id for post in posts}
users = await db.execute(select(User).where(User.id.in_(user_ids)))
user_map = {user.id: user for user in users.scalars()}
# Attach user info to each post
```
