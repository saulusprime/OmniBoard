# Comandi di sviluppo per la piattaforma Scacchi.
# Usa un singolo virtualenv di root condiviso da backend e frontend (entrambi Python).

VENV = .venv
PY   = $(VENV)/bin/python
PIP  = $(VENV)/bin/pip

.PHONY: help install backend frontend

help:
	@echo "make install   - crea .venv e installa le dipendenze di backend e frontend"
	@echo "make backend   - avvia il backend FastAPI su http://127.0.0.1:8000"
	@echo "make frontend  - avvia il frontend Django su http://127.0.0.1:8001"

install:
	python3 -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -r backend/requirements.txt -r frontend/requirements.txt

backend:
	cd backend && ../$(VENV)/bin/uvicorn app.main:app --reload --port 8000

frontend:
	$(PY) frontend/manage.py runserver 8001
