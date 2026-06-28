# Frontend — Django

Livello di presentazione della piattaforma Scacchi: pagine web, menu e form. Non possiede
dati di dominio: legge e scrive tutto tramite il backend FastAPI (vedi `web/api_client.py`).

## Avvio (sviluppo)

Assicurati che il backend sia in esecuzione (porta 8000), poi:

```bash
cd frontend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver 8001
```

Apri <http://127.0.0.1:8001/>. L'URL del backend si configura con `BACKEND_API_URL`
(vedi `.env.example` nella root).

> Nota: il frontend è volutamente senza database (le app Django che lo richiedono sono
> disattivate; i messaggi usano lo storage su cookie). Non serve eseguire `migrate`.

## Pagine

- `/` — presentazione e giochi disponibili
- `/giocatori/` — elenco e creazione giocatori
- `/gruppi/` — gruppi fondati, proposte e voti
- `/classifiche/` — classifica universale e per gioco (globale/nazionale/regionale)
- `/partite/registra/` — registrazione risultato (aggiorna i punteggi)

## Struttura

```text
frontend/
├── manage.py
├── scacchi_web/        # progetto Django (settings, urls, wsgi/asgi)
└── web/                # app: views, forms, api_client, urls, templates
```
