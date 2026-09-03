import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    os.makedirs(settings.download_folder, exist_ok=True)
    os.makedirs(settings.upload_folder, exist_ok=True)
    from app.models import (  # noqa: F401 — import all models so Base knows them
        player,
        serie_a_team,
        fanta_allenatore,
        fanta_team,
        season,
        competition,
        injury,
        serie_a_injury,
        lineup,
        lineup_import,
        season_data,
        trade,
        auction,
        player_merge,
    )
    Base.metadata.create_all(bind=engine)
    _migrate_add_lineage_id()
    _migrate_add_season_disclaimer()
    _migrate_add_trade_roster_ids()
    _migrate_add_roster_role()
    _migrate_add_leghe_id()
    _migrate_add_leghe_team_id()
    _migrate_widen_secondary_role()
    _migrate_widen_price_secondary_role()
    # L'ordine conta: normalizzare prima uniforma le eventuali coppie duplicate
    # che differiscono solo per maiuscole/minuscole (es. "ALBIOL" vs "Albiol"),
    # cosi' la deduplica le riconosce come lo stesso nome; il backfill usa il
    # nome gia' normalizzato per il match e va prima della deduplica per
    # sicurezza (nel caso rendesse due righe eleggibili per merge).
    _migrate_normalize_player_names()
    _migrate_backfill_fanta_id()
    _migrate_backfill_unknown_role()
    _migrate_dedupe_players()
    _migrate_merge_duplicate_teams()
    _migrate_seed_season_awards()


def _migrate_add_lineage_id():
    # create_all crea la nuova tabella fanta_team_lineages da se', ma non
    # altera fanta_teams (tabella esistente): la colonna va aggiunta a mano.
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE fanta_teams ADD COLUMN IF NOT EXISTS lineage_id "
            "INTEGER REFERENCES fanta_team_lineages(id)"
        ))


def _migrate_add_season_disclaimer():
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE seasons ADD COLUMN IF NOT EXISTS disclaimer TEXT"
        ))


def _migrate_add_trade_roster_ids():
    # create_all crea la tabella trade_items da se' se non esiste, ma non
    # aggiunge colonne a una tabella gia' esistente: va fatto a mano.
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE trade_items ADD COLUMN IF NOT EXISTS old_roster_id "
            "INTEGER REFERENCES fanta_rosters(id)"
        ))
        conn.execute(text(
            "ALTER TABLE trade_items ADD COLUMN IF NOT EXISTS new_roster_id "
            "INTEGER REFERENCES fanta_rosters(id)"
        ))


def _migrate_add_roster_role():
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE fanta_rosters ADD COLUMN IF NOT EXISTS role VARCHAR(2)"
        ))


def _migrate_add_leghe_id():
    # create_all non altera tabelle esistenti: la colonna va aggiunta a mano
    # sui DB gia' creati (idempotente grazie a IF NOT EXISTS).
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE competitions ADD COLUMN IF NOT EXISTS leghe_id INTEGER"
        ))


def _migrate_add_leghe_team_id():
    # create_all non altera tabelle esistenti: la colonna va aggiunta a mano
    # sui DB gia' creati (idempotente grazie a IF NOT EXISTS). L'indice unico
    # e' parziale (solo valori non-null) per permettere piu' squadre non
    # ancora collegate senza violare l'unicita'.
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE fanta_teams ADD COLUMN IF NOT EXISTS leghe_team_id INTEGER"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_fanta_team_leghe_team_id "
            "ON fanta_teams(leghe_team_id) WHERE leghe_team_id IS NOT NULL"
        ))


def _migrate_widen_secondary_role():
    # create_all non altera tabelle esistenti: il campo puo' contenere una lista
    # di ruoli Mantra separata da ";" (es. "B;Dd;E"), va allargata a mano sui DB
    # gia' creati con il VARCHAR(2) originale.
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE players ALTER COLUMN secondary_role TYPE VARCHAR(50)"
        ))


def _migrate_widen_price_secondary_role():
    # Il file quotazioni 2015-16 contiene liste ruoli Mantra piu' lunghe di
    # 10 caratteri (es. "Dd;Ds;Cd;Cs"): con VARCHAR(10) l'import falliva per
    # l'intera stagione (StringDataRightTruncation), lasciando 0 quotazioni.
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE player_season_prices ALTER COLUMN secondary_role TYPE VARCHAR(50)"
        ))


def _migrate_dedupe_players():
    """L'import storico rose (backend/etl/import_history.py) crea Player per
    nome, senza fanta_id: quando il sync live quotazioni crea poi lo stesso
    giocatore per fanta_id, restano due righe distinte per la stessa persona
    (una con fanta_id NULL, una valorizzata). Ricollega lo storico rose
    (l'unico dato reale sulla riga senza fanta_id, verificato non esserci
    altrove) alla riga con fanta_id ed elimina il duplicato. Idempotente:
    se non ci sono piu' duplicati non fa nulla."""
    from sqlalchemy import func
    from app.models.player import Player, PlayerArchiveSeasonStat
    from app.models.player_merge import PlayerMergeDismissal
    from app.models.fanta_team import FantaRoster

    db = SessionLocal()
    try:
        duplicated_names = [
            row[0] for row in
            db.query(Player.name).group_by(Player.name).having(func.count() > 1).all()
        ]
        if not duplicated_names:
            return

        merged_players = 0
        relinked_rosters = 0
        for name in duplicated_names:
            candidates = db.query(Player).filter(Player.name == name).all()
            without_fanta_id = [p for p in candidates if p.fanta_id is None]
            with_fanta_id = [p for p in candidates if p.fanta_id is not None]
            if len(without_fanta_id) != 1 or len(with_fanta_id) != 1:
                # Non il pattern atteso (1 senza + 1 con fanta_id): non tocco
                # nulla, va risolto a mano.
                continue

            old_player = without_fanta_id[0]
            keep_player = with_fanta_id[0]
            if old_player.role and keep_player.role and old_player.role != keep_player.role:
                # Ruoli incompatibili (es. P/D): quasi certo che siano due
                # persone reali diverse con lo stesso nome, non un
                # giocatore storico poi arrivato al sync live — non unire
                # (rispetta anche una eventuale separazione fatta a mano
                # via /player-merge/split-role).
                continue
            low, high = min(old_player.id, keep_player.id), max(old_player.id, keep_player.id)
            if db.query(PlayerMergeDismissal).filter(
                PlayerMergeDismissal.player_id_low == low,
                PlayerMergeDismissal.player_id_high == high,
            ).first():
                # L'admin ha rifiutato esplicitamente questa coppia (es. dopo
                # una separazione manuale di due persone con lo stesso nome
                # e lo stesso ruolo): non riproporla mai piu' come duplicato.
                continue

            rosters = db.query(FantaRoster).filter(FantaRoster.player_id == old_player.id).all()
            for roster in rosters:
                conflict = db.query(FantaRoster).filter(
                    FantaRoster.player_id == keep_player.id,
                    FantaRoster.fanta_team_id == roster.fanta_team_id,
                    FantaRoster.season_id == roster.season_id,
                ).first()
                if conflict:
                    # Il giocatore risulta gia' in quella rosa sull'altra riga:
                    # non sovrascrivo, lascio la riga vecchia per non perdere dati.
                    continue
                roster.player_id = keep_player.id
                relinked_rosters += 1

            for archive_row in db.query(PlayerArchiveSeasonStat).filter(
                PlayerArchiveSeasonStat.player_id == old_player.id
            ).all():
                conflict = db.query(PlayerArchiveSeasonStat).filter(
                    PlayerArchiveSeasonStat.player_id == keep_player.id,
                    PlayerArchiveSeasonStat.season_id == archive_row.season_id,
                    PlayerArchiveSeasonStat.team_name == archive_row.team_name,
                ).first()
                if conflict:
                    # Stessa stagione/squadra gia' presente sull'altra riga:
                    # lascio quella vecchia com'e', non sovrascrivo.
                    continue
                archive_row.player_id = keep_player.id

            db.flush()
            remaining = (
                db.query(FantaRoster).filter(FantaRoster.player_id == old_player.id).count()
                + db.query(PlayerArchiveSeasonStat).filter(PlayerArchiveSeasonStat.player_id == old_player.id).count()
            )
            if remaining == 0:
                db.delete(old_player)
                merged_players += 1

        db.commit()
        if merged_players:
            logger.info(
                "Deduplica giocatori: %s righe duplicate rimosse, %s rose ricollegate",
                merged_players, relinked_rosters,
            )
    finally:
        db.close()


def _migrate_merge_duplicate_teams():
    """La stagione 2023-24 ha creato due righe FantaTeam per 6 squadre reali:
    il file rose CSV (_import_rose_csv_2023) e i file classifiche/calendario
    usano un nome leggermente diverso (apostrofi, trattini, spazi, refusi)
    per la stessa squadra, e norm() in import_history.py normalizza solo
    spazi/maiuscole. Risultato: una riga ha la rosa (25 giocatori dall'asta)
    e 0 partite/classifiche, l'altra ha partite/classifiche e 0 rose —
    verificato a mano, non e' un'euristica generica. Da qui in avanti
    TEAM_ALIASES previene la ricomparsa in un futuro re-import da zero;
    questa migrazione unisce una tantum i dati gia' divisi in DB.
    Idempotente: salta le coppie gia' unite (remove_id non esiste piu')."""
    from app.models.fanta_team import FantaTeam, FantaRoster, FantaTeamCoach, FantaTeamLogo
    from app.models.competition import MatchResult, CompetitionStanding

    # (keep_id, remove_id): keep = riga con partite/classifica (nome canonico
    # scelto per coerenza con le altre stagioni; per "SER" senza precedente,
    # confermato dall'utente).
    TEAM_MERGES = [
        (141, 147),  # bestplayerscrew <- Best Player Crew
        (125, 150),  # Facoceris Karma <- Facoceri's Karma
        (126, 151),  # Real Muraturi <- Real Muratori
        (134, 153),  # AL-FIZZY <- AL FIZZY
        (136, 154),  # Nikafootballclub <- Nika football club
        (135, 152),  # SER - otto <- SER
    ]

    db = SessionLocal()
    try:
        merged = 0
        for keep_id, remove_id in TEAM_MERGES:
            remove_team = db.query(FantaTeam).filter(FantaTeam.id == remove_id).first()
            if not remove_team:
                continue

            db.query(FantaRoster).filter(FantaRoster.fanta_team_id == remove_id).update(
                {"fanta_team_id": keep_id}
            )
            db.flush()

            still_referenced = (
                db.query(FantaRoster).filter(FantaRoster.fanta_team_id == remove_id).first()
                or db.query(MatchResult).filter(
                    (MatchResult.fanta_team_home_id == remove_id)
                    | (MatchResult.fanta_team_away_id == remove_id)
                ).first()
                or db.query(CompetitionStanding).filter(CompetitionStanding.fanta_team_id == remove_id).first()
                or db.query(FantaTeamCoach).filter(FantaTeamCoach.fanta_team_id == remove_id).first()
                or db.query(FantaTeamLogo).filter(FantaTeamLogo.fanta_team_id == remove_id).first()
            )
            if still_referenced:
                logger.warning(
                    "Merge squadra %s -> %s saltato: restano riferimenti non ricollegati",
                    remove_id, keep_id,
                )
                continue

            db.delete(remove_team)
            merged += 1

        db.commit()
        if merged:
            logger.info("Unite %s squadre duplicate (stagione 2023-24)", merged)
    finally:
        db.close()


def _migrate_normalize_player_names():
    """Alcuni giocatori (import storico) hanno il nome tutto maiuscolo
    (es. "ACERBI") invece del formato stile fantacalcio.it (es. "Acerbi",
    "De Gea", "N'Dicka"). Uniforma con str.title(), verificato a mano sui
    casi con apostrofi/trattini/nomi doppi. Idempotente."""
    from app.models.player import Player

    db = SessionLocal()
    try:
        normalized = 0
        for p in db.query(Player).all():
            if p.name == p.name.upper() and p.name != p.name.title():
                p.name = p.name.title()
                normalized += 1
        db.commit()
        if normalized:
            logger.info("Normalizzati %s nomi giocatore da MAIUSCOLO a Title Case", normalized)
    finally:
        db.close()


def _normalize_historical_name(name: str) -> str:
    """Rumore tipografico comune nei file storici (spazi finali, maiuscole
    incoerenti, punto finale su nomi abbreviati come "F."): normalizza per
    il match esatto in _migrate_backfill_fanta_id, senza introdurre
    ambiguita' (non e' un'euristica fuzzy, solo pulizia di formattazione)."""
    n = " ".join(name.split()).lower()
    return n[:-1] if n.endswith(".") else n


def _migrate_backfill_fanta_id():
    """Alcuni Player creati dall'import storico rose non sono mai apparsi
    nel sync live quotazioni (mai collegati a fanta_id, il sync live collega
    solo per fanta_id, mai per nome) pur avendo statistiche/quotazioni/voti
    storici identificabili per nome. Collega fanta_id solo quando il nome
    normalizzato ha un'unica corrispondenza non ambigua nelle tabelle
    storiche e quel fanta_id non e' gia' usato da un'altra riga Player.
    Idempotente."""
    from app.models.player import Player
    from app.models.season_data import PlayerSeasonPrice, PlayerSeasonStat, PlayerSeasonVote

    db = SessionLocal()
    try:
        used_fanta_ids = {
            row[0] for row in db.query(Player.fanta_id).filter(Player.fanta_id.isnot(None)).all()
        }

        name_to_fanta_ids: dict[str, set[int]] = {}
        for model in (PlayerSeasonPrice, PlayerSeasonStat, PlayerSeasonVote):
            for name, fanta_id in db.query(model.player_name, model.fanta_player_id).distinct().all():
                name_to_fanta_ids.setdefault(_normalize_historical_name(name), set()).add(fanta_id)

        backfilled = 0
        for p in db.query(Player).filter(Player.fanta_id.is_(None)).all():
            candidates = name_to_fanta_ids.get(_normalize_historical_name(p.name))
            if not candidates or len(candidates) != 1:
                continue
            fanta_id = next(iter(candidates))
            if fanta_id in used_fanta_ids:
                continue
            p.fanta_id = fanta_id
            used_fanta_ids.add(fanta_id)
            backfilled += 1

        db.commit()
        if backfilled:
            logger.info("Backfill fanta_id: %s giocatori collegati allo storico", backfilled)
    finally:
        db.close()


_SEASON_AWARDS_HISTORY = [
    # (season_label, goku_team, goku_score, goku_detail, oscar_team, oscar_score, oscar_detail)
    ("2025-26", "Hertavernello", 94.0, "17ª giornata", "Pumas", 52.5, "36ª giornata"),
    ("2024-25", "CSKA La Rissa", 93.5, "1ª giornata", "Birra Real", 55.5, "4ª giornata"),
    ("2023-24", "Carrapipi", 100.5, "1ª giornata", "Marlena", 43.5, "semifinale andata Ciempions"),
    ("2022-23", "Deportivo la Carogna", 96.0, "1ª giornata", "Deportivo la Carogna", 49.5, "38ª giornata"),
    ("2021-22", "Pettini pe i Tignusi", 94.0, "26ª giornata", "Pumas", 57.0, "24ª giornata"),
    ("2020-21", "Herta Vernello", 105.5, "32ª giornata", "Fragolina-XL", 53.0, "21ª giornata"),
    ("2019-20", "Pumas", 100.5, "35ª giornata", "Bestplayerscrew", 56.5, "13ª giornata"),
    ("2018-19", "Sao Paulo", 95.5, "18ª giornata", "Sao Paulo", 48.5, "11ª giornata"),
]


def _migrate_seed_season_awards():
    """Seed una tantum dello storico Premio Goku/Oscar (2018-19..2025-26),
    fornito manualmente dall'utente — non ricavabile dai dati già in DB.
    Idempotente: salta le stagioni già presenti."""
    from app.models.competition import SeasonAward, AwardType

    db = SessionLocal()
    try:
        existing = {row[0] for row in db.query(SeasonAward.season_label).distinct().all()}
        seeded = 0
        for season_label, goku_team, goku_score, goku_detail, oscar_team, oscar_score, oscar_detail in _SEASON_AWARDS_HISTORY:
            if season_label in existing:
                continue
            db.add(SeasonAward(
                season_label=season_label, award_type=AwardType.GOKU,
                team_name=goku_team, score=goku_score, detail=goku_detail,
            ))
            db.add(SeasonAward(
                season_label=season_label, award_type=AwardType.OSCAR,
                team_name=oscar_team, score=oscar_score, detail=oscar_detail,
            ))
            seeded += 1
        db.commit()
        if seeded:
            logger.info("Seed storico Premio Goku/Oscar: %s stagioni inserite", seeded)
    finally:
        db.close()


def _migrate_backfill_unknown_role():
    """L'import storico rose 2020-21 da PDF non aveva la colonna ruolo: i
    Player creati da li' hanno role='?' come placeholder. Backfill dal ruolo
    piu' recente disponibile in player_season_stats/prices per lo stesso
    fanta_id. Idempotente."""
    from app.models.player import Player
    from app.models.season_data import PlayerSeasonStat, PlayerSeasonPrice

    db = SessionLocal()
    try:
        role_by_fanta_id_season: dict[int, list] = {}
        for model in (PlayerSeasonStat, PlayerSeasonPrice):
            for fanta_id, season_id, role in (
                db.query(model.fanta_player_id, model.season_id, model.role)
                .filter(model.role.isnot(None))
                .all()
            ):
                role_by_fanta_id_season.setdefault(fanta_id, []).append((season_id, role))

        backfilled = 0
        for p in db.query(Player).filter(Player.role == "?").all():
            if not p.fanta_id:
                continue
            entries = role_by_fanta_id_season.get(p.fanta_id)
            if not entries:
                continue
            # Il ruolo piu' recente (stagione piu' alta) come migliore stima
            # del ruolo "attuale" del giocatore.
            p.role = max(entries, key=lambda e: e[0])[1]
            backfilled += 1

        db.commit()
        if backfilled:
            logger.info("Backfill ruolo: %s giocatori con ruolo '?' risolti dallo storico", backfilled)
    finally:
        db.close()
