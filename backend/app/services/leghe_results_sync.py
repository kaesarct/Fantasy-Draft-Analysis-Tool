"""Import calendario/risultati da leghe.fantacalcio.it in MatchResult.

Sostituisce, competizione per competizione, il ripiego di awards.py basato su
CompetitionStanding con dati reali: stesso formato Excel gia' interpretato da
etl/import_history.py per lo storico (regex duplicate qui, non importate — 4
righe stabili, evita di far dipendere app/ da uno script one-off in etl/)."""
import io
import re
import unicodedata

import pandas as pd
from sqlalchemy.orm import Session

from app.models.competition import (
    Competition, CompetitionGroup, CompetitionGroupTeam, CompetitionMatchday, CompetitionMatchdayScore,
    CompetitionPhase, MatchResult,
)
from app.models.fanta_team import FantaTeam, League
from app.models.season import Season
from app.services.competition_provisioning import MAIN_LEAGUE_TYPES, _ensure_league_and_competition
from app.services.leghe_client import LegheClient
from app.services.leghe_competition_sync import KNOWN_TYPES, NAME_MAP, ensure_competitions

GIORNATA_RE = re.compile(r"(\d+)ª\s+Giornata\s+lega", re.IGNORECASE)
SERIE_A_RE = re.compile(r"(\d+)ª\s+Giornata\s+serie\s+a", re.IGNORECASE)
LINEUP_TITLE_RE = re.compile(r"^(.+?)\s*·\s*Giornata\s+(\d+)$", re.IGNORECASE)
GOALS_RE = re.compile(r"^(\d+)\s*-\s*(\d+)$")
GIRONE_LETTER_RE = re.compile(r"^[A-Z]$")


def _name_key(name: str) -> str:
    """Chiave di confronto tollerante a accenti, maiuscole, spazi e punteggiatura:
    il nome nell'Excel puo' differire da quello dell'API teams per rumore tipografico."""
    stripped = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    return "".join(c for c in stripped.casefold() if c.isalnum())


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def _phase_from_label(text: str) -> CompetitionPhase | None:
    s = text.strip().casefold()
    if "giron" in s:
        return CompetitionPhase.GROUP
    if "ottavi" in s:
        return CompetitionPhase.ROUND_OF_16
    if "quart" in s:
        return CompetitionPhase.QUARTER_FINAL
    if "semifinal" in s:
        return CompetitionPhase.SEMI_FINAL
    if "finale" in s:
        return CompetitionPhase.FINAL
    return None


def _serie_a_day_for_block(df, row: int, col: int) -> int | None:
    """Giornata di Serie A scritta sulla stessa riga, a destra dell'intestazione
    'Nª Giornata lega' e prima di quella del blocco successivo."""
    for c in range(col + 1, df.shape[1]):
        cell = df.iat[row, c]
        if not isinstance(cell, str):
            continue
        if GIORNATA_RE.search(cell):
            return None
        match = SERIE_A_RE.search(cell)
        if match:
            return int(match.group(1))
    return None


def _parse_block(df, start: int, col: int, match_day: int, phase: CompetitionPhase) -> list[dict]:
    """Partite di un singolo blocco 'Nª Giornata lega'. Nessuna scrittura DB:
    funzione pura, cosi' e' testabile senza sessione."""
    matches = []
    for idx in range(start, len(df)):
        home = df.iat[idx, col]
        if _is_blank(home) or (isinstance(home, str) and GIORNATA_RE.search(home)):
            break
        shift = 1 if isinstance(home, str) and GIRONE_LETTER_RE.match(home.strip()) else 0
        if col + shift + 4 >= df.shape[1]:
            break
        home = df.iat[idx, col + shift]
        away = df.iat[idx, col + shift + 3]
        goals = df.iat[idx, col + shift + 4]
        if _is_blank(home) or _is_blank(away):
            break

        goals_match = GOALS_RE.match(str(goals).strip()) if not _is_blank(goals) else None
        if not goals_match:
            # Nessun punteggio "N-M": giornata non ancora giocata (il caso
            # normale scaricando durante la stagione) — non un vero 0-0.
            continue

        score_home = None if _is_blank(df.iat[idx, col + shift + 1]) else float(df.iat[idx, col + shift + 1])
        score_away = None if _is_blank(df.iat[idx, col + shift + 2]) else float(df.iat[idx, col + shift + 2])
        matches.append({
            "match_day": match_day, "phase": phase,
            "home_name": str(home).strip(), "away_name": str(away).strip(),
            "score_home": score_home, "score_away": score_away,
            "goals_home": int(goals_match.group(1)), "goals_away": int(goals_match.group(2)),
        })
    return matches


def parse_calendar_excel(excel_bytes: bytes, is_cup: bool) -> list[dict]:
    """Tutte le partite gia' giocate in un Excel 'Calendario' di
    leghe.fantacalcio.it. `is_cup` decide la fase di default (GROUP per le
    coppe, REGULAR per i campionati a girone unico) prima del primo eventuale
    cambio fase rilevato nel file."""
    df = pd.read_excel(io.BytesIO(excel_bytes), header=None)
    matches = []
    current_phase = CompetitionPhase.GROUP if is_cup else CompetitionPhase.REGULAR
    for idx in range(len(df)):
        first = df.iat[idx, 0]
        if isinstance(first, str) and not GIORNATA_RE.search(first):
            label_phase = _phase_from_label(first)
            if label_phase:
                current_phase = label_phase
        for col in range(df.shape[1]):
            cell = df.iat[idx, col]
            if not isinstance(cell, str):
                continue
            match = GIORNATA_RE.search(cell)
            if not match:
                continue
            match_day = int(match.group(1))
            matches.extend(_parse_block(df, idx + 1, col, match_day, current_phase))
    return matches


def parse_serie_a_days(excel_bytes: bytes) -> dict[int, int]:
    """Giornata di lega -> giornata di Serie A, da tutte le intestazioni del
    Calendario, anche dei turni non ancora giocati."""
    df = pd.read_excel(io.BytesIO(excel_bytes), header=None)
    days: dict[int, int] = {}
    for idx in range(len(df)):
        for col in range(df.shape[1]):
            cell = df.iat[idx, col]
            match = GIORNATA_RE.search(cell) if isinstance(cell, str) else None
            serie_a_day = _serie_a_day_for_block(df, idx, col) if match else None
            if serie_a_day is not None:
                days[int(match.group(1))] = serie_a_day
    return days


def _save_matchdays(db: Session, comp: Competition, days: dict[int, int]) -> None:
    existing = {
        row.match_day: row
        for row in db.query(CompetitionMatchday).filter(CompetitionMatchday.competition_id == comp.id)
    }
    for match_day, serie_a_day in days.items():
        row = existing.get(match_day)
        if row:
            row.serie_a_day = serie_a_day
        else:
            db.add(CompetitionMatchday(competition_id=comp.id, match_day=match_day, serie_a_day=serie_a_day))


def parse_group_teams(excel_bytes: bytes) -> dict[str, set[str]]:
    """Composizione dei gironi letta dall'Excel 'Calendario': la lettera in
    prima colonna di ogni riga partita indica il girone. Considera anche le
    partite non ancora giocate, che _parse_block scarta: sono quelle a
    rivelare l'intero girone fin dalla prima giornata."""
    df = pd.read_excel(io.BytesIO(excel_bytes), header=None)
    groups: dict[str, set[str]] = {}
    for idx in range(len(df)):
        for col in range(df.shape[1]):
            cell = df.iat[idx, col]
            if not (isinstance(cell, str) and GIORNATA_RE.search(cell)):
                continue
            for row in range(idx + 1, len(df)):
                letter = df.iat[row, col]
                if not (isinstance(letter, str) and GIRONE_LETTER_RE.match(letter.strip())):
                    break
                if col + 4 >= df.shape[1]:
                    break
                home, away = df.iat[row, col + 1], df.iat[row, col + 4]
                if _is_blank(home) or _is_blank(away):
                    break
                groups.setdefault(letter.strip(), set()).update({str(home).strip(), str(away).strip()})
    return groups


def _sync_groups(db: Session, comp: Competition, groups: dict[str, set[str]], name_to_team: dict) -> None:
    """Crea i gironi della coppa e vi assegna le squadre; una squadra gia'
    iscritta ad altro girone della stessa competizione (es. "Girone Unico"
    creato a mano) viene spostata."""
    existing = {
        g.name: g for g in db.query(CompetitionGroup).filter(CompetitionGroup.competition_id == comp.id)
    }
    for letter, names in sorted(groups.items()):
        group = existing.get(f"Girone {letter}")
        if not group:
            group = CompetitionGroup(competition_id=comp.id, name=f"Girone {letter}")
            db.add(group)
            db.flush()
            existing[group.name] = group
        for name in names:
            team = name_to_team.get(_name_key(name))
            if not team:
                continue
            db.query(CompetitionGroupTeam).filter(
                CompetitionGroupTeam.fanta_team_id == team.id,
                CompetitionGroupTeam.group_id.in_([g.id for g in existing.values()]),
                CompetitionGroupTeam.group_id != group.id,
            ).delete(synchronize_session=False)
            already = db.query(CompetitionGroupTeam).filter(
                CompetitionGroupTeam.group_id == group.id, CompetitionGroupTeam.fanta_team_id == team.id
            ).first()
            if not already:
                db.add(CompetitionGroupTeam(group_id=group.id, fanta_team_id=team.id))


def _import_calendar(
    db: Session, comp: Competition, comp_type: str, excel_bytes: bytes, name_to_team: dict[str, FantaTeam],
    matched_ids: set[int] | None = None,
) -> dict:
    """Importa partite e (per le coppe) gironi da un Excel 'Calendario' gia'
    scaricato: usata sia dalla sync automatica sia dal caricamento manuale.
    `matched_ids` (facoltativo) raccoglie le squadre riconosciute nel file."""
    is_cup = comp_type not in {"GOLD", "BRONZE", "CARBON", "SILVER"}
    matches = parse_calendar_excel(excel_bytes, is_cup)
    if is_cup:
        groups = parse_group_teams(excel_bytes)
        if groups:
            _sync_groups(db, comp, groups, name_to_team)

    imported = updated = 0
    unmatched: set[str] = set()
    for m in matches:
        home_team = name_to_team.get(_name_key(m["home_name"]))
        away_team = name_to_team.get(_name_key(m["away_name"]))
        if matched_ids is not None:
            matched_ids.update(t.id for t in (home_team, away_team) if t)
        if not home_team:
            unmatched.add(m["home_name"])
        if not away_team:
            unmatched.add(m["away_name"])
        if not home_team or not away_team:
            continue

        existing = db.query(MatchResult).filter(
            MatchResult.competition_id == comp.id,
            MatchResult.match_day == m["match_day"],
            MatchResult.fanta_team_home_id == home_team.id,
            MatchResult.fanta_team_away_id == away_team.id,
        ).first()
        values = dict(
            score_home=m["score_home"], score_away=m["score_away"],
            goals_home=m["goals_home"], goals_away=m["goals_away"],
            phase=m["phase"],
        )
        if existing:
            for k, v in values.items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(MatchResult(
                competition_id=comp.id, match_day=m["match_day"],
                fanta_team_home_id=home_team.id, fanta_team_away_id=away_team.id,
                **values,
            ))
            imported += 1

    serie_a_days = parse_serie_a_days(excel_bytes)
    _save_matchdays(db, comp, serie_a_days)
    db.commit()
    return {
        "matches_imported": imported, "matches_updated": updated,
        "serie_a_days": len(serie_a_days), "teams_unmatched": sorted(unmatched),
    }


def parse_lineup_totals(df) -> dict[str, float]:
    """Totale di giornata di ogni squadra in un Excel 'Formazioni': nome della
    squadra sopra la cella 'Modulo', con 'Totale' e il valore sulla stessa riga.
    I blocchi sono affiancati su due colonne, tranne in Silver (uno sotto l'altro)."""
    totals: dict[str, float] = {}
    for row in range(1, len(df)):
        for col in range(df.shape[1] - 5):
            if df.iat[row, col] != "Modulo" or df.iat[row, col + 4] != "Totale":
                continue
            name = df.iat[row - 1, col]
            total = pd.to_numeric(df.iat[row, col + 5], errors="coerce")
            if not _is_blank(name) and not pd.isna(total):
                totals[str(name).strip()] = float(total)
    return totals


def _serie_a_day(db: Session, season: Season, comp_type: str, league_day: int) -> int | None:
    """Giornata di Serie A di un turno di lega/coppa, dal Calendario gia'
    importato. Silver non ha un Calendario: gioca gli stessi turni dei campionati."""
    types = list(MAIN_LEAGUE_TYPES) if comp_type == "SILVER" else [comp_type]
    row = (
        db.query(CompetitionMatchday.serie_a_day)
        .join(Competition, Competition.id == CompetitionMatchday.competition_id)
        .filter(
            Competition.season_id == season.id, Competition.type.in_(types),
            CompetitionMatchday.match_day == league_day,
        )
        .first()
    )
    return row[0] if row else None


def _rename_candidates(db: Session, season: Season, comp_type: str, matched_ids: set[int]) -> list[dict]:
    """Squadre della stagione che il file non ha riconosciuto: possibili
    destinatarie di una rinomina (il file porta un nome nuovo). Per i campionati
    solo quelle della stessa lega; per coppe e Silver tutte."""
    query = db.query(FantaTeam).filter(FantaTeam.season_id == season.id)
    if matched_ids:
        query = query.filter(FantaTeam.id.notin_(matched_ids))
    if comp_type in MAIN_LEAGUE_TYPES:
        query = query.join(League, League.id == FantaTeam.league_id).filter(League.level == comp_type)
    return [{"id": t.id, "name": t.name} for t in query.order_by(FantaTeam.name)]


def _import_lineups(
    db: Session, season: Season, comp: Competition, comp_type: str, league_day: int,
    totals: dict[str, float], name_to_team: dict[str, FantaTeam], matched_ids: set[int],
) -> dict:
    """Salva i totali in CompetitionMatchdayScore, sulla giornata di Serie A
    (la stessa numerazione della sync teamLineup). Senza corrispondenza nel
    Calendario rifiuta il file: nessuna stima del numero di giornata."""
    serie_a_day = _serie_a_day(db, season, comp_type, league_day)
    if serie_a_day is None:
        source = "Gold, Bronze o Carbon" if comp_type == "SILVER" else comp_type
        raise ValueError(
            f"{comp_type} giornata {league_day}: manca la corrispondenza con la giornata di Serie A, "
            f"carica prima il Calendario di {source}"
        )

    imported = updated = 0
    unmatched: list[str] = []
    for name, total in totals.items():
        team = name_to_team.get(_name_key(name))
        if not team:
            unmatched.append(name)
            continue
        matched_ids.add(team.id)
        existing = db.query(CompetitionMatchdayScore).filter(
            CompetitionMatchdayScore.competition_id == comp.id,
            CompetitionMatchdayScore.fanta_team_id == team.id,
            CompetitionMatchdayScore.match_day == serie_a_day,
        ).first()
        if existing:
            existing.score = total
            updated += 1
        else:
            db.add(CompetitionMatchdayScore(
                competition_id=comp.id, fanta_team_id=team.id, match_day=serie_a_day, score=total,
            ))
            imported += 1

    db.commit()
    return {
        "scores_imported": imported, "scores_updated": updated,
        "league_day": league_day, "serie_a_day": serie_a_day, "teams_unmatched": sorted(unmatched),
    }


def import_calendar_file(db: Session, season: Season, excel_bytes: bytes) -> dict:
    """Import manuale di un Excel scaricato dal sito, senza login ne' chiamate a
    leghe.fantacalcio.it. Il tipo di file e la competizione si riconoscono dal
    titolo in A1: "Calendario CIEMPIONS" (partite e gironi) oppure
    "GOLD · Giornata 4" (formazioni: totale di ogni squadra). Solleva
    ValueError se il file non e' riconosciuto o non si puo' collocare."""
    try:
        df = pd.read_excel(io.BytesIO(excel_bytes), header=None)
    except Exception:
        raise ValueError("File non leggibile: serve un Excel .xlsx scaricato da leghe.fantacalcio.it")
    title = str(df.iat[0, 0]).strip() if df.shape[0] and df.shape[1] else ""
    lineup_title = LINEUP_TITLE_RE.match(title)
    if title.lower().startswith("calendario "):
        raw_name = title[len("calendario "):].strip().upper()
    elif lineup_title:
        raw_name = lineup_title.group(1).strip().upper()
    else:
        raise ValueError("Il file non sembra un 'Calendario' o una 'Formazione' di leghe.fantacalcio.it (titolo mancante in A1)")
    comp_type = NAME_MAP.get(raw_name, raw_name)
    if comp_type not in KNOWN_TYPES:
        raise ValueError(f"Competizione '{raw_name}' non riconosciuta")
    totals = parse_lineup_totals(df) if lineup_title else {}
    if lineup_title and not totals:
        raise ValueError("Nessuna squadra con un totale trovata nel file")

    comp = db.query(Competition).filter(Competition.season_id == season.id, Competition.type == comp_type).first()
    created = comp is None
    if created:
        # Come ensure_competitions: una competizione che compare a stagione in
        # corso (es. UEFA a fine gironi) viene creata dal suo primo file.
        _ensure_league_and_competition(db, season, comp_type)
        comp = db.query(Competition).filter(Competition.season_id == season.id, Competition.type == comp_type).first()

    name_to_team = {
        _name_key(t.name): t for t in db.query(FantaTeam).filter(FantaTeam.season_id == season.id)
    }
    matched_ids: set[int] = set()
    if lineup_title:
        league_day = int(lineup_title.group(2))
        result = _import_lineups(db, season, comp, comp_type, league_day, totals, name_to_team, matched_ids)
        key = f"{comp_type} · giornata {league_day}"
    else:
        result = _import_calendar(db, comp, comp_type, excel_bytes, name_to_team, matched_ids)
        key = comp_type
    result["appena_creata"] = created
    if result["teams_unmatched"]:
        result["rename_candidates"] = _rename_candidates(db, season, comp_type, matched_ids)
    return {key: result}


def sync_results(db: Session, season: Season, comp_types: list[str] | None = None) -> dict:
    client = LegheClient()
    client.login()

    all_leghe_comps = client.list_competitions()
    # Crea (se mancano) e aggancia tutte le competizioni note trovate su
    # leghe.fantacalcio.it (Silver inclusa: serve comunque ad altre sync,
    # anche se questa non la usa mai — vedi filtro sotto) — cosi' una
    # comparsa a stagione in corso (es. UEFA) viene coperta gia' in questo
    # stesso giro.
    ensured = ensure_competitions(db, season, all_leghe_comps)
    newly_created = set(ensured["created"])
    report = {}

    query = db.query(Competition).filter(
        Competition.season_id == season.id,
        Competition.leghe_id.isnot(None),
        # Silver non ha mai un calendario testa a testa da scaricare (e' una
        # classifica ad accumulo che rispecchia il campionato di appartenenza,
        # verificato dal vivo: l'export ritorna "File non disponibile" come
        # per Tenkaichi) — e non serve comunque al calcolo Goku/Oscar.
        Competition.type != "SILVER",
    )
    if comp_types:
        query = query.filter(Competition.type.in_(comp_types))

    for comp in query.all():
        comp_type = comp.type.value if hasattr(comp.type, "value") else comp.type
        try:
            teams_by_leghe_id = client.list_competition_teams(comp.leghe_id)
            our_teams = {
                t.leghe_team_id: t
                for t in db.query(FantaTeam).filter(
                    FantaTeam.season_id == season.id, FantaTeam.leghe_team_id.isnot(None)
                )
            }
            name_to_team: dict[str, FantaTeam] = {}
            for leghe_team_id, name in teams_by_leghe_id.items():
                team = our_teams.get(leghe_team_id)
                if team:
                    name_to_team[_name_key(name)] = team
            for team in our_teams.values():
                name_to_team.setdefault(_name_key(team.name), team)

            report[comp_type] = _import_calendar(
                db, comp, comp_type, client.download_results_excel(comp.leghe_id, comp_type), name_to_team
            )
            report[comp_type]["appena_creata"] = comp_type in newly_created
        except Exception as e:
            db.rollback()
            report[comp_type] = {"error": str(e)}

    return report
