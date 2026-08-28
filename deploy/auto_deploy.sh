#!/bin/bash
# Deploy automatico sul NAS quando compare un nuovo tag Git.
#
# Pensato per girare come Task pianificato di DSM (utente root, ogni N
# minuti) — vedi DEPLOY_NAS.md, sezione "Deploy automatico su tag".
#
# Logica: confronta il commit puntato dal tag più recente con l'ultimo
# commit già deployato (tracciato per SHA, non per nome tag — funziona
# sia con tag che si spostano sia con tag incrementali). Se diverso,
# esegue checkout del tag, rebuild dello stack e aggiorna il marker
# solo se il deploy va a buon fine.
#
# Non modifica MAI file locali di proposito: questo repository sul NAS
# va trattato come sola destinazione di deploy, non come copia di
# lavoro — non editarci dentro a mano.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="docker-compose.prod.yml"
MARKER_FILE="$REPO_DIR/.last_deployed_commit"
LOG_FILE="$REPO_DIR/deploy/deploy.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

cd "$REPO_DIR"

git fetch --tags origin >> "$LOG_FILE" 2>&1

LATEST_TAG="$(git for-each-ref --sort=-creatordate --format='%(refname:short)' refs/tags | head -1)"
if [ -z "$LATEST_TAG" ]; then
  # Nessun tag esiste ancora: niente da fare, non è un errore.
  exit 0
fi

LATEST_SHA="$(git rev-list -n 1 "$LATEST_TAG")"
LAST_DEPLOYED_SHA=""
if [ -f "$MARKER_FILE" ]; then
  LAST_DEPLOYED_SHA="$(cat "$MARKER_FILE")"
fi

if [ "$LATEST_SHA" = "$LAST_DEPLOYED_SHA" ]; then
  # Già deployato, nessun tag nuovo.
  exit 0
fi

log "Nuovo tag rilevato: $LATEST_TAG ($LATEST_SHA) — avvio deploy"

git checkout --force "$LATEST_TAG" >> "$LOG_FILE" 2>&1

export APP_VERSION="$LATEST_TAG"
if docker compose -f "$COMPOSE_FILE" up -d --build >> "$LOG_FILE" 2>&1; then
  echo "$LATEST_SHA" > "$MARKER_FILE"
  log "Deploy completato: $LATEST_TAG"
else
  log "ERRORE durante il deploy di $LATEST_TAG — marker NON aggiornato, verrà ritentato al prossimo giro"
  exit 1
fi
