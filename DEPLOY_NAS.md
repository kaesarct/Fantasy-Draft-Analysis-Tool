# Deploy su NAS Synology (dietro FritzBox)

Guida per portare `ft-platform` dal tuo PC a un NAS Synology in casa, raggiungibile
da fuori tramite un dominio DDNS e reverse proxy HTTPS, con il router **FritzBox**
che fa da modem/firewall verso internet.

> ⚠️ Esporre servizi verso internet aumenta la superficie d'attacco della tua rete
> domestica. Questa guida include gli accorgimenti minimi (HTTPS, niente porte di
> database esposte, 2FA, blocco IP) ma la sicurezza del NAS resta responsabilità
> di chi lo amministra: mantienilo aggiornato e monitora i log di accesso.

## Architettura

```
Internet
   │  porte 443 (e 80 solo per il rinnovo del certificato)
   ▼
FritzBox (port forwarding verso l'IP del NAS)
   ▼
NAS Synology — Reverse Proxy (DSM) + certificato Let's Encrypt
   ▼  proxy verso 127.0.0.1:4200
Container "frontend" (Nginx + build Angular di produzione)
   │  proxy interno /api, /static → rete Docker privata
   ▼
Container "backend" (FastAPI) ── Container "db" (PostgreSQL)
```

Solo il container `frontend` pubblica una porta sull'host (`127.0.0.1:4200`, solo
loopback). Backend e database sono raggiungibili esclusivamente dalla rete Docker
interna: da fuori dal NAS non sono mai accessibili direttamente, nemmeno da chi è
sulla rete LAN di casa.

## Prerequisiti

- NAS Synology con **DSM 7.x** e pacchetto **Container Manager** installato.
- Accesso SSH abilitato (Pannello di controllo → Terminale e SNMP).
- Un hostname raggiungibile da internet. Consigliato il servizio **Synology DDNS**
  (gratuito, integrato nativamente con il Centro Certificati e il reverse proxy di
  DSM: Pannello di controllo → Accesso esterno → DDNS). In alternativa puoi usare
  il **MyFRITZ!** del FritzBox, ma l'emissione automatica dei certificati Let's
  Encrypt è più semplice restando nell'ecosistema Synology.
- Un repository Git privato dove pubblicare il codice (es. un repository privato
  su GitHub). Il progetto è già stato inizializzato come repo Git locale.

## 1. Rete: DDNS + port forwarding sul FritzBox

1. Su DSM: **Pannello di controllo → Accesso esterno → DDNS** → aggiungi un
   hostname Synology (es. `tuonome.synology.me`).
2. Sul FritzBox (`fritz.box` → Internet → Permessi → Port forwarding, oppure
   "Freigaben"): inoltra le porte **443** (HTTPS) e **80** (solo per la validazione
   ACME di Let's Encrypt) verso l'indirizzo IP locale del NAS.
3. Assegna al NAS un **IP statico** nella LAN (dal FritzBox: Rete Home →
   Dispositivi di rete → modifica dispositivo → "sempre lo stesso IP"), altrimenti
   il port forwarding può rompersi se il DHCP riassegna un IP diverso.

## 2. Reverse proxy + certificato HTTPS su DSM

1. **Centro Certificati** (Pannello di controllo) → aggiungi un nuovo certificato
   → "Ottieni un certificato gratuito da Let's Encrypt" → usa l'hostname DDNS
   configurato al punto 1. Synology lo rinnova automaticamente.
2. **Pannello di controllo → Portale delle applicazioni → Regole del proxy
   inverso** → crea una nuova regola:
   - Sorgente: protocollo `HTTPS`, hostname `tuonome.synology.me`, porta `443`,
     certificato quello appena creato.
   - Destinazione: protocollo `HTTP`, hostname `127.0.0.1`, porta `4200` (il
     container `frontend`).

A questo punto `https://tuonome.synology.me` mostra l'app; le chiamate a
`/api/...` e `/static/...` vengono già instradate al backend dal proprio Nginx
del container frontend (vedi `frontend/nginx.conf`), quindi non serve nessuna
regola di proxy aggiuntiva né configurare CORS.

## 3. Checklist di hardening (prima di andare online)

- [ ] **2FA** obbligatoria sull'account DSM usato per amministrare.
- [ ] Account `admin` di default **disabilitato o rinominato** (OWASP A07 /
      CWE-521 — credenziali di default o deboli sono il primo vettore di attacco
      sui NAS esposti).
- [ ] **Auto Block** attivo (Pannello di controllo → Sicurezza → Protezione):
      blocca un IP dopo N tentativi di accesso falliti.
- [ ] DSM e i pacchetti installati **sempre aggiornati** (Security Advisor).
- [ ] Nessuna porta di gestione (5000/5001 DSM, 5432 Postgres) inoltrata sul
      FritzBox: solo 443 (e 80 per l'ACME challenge) devono raggiungere il NAS.
- [ ] Credenziali Postgres **ruotate** rispetto ai valori di default presenti
      in `docker-compose.yml` (`ft_user` / `ft_password`) — vedi passo 4.
- [ ] Backup periodico del volume `pgdata` (Hyper Backup, o `pg_dump` schedulato
      con un task pianificato DSM).
- [ ] Password dell'account admin dell'app (non DSM) **lunga e casuale** — il
      login non ha rate-limiting, quindi una password debole è comunque
      soggetta a forza bruta se l'app resta esposta a internet (vedi passo 4).

## 4. Portare il codice sul NAS

Il progetto è ora un repository Git locale sul tuo PC. Per aggiornare il NAS in
futuro con un semplice `git pull` serve un repository remoto:

```bash
# Sul PC, una tantum: crea un repository privato su GitHub, poi:
git remote add origin git@github.com:<tuo-utente>/ft-platform.git
git push -u origin master
```

Poi, via SSH sul NAS:

```bash
ssh <utente>@tuonome.synology.me
git clone git@github.com:<tuo-utente>/ft-platform.git
cd ft-platform
```

**I file `.env` non vengono mai versionati** (sono in `.gitignore`): vanno creati
a mano sul NAS.

- `backend/.env` — copia da `backend/.env.example` e compila con le credenziali
  reali di fantacalcio.it e del database (usa gli stessi valori di `DB_USER` /
  `DB_PASSWORD` / `DB_NAME` che metterai nel passo successivo). Usato solo se
  esegui il backend senza Docker: `docker-compose.prod.yml` non lo legge.
- `.env` nella root — copia da `.env.example` (vedi anche il commento sulla
  formula di `FANTA_YEAR_QUOTAZIONI` nel file stesso) e compila con i valori
  reali. `docker-compose.prod.yml` legge **solo** questo file per Postgres,
  fantacalcio.it e CORS.

  Genera una password Postgres forte, ad es. `openssl rand -base64 24`, invece
  di riusare `ft_password`.

  Genera anche `JWT_SECRET` (`openssl rand -hex 32`) e, **dopo** il primo avvio
  del backend (serve l'immagine già buildata), `ADMIN_PASSWORD_HASH`:
  ```bash
  docker compose -f docker-compose.prod.yml exec backend python -m app.services.auth_service "la-tua-password"
  ```
  Imposta anche `ADMIN_USERNAME`. Senza questi tre valori il login admin (che
  protegge sync/import/scrittura e il pannello Admin) rifiuta sempre le
  credenziali. `COOKIE_SECURE` deve restare `true` in produzione (richiede
  HTTPS, già garantito dal reverse proxy DSM del passo 2).

Copia questi due `.env` sul NAS via SCP/SFTP (mai via Git):

```bash
scp backend/.env <utente>@tuonome.synology.me:~/ft-platform/backend/.env
scp .env <utente>@tuonome.synology.me:~/ft-platform/.env
```

## 5. Portare i dati esistenti (se non parti da zero)

Se sul NAS deve arrivare lo storico/i dati già presenti sul PC (stagioni
importate, rose, infortuni, ecc.) e non un database vuoto, il dump va
caricato **prima** che il backend crei le tabelle — `Base.metadata.
create_all()` le crea vuote al primo avvio, e un ripristino successivo
fallirebbe sulle istruzioni `CREATE TABLE` (tabelle già esistenti).

Sul PC, dump completo del database attuale:

```bash
docker compose exec db pg_dump -U ft_user -d ft_platform --no-owner --no-privileges > backup.sql
```

Copia `backup.sql` sul NAS (mai via Git):

```bash
scp backup.sql <utente>@tuonome.synology.me:~/ft-platform/backup.sql
```

Sul NAS, avvia **solo** il database (non ancora backend/frontend) e
ripristina il dump nel database ancora vuoto:

```bash
cd ft-platform
docker compose -f docker-compose.prod.yml up -d db
docker compose -f docker-compose.prod.yml ps   # attendi "healthy"
cat backup.sql | docker compose -f docker-compose.prod.yml exec -T db \
  psql -U <DB_USER> -d <DB_NAME>
```

Usa lo stesso `DB_USER`/`DB_NAME` che hai messo nel `.env` del NAS (passo
4). Solo dopo il ripristino avvia il resto dello stack (passo 6):
`create_all()` troverà le tabelle già popolate e non le toccherà (crea
solo quelle mancanti, mai distruttivo su quelle esistenti).

## 6. Primo avvio

Via SSH sul NAS, dalla cartella del progetto:

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend
```

In alternativa puoi importare il progetto in **Container Manager → Progetto →
Crea**, indicando `docker-compose.prod.yml` come file compose.

Verifica che l'app sia raggiungibile su `https://tuonome.synology.me` e che
`https://tuonome.synology.me/api/health` risponda `{"status": "ok", ...}`.

## 7. Aggiornamenti futuri

Workflow ordinario una volta che tutto è deployato:

```bash
# 1. Sul PC: sviluppi, verifichi in locale, poi:
git add <file modificati>
git commit -m "..."
git push

# 2. Sul NAS, via SSH:
cd ft-platform
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

`up -d --build` ricostruisce solo le immagini i cui file sorgente sono cambiati
e riavvia esclusivamente i container interessati; il volume `pgdata` (dati del
database) non viene toccato.

### Nota importante sullo schema del database

Il backend inizializza il database con `Base.metadata.create_all()`
(`backend/app/database.py`): questo crea automaticamente le **tabelle mancanti**
a ogni avvio, ma **non modifica le tabelle già esistenti** — se un aggiornamento
futuro aggiunge una colonna a un modello già in produzione, quella colonna non
comparirà da sola sul NAS. Il progetto già segue un pattern per questi casi
(`_migrate_add_leghe_id()` in `database.py`): un'istruzione
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` idempotente eseguita a ogni avvio.
Se aggiungi colonne a un modello esistente, aggiungi una funzione di migrazione
analoga prima di fare il deploy sul NAS.

Prima di aggiornamenti che toccano lo schema dati, fai un backup:

```bash
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U ft_user ft_platform > backup_$(date +%Y%m%d).sql
```

## 8. Deploy automatico su tag (opzionale)

Invece di collegarti via SSH a ogni aggiornamento, puoi far controllare al NAS
da solo se c'è un nuovo tag Git e, se sì, fare da solo `git pull` + rebuild.
Nessuna porta aggiuntiva esposta verso internet: è il NAS a interrogare
GitHub (connessione in uscita, già permessa), non il contrario — niente
webhook da ricevere.

**Come funziona**: `deploy/auto_deploy.sh` confronta il commit puntato
dall'ultimo tag creato con l'ultimo commit già deployato (tracciato per SHA
in `.last_deployed_commit`, un file locale al NAS, mai versionato). Se sono
diversi: `git checkout` sul tag, `docker compose up -d --build`, e solo se
va a buon fine aggiorna il marker. In caso di errore il marker non si
aggiorna, quindi il tag "fallito" viene ritentato al giro successivo. Tutto
viene loggato in `deploy/deploy.log` (anch'esso non versionato).

> ⚠️ Da questo momento il repository sul NAS va trattato come **sola
> destinazione di deploy**: lo script fa `git checkout --force` su un tag,
> quindi eventuali modifiche fatte a mano dentro quella cartella verrebbero
> perse al giro successivo. Sviluppa sempre sul PC, mai direttamente sul NAS.

### Sul PC: taggare una release

Quando una serie di commit è pronta per andare in produzione:

```bash
git tag -f deploy
git push origin deploy --force
```

(`-f`/`--force` perché `deploy` è un tag "mobile": lo sposti sull'ultimo
commit pronto invece di crearne uno nuovo ogni volta — lo script rileva il
cambiamento dal commit puntato, non dal nome del tag, quindi funziona anche
così). Se preferisci invece un tag diverso per ogni release (es. `v1.3.0`),
va bene lo stesso: lo script prende sempre il tag più recente per data di
creazione.

### Sul NAS: pianificare lo script

**Pannello di controllo → Utente e servizio → Pianificazione attività →
Crea → Attività attivata → Script definito dall'utente**:

- Utente: **root** (evita di dover gestire `sudo` in un contesto non
  interattivo, dove non può chiedere la password)
- Pianificazione: ricorrente, ogni 15-30 minuti va bene per un uso casalingo
- Impostazioni attività → Comando:
  ```bash
  bash /volume1/KaesarNas/ft-platform/deploy/auto_deploy.sh
  ```

Al primo giro utile dopo aver pushato il tag `deploy`, l'attività fa il
deploy da sola. Controlla l'esito con:

```bash
cat /volume1/KaesarNas/ft-platform/deploy/deploy.log
```

## Differenze tra `docker-compose.yml` e `docker-compose.prod.yml`

| | `docker-compose.yml` (dev, PC) | `docker-compose.prod.yml` (NAS) |
|---|---|---|
| Frontend | `ng serve` (dev server, hot reload) | build Angular ottimizzata + Nginx |
| Porta frontend | `4200` su tutte le interfacce | `127.0.0.1:4200` (solo loopback) |
| Porta backend | `8000` pubblicata | non pubblicata (solo rete Docker) |
| Porta Postgres | `5432` pubblicata | non pubblicata (solo rete Docker) |
| Credenziali DB | hardcoded nel file | da variabili d'ambiente (`.env`) |

Il `docker-compose.yml` esistente resta invariato e continua a essere quello
giusto per lo sviluppo locale sul tuo PC.
