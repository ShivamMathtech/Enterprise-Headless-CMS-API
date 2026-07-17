# Architecture

## Modular monolith

The project is a modular monolith designed to remain straightforward for a small team while preserving clear extraction boundaries for future services.

- Identity and access
- Site and localization management
- Content modeling
- Editorial workflow
- Media library
- Navigation and redirects
- Delivery APIs
- Integrations and webhooks
- Analytics and audit

## Data integrity controls

- Unique content slugs are scoped by environment, content type and locale.
- Content-type keys, environment keys, locales, tags, menus and redirects are unique within a site.
- Content revisions are uniquely numbered per entry.
- Optimistic concurrency rejects stale `expected_version` updates.
- Published delivery queries never return draft, rejected, archived or scheduled entries.
- API keys are stored only as SHA-256 hashes; plaintext is returned once.
- Refresh tokens are stored as hashes and rotated within token families.

## Scaling roadmap

1. Move media to object storage and a CDN.
2. Use PostgreSQL read replicas for high-volume delivery traffic.
3. Cache public entries and menus in Redis or edge caches.
4. Separate delivery and management APIs when traffic patterns diverge.
5. Process webhooks, image transformations and search indexing asynchronously.
6. Add OpenSearch/Elasticsearch for full-text and faceted content search.
7. Add event streaming for analytics, rebuilds and downstream synchronization.
