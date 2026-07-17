import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os
import shutil
import pytest

TEST_DB = Path('test_cms.db')
TEST_UPLOADS = Path('test_uploads')
os.environ['DATABASE_URL'] = f'sqlite:///./{TEST_DB}'
os.environ['UPLOAD_DIR'] = str(TEST_UPLOADS)
os.environ['PUBLIC_MEDIA_BASE_URL'] = 'http://testserver/media'
os.environ['DEBUG'] = 'true'

if TEST_DB.exists():
    TEST_DB.unlink()
if TEST_UPLOADS.exists():
    shutil.rmtree(TEST_UPLOADS)

from fastapi.testclient import TestClient
from app.database import Base, engine
from app.main import app
from scripts.seed import seed

Base.metadata.create_all(bind=engine)
seed()


@pytest.fixture(scope='session')
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope='session')
def auth():
    def _auth(client, email, password='Password@123'):
        response = client.post('/api/v1/auth/login', json={'email': email, 'password': password})
        assert response.status_code == 200, response.text
        return {'Authorization': f"Bearer {response.json()['access_token']}"}
    return _auth
