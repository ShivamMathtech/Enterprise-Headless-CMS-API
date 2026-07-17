install:
	python -m pip install -r requirements.txt
migrate:
	alembic upgrade head
seed:
	python -m scripts.seed
run:
	uvicorn app.main:app --reload
test:
	pytest -q
openapi:
	python -m scripts.export_openapi
postman:
	python -m scripts.export_postman
