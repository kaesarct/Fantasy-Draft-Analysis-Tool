"""Scambi tra squadre (Trade/TradeItem) — l'admin registra scambi gia'
concordati fuori piattaforma (niente flusso di proposta/accettazione).

Regola di ricalcolo prezzo (fornita dall'utente, verificata su un esempio
reale 3 giocatori per lato): ogni squadra cede un insieme di giocatori e ne
riceve altrettanti (stesso multiset di ruoli classici). I "milioni"
complessivi restano gli stessi per squadra: si ordinano i giocatori cedute
da ciascun lato per prezzo decrescente (parita' -> quotazione attuale) e si
riassegnano incrociati per rango — il k-esimo giocatore che arriva prende
il prezzo che il k-esimo giocatore uscente aveva prima dello scambio.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.trade import Trade, TradeItem
from app.models.fanta_team import FantaTeam, FantaRoster
from app.models.player import PlayerSnapshot
from app.services.auth_service import require_admin

router = APIRouter(prefix="/trades", tags=["trades"])


def _current_price(db: Session, player_id: int, season_id: int) -> float:
    snap = (
        db.query(PlayerSnapshot)
        .filter(PlayerSnapshot.player_id == player_id, PlayerSnapshot.season_id == season_id)
        .order_by(PlayerSnapshot.match_day.desc())
        .first()
    )
    return snap.price if snap else 0.0


def _active_roster_rows(db: Session, team_id: int, player_ids: list[int], season_id: int) -> list[FantaRoster]:
    rows = (
        db.query(FantaRoster)
        .filter(
            FantaRoster.fanta_team_id == team_id,
            FantaRoster.season_id == season_id,
            FantaRoster.player_id.in_(player_ids),
            FantaRoster.is_active == True,
        )
        .all()
    )
    missing = set(player_ids) - {r.player_id for r in rows}
    if missing:
        raise HTTPException(400, f"Giocatori non in rosa attiva per la squadra {team_id}: {sorted(missing)}")
    return rows


def _trade_summary(db: Session, trade: Trade) -> dict:
    team_a = db.query(FantaTeam).filter(FantaTeam.id == trade.team_a_id).first()
    team_b = db.query(FantaTeam).filter(FantaTeam.id == trade.team_b_id).first()
    items = db.query(TradeItem).filter(TradeItem.trade_id == trade.id).all()
    return {
        "id": trade.id,
        "season_id": trade.season_id,
        "team_a_id": trade.team_a_id,
        "team_a_name": team_a.name if team_a else None,
        "team_b_id": trade.team_b_id,
        "team_b_name": team_b.name if team_b else None,
        "trade_date": trade.approved_at,
        "notes": trade.notes,
        "items": [
            {
                "player_id": i.player_id,
                "player_name": i.player.name if i.player else None,
                "role": i.player.role if i.player else None,
                "from_team_id": i.from_team_id,
                "to_team_id": i.to_team_id,
                "price_before": i.price_before,
                "price_after": i.price_after,
            }
            for i in items
        ],
    }


@router.get("")
def list_trades(season_id: int, db: Session = Depends(get_db)):
    trades = (
        db.query(Trade)
        .filter(Trade.season_id == season_id)
        .order_by(Trade.approved_at.desc())
        .all()
    )
    return [_trade_summary(db, t) for t in trades]


class TradeCreate(BaseModel):
    season_id: int
    team_a_id: int
    team_b_id: int
    trade_date: datetime | None = None
    notes: str | None = None
    player_ids_a: list[int]  # giocatori che A cede a B
    player_ids_b: list[int]  # giocatori che B cede ad A


@router.post("")
def create_trade(data: TradeCreate, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    if data.team_a_id == data.team_b_id:
        raise HTTPException(400, "Le due squadre devono essere diverse")
    if not data.player_ids_a or not data.player_ids_b:
        raise HTTPException(400, "Servono giocatori da entrambi i lati dello scambio")

    team_a = db.query(FantaTeam).filter(FantaTeam.id == data.team_a_id).first()
    team_b = db.query(FantaTeam).filter(FantaTeam.id == data.team_b_id).first()
    if not team_a or not team_b:
        raise HTTPException(404, "Squadra non trovata")
    if team_a.season_id != data.season_id or team_b.season_id != data.season_id:
        raise HTTPException(400, "Le squadre non appartengono alla stagione indicata")

    rows_a = _active_roster_rows(db, data.team_a_id, data.player_ids_a, data.season_id)
    rows_b = _active_roster_rows(db, data.team_b_id, data.player_ids_b, data.season_id)

    roles_a = sorted(r.player.role for r in rows_a)
    roles_b = sorted(r.player.role for r in rows_b)
    if roles_a != roles_b:
        raise HTTPException(
            400,
            f"I ruoli scambiati non corrispondono: la squadra A cede {roles_a}, "
            f"la squadra B cede {roles_b} — devono essere lo stesso multiset di ruoli",
        )

    def sort_key(row: FantaRoster):
        return (row.purchase_price, _current_price(db, row.player_id, data.season_id))

    a_movers = sorted(rows_a, key=sort_key, reverse=True)
    b_movers = sorted(rows_b, key=sort_key, reverse=True)

    trade_date = data.trade_date or datetime.utcnow()
    trade = Trade(
        season_id=data.season_id, team_a_id=data.team_a_id, team_b_id=data.team_b_id,
        approved_at=trade_date, notes=data.notes,
    )
    db.add(trade)
    db.flush()

    for outgoing, incoming, from_id, to_id in (
        (a_movers, b_movers, data.team_a_id, data.team_b_id),
        (b_movers, a_movers, data.team_b_id, data.team_a_id),
    ):
        for old_row, counterpart in zip(outgoing, incoming):
            new_price = counterpart.purchase_price
            old_row.is_active = False
            old_row.released_at = trade_date
            new_row = FantaRoster(
                fanta_team_id=to_id, player_id=old_row.player_id, season_id=data.season_id,
                purchase_price=new_price, acquired_at=trade_date,
            )
            db.add(new_row)
            db.flush()
            db.add(TradeItem(
                trade_id=trade.id, player_id=old_row.player_id,
                from_team_id=from_id, to_team_id=to_id,
                price_before=old_row.purchase_price, price_after=new_price,
                old_roster_id=old_row.id, new_roster_id=new_row.id,
            ))

    db.commit()
    return _trade_summary(db, trade)


@router.delete("/{trade_id}")
def cancel_trade(trade_id: int, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if not trade:
        raise HTTPException(404, "Scambio non trovato")

    items = db.query(TradeItem).filter(TradeItem.trade_id == trade_id).all()
    old_ids = [i.old_roster_id for i in items if i.old_roster_id]
    new_ids = [i.new_roster_id for i in items if i.new_roster_id]

    # Prima gli item (referenziano le righe roster), poi le righe roster stesse.
    db.query(TradeItem).filter(TradeItem.trade_id == trade_id).delete()
    db.flush()

    if new_ids:
        db.query(FantaRoster).filter(FantaRoster.id.in_(new_ids)).delete(synchronize_session=False)
    if old_ids:
        db.query(FantaRoster).filter(FantaRoster.id.in_(old_ids)).update(
            {FantaRoster.is_active: True, FantaRoster.released_at: None}, synchronize_session=False
        )

    db.delete(trade)
    db.commit()
    return {"ok": True}
