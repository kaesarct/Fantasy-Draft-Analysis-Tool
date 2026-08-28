"""Riconciliazione rose post mercato di riparazione invernale.

L'asta di riparazione avviene fuori piattaforma (a prezzo di acquisto);
qui si carica un unico file con la rosa finale di tutte le squadre della
lega e il sistema calcola svincoli/acquisti per differenza rispetto alla
rosa attiva attuale — nessuna offerta/competizione gestita dal sistema.

Formati supportati: CSV/dat (colonne tollerante a varianti di nome), Excel,
e l'HTML storico "rosa squadre" (tabelle nidificate per squadra, verificato
su un file reale — vedi _parse_html_rosters).
"""
import io
import re
from datetime import datetime

import pandas as pd
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.fanta_team import FantaTeam, FantaRoster, League
from app.models.player import Player
from app.routers.league import MAIN_LEAGUE_TYPES
from app.services.auth_service import require_admin
from app.services.sync_service import _match_player_id

router = APIRouter(prefix="/winter-market", tags=["winter-market"])

_TEAM_COLUMNS = ["squadra", "team", "fanta_team", "nome_squadra"]
_PLAYER_COLUMNS = ["giocatore", "nome", "player", "nome_giocatore"]
_PRICE_COLUMNS = ["prezzo", "costo", "price", "quotazione"]
_ROLE_COLUMNS = ["ruolo", "role", "r"]
_VALID_ROLES = {"P", "D", "C", "A"}

# Formato "rosa squadre" storico (es. STAGIONI/*/tamarros *.html): una
# <table> per squadra, prima riga <td colspan=3><strong>NOME</strong></td>,
# poi righe <td>ruolo</td><td>(CLUB) Giocatore</td><td>prezzo</td>.
_CLUB_PREFIX_RE = re.compile(r"^\([A-Z]+\)\s*")
# Alcuni export hanno un numero (posizione/ID) prima del nome squadra, es. "1Zu' Pietro".
_TEAM_NUMERIC_PREFIX_RE = re.compile(r"^\d+\s*")


def _parse_html_rosters(content: bytes) -> pd.DataFrame:
    soup = BeautifulSoup(content, "html.parser")
    rows = []
    for team_table in soup.find_all("table"):
        trs = team_table.find_all("tr")
        if not trs:
            continue
        header_tds = trs[0].find_all("td")
        if len(header_tds) != 1 or not header_tds[0].find("strong"):
            continue  # non e' una tabella-squadra (es. il contenitore esterno)
        team_name = _TEAM_NUMERIC_PREFIX_RE.sub("", header_tds[0].get_text(strip=True))
        for tr in trs[1:]:
            tds = tr.find_all("td")
            if len(tds) != 3:
                continue
            player_name = _CLUB_PREFIX_RE.sub("", tds[1].get_text(strip=True))
            role = tds[0].get_text(strip=True).upper()
            rows.append({
                "squadra": team_name,
                "giocatore": player_name,
                "prezzo": tds[2].get_text(strip=True),
                "ruolo": role if role in _VALID_ROLES else None,
            })
    return pd.DataFrame(rows)


def _pick_column(columns, candidates: list[str]) -> str | None:
    lowered = {str(c).lower().strip(): c for c in columns}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return None


def _read_file(file: UploadFile) -> pd.DataFrame:
    content = file.file.read()
    name = (file.filename or "").lower()
    if name.endswith(".html") or name.endswith(".htm"):
        return _parse_html_rosters(content)
    if name.endswith(".csv") or name.endswith(".dat"):
        return pd.read_csv(io.BytesIO(content), sep=None, engine="python")
    return pd.read_excel(io.BytesIO(content))


@router.post("/reconcile")
def reconcile_winter_market(
    season_id: int = Form(...),
    league_level: str = Form(...),
    dry_run: bool = Form(True),
    create_missing_players: bool = Form(False),
    market_date: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    league_level = league_level.upper()
    if league_level not in MAIN_LEAGUE_TYPES:
        raise HTTPException(400, f"Lega non valida: {league_level}")
    league = db.query(League).filter(
        League.season_id == season_id, League.level == league_level
    ).first()
    if not league:
        raise HTTPException(
            400,
            f"Nessuna lega {league_level} per questa stagione: creala prima in Gestione Squadre.",
        )

    df = _read_file(file)
    team_col = _pick_column(df.columns, _TEAM_COLUMNS)
    player_col = _pick_column(df.columns, _PLAYER_COLUMNS)
    price_col = _pick_column(df.columns, _PRICE_COLUMNS)
    role_col = _pick_column(df.columns, _ROLE_COLUMNS)
    if not team_col or not player_col or not price_col:
        raise HTTPException(
            400,
            f"Colonne non riconosciute (trovate: {list(df.columns)}). "
            "Serve una colonna squadra, una giocatore, una prezzo.",
        )

    teams_by_name = {
        t.name.strip().lower(): t
        for t in db.query(FantaTeam).filter(
            FantaTeam.season_id == season_id, FantaTeam.league_id == league.id
        ).all()
    }

    rows_by_team: dict[int, list[tuple[int, float]]] = {}
    unmatched_teams: set[str] = set()
    unmatched_players: set[str] = set()
    created_players: list[dict] = []
    new_team_ids: set[int] = set()

    for _, row in df.iterrows():
        team_name = str(row[team_col]).strip()
        player_name = str(row[player_col]).strip()
        try:
            price = float(row[price_col])
        except (TypeError, ValueError):
            continue

        team = teams_by_name.get(team_name.lower())
        if not team:
            if not team_name:
                unmatched_teams.add(team_name)
                continue
            # Nome mai visto in questa lega/stagione: squadra nuova arrivata
            # (tipicamente non esisteva l'anno scorso) — creata al volo.
            # Flush senza commit se dry_run, stesso pattern già usato sotto
            # per i giocatori mancanti: l'id serve per l'anteprima ma la riga
            # non sopravvive se la richiesta non arriva a db.commit().
            team = FantaTeam(name=team_name, season_id=season_id, league_id=league.id)
            db.add(team)
            db.flush()
            teams_by_name[team_name.lower()] = team
            new_team_ids.add(team.id)
        row_role = str(row[role_col]).strip().upper() if role_col else None
        if row_role not in _VALID_ROLES:
            row_role = None
        player_id = _match_player_id(db, player_name)
        if not player_id and create_missing_players:
            if row_role is None:
                unmatched_players.add(player_name)
                continue
            display_name = player_name.title() if player_name.isupper() else player_name
            new_player = Player(name=display_name, role=row_role)
            db.add(new_player)
            db.flush()
            player_id = new_player.id
            created_players.append({"player_id": player_id, "player_name": display_name, "role": row_role})
        if not player_id:
            unmatched_players.add(player_name)
            continue
        rows_by_team.setdefault(team.id, []).append((player_id, price, row_role))

    market_dt = datetime.fromisoformat(market_date) if market_date else datetime.utcnow()
    players_by_id = {p.id: p for p in db.query(Player).all()}

    report = []
    for team_id, new_entries in rows_by_team.items():
        team = db.query(FantaTeam).filter(FantaTeam.id == team_id).first()
        current_rows = (
            db.query(FantaRoster)
            .filter(
                FantaRoster.fanta_team_id == team_id,
                FantaRoster.season_id == season_id,
                FantaRoster.is_active == True,
            )
            .all()
        )
        current_by_player = {r.player_id: r for r in current_rows}
        new_player_ids = {pid for pid, _, _ in new_entries}

        released = [r for pid, r in current_by_player.items() if pid not in new_player_ids]
        added = [(pid, price, role) for pid, price, role in new_entries if pid not in current_by_player]

        credit_refund = sum(r.purchase_price for r in released)
        credit_spent = sum(price for _, price, _ in added)

        if not dry_run:
            for r in released:
                r.is_active = False
                r.released_at = market_dt
            for pid, price, role in added:
                db.add(FantaRoster(
                    fanta_team_id=team_id, player_id=pid, season_id=season_id,
                    purchase_price=price, acquired_at=market_dt, role=role,
                ))
            team.remaining_credits = (team.remaining_credits or 0.0) + credit_refund - credit_spent
            team.credits_spent = (team.credits_spent or 0.0) - credit_refund + credit_spent

        report.append({
            "team_id": team_id,
            "team_name": team.name,
            "is_new_team": team_id in new_team_ids,
            "released": [
                {"player_id": r.player_id, "player_name": players_by_id[r.player_id].name, "refund": r.purchase_price}
                for r in released
            ],
            "added": [
                {"player_id": pid, "player_name": players_by_id[pid].name, "price": price}
                for pid, price, _ in added
            ],
            "credit_refund": credit_refund,
            "credit_spent": credit_spent,
            "credit_delta": credit_refund - credit_spent,
        })

    all_league_teams = db.query(FantaTeam).filter(
        FantaTeam.season_id == season_id, FantaTeam.league_id == league.id
    ).all()
    teams_without_data = [
        {"team_id": t.id, "team_name": t.name}
        for t in all_league_teams
        if t.id not in rows_by_team
    ]

    if not dry_run:
        db.commit()

    return {
        "ok": True,
        "applied": not dry_run,
        "league_level": league_level,
        "report": report,
        "created_players": created_players,
        "unmatched_teams": sorted(unmatched_teams),
        "unmatched_players": sorted(unmatched_players),
        "teams_without_data": teams_without_data,
    }
