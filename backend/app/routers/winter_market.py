"""Riconciliazione rose post mercato di riparazione invernale.

L'asta di riparazione avviene fuori piattaforma (a prezzo di acquisto);
qui si carica un unico file con la rosa finale di tutte le squadre della
lega e il sistema calcola svincoli/acquisti per differenza rispetto alla
rosa attiva attuale — nessuna offerta/competizione gestita dal sistema.

Formato colonne non ancora confermato su un file reale: parser tollerante
a varianti di nome colonna, da adattare al primo file vero fornito.
"""
import io
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.fanta_team import FantaTeam, FantaRoster
from app.models.player import Player
from app.services.auth_service import require_admin
from app.services.sync_service import _match_player_id

router = APIRouter(prefix="/winter-market", tags=["winter-market"])

_TEAM_COLUMNS = ["squadra", "team", "fanta_team", "nome_squadra"]
_PLAYER_COLUMNS = ["giocatore", "nome", "player", "nome_giocatore"]
_PRICE_COLUMNS = ["prezzo", "costo", "price", "quotazione"]


def _pick_column(columns, candidates: list[str]) -> str | None:
    lowered = {str(c).lower().strip(): c for c in columns}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return None


def _read_file(file: UploadFile) -> pd.DataFrame:
    content = file.file.read()
    name = (file.filename or "").lower()
    if name.endswith(".csv") or name.endswith(".dat"):
        return pd.read_csv(io.BytesIO(content), sep=None, engine="python")
    return pd.read_excel(io.BytesIO(content))


@router.post("/reconcile")
def reconcile_winter_market(
    season_id: int = Form(...),
    dry_run: bool = Form(True),
    market_date: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    df = _read_file(file)
    team_col = _pick_column(df.columns, _TEAM_COLUMNS)
    player_col = _pick_column(df.columns, _PLAYER_COLUMNS)
    price_col = _pick_column(df.columns, _PRICE_COLUMNS)
    if not team_col or not player_col or not price_col:
        raise HTTPException(
            400,
            f"Colonne non riconosciute (trovate: {list(df.columns)}). "
            "Serve una colonna squadra, una giocatore, una prezzo.",
        )

    teams_by_name = {
        t.name.strip().lower(): t
        for t in db.query(FantaTeam).filter(FantaTeam.season_id == season_id).all()
    }

    rows_by_team: dict[int, list[tuple[int, float]]] = {}
    unmatched_teams: set[str] = set()
    unmatched_players: set[str] = set()

    for _, row in df.iterrows():
        team_name = str(row[team_col]).strip()
        player_name = str(row[player_col]).strip()
        try:
            price = float(row[price_col])
        except (TypeError, ValueError):
            continue

        team = teams_by_name.get(team_name.lower())
        if not team:
            unmatched_teams.add(team_name)
            continue
        player_id = _match_player_id(db, player_name)
        if not player_id:
            unmatched_players.add(player_name)
            continue
        rows_by_team.setdefault(team.id, []).append((player_id, price))

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
        new_player_ids = {pid for pid, _ in new_entries}

        released = [r for pid, r in current_by_player.items() if pid not in new_player_ids]
        added = [(pid, price) for pid, price in new_entries if pid not in current_by_player]

        credit_refund = sum(r.purchase_price for r in released)
        credit_spent = sum(price for _, price in added)

        if not dry_run:
            for r in released:
                r.is_active = False
                r.released_at = market_dt
            for pid, price in added:
                db.add(FantaRoster(
                    fanta_team_id=team_id, player_id=pid, season_id=season_id,
                    purchase_price=price, acquired_at=market_dt,
                ))
            team.remaining_credits = (team.remaining_credits or 0.0) + credit_refund - credit_spent
            team.credits_spent = (team.credits_spent or 0.0) - credit_refund + credit_spent

        report.append({
            "team_id": team_id,
            "team_name": team.name,
            "released": [
                {"player_id": r.player_id, "player_name": players_by_id[r.player_id].name, "refund": r.purchase_price}
                for r in released
            ],
            "added": [
                {"player_id": pid, "player_name": players_by_id[pid].name, "price": price}
                for pid, price in added
            ],
            "credit_refund": credit_refund,
            "credit_spent": credit_spent,
            "credit_delta": credit_refund - credit_spent,
        })

    if not dry_run:
        db.commit()

    return {
        "ok": True,
        "applied": not dry_run,
        "report": report,
        "unmatched_teams": sorted(unmatched_teams),
        "unmatched_players": sorted(unmatched_players),
    }
