"""Import storico stats/quotazioni per stagione da fantacalcio.it.

Il season_code fantacalcio corrisponde a Season.year_start - 2005. Gli import
gia' eseguiti sono tracciati in ImportedSeasonData e non vengono ripetuti,
salvo force=True.
"""
import csv
import io
import tempfile
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.models.season import Season
from app.models.season_data import ImportedSeasonData, PlayerSeasonStat, PlayerSeasonPrice
from app.services.fanta_client import fanta_client

import logging
logger = logging.getLogger(__name__)

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
