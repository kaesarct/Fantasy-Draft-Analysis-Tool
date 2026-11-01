"""Leghe.fantacalcio.it client — login + lettura competizioni/formazioni via REST.

La vecchia UI (server-side, scraping via Playwright) e' stata sostituita da una
SPA con routing e API completamente diversi: competizioni e formazioni si
leggono ora con chiamate REST autenticate su apileague.fantacalcio.it, con lo
stesso app_key + Bearer JWT di lega gia' usato per il login (verificato contro
il sito reale: nessun browser necessario)."""
import logging
import re

import requests

from app.config import settings

logger = logging.getLogger(__name__)


# apileague.fantacalcio.it (CloudFront) risponde 403 "Request failed" allo
# user-agent di default di python-requests, a prescindere dalle credenziali:
# con header da browser risponde normalmente.
BROWSER_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "origin": "https://leghe.fantacalcio.it",
    "referer": "https://leghe.fantacalcio.it/",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}


class LegheClient:
    LOGIN_URL = "https://apileague.fantacalcio.it/onboarding/v1/login"
    APILEAGUE_BASE = "https://apileague.fantacalcio.it"

    def __init__(self, alias_lega: str | None = None, app_key: str | None = None):
        self.alias_lega = alias_lega or settings.fanta_lega_name
        self.lega_page_url = f"{settings.fanta_leghe_base_url}{self.alias_lega}"
        self.session = requests.Session()
        # Imposta prima i BROWSER_HEADERS sulla sessione cosi' _discover_app_key()
        # non parte con lo user-agent di default di python-requests.
        self.session.headers.update(BROWSER_HEADERS)
        discovered_key = app_key or self._discover_app_key()
        self.session.headers.update({"app_key": discovered_key})

        self.utente = None
        self.leghe: list[dict] = []
        self._lega_jwt: str | None = None
        self.my_team_id: int | None = None
        self._players_cache: dict[int, dict] | None = None
        self._calendar_cache: dict[int, list[dict]] = {}
        self._competitions_cache: list[dict] | None = None

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
        if not lega and self.leghe and not self.alias_lega:
            lega = self.leghe[0]
            self.alias_lega = lega.get("alias", "")
        if not lega or not lega.get("jwt"):
            alias_list = ", ".join(l.get("alias", "?") for l in self.leghe) or "nessuna"
            raise RuntimeError(
                f"Lega con alias '{self.alias_lega}' non trovata (o senza jwt) tra le leghe dell'utente ({alias_list})"
            )
        self._lega_jwt = lega["jwt"]
        self.my_team_id = lega.get("id_squadra")

        return self.utente

    def _lega_headers(self) -> dict:
        if not self._lega_jwt:
            raise RuntimeError("login() non eseguito: manca il jwt di lega")
        return {
            **BROWSER_HEADERS,
            "app_key": self.session.headers["app_key"],
            "authorization": f"Bearer {self._lega_jwt}",
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
        self._competitions_cache = resp.json()
        return self._competitions_cache

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

    def get_league_players(self) -> dict[int, dict]:
        """Anagrafica completa di tutti i calciatori della lega (nomi, ruoli e club Serie A)."""
        if self._players_cache is not None:
            return self._players_cache

        role_map = {1: "P", 2: "D", 3: "C", 4: "A"}
        try:
            resp = requests.get(
                f"{self.APILEAGUE_BASE}/onboarding/v1/league/players",
                headers=self._lega_headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("players") or []
            self._players_cache = {}
            for p in data:
                self._players_cache[p["id"]] = {
                    "name": p.get("name"),
                    "role": role_map.get(p.get("fcrle"), "?"),
                    "club": p.get("stnme", "-"),
                    "tname": p.get("tname", ""),
                }
            return self._players_cache
        except Exception as e:
            logger.warning("Impossibile caricare anagrafica giocatori: %s", e)
            return {}

    def get_league_settings(self) -> dict:
        """Regole di lega: modificatore difesa (smodd), sostituzioni (subst), soglie gol (step), bonus/malus (bnMls)."""
        try:
            resp = requests.get(
                f"{self.APILEAGUE_BASE}/onboarding/v1/league/settings",
                headers=self._lega_headers(),
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json() or {}
        except Exception as e:
            logger.warning("Impossibile caricare impostazioni di lega: %s", e)
            return {}

    def get_competition_calendar(self, id_comp: int, force_refresh: bool = False) -> list[dict]:
        """Calendario completo della competizione con match, giornate di lega, giornate di Serie A e punteggi."""
        if not force_refresh and id_comp in self._calendar_cache:
            return self._calendar_cache[id_comp]
        try:
            resp = requests.get(
                f"{self.APILEAGUE_BASE}/onboarding/v1/league/competition/calendar/{id_comp}",
                headers=self._lega_headers(),
                timeout=15,
            )
            resp.raise_for_status()
            cal = resp.json() or []
            self._calendar_cache[id_comp] = cal
            return cal
        except Exception as e:
            logger.warning("Impossibile caricare calendario comp %s: %s", id_comp, e)
            return []

    def _resolve_comp_round(self, id_comp: int, giornata: int) -> tuple[int, int] | None:
        """Ritorna (comp_round, championship_day) per una competizione data la giornata
        di Serie A (o di lega). Se la competizione ha un calendario e la giornata non
        vi compare, ritorna None (es. coppa che non gioca in quel turno)."""
        cal = self.get_competition_calendar(id_comp)
        if cal:
            day_info = next((d for d in cal if d.get("championshipMatchDay") == giornata), None)
            if not day_info:
                day_info = next((d for d in cal if d.get("matchDay") == giornata), None)
            if not day_info:
                return None
            return int(day_info.get("matchDay", giornata)), int(day_info.get("championshipMatchDay", giornata))

        comps = self._competitions_cache or []
        comp = next((c for c in comps if c.get("id") == id_comp), None)
        if comp:
            s_day = comp.get("sDay", 1) or 1
            e_day = comp.get("eDay", 38) or 38
            if s_day <= giornata <= e_day:
                return (giornata - s_day + 1), giornata
        return giornata, giornata

    def get_match_lineup(
        self,
        id_comp: int,
        comp_round: int,
        giornata: int,
        home_id: int,
        away_id: int = 0,
    ) -> tuple[dict | None, str | None]:
        """Formazione completa del match (home vs away, o singola squadra con away_id=0 per Silver)
        da gaming/v1/teamLineup/{id_comp}/{comp_round}/{giornata}/{home_id}/{away_id}."""
        url = f"{self.APILEAGUE_BASE}/gaming/v1/teamLineup/{id_comp}/{comp_round}/{giornata}/{home_id}/{away_id}"
        try:
            resp = requests.get(url, headers=self._lega_headers(), timeout=15)
        except Exception as e:
            return None, f"richiesta fallita: {e}"

        if not resp.ok:
            return None, f"HTTP {resp.status_code}"

        try:
            data = resp.json()
        except Exception as e:
            return None, f"JSON non valido: {e}"

        if not isinstance(data, dict):
            return None, f"formato non valido ({type(data).__name__})"

        home = data.get("home") or {}
        away = data.get("away") or {}
        home_starts = home.get("starts") or []
        away_starts = away.get("starts") or []

        if not home_starts and not away_starts:
            return None, "Formazioni non ancora visibili o non inserite."
        if not home_starts:
            return None, "La formazione della squadra non è ancora visibile o non è stata inserita."
        if away_id != 0 and not away_starts:
            return None, "La formazione della squadra ospite non è ancora visibile o non è stata inserita."

        return data, None

    def get_team_lineup(
        self, id_comp: int, giornata: int, team_id: int, comp_round: int | None = None
    ) -> dict | None:
        """Formazione (titolari/panchina) di una squadra per una giornata di una
        competizione. Risolve automaticamente comp_round (giornata di lega) dal
        calendario della competizione quando non specificato."""
        if comp_round is None:
            resolved = self._resolve_comp_round(id_comp, giornata)
            if resolved is None:
                return None
            comp_round, championship_day = resolved
        else:
            championship_day = giornata

        resp = requests.get(
            f"{self.APILEAGUE_BASE}/gaming/v1/teamLineup/{id_comp}/{comp_round}/{championship_day}/{team_id}/0",
            headers=self._lega_headers(),
            timeout=15,
        )
        if resp.status_code == 400:
            return None
        resp.raise_for_status()
        home = resp.json().get("home")
        if not home or (not home.get("starts") and home.get("tot") is None):
            return None
        return home

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

    def download_results_excel(self, id_competizione: int, nome_competizione: str) -> bytes:
        """Excel "Calendario" (partite + punteggi) di una competizione (endpoint legacy).
        Nota: l'endpoint legacy su leghe.fantacalcio.it richiede cookie di sessione web
        tradizionali; le sync usano ora direttamente get_competition_calendar() su apileague."""
        resp = self.session.get(
            "https://leghe.fantacalcio.it/servizi/v1_legheCompetizione/excel",
            params={
                "alias_lega": self.alias_lega,
                "id_competizione": id_competizione,
                "nome_competizione": nome_competizione,
            },
            headers=self._lega_headers(),
            timeout=20,
        )
        resp.raise_for_status()
        if resp.headers.get("content-type", "").startswith("application/json"):
            raise RuntimeError(f"Download risultati fallito per competizione {id_competizione}: {resp.text}")
        return resp.content

    def get_tutte_le_formazioni(self, giornata: int) -> dict:
        """Formazioni di tutte le competizioni della lega per la giornata data.
        Ritorna {slug_competizione: {"id_comp", "giornata", "dati": {nome_squadra: lineup}} | None}
        — None se nessuna squadra della competizione ha ancora una formazione
        per quella giornata (es. competizione non ancora iniziata)."""
        risultati = {}
        for comp in self.list_competitions():
            if comp.get("del"):
                continue
            slug = comp["name"].strip().lower().replace(" ", "_")
            id_comp = comp["id"]

            resolved = self._resolve_comp_round(id_comp, giornata)
            if resolved is None:
                risultati[slug] = None
                continue
            comp_round, championship_day = resolved

            squadre = self.list_competition_teams(id_comp)
            dati = {}
            for team_id, nome_squadra in squadre.items():
                lineup = self.get_team_lineup(id_comp, championship_day, team_id, comp_round=comp_round)
                if lineup is not None and lineup.get("starts"):
                    dati[nome_squadra] = lineup

            risultati[slug] = {"id_comp": id_comp, "giornata": championship_day, "dati": dati} if dati else None

        return risultati
