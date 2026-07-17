# API Integration Guide

## Authentication

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "admin@cms.example.com",
  "password": "Password@123"
}
```

Use the returned access token:

```http
Authorization: Bearer <access_token>
```

Refresh tokens rotate on every successful refresh. Reusing an older refresh token revokes the remaining token family.

## Create and publish content

1. `POST /api/v1/sites`
2. `POST /api/v1/content-types`
3. `POST /api/v1/content-types/{id}/publish`
4. `POST /api/v1/entries`
5. `POST /api/v1/entries/{id}/submit`
6. `POST /api/v1/entries/{id}/approve`
7. `POST /api/v1/entries/{id}/publish`

## Public delivery

```http
GET /api/v1/delivery/sites/demo/entries/article/welcome-enterprise-cms
```

Optional scoped key:

```http
X-API-Key: cms_prefix.secret
```

## Optimistic concurrency

Send `expected_version` when updating an entry. A stale version receives HTTP 409 with the current version.

## Preview

Create a time-limited preview token:

```http
POST /api/v1/entries/{entry_id}/preview-token
```

Consume it without publishing:

```http
GET /api/v1/preview/{token}
```

## Webhooks

Configured events include `entry.updated`, `entry.submitted`, `entry.approved`, `entry.rejected`, `entry.published`, `entry.unpublished`, `entry.archived`, `media.created` and wildcard `*`.
