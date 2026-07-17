from datetime import datetime, timedelta, timezone


def test_refresh_rotation_and_reuse_detection(client):
    login = client.post('/api/v1/auth/login', json={
        'email': 'admin@cms.example.com',
        'password': 'Password@123',
    })
    assert login.status_code == 200, login.text
    first = login.json()['refresh_token']
    rotated = client.post('/api/v1/auth/refresh', json={'refresh_token': first})
    assert rotated.status_code == 200, rotated.text
    reuse = client.post('/api/v1/auth/refresh', json={'refresh_token': first})
    assert reuse.status_code == 401


def test_complete_enterprise_cms_lifecycle(client, auth):
    admin = auth(client, 'admin@cms.example.com')

    author_create = client.post('/api/v1/auth/users', headers=admin, json={
        'email': 'writer@test.example.com',
        'full_name': 'Enterprise Writer',
        'password': 'Password@123',
        'role': 'user',
    })
    assert author_create.status_code == 201, author_create.text
    author_id = author_create.json()['id']
    author = auth(client, 'writer@test.example.com')

    site_resp = client.post('/api/v1/sites', headers=admin, json={
        'key': 'enterprise-news',
        'name': 'Enterprise Newsroom',
        'description': 'Multi-channel editorial workspace',
        'default_locale': 'en-US',
        'timezone': 'Asia/Kolkata',
        'settings': {'brand': 'Enterprise News'},
    })
    assert site_resp.status_code == 201, site_resp.text
    site_id = site_resp.json()['id']

    member = client.post(f'/api/v1/sites/{site_id}/members', headers=admin, json={
        'user_id': author_id,
        'role': 'author',
    })
    assert member.status_code == 201, member.text

    environments = client.get(f'/api/v1/sites/{site_id}/environments', headers=admin)
    assert environments.status_code == 200
    prod_id = next(x['id'] for x in environments.json() if x['key'] == 'production')

    locale = client.post(f'/api/v1/sites/{site_id}/locales', headers=admin, json={
        'code': 'hi-IN',
        'name': 'Hindi (India)',
        'is_default': False,
    })
    assert locale.status_code == 201, locale.text

    content_type = client.post('/api/v1/content-types', headers=admin, json={
        'site_id': site_id,
        'key': 'article',
        'name': 'Article',
        'description': 'Editorial article with SEO metadata',
        'display_field': 'title',
        'is_singleton': False,
        'schema_definition': {
            'fields': [
                {'key': 'summary', 'type': 'text', 'required': True},
                {'key': 'body', 'type': 'rich_text', 'required': True},
                {'key': 'featured', 'type': 'boolean', 'required': False},
                {'key': 'priority', 'type': 'integer', 'required': False},
            ]
        },
    })
    assert content_type.status_code == 201, content_type.text
    content_type_id = content_type.json()['id']
    published_type = client.post(f'/api/v1/content-types/{content_type_id}/publish', headers=admin)
    assert published_type.status_code == 200

    tag = client.post('/api/v1/tags', headers=admin, json={
        'site_id': site_id,
        'name': 'FastAPI',
        'slug': 'fastapi',
        'color': '#2563EB',
    })
    assert tag.status_code == 201, tag.text
    tag_id = tag.json()['id']

    folder = client.post('/api/v1/media/folders', headers=admin, json={
        'site_id': site_id,
        'name': 'Article Images',
    })
    assert folder.status_code == 201, folder.text
    folder_id = folder.json()['id']

    upload = client.post(
        '/api/v1/media/upload',
        headers=admin,
        data={'site_id': site_id, 'folder_id': folder_id, 'title': 'Hero image', 'alt_text': 'Enterprise CMS hero'},
        files={'file': ('hero.txt', b'cms-media-payload', 'text/plain')},
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()['checksum_sha256']

    entry = client.post('/api/v1/entries', headers=author, json={
        'site_id': site_id,
        'environment_id': prod_id,
        'content_type_id': content_type_id,
        'locale': 'en-US',
        'title': 'Building an Enterprise Headless CMS',
        'slug': 'building-enterprise-headless-cms',
        'data': {
            'summary': 'A practical architecture guide.',
            'body': '<p>Enterprise CMS content body.</p>',
            'featured': True,
            'priority': 1,
        },
        'seo': {
            'title': 'Enterprise Headless CMS with FastAPI',
            'description': 'A complete enterprise CMS backend architecture guide.',
        },
        'tag_ids': [tag_id],
    })
    assert entry.status_code == 201, entry.text
    entry_id = entry.json()['id']
    assert entry.json()['version'] == 1

    updated = client.patch(f'/api/v1/entries/{entry_id}', headers=author, json={
        'expected_version': 1,
        'data': {
            'summary': 'A practical architecture and implementation guide.',
            'body': '<p>Updated enterprise CMS content body.</p>',
            'featured': True,
            'priority': 2,
        },
        'note': 'Improved the article summary and priority.',
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()['version'] == 2

    conflict = client.patch(f'/api/v1/entries/{entry_id}', headers=author, json={
        'expected_version': 1,
        'title': 'Stale update should fail',
    })
    assert conflict.status_code == 409

    revisions = client.get(f'/api/v1/entries/{entry_id}/revisions', headers=author)
    assert revisions.status_code == 200
    assert len(revisions.json()) >= 2

    comment = client.post(f'/api/v1/entries/{entry_id}/comments', headers=author, json={
        'body': 'Please verify the SEO title before publishing.',
    })
    assert comment.status_code == 201, comment.text

    submitted = client.post(f'/api/v1/entries/{entry_id}/submit', headers=author, json={'note': 'Ready for review'})
    assert submitted.status_code == 200
    approved = client.post(f'/api/v1/entries/{entry_id}/approve', headers=admin, json={'note': 'Editorial review passed'})
    assert approved.status_code == 200, approved.text
    published = client.post(f'/api/v1/entries/{entry_id}/publish', headers=admin)
    assert published.status_code == 200, published.text
    assert published.json()['status'] == 'published'

    preview = client.post(f'/api/v1/entries/{entry_id}/preview-token', headers=author)
    assert preview.status_code == 200
    preview_result = client.get(f"/api/v1/preview/{preview.json()['token']}")
    assert preview_result.status_code == 200
    assert preview_result.json()['slug'] == 'building-enterprise-headless-cms'

    public = client.get('/api/v1/delivery/sites/enterprise-news/entries/article/building-enterprise-headless-cms')
    assert public.status_code == 200, public.text
    assert public.json()['data']['priority'] == 2

    menu = client.post('/api/v1/menus', headers=admin, json={
        'site_id': site_id,
        'key': 'main-navigation',
        'name': 'Main Navigation',
        'locale': 'en-US',
    })
    assert menu.status_code == 201
    menu_id = menu.json()['id']
    item = client.post(f'/api/v1/menus/{menu_id}/items', headers=admin, json={
        'label': 'CMS Guide',
        'entry_id': entry_id,
        'position': 0,
    })
    assert item.status_code == 201, item.text
    public_menu = client.get('/api/v1/delivery/sites/enterprise-news/menus/main-navigation')
    assert public_menu.status_code == 200
    assert public_menu.json()['items'][0]['label'] == 'CMS Guide'

    redirect = client.post('/api/v1/redirects', headers=admin, json={
        'site_id': site_id,
        'source_path': '/old-cms-guide',
        'destination_url': '/building-enterprise-headless-cms',
        'status_code': 301,
    })
    assert redirect.status_code == 201
    resolved = client.get('/api/v1/delivery/sites/enterprise-news/redirects/resolve', params={'path': '/old-cms-guide'})
    assert resolved.status_code == 200

    api_key = client.post('/api/v1/api-keys', headers=admin, json={
        'site_id': site_id,
        'name': 'Production Delivery Key',
        'scopes': ['delivery:read'],
    })
    assert api_key.status_code == 201, api_key.text
    secret = api_key.json()['secret']
    keyed_delivery = client.get(
        '/api/v1/delivery/sites/enterprise-news/entries',
        headers={'X-API-Key': secret},
        params={'content_type': 'article'},
    )
    assert keyed_delivery.status_code == 200, keyed_delivery.text
    assert len(keyed_delivery.json()) == 1

    webhook = client.post('/api/v1/webhooks', headers=admin, json={
        'site_id': site_id,
        'name': 'Deployment Hook',
        'url': 'https://example.com/cms-hook',
        'events': ['entry.published'],
    })
    assert webhook.status_code == 201, webhook.text
    webhook_id = webhook.json()['id']
    delivery = client.post(f'/api/v1/webhooks/{webhook_id}/test', headers=admin)
    assert delivery.status_code == 200, delivery.text
    assert delivery.json()['status'] == 'succeeded'

    health = client.get('/api/v1/reports/content-health', headers=admin, params={'site_id': site_id})
    assert health.status_code == 200
    assert health.json()['total_entries'] == 1
    dashboard = client.get('/api/v1/reports/dashboard', headers=admin, params={'site_id': site_id})
    assert dashboard.status_code == 200
    assert dashboard.json()['entries'] == 1
    logs = client.get('/api/v1/reports/audit-logs', headers=admin, params={'site_id': site_id})
    assert logs.status_code == 200
    assert len(logs.json()) >= 10


def test_scheduled_publish_processor(client, auth):
    admin = auth(client, 'admin@cms.example.com')
    sites = client.get('/api/v1/sites', headers=admin).json()
    site = next(s for s in sites if s['key'] == 'demo')
    envs = client.get(f"/api/v1/sites/{site['id']}/environments", headers=admin).json()
    prod = next(e for e in envs if e['key'] == 'production')
    types = client.get('/api/v1/content-types', headers=admin, params={'site_id': site['id']}).json()
    article = next(t for t in types if t['key'] == 'article')
    entry = client.post('/api/v1/entries', headers=admin, json={
        'site_id': site['id'],
        'environment_id': prod['id'],
        'content_type_id': article['id'],
        'locale': 'en-US',
        'title': 'Scheduled CMS Release',
        'slug': 'scheduled-cms-release',
        'data': {
            'summary': 'Scheduled publication test',
            'body': '<p>Scheduled body</p>',
            'featured': False,
            'author_name': 'CMS Platform Team',
        },
        'seo': {'title': 'Scheduled CMS Release', 'description': 'Scheduled release validation'},
    })
    assert entry.status_code == 201, entry.text
    entry_id = entry.json()['id']
    assert client.post(f'/api/v1/entries/{entry_id}/submit', headers=admin, json={}).status_code == 200
    assert client.post(f'/api/v1/entries/{entry_id}/approve', headers=admin, json={}).status_code == 200
    schedule_time = datetime.now(timezone.utc) + timedelta(minutes=5)
    scheduled = client.post(f'/api/v1/entries/{entry_id}/schedule', headers=admin, json={'publish_at': schedule_time.isoformat()})
    assert scheduled.status_code == 200, scheduled.text
    assert client.post(f'/api/v1/entries/{entry_id}/cancel-schedule', headers=admin).status_code == 200
