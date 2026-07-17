# Windows Setup

## Recommended runtime

Use Python 3.12 for broad binary-package compatibility.

```powershell
cd enterprise-cms-api
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` for SQLite:

```env
DATABASE_URL=sqlite:///./cms.db
REDIS_URL=
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
TRUSTED_HOSTS=localhost,127.0.0.1,testserver
UPLOAD_DIR=./uploads
PUBLIC_MEDIA_BASE_URL=http://127.0.0.1:8000/media
```

Initialize and run:

```powershell
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload
```

Run validation:

```powershell
pytest -q
python -m scripts.export_openapi
python -m scripts.export_postman
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```
