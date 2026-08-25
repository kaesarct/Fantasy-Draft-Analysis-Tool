"""Import statistiche stagionali storiche da pianetafanta.it.

Fonte scelta dall'utente per le stagioni di cui non abbiamo dati per
giornata (2006-07..2014-15): un archivio con una riga aggregata per
giocatore/stagione/squadra (non per giornata). La tabella e' paginata
lato server (~20 righe/pagina, verificato: nessuna API JSON dietro),
quindi si scarica e parsa una pagina alla volta finche' una pagina non
torna piu' righe.
"""
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.player import Player, PlayerArchiveSeasonStat
from app.models.season import Season
from app.services.auth_service import require_admin
from app.services.sync_service import _match_player_id

router = APIRouter(prefix="/player-stats-archive", tags=["player-stats-archive"])

BASE_URL = "https://www.pianetafanta.it/statistiche-fantacalcio/archivio"
_VALID_ROLES = {"P", "D", "C", "A"}
# Pianetafanta disambigua i cognomi comuni con un'iniziale finale
# ("GABBIADINI M."), che spesso il nostro DB (fonte fantacalcio.it) non usa
# ("Gabbiadini"). Prima di creare un giocatore nuovo, si prova il nome senza
# l'iniziale: se esiste un'unica corrispondenza esatta, e' lo stesso giocatore.
_TRAILING_INITIAL_RE = re.compile(r"^(.*)\s+[A-Za-z]{1,3}\.?$")


def _match_player_id_fuzzy(db: Session, name: str) -> Optional[int]:
    player_id = _match_player_id(db, name)
    if player_id:
        return player_id
    m = _TRAILING_INITIAL_RE.match(name.strip())
    if not m:
        return None
    return _match_player_id(db, m.group(1).strip())


def _fetch_page(season_code: str, page: int) -> str:
    resp = requests.get(
        BASE_URL,
        params={"cerca": 1, "st": season_code, "ord": "MF", "dir": "desc", "p": page},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.text


def _header_code(th) -> str:
    a = th.find("a")
    if a:
        arrow = a.find("span", class_="sa-sort-arrow")
        if arrow:
            arrow.extract()
        return a.get_text(strip=True)
    return th.get_text(strip=True)


def _cell_value(td) -> Optional[str]:
    if td.find(class_="sa-dash"):
        return "0"
    icon_num = td.find(class_="sa-icon-num")
    if icon_num:
        return icon_num.get_text(strip=True)
    return td.get_text(strip=True)


def _parse_num(text: Optional[str]) -> Optional[float]:
    if text is None:
        return None
    text = text.strip().replace(",", ".")
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_page_rows(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return []
    thead = table.find("thead")
    tbody = table.find("tbody")
    if not thead or not tbody:
        return []
    header_row = thead.find_all("tr")[-1]
    header_ths = header_row.find_all("th")[2:]  # salta checkbox e "GIOCATORE"
    header_codes = [_header_code(th) for th in header_ths]

    rows = []
    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        name_td = tds[1]
        name_link = name_td.find(class_="sa-nome-link")
        if not name_link:
            continue
        role_badge = name_td.find(class_="sa-ruolo-badge")
        team_div = name_td.find(class_="sa-squadra-nome")
        row = {
            "role": role_badge.get_text(strip=True) if role_badge else None,
            "player_name": name_link.get_text(strip=True),
            "team_name": team_div.get_text(strip=True) if team_div else None,
        }
        for code, td in zip(header_codes, tds[2:]):
            row[code] = _cell_value(td)
        rows.append(row)
    return rows


def _scrape_season(season_code: str, max_pages: int = 60, delay: float = 0.4) -> list[dict]:
    all_rows = []
    page = 1
    while page <= max_pages:
        html = _fetch_page(season_code, page)
        rows = _parse_page_rows(html)
        if not rows:
            break
        all_rows.extend(rows)
        page += 1
        time.sleep(delay)
    return all_rows


@router.post("/sync")
def sync_player_stats_archive(
    season_id: int = Query(...),
    season_code: str = Query(..., description='es. "2014_2015"'),
    dry_run: bool = Query(True),
    create_missing_players: bool = Query(False),
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(404, "Stagione non trovata")

    try:
        raw_rows = _scrape_season(season_code)
    except requests.RequestException as e:
        raise HTTPException(502, f"Errore nello scaricare l'archivio: {e}")

    unmatched_players: list[str] = []
    created_players: list[dict] = []
    upserted = 0

    existing = {
        (s.player_id, s.team_name): s
        for s in db.query(PlayerArchiveSeasonStat).filter(PlayerArchiveSeasonStat.season_id == season_id).all()
    }

    for row in raw_rows:
        player_name = row["player_name"].strip()
        role = (row.get("role") or "").strip().upper()
        player_id = _match_player_id_fuzzy(db, player_name)
        if not player_id and create_missing_players and role in _VALID_ROLES:
            new_player = Player(name=player_name.title(), role=role)
            db.add(new_player)
            db.flush()
            player_id = new_player.id
            created_players.append({"player_id": player_id, "player_name": new_player.name, "role": role})
        if not player_id:
            unmatched_players.append(player_name)
            continue

        team_name = row.get("team_name")
        key = (player_id, team_name)
        stat = existing.get(key)
        if not stat:
            stat = PlayerArchiveSeasonStat(player_id=player_id, season_id=season_id, team_name=team_name)
            db.add(stat)
            existing[key] = stat

        stat.role = role or stat.role
        stat.presences = int(_parse_num(row.get("P")) or 0)
        stat.starter_count = int(_parse_num(row.get("T")) or 0)
        stat.quota = _parse_num(row.get("Q"))
        stat.vote_gazzetta = _parse_num(row.get("MG"))
        stat.vote_corriere = _parse_num(row.get("MC"))
        stat.vote_tuttosport = _parse_num(row.get("MT"))
        stat.vote_avg2 = _parse_num(row.get("M2"))
        stat.vote_avg3 = _parse_num(row.get("M3"))
        stat.vote_fantacalcio = _parse_num(row.get("MF"))
        stat.goals_scored = int(_parse_num(row.get("GF")) or 0)
        stat.goals_conceded = int(_parse_num(row.get("GS")) or 0)
        stat.assists = int(_parse_num(row.get("AS")) or 0)
        stat.own_goals = int(_parse_num(row.get("AU")) or 0)
        stat.yellow_cards = int(_parse_num(row.get("A")) or 0)
        stat.red_cards = int(_parse_num(row.get("E")) or 0)
        stat.penalties_scored = int(_parse_num(row.get("TR")) or 0)
        stat.penalties_missed = int(_parse_num(row.get("SB")) or 0)
        stat.penalties_saved = int(_parse_num(row.get("PA")) or 0)
        stat.penalties_conceded = int(_parse_num(row.get("SU")) or 0)
        upserted += 1

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return {
        "ok": True,
        "applied": not dry_run,
        "season_code": season_code,
        "rows_scraped": len(raw_rows),
        "rows_upserted": upserted,
        "created_players": created_players,
        "unmatched_players": sorted(set(unmatched_players)),
    }
