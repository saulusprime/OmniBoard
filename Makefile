# Comandi di sviluppo per la piattaforma Scacchi.
# Usa un singolo virtualenv di root condiviso da backend e frontend (entrambi Python).

VENV = .venv
PY   = $(VENV)/bin/python
PIP  = $(VENV)/bin/pip

.PHONY: help install backend frontend migrate migration piper

help:
	@echo "make install   - crea .venv e installa le dipendenze di backend e frontend"
	@echo "make backend   - avvia il backend FastAPI su http://127.0.0.1:8000"
	@echo "make frontend  - avvia il frontend Django su http://127.0.0.1:8001"
	@echo "make migrate   - porta il database all'ultima revisione (alembic upgrade head)"
	@echo 'make migration m="descrizione" - genera una migrazione dai modelli (autogenerate)'
	@echo "make piper     - abilita le voci italiane del TTS (piper-tts, GPL-3: scelta esplicita)"

install:
	git submodule update --init  # integrazioni/KittenTTS (dipendenza del backend)
	python3 -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -r backend/requirements.txt -r frontend/requirements.txt

backend:
	cd backend && ../$(VENV)/bin/uvicorn app.main:app --reload --port 8000

frontend:
	$(PY) frontend/manage.py runserver 8001

migrate:
	cd backend && ../$(VENV)/bin/alembic upgrade head

# Genera una revisione confrontando i modelli con il DB: make migration m="descrizione"
migration:
	cd backend && ../$(VENV)/bin/alembic revision --autogenerate -m "$(m)"

# Voci italiane del servizio /tts: piper-tts e' opzionale (GPL-3, progetto MIT).
piper:
	$(PIP) install piper-tts
	@echo "Fatto. La voce italiana (it_IT-paola-medium) si scarica al primo uso di /tts?lang=it"
