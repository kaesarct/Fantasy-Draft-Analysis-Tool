"""Leghe.fantacalcio.it client — login + lettura competizioni/formazioni via REST.

La vecchia UI (server-side, scraping via Playwright) e' stata sostituita da una
SPA con routing e API completamente diversi: competizioni e formazioni si
leggono ora con chiamate REST autenticate su apileague.fantacalcio.it, con lo
stesso app_key + Bearer JWT di lega gia' usato per il login (verificato contro
il sito reale: nessun browser necessario)."""
import re

import requests

from app.config import settings

import logging
logger = logging.getLogger(__name__)


class LegheClient:
    LOGIN_URL = "https://apileague.fantacalcio.it/onboarding/v1/login"
    APILEAGUE_BASE = "https://apileague.fantacalcio.it"

    def __init__(self, alias_lega: str | None = None, app_key: str | None = None):
        self.alias_lega = alias_lega or settings.fanta_lega_name
        self.lega_page_url = f"{settings.fanta_leghe_base_url}{self.alias_lega}"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "app_key": app_key or self._discover_app_key(),
                "accept": "application/json",
                "content-type": "application/json",
            }
        )
        self.utente = None
        self.leghe: list[dict] = []
        self._lega_jwt: str | None = None

    def _discover_app_key(self) -> str:
        # authAppKey e' iniettato dal server nell'HTML (script#serverBridge), non nei bundle JS:
        # piu' stabile da leggere da li' che affidarsi a una chiave fissa nel codice.
        # Va letta dalla homepage leghe: la pagina della lega redirige a /view/dashboard
        # e risponde 404 alle richieste non autenticate, quindi non espone la chiave.
        try:
            res = self.session.get(settings.fanta_leghe_base_url, timeout=10)
            match = re.search(r'authAppKey"?\s*:\s*"([^"]+)"', res.text)
            if match:
                return match.group(1)
            logger.warning("authAppKey non trovato nella homepage leghe, uso il fallback")
        except requests.RequestException as e:
            logger.warning("Discovery app_key fallita, uso il fallback: %s", e)
        return settings.fanta_app_key_fallback

    def login(self, username: str | None = None, password: str | None = None) -> dict:
        username = username or settings.fanta_username
        password = password or settings.fanta_password
        if not username or not password:
            raise ValueError(
                "Credenziali mancanti: passa username/password o imposta FANTA_USERNAME/FANTA_PASSWORD"
            )

        res = self.session.post(
            self.LOGIN_URL, json={"username": username, "password": password}, timeout=15
        )
        res.raise_for_status()
        data = res.json()
        if not data.get("success"):
            raise RuntimeError(f"Login fallito: {data}")

        self.utente = data["data"]["utente"]
        self.leghe = data["data"].get("leghe") or []
        logger.debug("Login leghe avvenuto con successo")

        lega = next((l for l in self.leghe if l.get("alias") == self.alias_lega), None)
        if not lega or not lega.get("jwt"):
            raise RuntimeError(
                f"Lega con alias '{self.alias_lega}' non trovata (o senza jwt) tra le leghe dell'utente"
            )
        self._lega_jwt = lega["jwt"]

        return self.utente

    def _lega_headers(self) -> dict:
        if not self._lega_jwt:
            raise RuntimeError("login() non eseguito: manca il jwt di lega")
        return {
            "app_key": self.session.headers["app_key"],
            "authorization": f"Bearer {self._lega_jwt}",
            "accept": "application/json",
        }

    def list_competitions(self) -> list[dict]:
        """Competizioni della lega per la stagione corrente: id, name, sDay/eDay
        (giornate di validita'), type, tmids (id squadre partecipanti)."""
        resp = requests.get(
            f"{self.APILEAGUE_BASE}/onboarding/v1/league/competitions",
            headers=self._lega_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def list_competition_teams(self, id_comp: int) -> dict[int, str]:
        """id squadra (lato leghe.fantacalcio.it) -> nome squadra, per una competizione."""
        teams: dict[int, str] = {}
        page = 1
        while page <= 10:
            resp = requests.get(
                f"{self.APILEAGUE_BASE}/onboarding/v1/league/competition/teams",
                params={"page": page, "pageSize": 50, "competitionId": id_comp},
                headers=self._lega_headers(),
                timeout=15,
            )
            resp.raise_for_status()
            body = resp.json()
            for row in body.get("data") or []:
                teams[row["id"]] = row["n"]
            if not body.get("nextPage"):
                break
            page += 1
        return teams

    def get_team_lineup(self, id_comp: int, giornata: int, team_id: int) -> dict | None:
        """Formazione (titolari/panchina) di una squadra per una giornata di una
        competizione. None se non ancora disponibile: sia quando il sito risponde
        200 con home=null (giornata futura ma nel calendario), sia quando risponde
        400 "LU001 Match day configuration not found or not active" (giornata non
        ancora attivata per questa competizione, es. non ancora iniziata)."""
        resp = requests.get(
            f"{self.APILEAGUE_BASE}/gaming/v1/teamLineup/{id_comp}/{giornata}/{giornata}/{team_id}/0",
            headers=self._lega_headers(),
            timeout=15,
        )
        if resp.status_code == 400:
            return None
        resp.raise_for_status()
        return resp.json().get("home")

    def get_participants(self) -> list[dict]:
        """Tutti i partecipanti della lega (squadre + allenatori con email/codice
        invito): usato per il collegamento manuale annuale in Admin
        (POST /leghe-sync/apply), non per sync automatiche."""
        resp = requests.get(
            f"{self.APILEAGUE_BASE}/onboarding/v1/invitation/participants",
            params={"pageNumber": 1, "pageSize": 1000},
            headers=self._lega_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def get_tutte_le_formazioni(self, giornata: int) -> dict:
        """Formazioni di tutte le competizioni della lega per la giornata data.
        Ritorna {slug_competizione: {"id_comp", "giornata", "dati": {nome_squadra: lineup}} | None}
        — None se nessuna squadra della competizione ha ancora una formazione
        per quella giornata (es. competizione non ancora iniziata)."""
        risultati = {}
        for comp in self.list_competitions():
            slug = comp["name"].strip().lower().replace(" ", "_")
            id_comp = comp["id"]

            squadre = self.list_competition_teams(id_comp)
            dati = {}
            for team_id, nome_squadra in squadre.items():
                lineup = self.get_team_lineup(id_comp, giornata, team_id)
                if lineup is not None:
                    dati[nome_squadra] = lineup

            risultati[slug] = {"id_comp": id_comp, "giornata": giornata, "dati": dati} if dati else None

        return risultati
