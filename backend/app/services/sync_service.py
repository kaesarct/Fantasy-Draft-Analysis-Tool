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
from app.services.leghe_competition_sync import sync_competition_leghe_ids

import logging
logger = logging.getLogger(__name__)


def _best_effort_ensure_competitions(db: Session, season_id: int) -> None:
    """Crea/aggancia le Competition mancanti (es. UEFA, creata su
    leghe.fantacalcio.it solo a stagione inoltrata, a fine gironi Ciempions)
    come effetto collaterale delle sync di routine — cosi' non serve un
    passaggio manuale da Gestione Squadre ne' un "Carica da
    leghe.fantacalcio.it" dedicato. Un errore qui (login leghe fallito,
    competizione ancora assente) non deve mai far fallire la sync
    principale, che e' il suo scopo primario."""
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        return
    try:
        sync_competition_leghe_ids(db, season)
    except Exception as e:
        logger.warning("Aggancio/creazione Competition fallito (non bloccante): %s", e)


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

    _best_effort_ensure_competitions(db, season_id)

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

    # Solo righe con ID numerico (esclude le righe di intestazione ripetute
    # per ogni squadra: "Cod./Ruolo/Nome/Voto/Gf/Gs/Rp/Rs/Rf/Au/Amm/Esp/Ass").
    df = df[df.iloc[:, 0].astype(str).str.isdigit()]

    def _int(v) -> int:
        return int(v) if pd.notna(v) else 0

    saved = 0
    for _, row in df.iterrows():
        try:
            fanta_id = int(row.values[0])
            vote_val = row.values[3]
            if pd.isna(vote_val) or str(vote_val).strip().lower() == "sv":
                vote = None
            else:
                # Un voto provvisorio (calcolato con una formula statistica in
                # attesa della pagella ufficiale) e' segnato con un asterisco
                # finale, es. "6*": il numero resta comunque utilizzabile.
                vote = float(str(vote_val).rstrip("*"))
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
        score_data = dict(
            vote=vote,
            goals=_int(row.values[4]),           # Gf
            own_goals=_int(row.values[9]),        # Au
            yellow_cards=_int(row.values[10]),    # Amm
            red_cards=_int(row.values[11]),       # Esp
            assists=_int(row.values[12]),         # Ass
            penalties_saved=_int(row.values[6]),  # Rp
            penalties_missed=_int(row.values[7]), # Rs
        )
        if not score:
            score = PlayerMatchScore(player_id=player.id, season_id=season_id, match_day=day, **score_data)
            db.add(score)
        else:
            for k, v in score_data.items():
                setattr(score, k, v)
        saved += 1

    db.commit()

    _best_effort_ensure_competitions(db, season_id)

    return {"ok": True, "saved": saved, "match_day": day}


def _match_player_id(db: Session, player_name: str) -> int | None:
    """Match esatto case-insensitive su Player.name. Se ambiguo (es. una riga
    storica senza fanta_id e una reale dall'ultima sincronizzazione quotazioni),
    preferisce l'unica con fanta_id impostato; altrimenti None (niente scelte
    arbitrarie tra piu' giocatori realmente distinti)."""
    matches = db.query(Player).filter(Player.name.ilike(player_name)).all()
    if len(matches) == 1:
        return matches[0].id
    with_fanta_id = [p for p in matches if p.fanta_id is not None]
    if len(with_fanta_id) == 1:
        return with_fanta_id[0].id
    return None


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
                logo_url=entry.get("logo_url"),
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
            report.logo_url = entry.get("logo_url")
            report.last_updated_at = now
            report.last_seen_at = now
            db.add(SerieAInjuryDescription(
                report_id=report.id, description=entry["description"], recorded_at=now,
            ))
            updated += 1
        else:
            report.logo_url = entry.get("logo_url")
            report.last_seen_at = now
            unchanged += 1

        # Ritenta il collegamento se non risolto in precedenza (es. il match
        # e' diventato univoco dopo una sincronizzazione quotazioni piu' recente).
        if report.player_id is None:
            report.player_id = _match_player_id(db, report.player_name)

    db.commit()
    return {"ok": True, "created": created, "updated": updated, "unchanged": unchanged, "archived": archived}
