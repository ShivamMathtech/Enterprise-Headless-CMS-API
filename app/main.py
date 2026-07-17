import uuid
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from app.core.config import get_settings
from app.database import engine
from app.api import auth, sites, content_types, entries, media, navigation, integrations, reports, public

settings = get_settings()
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=settings.app_name,
    version='1.0.0',
    description=(
        'Enterprise headless CMS backend for multi-site content modeling, editorial workflows, '
        'media, localization, delivery APIs, webhooks, API keys, navigation and analytics.'
    ),
    contact={'name': 'CMS Platform Team'},
    license_info={'name': 'MIT'},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts or ['*'])
app.mount('/media', StaticFiles(directory=settings.upload_dir), name='media')


@app.middleware('http')
async def request_context(request: Request, call_next):
    request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers['X-Request-ID'] = request_id
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            'detail': 'Request validation failed',
            'request_id': getattr(request.state, 'request_id', None),
            'errors': exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    if settings.debug:
        raise exc
    return JSONResponse(
        status_code=500,
        content={
            'detail': 'Internal server error',
            'request_id': getattr(request.state, 'request_id', None),
        },
    )


@app.get('/health', tags=['System'])
def health():
    return {'status': 'healthy', 'service': settings.app_name, 'environment': settings.environment}


@app.get('/ready', tags=['System'])
def ready():
    with engine.connect() as connection:
        connection.execute(text('SELECT 1'))
    return {'status': 'ready', 'database': 'connected'}


for router in (
    auth.router,
    sites.router,
    content_types.router,
    entries.router,
    media.router,
    navigation.router,
    integrations.router,
    reports.router,
):
    app.include_router(router, prefix=settings.api_v1_prefix)

app.include_router(public.router, prefix=settings.api_v1_prefix)
