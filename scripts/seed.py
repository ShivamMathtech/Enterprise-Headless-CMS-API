from sqlalchemy import select
from app.database import SessionLocal
from app.core.config import get_settings
from app.core.security import hash_password
from app.models.entities import (
    User, Role, Site, SiteMember, SiteRole, Environment, Locale,
    ContentType, ContentEntry, EntryStatus
)
from app.services import create_revision

PASSWORD = 'Password@123'
USERS = [
    ('admin@cms.example.com', 'CMS Super Administrator', Role.super_admin),
    ('platform@cms.example.com', 'Platform Administrator', Role.platform_admin),
    ('auditor@cms.example.com', 'Compliance Auditor', Role.auditor),
    ('developer@cms.example.com', 'Platform Developer', Role.developer),
    ('editor@cms.example.com', 'Content Editor', Role.user),
    ('author@cms.example.com', 'Content Author', Role.user),
    ('reviewer@cms.example.com', 'Content Reviewer', Role.user),
    ('media@cms.example.com', 'Media Manager', Role.user),
]


def seed():
    settings = get_settings()
    db = SessionLocal()
    try:
        users = {}
        for email, name, role in USERS:
            user = db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(email=email, full_name=name, password_hash=hash_password(PASSWORD), role=role)
                db.add(user)
                db.flush()
            users[email] = user
        site = db.scalar(select(Site).where(Site.key == 'demo'))
        if not site:
            admin = users['admin@cms.example.com']
            site = Site(
                key='demo',
                name='Demo Enterprise Website',
                description='Seeded multi-site CMS workspace',
                default_locale='en-US',
                timezone='Asia/Kolkata',
                settings={'brand': 'MathTech CMS', 'preview_base_url': 'http://localhost:3000/preview'},
                created_by=admin.id,
            )
            db.add(site)
            db.flush()
            memberships = [
                (admin, SiteRole.owner),
                (users['editor@cms.example.com'], SiteRole.editor),
                (users['author@cms.example.com'], SiteRole.author),
                (users['reviewer@cms.example.com'], SiteRole.reviewer),
                (users['media@cms.example.com'], SiteRole.media_manager),
                (users['developer@cms.example.com'], SiteRole.developer),
            ]
            for member, role in memberships:
                db.add(SiteMember(site_id=site.id, user_id=member.id, role=role))
            dev = Environment(site_id=site.id, key='development', name='Development')
            prod = Environment(site_id=site.id, key='production', name='Production', is_production=True)
            db.add_all([dev, prod])
            db.flush()
            db.add_all([
                Locale(site_id=site.id, code='en-US', name='English (United States)', is_default=True),
                Locale(site_id=site.id, code='hi-IN', name='Hindi (India)', is_default=False),
            ])
            article = ContentType(
                site_id=site.id,
                key='article',
                name='Article',
                description='SEO-ready editorial article',
                schema_definition={
                    'fields': [
                        {'key': 'summary', 'type': 'text', 'required': True},
                        {'key': 'body', 'type': 'rich_text', 'required': True},
                        {'key': 'featured', 'type': 'boolean', 'required': False},
                        {'key': 'author_name', 'type': 'text', 'required': True},
                    ]
                },
                display_field='title',
                is_published=True,
                created_by=admin.id,
            )
            db.add(article)
            db.flush()
            entry = ContentEntry(
                site_id=site.id,
                environment_id=prod.id,
                content_type_id=article.id,
                locale='en-US',
                title='Welcome to the Enterprise CMS',
                slug='welcome-enterprise-cms',
                status=EntryStatus.published,
                workflow_stage='published',
                data={
                    'summary': 'A production-style headless CMS starter built with FastAPI.',
                    'body': '<p>This entry is available through the public delivery API.</p>',
                    'featured': True,
                    'author_name': 'CMS Platform Team',
                },
                seo={'title': 'Enterprise CMS', 'description': 'FastAPI enterprise CMS demonstration'},
                created_by=admin.id,
                updated_by=admin.id,
                approved_by=admin.id,
                published_by=admin.id,
                published_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc),
            )
            db.add(entry)
            db.flush()
            create_revision(db, entry, admin.id, 'Seeded published version')
        db.commit()
        print(f'Seed complete. Database: {settings.database_url}')
        print(f'All demo accounts use: {PASSWORD}')
    finally:
        db.close()


if __name__ == '__main__':
    seed()
