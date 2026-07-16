"""Import storico stats/quotazioni per stagione da fantacalcio.it.

Il season_code fantacalcio corrisponde a Season.year_start - 2005. Gli import
gia' eseguiti sono tracciati in ImportedSeasonData e non vengono ripetuti,
salvo force=True.
"""
import csv
import io
import re
import tempfile
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.models.season import Season
from app.models.season_data import ImportedSeasonData, PlayerSeasonStat, PlayerSeasonPrice, PlayerSeasonVote
from app.services.fanta_client import fanta_client

import logging
logger = logging.getLogger(__name__)

MAX_MATCH_DAY = 38

VOTES_COLUMNS = [
    "match_day", "role", "player_name", "team", "vote", "goals_scored",
    "goals_conceded", "penalties_saved", "penalties_scored", "penalties_missed",
    "own_goals", "yellow_cards", "red_cards", "assists",
]

SEASON_BASE_YEAR = 2005

_STATS_COLUMNS = {
    "role": "R",
    "player_name": "Nome",
    "team": "Squadra",
    "matches_played": "Pv",
    "average_vote": "Mv",
    "fantasy_average": "Fm",
    "goals_scored": "Gf",
    "goals_conceded": "Gs",
    "penalties_saved": "Rp",
    "penalties_scored": "Rc",
    "penalties_missed": "R-",
    "assists": "Ass",
    "yellow_cards": "Amm",
    "red_cards": "Esp",
    "own_goals": "Au",
}

_PRICES_COLUMNS = {
    "role": "R",
    "secondary_role": "RM",
    "player_name": "Nome",
    "team": "Squadra",
    "market_value_a": "Qt.A",
    "market_value_i": "Qt.I",
    "difference": "Diff.",
    "market_value_a_m": "Qt.A M",
    "market_value_i_m": "Qt.I M",
    "difference_m": "Diff.M",
    "fvm": "FVM",
    "fvm_m": "FVM M",
}

DATA_TYPE_CONFIG = {
    "stats": {
        "download": fanta_client.download_stats_excel,
        "model": PlayerSeasonStat,
        "columns": _STATS_COLUMNS,
    },
    "prices": {
        "download": fanta_client.download_prices_excel,
        "model": PlayerSeasonPrice,
        "columns": _PRICES_COLUMNS,
    },
}


def _import_excel(db: Session, model, columns: dict, file_path: str, season_id: int) -> int:
    df = pd.read_excel(file_path, skiprows=1)
    count = 0
    for _, row in df.iterrows():
        try:
            fanta_player_id = int(row["Id"])
        except (ValueError, KeyError, TypeError):
            continue

        values = {}
        for field, excel_col in columns.items():
            value = row.get(excel_col)
            if pd.isna(value):
                values[field] = None
            else:
                # I tipi scalari numpy non sono adattabili da psycopg2.
                values[field] = value.item() if hasattr(value, "item") else value

        record = (
            db.query(model)
            .filter(
                model.season_id == season_id,
                model.fanta_player_id == fanta_player_id,
            )
            .first()
        )
        if not record:
            db.add(model(season_id=season_id, fanta_player_id=fanta_player_id, **values))
            # autoflush e' disattivato: senza flush un Id duplicato nel file
            # non verrebbe visto dalla query e violerebbe il vincolo unico.
            db.flush()
        else:
            for field, value in values.items():
                setattr(record, field, value)
        count += 1
    return count


def import_season_data(db: Session, season_id: int, data_type: str, force: bool = False) -> dict:
    """Orchestrazione: cache-check -> download in tempdir -> parse+upsert -> marcatura."""
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        return {"ok": False, "message": f"Stagione {season_id} non trovata"}

    config = DATA_TYPE_CONFIG[data_type]

    already = (
        db.query(ImportedSeasonData)
        .filter(
            ImportedSeasonData.season_id == season_id,
            ImportedSeasonData.data_type == data_type,
        )
        .first()
    )
    if already and not force:
        return {"ok": True, "imported": False, "message": "Dati gia' importati (usa force per reimportare)"}

    season_code = season.year_start - SEASON_BASE_YEAR
    with tempfile.TemporaryDirectory() as tmp_dir:
        file_path = config["download"](season_code, tmp_dir)
        if not file_path:
            return {"ok": False, "message": "Errore durante il download del file da Fantacalcio"}

        try:
            rows = _import_excel(db, config["model"], config["columns"], file_path, season_id)
        except Exception as e:
            db.rollback()
            logger.error(
                "Errore parsing/import %s per stagione %s: %s", data_type, season.label, e
            )
            return {"ok": False, "message": "Errore durante l'elaborazione del file scaricato"}

    if rows == 0:
        db.rollback()
        return {"ok": False, "message": "Nessun dato trovato per questa stagione"}

    if already:
        already.imported_at = datetime.utcnow()
    else:
        db.add(ImportedSeasonData(season_id=season_id, data_type=data_type))
    db.commit()
    logger.info("Importate %s righe %s per stagione %s", rows, data_type, season.label)
    return {"ok": True, "imported": True, "rows": rows, "season": season.label}


def _parse_vote(value) -> float | None:
    """Il voto puo' comparire come stringa con suffisso (es. "6*"): si tollera
    invece di scartare l'intera riga (a differenza di sync_service.sync_votes)."""
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() == "sv":
        return None
    match = re.match(r"[\d.]+", text)
    return float(match.group()) if match else None


def _parse_votes_dataframe(file_path: str) -> list[dict]:
    """Excel voti per giornata: righe raggruppate per squadra (riga con solo il
    nome squadra, poi sotto-header "Cod. Ruolo Nome Voto Gf Gs Rp Rs Rf Au Amm
    Esp Ass", poi le righe giocatore). La squadra si ricava per forward-fill
    dall'ultima riga-intestazione vista."""
    df = pd.read_excel(file_path, header=None, skiprows=4)
    if df.shape[1] == 0:
        return []

    def _num(v):
        if pd.isna(v):
            return None
        return v.item() if hasattr(v, "item") else v

    rows = []
    current_team = None
    for _, r in df.iterrows():
        values = r.values
        col0 = values[0]
        col0_str = "" if pd.isna(col0) else str(col0).strip()
        rest_na = all(pd.isna(x) for x in values[1:])

        if isinstance(col0, str) and rest_na and col0_str and col0_str != "Cod.":
            current_team = col0_str
            continue
        if not col0_str.isdigit():
            continue

        role = values[1] if not pd.isna(values[1]) else None
        if role not in ("P", "D", "C", "A"):
            # Il foglio include anche la riga dell'allenatore (ruolo "ALL"):
            # non e' un giocatore, non appartiene allo storico voti giocatori.
            continue

        rows.append({
            "fanta_player_id": int(col0_str),
            "role": role,
            "player_name": values[2] if not pd.isna(values[2]) else None,
            "team": current_team,
            "vote": _parse_vote(values[3]),
            "goals_scored": _num(values[4]),
            "goals_conceded": _num(values[5]),
            "penalties_saved": _num(values[6]),
            "penalties_scored": _num(values[7]),
            "penalties_missed": _num(values[8]),
            "own_goals": _num(values[9]),
            "yellow_cards": _num(values[10]),
            "red_cards": _num(values[11]),
            "assists": _num(values[12]),
        })
    return rows


def import_season_votes(db: Session, season_id: int, force: bool = False) -> dict:
    """Come import_season_data, ma i voti sono pubblicati per giornata: cicla
    fino a MAX_MATCH_DAY download separati, saltando le giornate senza dati."""
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        return {"ok": False, "message": f"Stagione {season_id} non trovata"}

    already = (
        db.query(ImportedSeasonData)
        .filter(
            ImportedSeasonData.season_id == season_id,
            ImportedSeasonData.data_type == "votes",
        )
        .first()
    )
    if already and not force:
        return {"ok": True, "imported": False, "message": "Dati gia' importati (usa force per reimportare)"}

    season_code = season.year_start - SEASON_BASE_YEAR
    total_rows = 0
    skipped_match_days = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        for match_day in range(1, MAX_MATCH_DAY + 1):
            file_path = fanta_client.download_votes_excel(season_code, match_day, tmp_dir)
            if not file_path:
                skipped_match_days.append(match_day)
                continue

            try:
                rows = _parse_votes_dataframe(file_path)
            except Exception as e:
                db.rollback()
                logger.error(
                    "Errore parsing voti giornata %s stagione %s: %s", match_day, season.label, e
                )
                skipped_match_days.append(match_day)
                continue

            if not rows:
                skipped_match_days.append(match_day)
                continue

            for row in rows:
                record = (
                    db.query(PlayerSeasonVote)
                    .filter(
                        PlayerSeasonVote.season_id == season_id,
                        PlayerSeasonVote.fanta_player_id == row["fanta_player_id"],
                        PlayerSeasonVote.match_day == match_day,
                    )
                    .first()
                )
                if not record:
                    db.add(PlayerSeasonVote(season_id=season_id, match_day=match_day, **row))
                    db.flush()
                else:
                    for field, value in row.items():
                        if field != "fanta_player_id":
                            setattr(record, field, value)
            total_rows += len(rows)

    if total_rows == 0:
        db.rollback()
        return {"ok": False, "message": "Nessun dato voti trovato per questa stagione"}

    if already:
        already.imported_at = datetime.utcnow()
    else:
        db.add(ImportedSeasonData(season_id=season_id, data_type="votes"))
    db.commit()
    logger.info(
        "Importate %s righe voti per stagione %s (giornate saltate: %s)",
        total_rows, season.label, skipped_match_days,
    )
    return {
        "ok": True, "imported": True, "rows": total_rows,
        "season": season.label, "skipped_match_days": skipped_match_days,
    }


def build_csv(db: Session, season_id: int, data_type: str) -> io.BytesIO:
    """CSV in memoria (nessun file su disco) con tutte le righe della stagione."""
    model = DATA_TYPE_CONFIG[data_type]["model"]
    fieldnames = ["season_id", "fanta_player_id", *DATA_TYPE_CONFIG[data_type]["columns"].keys()]

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for record in db.query(model).filter(model.season_id == season_id).all():
        writer.writerow({field: getattr(record, field) for field in fieldnames})

    byte_buffer = io.BytesIO(buffer.getvalue().encode("utf-8"))
    byte_buffer.seek(0)
    return byte_buffer


def build_votes_csv(db: Session, season_id: int, match_day: int | None = None) -> io.BytesIO:
    """Come build_csv, ma per PlayerSeasonVote: opzionalmente filtrato per giornata."""
    fieldnames = ["season_id", "fanta_player_id", *VOTES_COLUMNS]

    query = db.query(PlayerSeasonVote).filter(PlayerSeasonVote.season_id == season_id)
    if match_day is not None:
        query = query.filter(PlayerSeasonVote.match_day == match_day)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for record in query.order_by(PlayerSeasonVote.match_day, PlayerSeasonVote.player_name).all():
        writer.writerow({field: getattr(record, field) for field in fieldnames})

    byte_buffer = io.BytesIO(buffer.getvalue().encode("utf-8"))
    byte_buffer.seek(0)
    return byte_buffer
