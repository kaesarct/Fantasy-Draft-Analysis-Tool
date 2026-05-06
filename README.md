# ⚽ FantaDash — Sistema di Analisi per Fantacalcio Privato
<div align="center"><img alt="GitHub top language" src="https://img.shields.io/github/languages/top/pygera/fantacalcio-bot?logo=python"></div>
Applicazione web Django per la gestione e l'analisi di una lega di fantacalcio privata. Integra dati storici scaricati dall'API di Fantacalcio.it con strategie personali pre-asta, permettendo analisi incrociate su più stagioni.

---

## 📋 Indice

- [Funzionalità](#-funzionalità)
- [Stack Tecnologico](#-stack-tecnologico)
- [Struttura del Progetto](#-struttura-del-progetto)
- [Modelli Dati](#-modelli-dati)
- [Installazione](#-installazione)
- [Configurazione `.env`](#-configurazione-env)
- [Comandi di Gestione](#-comandi-di-gestione)
- [Dashboard Admin](#-dashboard-import-admin)
- [Frontend — URL disponibili](#-frontend--url-disponibili)
- [Sistema di Logging](#-sistema-di-logging)
- [Deploy & Note Tecniche](#-deploy--note-tecniche)

---

## ✨ Funzionalità

### 📊 Analisi Dati
| Sezione | Descrizione |
|---|---|
| **Scheda Giocatore** | Storico statistiche stagionali (Mv, Fm, Gol, Assist, Amm, Esp), voti per giornata cromatici, box pre-asta personale |
| **Classifica** | Top 100 calciatori per stagione e ruolo, ordinabile per 5 metriche differenti |
| **Confronto** | Tabella side-by-side multi-stagione tra 2 calciatori qualsiasi |

### 🏆 Fantacompetizioni
| Sezione | Descrizione |
|---|---|
| **Leghe** | Creazione e gestione leghe private |
| **Fantasquadre** | Creazione squadre con assegnazione presidenti multipli e crediti |
| **Rosa** | Visualizzazione rosa raggruppata per ruolo con statistiche live, upload Excel ingaggi, rimozione singolo giocatore |

### ⚙️ Admin & Import
| Funzione | Descrizione |
|---|---|
| **Download Statistiche** | Scarica storici statistiche da API Fantacalcio.it (skip se già presenti, forza per stagione attuale) |
| **Import Statistiche** | Importa i file `.xlsx` scaricati nel database Django |
| **Download Voti** | Scarica voti per giornata storici |
| **Import Voti** | Importa i voti nel database |
| **Import Pre-Asta** | Carica un file Excel Fantalab con la tua strategia d'asta personale |
| **Cancella DB** | Svuota completamente il database (con conferma) |

---

## 🛠 Stack Tecnologico

| Componente | Tecnologia |
|---|---|
| **Backend** | Django 4.2 (Python) |
| **Database** | SQLite (dev) / PostgreSQL (prod) |
| **Frontend** | HTML + CSS vanilla (dark mode, no framework) |
| **Parsing Excel** | pandas + openpyxl |
| **API Client** | requests + BeautifulSoup4 |
| **Task Asincroni** | `threading.Thread` (no Celery richiesto) |
| **Auth** | Django Auth con modello custom `FantaPresidente` |
| **Logging** | `logging.handlers.RotatingFileHandler` → `fanta_debug.log` |
| **Config** | `python-dotenv` + file `.env` |

---

## 📁 Struttura del Progetto

```
fanta/
│
├── fanta_project/         # Config Django (settings, urls, wsgi)
│   ├── settings.py
│   └── urls.py
│
├── core/                  # Modelli condivisi (Stagione, SquadraReale, ImportTask)
├── users/                 # Modello utente custom (FantaPresidente)
├── players/               # Calciatore, CalciatoreStagione
├── stats/                 # VotoPartita, StatisticaCalciatore, Dashboard import, Analisi
│   ├── management/commands/   # import_from_api.py
│   ├── static/stats/          # CSS e JS della dashboard admin
│   ├── templates/admin/       # import_dashboard.html
│   ├── utils/
│   │   ├── downloader.py      # Scarica file da API Fantacalcio
│   │   └── importer.py        # Importa statistiche e voti nel DB
│   ├── views.py               # API endpoint dashboard (POST actions)
│   ├── views_analisi.py       # Home + viste analisi frontend
│   ├── urls.py                # URL dashboard admin
│   └── urls_analisi.py        # URL analisi frontend
│
├── strategy/              # Analisi pre-asta
│   ├── models.py          # AnalisiPreAsta
│   ├── utils/importer.py  # Parser Excel Fantalab
│   └── admin.py
│
├── fantacalcio/           # Lega, FantaSquadra, Ingaggio
│   ├── models.py
│   ├── views.py           # CRUD leghe/squadre/rosa
│   ├── urls.py
│   └── forms.py
│
├── templates/             # Template globali (base.html, login, analisi, fantacalcio)
│   ├── base.html
│   ├── home.html
│   ├── registration/login.html
│   ├── analisi/
│   │   ├── giocatore.html
│   │   ├── classifica.html
│   │   └── confronto.html
│   └── fantacalcio/
│       ├── lega_list.html
│       ├── lega_detail.html
│       ├── squadra_form.html
│       └── rosa.html
│
├── dati_scaricati/        # File .xlsx scaricati dall'API (gitignored)
│   ├── statistiche/
│   ├── voti/
│   └── preasta/
│
├── fanta_debug.log        # Log rotante (gitignored)
├── .env                   # Variabili d'ambiente (gitignored)
├── .env.example           # Template env da copiare
└── requirements.txt
```

---

## 🗄 Modelli Dati

```
Stagione ──────────────────────────────────┐
SquadraReale ──────────────────────────┐   │
                                       │   │
Calciatore ──► CalciatoreStagione ◄────┘───┘
                      │
          ┌───────────┼───────────────┐
          ▼           ▼               ▼
    VotoPartita  StatisticaCalciatore  AnalisiPreAsta
                                           │
                                      (utente: FantaPresidente)

Lega ──► FantaSquadra ──► Ingaggio ──► CalciatoreStagione
              │
         (presidenti: M2M → FantaPresidente)
```

### Modelli principali

| Modello | App | Descrizione |
|---|---|---|
| `Stagione` | `core` | Anno (es. `2024/2025`), flag `attiva` |
| `SquadraReale` | `core` | Serie A team con sigla (es. `INT`) |
| `ImportTask` | `core` | Traccia ogni operazione async con stato e progresso |
| `Calciatore` | `players` | Anagrafica (nome, cognome, ruolo base) |
| `CalciatoreStagione` | `players` | Lega calciatore + stagione + squadra reale + quotazione |
| `VotoPartita` | `stats` | Voto + bonus/malus per giornata |
| `StatisticaCalciatore` | `stats` | Riepilogo stagionale (Mv, Fm, Gol, Ass...) |
| `AnalisiPreAsta` | `strategy` | Strategia personale: fascia, prezzo max, budget%, PMA, note |
| `Lega` | `fantacalcio` | Contenitore fantacompetizione |
| `FantaSquadra` | `fantacalcio` | Squadra in una lega + stagione, M2M presidenti |
| `Ingaggio` | `fantacalcio` | Giocatore nella rosa con costo d'acquisto |
| `FantaPresidente` | `users` | Estende `AbstractUser` |

---

## 🚀 Installazione

### Prerequisiti
- Python 3.11+
- pip
- (Opzionale) PostgreSQL se non si vuole SQLite

### Setup

```bash
# 1. Clona il progetto
git clone <repo-url>
cd fanta

# 2. Crea e attiva il virtualenv
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 3. Installa le dipendenze
pip install -r requirements.txt

# 4. Configura le variabili d'ambiente
cp .env.example .env
# → Modifica .env con le tue credenziali

# 5. Applica le migrazioni
python manage.py migrate

# 6. Crea il superutente
python manage.py createsuperuser

# 7. Raccogli i file statici (solo prod)
python manage.py collectstatic

# 8. Avvia il server di sviluppo
python manage.py runserver
```

Poi apri: **http://localhost:8000**

---

## 🔐 Configurazione `.env`

Copia `.env.example` in `.env` e compila:

```env
# Sicurezza Django
SECRET_KEY=tua_secret_key_super_sicura
DEBUG=True

# Credenziali API Fantacalcio.it
FANTA_USERNAME=tuo_username_fantacalcio
FANTA_PASSWORD=tua_password_fantacalcio
BASE_URL=https://api.fantacalcio.it/
BASE_API=v1/

# PostgreSQL (opzionale — se non specificato usa SQLite)
# DB_NAME=fanta_db
# DB_USER=postgres
# DB_PASSWORD=postgres
# DB_HOST=localhost
# DB_PORT=5432
```

> [!WARNING]
> Non committare mai il file `.env` — è già incluso nel `.gitignore`.

---

## 🖥 Comandi di Gestione

```bash
# Importa dati pre-asta da Excel (command management legacy)
python manage.py import_preasta --user admin --file dati_scaricati/preasta/preasta_stagione_20.xlsx
```

Per tutti gli altri import usa la **Dashboard Admin** (più comoda e con progress tracking).

---

## ⚙️ Dashboard Import Admin

> **URL:** `/admin/import-dashboard/`  
> **Accesso:** solo staff (`is_staff = True`)

La dashboard offre 5 azioni asincrone con barra di progresso in tempo reale:

| Azione | Descrizione |
|---|---|
| **Download Statistiche** | Scarica file `.xlsx` per ogni stagione dall'API. Skip automatico se già presenti (eccetto stagione attuale, sempre riscaricata) |
| **Import Statistiche** | Parsa i file e popola `StatisticaCalciatore` e `CalciatoreStagione` |
| **Download Voti** | Scarica file voti giornata per giornata. Le giornate già presenti vengono skippate (eccetto ultima) |
| **Import Voti** | Popola `VotoPartita` |
| **Import Pre-Asta** | Upload Excel Fantalab → popola `AnalisiPreAsta` per l'utente admin |

Il campo **Stagione** è una `<select>` automatica che traduce il nome stagione nel `season_id` API.

Ogni task gira in un `threading.Thread` separato e aggiorna `ImportTask` nel DB. La dashboard fa polling ogni 2 secondi per aggiornare la progress bar.

---

## 🌐 Frontend — URL disponibili

| URL | Pagina | Auth richiesta |
|---|---|---|
| `/` | **Home Dashboard** — link a tutte le sezioni + stats DB | ✅ Login |
| `/login/` | Pagina di accesso | ❌ Pubblica |
| `/logout/` | Logout | ✅ Login |
| `/analisi/giocatore/?q=Lautaro` | Scheda giocatore con storico e pre-asta | ✅ Login |
| `/analisi/classifica/` | Classifica stagionale filtrabile | ✅ Login |
| `/analisi/confronto/?q1=X&q2=Y` | Confronto side-by-side | ✅ Login |
| `/leghe/` | Lista leghe + crea nuova | ✅ Login |
| `/leghe/<id>/` | Dettaglio lega, squadre per stagione | ✅ Login |
| `/leghe/<id>/squadra/crea/` | Crea fantasquadra | ✅ Login |
| `/leghe/<id>/squadra/<id>/modifica/` | Modifica squadra e presidenti | ✅ Login |
| `/leghe/<id>/squadra/<id>/rosa/` | Rosa + upload Excel + rimozione | ✅ Login |
| `/admin/` | Django Admin | ✅ Staff |
| `/admin/import-dashboard/` | Dashboard import dati | ✅ Staff |

---

## 📄 Sistema di Logging

Il file `fanta_debug.log` (nella root del progetto, gitignored) raccoglie tutti gli eventi rilevanti con rotazione automatica:

- **Max dimensione:** 5 MB per file
- **Backup:** 3 file rotanti (15 MB totali)
- **Formato:** `[YYYY-MM-DD HH:MM:SS] LEVEL [logger] messaggio`

### Logger attivi

| Logger | Cosa monitora |
|---|---|
| `stats.views` | Ogni action POST della dashboard, avvio/fine thread |
| `stats.importer` | Statistiche e voti: file elaborati, tempi, errori Excel |
| `strategy.importer` | Import pre-asta: progresso ogni 10 righe, creati/aggiornati, errori |
| `fantacalcio.views` | CRUD leghe/squadre, upload rosa, giocatori non trovati |
| `stats.analisi` | Query analisi (placeholder per future estensioni) |

### Monitoraggio in tempo reale

```powershell
# Windows PowerShell
Get-Content .\fanta_debug.log -Wait -Tail 50
```

```bash
# macOS / Linux
tail -f fanta_debug.log
```

---

## 📦 Format Excel attesi

### Statistiche / Voti
File scaricati automaticamente dall'API Fantacalcio.it. Non modificare.

### Pre-Asta (Fantalab)
File esportato da [Fantalab.it](https://fantalab.it) con le seguenti colonne:

| Colonna | Tipo | Note |
|---|---|---|
| `Nome` | testo | Cognome + iniziale nome (es. `Lautaro M.`) |
| `Team` | testo | Nome squadra reale |
| `Ruolo` | testo | `P`, `D`, `C`, `A` |
| `Quo` | numero | Quotazione iniziale |
| `Fascia` | testo | Es. `Top`, `A`, `B`, `C` |
| `Prezzo` | numero | Prezzo massimo in crediti |
| `Budget` | testo | Es. `8.6%` (accettato con simbolo %) |
| `PMA` | numero decimale | Prezzo medio altre leghe |
| `Obiett.` | testo | Obiettivo d'asta (max 50 char) |
| `Commento` | testo | Note libere |
| `Nota 1..5` | testo | Note aggiuntive |

### Rosa Fantasquadra (upload manuale)
File Excel con almeno:

| Colonna | Nota |
|---|---|
| `Calciatore` oppure `Nome` | Cognome del giocatore |
| `Costo` oppure `Prezzo` | Costo d'acquisto in crediti |

---

## 🔧 Deploy & Note Tecniche

### Produzione (checklist minima)
1. Imposta `DEBUG=False` nel `.env`
2. Imposta `ALLOWED_HOSTS` in `settings.py`
3. Usa PostgreSQL (de-commenta le righe nel `.env`)
4. Esegui `python manage.py collectstatic`
5. Usa Gunicorn + Nginx (o equivalente)
6. Genera una `SECRET_KEY` sicura con:
   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

### Task asincroni
Il sistema usa `threading.Thread` per le operazioni di import. Per carichi elevati in produzione, considera la migrazione a **Celery + Redis** — la logica è già isolata in classi `*Importer` riutilizzabili.

### Database
SQLite è sufficiente per uso personale/team piccolo. Per più utenti concorrenti con import pesanti, PostgreSQL è consigliato (evita i lock di SQLite sui thread).

---

## 📝 Licenza

Progetto privato — uso interno. Non distribuire.
