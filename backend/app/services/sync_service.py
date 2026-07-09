"""Sync service — orchestrates data download and DB update."""
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
from app.services.fanta_client import fanta_client
from app.services.seriea_scraper import get_serie_a_injuries
from app.models.player import Player, PlayerSnapshot, PlayerMatchScore
from app.models.serie_a_team import SerieATeam
from app.models.serie_a_injury import SerieAInjuryReport, SerieAInjuryArchive, SerieAInjuryDescription
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


def _match_player_id(db: Session, player_name: str) -> int | None:
    """Match esatto case-insensitive su Player.name; None se 0 o >1 risultati."""
    matches = db.query(Player).filter(Player.name.ilike(player_name)).all()
    return matches[0].id if len(matches) == 1 else None


def sync_serie_a_injuries(db: Session) -> dict:
    """Scarica infortunati-serie-a e aggiorna report attivi / storico / archivio."""
    scraped = get_serie_a_injuries()
    if not scraped:
        return {"ok": False, "message": "Nessun dato ricevuto da fantacalcio.it"}

    now = datetime.utcnow()
    seen_keys = {(s["team_name"], s["player_name"]) for s in scraped}

    # Archivia i report non piu' presenti sulla pagina (= rientrati)
    archived = 0
    for report in db.query(SerieAInjuryReport).all():
        if (report.team_name, report.player_name) in seen_keys:
            continue
        archive = SerieAInjuryArchive(
            player_name=report.player_name,
            team_name=report.team_name,
            player_id=report.player_id,
            last_description=report.description,
            started_at=report.first_seen_at,
            ended_at=now,
        )
        db.add(archive)
        db.flush()
        db.query(SerieAInjuryDescription).filter(
            SerieAInjuryDescription.report_id == report.id
        ).update({"report_id": None, "archive_id": archive.id})
        db.delete(report)
        archived += 1

    created = updated = unchanged = 0
    for entry in scraped:
        report = db.query(SerieAInjuryReport).filter(
            SerieAInjuryReport.team_name == entry["team_name"],
            SerieAInjuryReport.player_name == entry["player_name"],
        ).first()

        if not report:
            report = SerieAInjuryReport(
                player_name=entry["player_name"],
                team_name=entry["team_name"],
                player_id=_match_player_id(db, entry["player_name"]),
                description=entry["description"],
                first_seen_at=now,
                last_seen_at=now,
                last_updated_at=now,
            )
            db.add(report)
            db.flush()
            db.add(SerieAInjuryDescription(
                report_id=report.id, description=entry["description"], recorded_at=now,
            ))
            created += 1
        elif report.description != entry["description"]:
            report.description = entry["description"]
            report.last_updated_at = now
            report.last_seen_at = now
            db.add(SerieAInjuryDescription(
                report_id=report.id, description=entry["description"], recorded_at=now,
            ))
            updated += 1
        else:
            report.last_seen_at = now
            unchanged += 1

    db.commit()
    return {"ok": True, "created": created, "updated": updated, "unchanged": unchanged, "archived": archived}
