# Backend — FastAPI

API e logica della piattaforma Scacchi: anagrafica giocatori, gruppi (con fondazione
tramite voto), punteggi per gioco, classifiche (universale e per gioco).

## Avvio (sviluppo)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Database: per default SQLite (`scacchi.db` nella cartella `backend/`). Per PostgreSQL
impostare `DATABASE_URL` (vedi `.env.example` nella root).

Documentazione interattiva dell'API: <http://127.0.0.1:8000/docs>

## Endpoint principali

| Metodo | Path | Descrizione |
|--------|------|-------------|
| POST   | `/users` | Crea un giocatore |
| GET    | `/users` · `/users/{id}` | Lista / dettaglio (con punteggi) |
| GET    | `/games` | Catalogo giochi |
| POST   | `/groups/proposals` | Proponi la fondazione di un gruppo |
| POST   | `/groups/proposals/{id}/vote` | Vota una proposta |
| GET    | `/groups` · `/groups/proposals` | Gruppi fondati / proposte |
| POST   | `/matches` | Registra il risultato di una partita (aggiorna i punteggi) |
| GET    | `/rankings/universal` | Classifica universale |
| GET    | `/rankings/games/{code}?scope=global\|national\|regional` | Classifica per gioco |

## Struttura

```text
backend/app/
├── main.py        # app FastAPI, lifespan (create_all + seed), router
├── database.py    # engine, sessione, Base
├── models.py      # modelli SQLAlchemy
├── schemas.py     # schemi Pydantic
├── security.py    # hashing password (pbkdf2, stdlib)
├── seed.py        # catalogo giochi iniziale
└── routers/       # users, games, groups, matches, rankings
```
