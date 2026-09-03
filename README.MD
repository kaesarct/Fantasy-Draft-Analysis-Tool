<div align="center">
    <img src="https://www.fantacalcio.it/images/logo-fantacalcio.svg" class="logo" width='100px' />
    <h1>Fantacalcio Platform</h1>
    <strong>Piattaforma Full-Stack (Angular + FastAPI) per la gestione della tua lega di Fantacalcio</strong>
    <br>
    <img alt="GitHub top language" src="https://img.shields.io/github/languages/top/pygera/fantacalcio-bot?logo=typescript">
</div>

# Fantacalcio Platform

La **Fantacalcio Platform** è una moderna applicazione web full-stack progettata per gestire, storicizzare e visualizzare tutti i dati della tua lega fantacalcio (inclusi grafici su prezzi, FVM, risultati e formazioni).

> **Nota:** Questa repository contiene l'evoluzione dell'originale "Fantacalcio Bot Telegram", che è stato completamente rimosso a favore di una piattaforma web completa.

## 🛠️ Stack Tecnologico

- **Frontend**: Angular 18 (standalone components, signals), PrimeNG (design system dark mode), ApexCharts per la visualizzazione dati.
- **Backend**: Python 3.12, FastAPI, SQLAlchemy, PostgreSQL, APScheduler per sincronizzazioni automatiche da fantacalcio.it.

## 🚀 Funzionalità Principali

- **Dashboard completa**: Statistiche veloci, prossimi incontri di Serie A e stato infortuni.
- **Statistiche Giocatori**: Dati anagrafici, ruolo, quotazioni, FVM (Fantavalore di Mercato) e tracking variazioni di prezzo.
- **Gestione Squadre**: Dati fanta-team, loghi stagionali, crediti residui e allenatori multipli per squadra.
- **Classifiche e Competizioni**: Supporto completo per campionati complessi (Gold, Bronze, Carbon, Silver League, Ciempions, UEFA).
- **Infortuni e Sostituzioni**: Tracking dei rientri previsti e gestione delle sostituzioni temporanee per infortuni prolungati (≥8 settimane).
- **Premio Goku & Premio Oscar**: pagina pubblica (nessun login richiesto) con il punteggio più alto/basso di giornata della stagione corrente, lo storico dal 2018/19 e il record assoluto in evidenza. Sotto Admin, una sezione "Coerenza Silver" segnala eventuali discrepanze tra la classifica Silver e quella del campionato di appartenenza (Gold/Bronze/Carbon) di ogni squadra.
- **Sync squadre/allenatori da leghe.fantacalcio.it**: sotto Admin, da usare una volta l'anno a inizio stagione — scarica i partecipanti reali dalla lega su leghe.fantacalcio.it e propone il collegamento a squadre/allenatori già presenti nel nostro DB (o la creazione di quelli nuovi), salvando l'id squadra esterno per future sincronizzazioni automatiche.

## 🐳 Installazione rapida con Docker (Raccomandata)

L'intero stack (Database, Backend API, Frontend Web) può essere avviato facilmente utilizzando Docker Compose.

### 1. Clona il repository

```bash
git clone https://github.com/tuo-username/ft-platform.git
cd ft-platform
```

### 2. Configura l'ambiente

Docker Compose legge le variabili dal file `.env` nella **root** del progetto (non da `backend/.env`, che serve solo per l'esecuzione locale senza Docker — vedi sotto).

```bash
cp .env.example .env
# Apri .env e inserisci FANTA_USERNAME, FANTA_PASSWORD, FANTA_YEAR_QUOTAZIONI, ecc.
```

> Un `FANTA_YEAR_QUOTAZIONI` sbagliato (es. una stagione futura non ancora pubblicata da fantacalcio.it) non da' errore: l'API risponde 200 OK ma con un Excel vuoto, e la sincronizzazione fallisce silenziosamente con "Download failed".

Le funzioni di scrittura (sync, import storico, inserimento/gestione infortuni,
pannello Admin) sono protette da un login admin. Genera l'hash della password e
il secret JWT **prima del primo avvio**, altrimenti il login non funzionerà:

```bash
openssl rand -hex 32   # -> valore per JWT_SECRET
# dopo il primo `docker-compose up` (serve l'immagine backend già buildata):
docker compose exec backend python -m app.services.auth_service "la-tua-password"   # -> valore per ADMIN_PASSWORD_HASH
```

Inserisci in `.env`: `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`, `JWT_SECRET`. Senza
questi valori l'endpoint di login rifiuta sempre le credenziali.

### 3. Avvia i servizi

```bash
docker-compose up --build -d
```

- **Frontend (Web App)**: `http://localhost:4200`
- **Backend (API Docs)**: `http://localhost:8000/docs`

## 💻 Ambiente di Sviluppo Locale

Se preferisci avviare l'applicazione in modalità dev sul tuo host:

### Backend (FastAPI)
```bash
cd backend
python -m venv venv
source venv/bin/activate  # su Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # Configura le variabili
uvicorn app.main:app --reload --port 8000
```

### Frontend (Angular)
```bash
cd frontend
npm install
npx ng serve
```

## 🔄 Sincronizzazione Dati

Il backend ha un job `APScheduler` integrato che scarica in autonomia le "Quotazioni" e i "Voti" ogni giorno alle `23:00`.
Puoi forzare la sincronizzazione in qualsiasi momento chiamando le API di sync (es. `POST /api/sync/prices?season_id=1`).

## 🔑 Sessione leghe.fantacalcio.it

Il download delle formazioni usa un browser autenticato (Playwright): l'endpoint
`V1_LegheFormazioni/Pagina` rifiuta le chiamate HTTP dirette. La sessione viene
salvata in `backend/session/tamarros_session.json` (montata nel container come
`/app/session`) e va rigenerata quando i cookie scadono — durano circa una settimana:

```bash
docker compose exec backend python capture_login_session.py
```

Il login è automatico e headless (il form leghe non ha captcha), quindi gira nel
container. Se il sito cambia il form o introduce un captcha, resta il fallback
manuale con browser visibile, da eseguire **sull'host**:

```bash
cd backend && python capture_login_session.py --manual
```

> Il mount della sessione è una **directory** (`./backend/session:/app/session`),
> non un file: un bind mount su un file inesistente fa creare a Docker una
> directory al suo posto, e ogni lettura della sessione fallisce con
> `IsADirectoryError`.

## 🩺 Diagnostica delle chiamate esterne

`backend/scripts/check_api.py` verifica, una per una, tutte le chiamate verso
`fantacalcio.it` e `leghe.fantacalcio.it` usando le stesse funzioni dell'app: se
il sito cambia HTML, endpoint o `app_key`, il guasto emerge qui invece che a
sincronizzazione fallita. È di sola lettura (nessuna scrittura su DB, gli Excel
vengono scaricati in una directory temporanea).

```bash
docker compose exec backend python -m scripts.check_api               # solo chiamate HTTP (~20s)
docker compose exec backend python -m scripts.check_api --playwright  # aggiunge dashboard lega + formazioni (~1 min)
```

Esce con codice `1` se almeno un check è `FAIL`. Nello stack di sviluppo il
codice del backend non è montato come volume: dopo aver modificato lo script
serve `docker compose up -d --build backend` (oppure, per una prova veloce,
`docker cp ./backend/scripts ft-platform-backend-1:/app/scripts`).

Cosa copre:

| Ambito | Check |
| --- | --- |
| fantacalcio.it pubblico | `live-serie-a` (ultima giornata + calendario), `probabili-formazioni-serie-a`, `infortunati-serie-a` — verifica che i selettori HTML esistano ancora |
| fantacalcio.it API | `POST api/v1/User/login`, `Excel/prices`, `Excel/stats`, `Excel/votes` — segnala il caso "200 OK ma file da 0 byte" |
| leghe.fantacalcio.it | homepage leghe, discovery `authAppKey`, `POST apileague/onboarding/v1/login`, alias lega confrontato con le leghe dell'utente, `league/competitions`, validità e scadenza del session file |
| leghe con browser (`--playwright`) | dropdown competizioni della dashboard, intercettazione `V1_LegheFormazioni/Pagina` |

I `WARN` di pre-stagione sono attesi: senza giornate giocate non ci sono voti da
scaricare, e finché non crei le competizioni in lega il dropdown è vuoto. Il
conteggio via `league/competitions` serve proprio a distinguere quel caso da una
sessione scaduta, che dalla sola dashboard sono indistinguibili.
