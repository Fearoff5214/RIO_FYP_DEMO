# Novaliseo Makefile — Windows-compatible with PowerShell
.PHONY: dev test lint migrate seed demo ingest-sample-kb install help

help:
	@echo "Novaliseo make targets:"
	@echo "  install         Install Python dependencies"
	@echo "  dev             Start all services (requires Docker or manual services)"
	@echo "  migrate         Run Alembic database migrations"
	@echo "  seed            Seed database with sample data"
	@echo "  test            Run all tests"
	@echo "  lint            Run ruff + mypy"
	@echo "  demo            Run golden end-to-end demo (mock mode)"
	@echo "  ingest-sample-kb  Ingest sample knowledge base documents"

install:
	pip install -r backend/requirements.txt

dev:
	@echo "Starting Novaliseo API..."
	uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000

migrate:
	cd backend && alembic upgrade head

seed:
	python scripts/seed_demo.py

test:
	pytest backend/tests/ -v --tb=short

lint:
	ruff check backend/ scripts/
	mypy backend/app/

demo:
	python scripts/run_demo.py

ingest-sample-kb:
	python scripts/load_kb.py
