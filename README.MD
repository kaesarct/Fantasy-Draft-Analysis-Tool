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

- **Infortuni scambiati**: il cambio ammette solo sostituti con quotazione ≤ a quella dell'infortunato; nel dialogo "Registra cambio" una spunta "Eccezione" consente un sostituto più caro (es. la quotazione dell'infortunato è scesa prima della registrazione) e lo segnala con "⚠ sopra il massimo". Se fantacalcio.it non risponde per aggiornare le quotazioni, il cambio si registra comunque con quelle salvate e compare un avviso.
- **Dashboard completa**: Statistiche veloci, prossimi incontri di Serie A e stato infortuni.
- **Statistiche Giocatori**: Dati anagrafici, ruolo, quotazioni, FVM (Fantavalore di Mercato) e tracking variazioni di prezzo.
- **Gestione Squadre**: Dati fanta-team, loghi stagionali, crediti residui e allenatori multipli per squadra.
- **Classifiche e Competizioni**: Supporto completo per campionati complessi (Gold, Bronze, Carbon, Silver League, Ciempions, UEFA). Se per una competizione non è salvata nessuna classifica (stagione in corso), viene calcolata al volo dai risultati sincronizzati: 3/1/0 punti dai gol da fasce per Gold/Bronze/Carbon, somma dei punteggi di giornata per Silver (dai punteggi sincronizzati e, per le giornate mancanti, dai risultati di Gold/Bronze/Carbon).
- **Infortuni e Sostituzioni**: Tracking dei rientri previsti e gestione delle sostituzioni temporanee per infortuni prolungati (≥8 settimane). Gli infortunati Serie A (ufficiali fantacalcio.it) sono raggruppati per squadra con sezioni collassabili, una barra di stemmi in alto per saltare direttamente alla squadra desiderata e un bottone "torna su" per tornare alla barra.
- **Regolamento**: pagina pubblica (voce di menu "Regolamento", nessun login) con il PDF del regolamento Tamarros 2026 incorporato e scaricabile; il file è in `frontend/public/regolamento-tamarros-2026.pdf` (per aggiornarlo basta sostituirlo).
- **Import da file (calendari e formazioni)**: in Admin → Sync leghe.fc.it il pulsante "Carica Excel (calendari e formazioni)" importa Excel scaricati a mano da leghe.fantacalcio.it, senza login automatico (utile quando la sync automatica riceve 403 dal sito). Tipo di file e competizione si riconoscono dal titolo in A1. Il **Calendario** ("Calendario CIEMPIONS") importa partite, punteggi, gironi delle coppe e la corrispondenza giornata di lega → giornata di Serie A di **tutti** i turni, anche quelli futuri (tabella `competition_matchdays`: le coppe non giocano ogni giornata, quindi non c'è un offset fisso). Il Calendario va quindi caricato una volta a inizio stagione per Gold, Bronze, Carbon e Ciempions; per la UEFA quando lo generi, a fine gironi di Ciempions (la sua numerazione non si deduce da quella di Ciempions). La **Formazione** ("GOLD · Giornata 4") importa il totale di ogni squadra in `CompetitionMatchdayScore` sulla giornata di Serie A corrispondente (la stessa numerazione della sync teamLineup); Silver usa la mappatura dei campionati. Una formazione di una competizione di cui non è stato caricato il Calendario (es. UEFA prima che esista) viene rifiutata con l'indicazione di caricarlo prima: il numero di giornata non viene mai stimato. Si possono selezionare più file insieme (anche solo alcuni: le coppe possono mancare); se la competizione non esiste ancora (es. UEFA) viene creata. Max 5 MB per file, solo .xlsx.
- **Controllo di coerenza dopo il caricamento**: a fine caricamento la pagina chiama `GET /awards/consistency-check` e mostra (1) Silver contro il campionato di appartenenza, squadra per squadra e giornata per giornata (in campionato il punteggio deve essere identico), (2) Goku e Oscar attuali. Le coppe non vengono confrontate con la lega: la formazione di coppa può essere diversa, e una prestazione di coppa conta per Goku/Oscar a parte (si scarta solo se è identica a quella di lega della stessa squadra). Un nome squadra del file non riconosciuto (es. squadra rinominata su leghe) viene elencato e la sua riga resta fuori dai confronti; sotto il nome la pagina propone di **aggiornare il nome di una squadra della stagione corrente** (menu con le squadre non riconosciute nel file, per i campionati solo quelle della stessa lega; preselezionata se l'abbinamento è unico): alla conferma chiama `POST /leghe-sync/rename-team` (solo admin, solo stagione corrente, rifiuta nomi già usati) e reimporta i file. Cambia solo il nome: lo storico delle stagioni passate non viene toccato.
- **Goku/Oscar e Silver: unione delle fonti**: i punteggi da Formazione (giornata di Serie A) e quelli dei risultati dei Calendari (giornata di lega) si sommano turno per turno, senza contarne due volte lo stesso: il turno è lo stesso se coincide la giornata di Serie A (tabella `competition_matchdays`); finché il Calendario non è stato caricato, si scarta il punteggio identico della stessa squadra. Le etichette dei turni usano la giornata di lega.
- **Live Silver: sostituzioni secondo il regolamento**: la simulazione dei punteggi live (`live_score_service.py`) non usa le impostazioni di sostituzione di leghe ma le regole del regolamento Tamarros: al massimo 3 sostituzioni, solo sullo stesso ruolo (nessun cambio modulo), con i sostituti in ordine di panchina. Chi non gioca e non ha un sostituto che prende voto prende 4 d'ufficio se restano sostituzioni libere (i sostituti veri hanno la priorità), altrimenti 0. Il 4 d'ufficio conta come sostituzione, è provvisorio finché un titolare deve ancora giocare, e non entra nel modificatore difesa (vale come un difensore in meno). Se le sostituzioni scarseggiano, 4 e 0 vengono assegnati in ordine di formazione (P, D, C, A). Le costanti sono `MAX_SUBSTITUTIONS` e `OFFICE_VOTE`; il percorso delle giornate già chiuse usa i numeri ufficiali di leghe.
- **Locandina della stagione in dashboard**: la dashboard mostra l'immagine `frontend/public/stagione.jpg`; per cambiarla ogni anno basta sostituire il file (o aggiornare il nome in `dashboard.component.ts`). Se il file manca la scheda non compare.
- **Giocatori delle stagioni passate**: l'elenco Giocatori di una stagione passata parte dalla tabella `players` e mostra chi ha una quotazione storica per quella stagione. Chi è uscito dalla Serie A prima della lista attuale e non è mai stato in una rosa importata non aveva una riga giocatore e non compariva (es. Bove nel 2024-25). All'avvio una migrazione idempotente (`_migrate_create_missing_players`, prima della deduplica) e l'import dei prezzi storici creano le righe mancanti da `player_season_prices` (`services/player_backfill.py`), con nome e ruolo della stagione più recente. Non coprono statistiche e voti storici. L'unione di due giocatori in Admin («Giocatori simili da verificare») passa il `fanta_id` di quello eliminato a quello che resta (e porta con sé lo storico di quotazioni/statistiche/voti senza conflitti), altrimenti il backfill all'avvio lo ricreerebbe; ripulisce anche conferme di ruolo e rifiuti di unione del giocatore eliminato, che prima bloccavano l'unione con «Errore durante il merge».
- **Altri record nella pagina Premi** (`GET /awards/records`, pubblico): sotto «Record assoluto» un pannello «Altri record» con miglior e peggior punteggio in campionato (punti), miglior e peggior Silver, più reti fatte e subite, migliore e peggiore differenza reti, acquisto più oneroso e giocatore acquistato più volte. I detentori di partenza sono in `BASELINE` (`services/records.py`); ad ogni richiesta vengono confrontati con i dati (classifiche finali di tutte le stagioni passate, classifiche calcolate dai risultati per la stagione in corso e per le prossime concluse): se un dato supera il record cambia il detentore, se pareggia compaiono entrambi (es. le 88 reti fatte: Baby Team 2023-24 e Pronto Cellulare 2019-20). Se i dati contraddicono un valore di partenza lo si vede nel log del backend. A stagione in corso contano solo i record che possono soltanto crescere (miglior punteggio, reti fatte, reti subite, miglior Silver), con l'etichetta «in corso»; i «peggiori» e la differenza reti si valutano a stagione conclusa. Le stagioni storiche incomplete (meno di 30 partite registrate o Silver sotto 1.000) sono escluse. Acquisto più oneroso e giocatore più acquistato (per squadra, anche tra stagioni) non hanno valori scritti a mano: si calcolano dalle rose.
- **Interruttore dell'integrazione con leghe** (`LEGHE_API_ENABLED`, spento di default): con `false` il backend non fa nessuna chiamata a `leghe.fantacalcio.it` né a `apileague.fantacalcio.it` (un solo punto di blocco in `LegheClient`, che solleva `LegheDisabledError`; le rotte rispondono 503 con un messaggio chiaro). Smettono di funzionare: «Carica da leghe» (partecipanti), «Sync risultati/calendario», «Sync punteggi + classifiche», «Sync formazioni» (pagina Partite) e il **Live Silver** (le formazioni di lega esistono solo su leghe: non c'è equivalente su fantacalcio.it). Al loro posto: **Admin → Sync leghe → «Carica Excel (calendari e formazioni)»**, con controllo di coerenza Silver, Goku e Oscar. I pulsanti si spengono da soli (`GET /api/features`). Restano attive le chiamate a `www.fantacalcio.it` (quotazioni, voti, giornata corrente, bollettino infortuni, partite) con le credenziali `FANTA_USERNAME`/`FANTA_PASSWORD`; l'aggancio automatico delle competizioni dopo le sync di quotazioni e voti viene saltato (le competizioni nascono dal primo calendario caricato). Per riattivare tutto: `LEGHE_API_ENABLED=true` nel `.env` e riavvio.
- **Classifica campionati (stagione in corso)**: GF/GS sono i gol da fasce; la somma dei punteggi fatti è nella colonna "Tot. punti" (in Silver "Acc."). A parità di punti conta la somma punti. La scheda Silver (classifica ad accumulo, senza partite) mostra solo G (giornate conteggiate), Acc., Media a giornata, Migliore e Peggiore (solo punteggi di campionato: le coppe non entrano in Silver).
- **Gironi delle coppe**: la sync risultati legge la composizione dei gironi (lettera A, B, …) dall'Excel Calendario di leghe.fantacalcio.it, anche per le giornate non ancora giocate, e la salva in `CompetitionGroup`; una squadra già iscritta a un altro girone della stessa coppa viene spostata. I punti classifica sono 3/1/0 dai gol. Se i gironi non sono ancora stati sincronizzati, ripiego sui gruppi di squadre che si sono incontrate.
- **Premio Goku & Premio Oscar**: pagina pubblica (nessun login richiesto) con il punteggio più alto/basso di giornata della stagione corrente, lo storico dal 2018/19 e il record assoluto in evidenza. In Goku/Oscar, se una prestazione di coppa ha lo stesso punteggio della stessa squadra in Gold/Bronze/Carbon, conta solo quella della lega (niente duplicati). Sotto Admin, una sezione "Coerenza Silver" segnala eventuali discrepanze tra la classifica Silver e quella del campionato di appartenenza (Gold/Bronze/Carbon) di ogni squadra.
- **Sync squadre/allenatori da leghe.fantacalcio.it**: sotto Admin, da usare una volta l'anno a inizio stagione — scarica i partecipanti reali dalla lega su leghe.fantacalcio.it e propone il collegamento a squadre/allenatori già presenti nel nostro DB. Per una squadra nuova (tipico a inizio stagione, prima che le squadre dell'anno vengano ricreate) permette anche di ereditare l'identità (lineage) da una squadra di stagioni passate, invece di partire scollegata dallo storico. Salva l'id squadra esterno per future sincronizzazioni automatiche. Crea e aggancia in automatico ogni competizione trovata su leghe.fantacalcio.it (Gold/Bronze/Carbon/Ciempions/Coppa Italia/Euro Cup/Silver, incluse quelle che compaiono più avanti nella stagione come UEFA) — sia al caricamento squadre/allenatori sia ad ogni sync di routine (voti, quotazioni, punteggi, risultati), senza bisogno di crearle a mano da Gestione Squadre. Il pulsante "Sync punteggi + classifiche" lancia di seguito entrambe le sync, così Goku/Oscar e Classifiche si popolano con un solo click. Permette due tipi di sync: i punteggi reali di giornata (fonte principale del Premio Goku/Oscar, copre anche Silver; quando sono 0, il report ne indica il motivo: giornata non attiva, già sincronizzata o squadre non collegate) e, quando serve l'accoppiamento partita/gol da fasce, il calendario completo via Excel.
- **Dump e restore del DB**: sotto Admin, permette di scaricare un dump completo del DB (tipicamente da prod) e ricaricarlo in un altro ambiente (tipicamente staging), utile quando qualcosa funziona in un ambiente ma non si riesce a riprodurlo nell'altro. Protetto dal login admin più una password dedicata (hash bcrypt in `.env`, mai in chiaro). Il restore, essendo distruttivo (sovrascrive interamente il DB dell'ambiente su cui gira), è inoltre disabilitato di default per ambiente e va abilitato esplicitamente (`ALLOW_DB_RESTORE=true`) solo dove serve davvero riceverlo. Il restore azzera lo schema `public` prima di caricare il dump (così non restano tabelle presenti solo nell'ambiente di destinazione, ad esempio nuove nel codice e assenti nel dump di prod, che bloccherebbero il caricamento), lo fa in una sola transazione (se fallisce il DB resta com'era) e al termine ricrea tabelle e colonne che il dump non conosce (`init_db`). In caso di errore la pagina mostra la causa riportata da Postgres.

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

Per la sezione Admin "Dump e restore DB" genera allo stesso modo una password dedicata
(`DB_OPS_PASSWORD_HASH`, stesso comando `auth_service` sopra) e, solo negli ambienti dove
serve davvero ricevere un restore (es. staging, mai in prod), imposta `ALLOW_DB_RESTORE=true`.

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

> **403 "Request failed" sul login (apileague.fantacalcio.it)**: il sito (CloudFront) blocca lo user-agent di default di `python-requests`. `LegheClient` invia perciò header da browser (`BROWSER_HEADERS` in `leghe_client.py`); se il 403 ricompare, controlla prima che quegli header siano ancora accettati.

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
