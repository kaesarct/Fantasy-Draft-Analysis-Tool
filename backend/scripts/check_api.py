"""Diagnostica delle chiamate esterne: fantacalcio.it e leghe.fantacalcio.it.

Sola lettura: nessuna scrittura su DB, gli Excel finiscono in una directory
temporanea (downloads/ non viene toccata). Esercita le funzioni realmente usate
dall'app, cosi' un cambio di HTML/endpoint lato fantacalcio.it emerge qui.

Uso (dentro il container backend):
    python -m scripts.check_api [--playwright]

--playwright aggiunge i controlli su leghe che richiedono il browser
autenticato (dashboard competizioni + V1_LegheFormazioni/Pagina): sono lenti
(~30s) e dipendono dal session file salvato.
"""
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

import requests

from app.config import settings
from app.services import seriea_scraper
from app.services.fanta_client import fanta_client
from app.services.leghe_client import LegheClient, SessionExpired

OK, WARN, FAIL = "OK", "WARN", "FAIL"
XLSX_MAGIC = b"PK\x03\x04"

results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    icon = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}[status]
    print(f"{icon} {name}" + (f" — {detail}" if detail else ""), flush=True)
    results.append((name, status, detail))


def run(name: str, fn) -> None:
    """Esegue un check isolando le eccezioni: un endpoint rotto non ferma gli altri."""
    try:
        status, detail = fn()
    except Exception as e:
        record(name, FAIL, f"{type(e).__name__}: {e}")
        return
    record(name, status, detail)


def mask(value: str) -> str:
    if not value:
        return "(vuoto)"
    if "@" in value:
        user, _, domain = value.partition("@")
        return f"{user[:2]}***@{domain}"
    return f"{value[:2]}***"


def describe_excel(path: str | None) -> tuple[str, str]:
    if not path:
        return FAIL, "nessun file scaricato (vedi log per lo status HTTP)"
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(4)
    if size == 0:
        return FAIL, "0 byte: 200 OK ma stagione/giornata non pubblicata"
    if head != XLSX_MAGIC:
        return WARN, f"{size} byte ma non e' un xlsx (magic={head!r})"
    return OK, f"{size} byte, xlsx valido"


# ── fantacalcio.it — pagine pubbliche ───────────────────────────────────────
def check_base_url():
    resp = requests.get(settings.fanta_base_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    status = OK if resp.ok else FAIL
    return status, f"HTTP {resp.status_code} ({len(resp.content)} byte)"


def check_last_matchday():
    day = fanta_client.get_last_matchday()
    if day < 0:
        return FAIL, "giornata non trovata: selettore 'h1.pl-2.title.w-100 small' cambiato o pagina non raggiungibile"
    return OK, f"ultima giornata conclusa = {day}"


def check_next_matches():
    matches = seriea_scraper.get_next_matches()
    if not matches:
        return FAIL, "0 partite: selettore 'li.match' cambiato o pagina non raggiungibile"
    played = sum(1 for m in matches if m["is_played"])
    sample = matches[0]
    return OK, (
        f"{len(matches)} partite ({played} giocate) — es. "
        f"{sample['home_team']}-{sample['away_team']} {sample['match_date']}"
    )


def check_probable_lineups():
    players = seriea_scraper.get_probable_lineups()
    if not players:
        return FAIL, "0 giocatori: selettore 'li.player-item.pill' cambiato"
    return OK, f"{len(players)} giocatori — es. {players[0]['name']} (fanta_id={players[0]['fanta_id']})"


def check_serie_a_injuries():
    injuries = seriea_scraper.get_serie_a_injuries()
    if not injuries:
        return WARN, "0 infortunati: possibile pagina vuota (pre-stagione) o selettore 'div.team-card' cambiato"
    teams = len({i["team_name"] for i in injuries})
    return OK, f"{len(injuries)} infortunati su {teams} squadre — es. {injuries[0]['player_name']}"


# ── fantacalcio.it — API autenticata ────────────────────────────────────────
def check_fanta_login():
    if not settings.fanta_username or not settings.fanta_password:
        return FAIL, "FANTA_USERNAME/FANTA_PASSWORD non configurate"
    if not fanta_client.login():
        return FAIL, f"login rifiutato per {mask(settings.fanta_username)}"
    cookies = len(fanta_client._session.cookies)
    return OK, f"utente {mask(settings.fanta_username)}, {cookies} cookie di sessione"


def check_excel_prices(tmpdir: str):
    def _check():
        path = fanta_client.download_prices_excel(int(settings.fanta_year_quotazioni), tmpdir)
        return describe_excel(path)

    return _check


def check_excel_stats(tmpdir: str):
    def _check():
        path = fanta_client.download_stats_excel(int(settings.fanta_year_quotazioni), tmpdir)
        return describe_excel(path)

    return _check


def check_excel_votes(tmpdir: str):
    def _check():
        day = fanta_client.get_last_matchday()
        if day < 1:
            return WARN, f"nessuna giornata conclusa (giornata={day}): check voti saltato"
        path = fanta_client.download_votes_excel(int(settings.fanta_year_quotazioni), day, tmpdir)
        status, detail = describe_excel(path)
        return status, f"giornata {day} — {detail}"

    return _check


# ── leghe.fantacalcio.it ────────────────────────────────────────────────────
def check_leghe_home():
    resp = requests.get(settings.fanta_leghe_base_url, timeout=15)
    if not resp.ok:
        return FAIL, f"HTTP {resp.status_code} su {settings.fanta_leghe_base_url}"
    return OK, f"HTTP {resp.status_code} ({len(resp.content)} byte)"


def check_app_key(state: dict):
    def _check():
        client = LegheClient()
        state["client"] = client
        html = requests.get(settings.fanta_leghe_base_url, timeout=15).text
        match = re.search(r'authAppKey"?\s*:\s*"([^"]+)"', html)
        if not match:
            return WARN, "authAppKey assente dalla homepage leghe: in uso il fallback di config.py"
        key = match.group(1)
        if key != settings.fanta_app_key_fallback:
            return OK, f"authAppKey letto dalla homepage ({key[:8]}…) — diverso dal fallback in config.py"
        return OK, f"authAppKey letto dalla homepage ({key[:8]}…), allineato al fallback"

    return _check


def check_leghe_login(state: dict):
    def _check():
        client = state.get("client") or LegheClient()
        state["client"] = client
        utente = client.login()
        return OK, f"utente '{utente.get('username')}', id={utente.get('id')}, {len(client.leghe)} leghe"

    return _check


def check_lega_alias(state: dict):
    def _check():
        if not settings.fanta_lega_name:
            return FAIL, "FANTA_LEGA_NAME non configurato: le chiamate leghe puntano alla homepage"
        client = state.get("client")
        if client is None or not client.leghe:
            return WARN, f"alias '{settings.fanta_lega_name}' non verificabile: login leghe non riuscito"
        lega = next((l for l in client.leghe if l.get("alias") == settings.fanta_lega_name), None)
        if lega is None:
            alias = ", ".join(l.get("alias", "?") for l in client.leghe) or "nessuna"
            return FAIL, f"alias '{settings.fanta_lega_name}' non tra le leghe dell'utente ({alias})"
        return OK, (
            f"'{lega['nome']}' → alias={lega['alias']}, id_lega={lega['id']}, "
            f"id_squadra={lega['id_squadra']}"
        )

    return _check


def check_session_file():
    path = settings.fanta_session_file
    if not os.path.exists(path):
        return FAIL, f"{path} assente: esegui capture_login_session.py"
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except json.JSONDecodeError as e:
        return FAIL, f"{path} non e' JSON valido: {e}"

    cookies = state.get("cookies") or []
    if not cookies:
        return FAIL, f"{path} senza cookie: sessione da rigenerare"

    now = datetime.now(timezone.utc).timestamp()
    expiries = [c["expires"] for c in cookies if c.get("expires", -1) > 0]
    scaduti = [c["name"] for c in cookies if 0 < c.get("expires", -1) < now]
    if scaduti:
        return WARN, f"{len(cookies)} cookie, {len(scaduti)} gia' scaduti ({', '.join(scaduti[:3])})"
    if expiries:
        prossima = datetime.fromtimestamp(min(expiries), timezone.utc)
        giorni = (min(expiries) - now) / 86400
        return OK, f"{len(cookies)} cookie, prima scadenza {prossima:%Y-%m-%d} (tra {giorni:.0f} giorni)"
    return OK, f"{len(cookies)} cookie di sola sessione (nessuna scadenza)"


def check_competizioni_api(state: dict):
    """Conteggio competizioni dalla REST API: distingue "nessuna competizione
    creata" da "discovery HTML rotta", che dalla dashboard sono indistinguibili."""

    def _check():
        client = state.get("client")
        if client is None or not client.leghe:
            return WARN, "login leghe non riuscito: conteggio competizioni non verificabile"
        lega = next((l for l in client.leghe if l.get("alias") == settings.fanta_lega_name), None)
        if lega is None or not lega.get("jwt"):
            return WARN, "jwt di lega non disponibile: conteggio competizioni non verificabile"
        resp = requests.get(
            "https://apileague.fantacalcio.it/onboarding/v1/league/competitions",
            headers={
                "app_key": client.session.headers["app_key"],
                "authorization": f"Bearer {lega['jwt']}",
                "accept": "application/json",
            },
            timeout=15,
        )
        if not resp.ok:
            return FAIL, f"HTTP {resp.status_code}: {resp.text[:120]}"
        competizioni = resp.json()
        state["n_comp_api"] = len(competizioni)
        if not competizioni:
            return WARN, "0 competizioni create in lega per questa stagione"
        return OK, f"{len(competizioni)} competizioni in lega"

    return _check


def check_competizioni(state: dict):
    def _check():
        client = state.get("client") or LegheClient()
        state["client"] = client
        try:
            competizioni = client.discover_competizioni()
        except SessionExpired:
            if state.get("n_comp_api") == 0:
                return WARN, "dropdown vuoto, coerente con 0 competizioni create in lega"
            raise
        state["competizioni"] = competizioni
        elenco = ", ".join(f"{n}={i}" for n, i in competizioni.items())
        return OK, f"{len(competizioni)} competizioni — {elenco}"

    return _check


def check_formazioni(state: dict):
    def _check():
        competizioni = state.get("competizioni")
        if not competizioni:
            return WARN, "competizioni non disponibili: check formazioni saltato"
        client = state["client"]
        nome, id_comp = next(iter(competizioni.items()))
        res = client.get_formazioni(id_comp)
        dati = res.get("dati") or {}
        squadre = dati.get("data") if isinstance(dati, dict) else None
        n_squadre = len(squadre) if isinstance(squadre, list) else "?"
        return OK, (
            f"'{nome}' (id_comp={id_comp}) giornata={res.get('giornata')}, "
            f"chiavi risposta={sorted(dati)[:5]}, squadre={n_squadre}"
        )

    return _check


def main() -> int:
    con_playwright = "--playwright" in sys.argv

    print("=" * 78)
    print("Diagnostica API — fantacalcio.it / leghe.fantacalcio.it")
    print(f"season_code={settings.fanta_year_quotazioni}  lega={settings.fanta_lega_name or '(non impostata)'}")
    print("=" * 78)

    print("\n── fantacalcio.it (pubblico) ─────────────────────────────────────")
    run("GET /", check_base_url)
    run("GET live-serie-a → ultima giornata", check_last_matchday)
    run("GET live-serie-a → prossime partite", check_next_matches)
    run("GET probabili-formazioni-serie-a", check_probable_lineups)
    run("GET infortunati-serie-a", check_serie_a_injuries)

    print("\n── fantacalcio.it (API autenticata) ──────────────────────────────")
    run("POST api/v1/User/login", check_fanta_login)
    with tempfile.TemporaryDirectory() as tmpdir:
        run(f"GET api/v1/Excel/prices/{settings.fanta_year_quotazioni}/1", check_excel_prices(tmpdir))
        run(f"GET api/v1/Excel/stats/{settings.fanta_year_quotazioni}/1", check_excel_stats(tmpdir))
        run(f"GET api/v1/Excel/votes/{settings.fanta_year_quotazioni}/<giornata>", check_excel_votes(tmpdir))

    print("\n── leghe.fantacalcio.it ──────────────────────────────────────────")
    state: dict = {}
    run("GET homepage leghe", check_leghe_home)
    run("discovery authAppKey", check_app_key(state))
    run("POST apileague/onboarding/v1/login", check_leghe_login(state))
    run("alias lega configurato", check_lega_alias(state))
    run("GET onboarding/v1/league/competitions", check_competizioni_api(state))
    run(f"session file ({settings.fanta_session_file})", check_session_file)

    if con_playwright:
        print("\n── leghe.fantacalcio.it (browser autenticato) ────────────────────")
        run("dashboard → competizioni", check_competizioni(state))
        run("V1_LegheFormazioni/Pagina", check_formazioni(state))
    else:
        print("\n(check Playwright saltati: rilancia con --playwright per includerli)")

    n_ok = sum(1 for _, s, _ in results if s == OK)
    n_warn = sum(1 for _, s, _ in results if s == WARN)
    n_fail = sum(1 for _, s, _ in results if s == FAIL)
    print("\n" + "=" * 78)
    print(f"Esito: {n_ok} OK, {n_warn} WARN, {n_fail} FAIL su {len(results)} check")
    for name, status, detail in results:
        if status != OK:
            print(f"  {status}: {name} — {detail}")
    print("=" * 78)
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
