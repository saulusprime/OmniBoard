# Come contribuire a Scacchi

Grazie per l'interesse verso **Scacchi**! I contributi sono benvenuti: codice, nuovi giochi,
documentazione, traduzioni, segnalazioni di bug e idee.

## Prima di iniziare

- Leggi il [Codice di Condotta](./CODE_OF_CONDUCT.md): partecipando lo accetti.
- Dai un'occhiata a [README.md](./README.md) per la visione e l'architettura, e a
  [MEMORY.md](./MEMORY.md) per le decisioni tecniche.
- Per segnalare una **vulnerabilità di sicurezza** non aprire una issue pubblica: segui
  [SECURITY.md](./SECURITY.md).

## Tipi di contributo

- 🐛 **Bug report** — apri una issue con il modello «Bug report».
- 💡 **Proposte di funzionalità o nuovi giochi** — apri una issue con il modello «Feature request».
- 🧩 **Nuovo gioco** — implementa le primitive del motore astratto e documenta le regole in
  [MANUAL.md](./MANUAL.md) usando il modello per nuovi giochi.
- 📝 **Documentazione** — miglioramenti a README/MANUAL/MEMORY e alle guide.

## Flusso di lavoro (Pull Request)

1. Fai un **fork** del repository e crea un branch descrittivo
   (es. `feat/motore-tris`, `fix/validazione-arrocco`).
2. Mantieni le modifiche **focalizzate**: una PR = un obiettivo.
3. Assicurati che **lint e test** passino in locale prima di aprire la PR.
4. Aggiorna la documentazione pertinente. In particolare, per ogni avanzamento significativo
   aggiorna **HANDOFF.md**, **README.md**, **MEMORY.md** e **MANUAL.md** (è una pratica
   continuativa del progetto).
5. Apri la Pull Request compilando il [modello di PR](./.github/PULL_REQUEST_TEMPLATE.md).

## Stile e qualità del codice

- Linguaggio principale: **Python 3.12+**.
- **Lint e formattazione:** `ruff` (lint + format).
- **Test:** `pytest`. Il **motore** deve restare logica pura e ben coperto da test.
- Messaggi di commit chiari; è consigliato lo stile
  [Conventional Commits](https://www.conventionalcommits.org/) (es. `feat:`, `fix:`, `docs:`).

> Comandi precisi (installazione, lint, test, avvio) saranno aggiunti qui appena lo scaffold
> del codice sarà presente.

## Licenza dei contributi

Contribuendo accetti che il tuo lavoro sia distribuito sotto la licenza **MIT** del progetto
(vedi [LICENCE.md](./LICENCE.md)).
