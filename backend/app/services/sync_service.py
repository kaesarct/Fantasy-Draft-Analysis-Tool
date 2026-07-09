"""Sync service — orchestrates data download and DB update."""
import pandas as pd
from sqlalchemy.orm import Session
from app.services.fanta_client import fanta_client
from app.models.player import Player, PlayerSnapshot, PlayerMatchScore
from app.models.serie_a_team import SerieATeam
from app.models.season import Season

import logging
logger = logging.getLogger(__name__)


def sync_prices(db: Session, season_id: int) -> dict:
    """Download quotazioni Excel and upsert Player + PlayerSnapshot."""
    path = fanta_client.download_prices()
    if not path:
        return {"ok": False, "message": "Download failed"}

    match_day = fanta_client.get_last_matchday()
    df = pd.read_excel(path, skiprows=1)

    created = updated = 0
    for _, row in df.iterrows():
        try:
            fanta_id = int(row["Id"])
        except (ValueError, KeyError):
            continue

        # Upsert Player
        player = db.query(Player).filter(Player.fanta_id == fanta_id).first()
        if not player:
            player = Player(
                fanta_id=fanta_id,
                name=str(row.get("Nome", "")),
                role=str(row.get("R", "")),
                secondary_role=str(row.get("RM", "")) if pd.notna(row.get("RM")) else None,
            )
            db.add(player)
            db.flush()
            created += 1
        else:
            player.role = str(row.get("R", player.role))
            updated += 1

        # Upsert PlayerSnapshot
        snap = (
            db.query(PlayerSnapshot)
            .filter(
                PlayerSnapshot.player_id == player.id,
                PlayerSnapshot.season_id == season_id,
                PlayerSnapshot.match_day == match_day,
            )
            .first()
        )
        snap_data = dict(
            price=float(row.get("Qt.A", 0) or 0),
            price_initial=float(row.get("Qt.I", 0) or 0),
            price_diff=float(row.get("Diff.", 0) or 0),
            price_mantra=float(row.get("Qt.A M", 0) or 0),
            price_mantra_initial=float(row.get("Qt.I M", 0) or 0),
            price_mantra_diff=float(row.get("Diff.M", 0) or 0),
            fvm=float(row.get("FVM", 0) or 0),
            fvm_mantra=float(row.get("FVM M", 0) or 0),
        )
        if not snap:
            snap = PlayerSnapshot(
                player_id=player.id, season_id=season_id, match_day=match_day, **snap_data
            )
            db.add(snap)
        else:
            for k, v in snap_data.items():
                setattr(snap, k, v)

    db.commit()
    logger.info("sync_prices: created=%s updated=%s matchday=%s", created, updated, match_day)
    return {"ok": True, "created": created, "updated": updated, "match_day": match_day}


def sync_votes(db: Session, season_id: int, match_day: int | None = None) -> dict:
    """Download voti Excel and upsert PlayerMatchScore."""
    day = match_day or fanta_client.get_last_matchday()
    path = fanta_client.download_votes(day)
    if not path:
        return {"ok": False, "message": "Download votes failed"}

    df = pd.read_excel(path, skiprows=4)
    if df.shape[1] == 0:
        # Nessuna giornata giocata ancora (es. stagione non iniziata): l'API
        # risponde 200 OK con un Excel senza dati utilizzabili.
        return {"ok": False, "message": f"Nessun voto disponibile per la giornata {day}"}

    # Solo righe con ID numerico
    df = df[df.iloc[:, 0].astype(str).str.isdigit()]

    saved = 0
    for _, row in df.iterrows():
        try:
            fanta_id = int(row.values[0])
            vote_val = row.values[5] if len(row.values) > 5 else None
            if vote_val == "sv" or pd.isna(vote_val):
                vote = None
            else:
                vote = float(vote_val)
        except Exception:
            continue

        player = db.query(Player).filter(Player.fanta_id == fanta_id).first()
        if not player:
            continue

        score = (
            db.query(PlayerMatchScore)
            .filter(
                PlayerMatchScore.player_id == player.id,
                PlayerMatchScore.season_id == season_id,
                PlayerMatchScore.match_day == day,
            )
            .first()
        )
        if not score:
            score = PlayerMatchScore(
                player_id=player.id, season_id=season_id, match_day=day, vote=vote
            )
            db.add(score)
        else:
            score.vote = vote
        saved += 1

    db.commit()
    return {"ok": True, "saved": saved, "match_day": day}
