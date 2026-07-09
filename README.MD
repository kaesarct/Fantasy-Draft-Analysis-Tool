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
