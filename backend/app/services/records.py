"""Record storici della lega mostrati nella pagina Premi.

Il punto di partenza sono i detentori forniti dall'admin (BASELINE). A ogni richiesta
vengono confrontati con i dati: classifiche finali delle stagioni passate e classifiche
calcolate al volo per le stagioni senza classifica salvata (quella in corso e le prossime
concluse). Se un dato supera il record il nuovo detentore prende il posto del vecchio, se
pareggia compaiono entrambi. Acquisto piu' oneroso e giocatore piu' acquistato non hanno
un valore scritto a mano: si calcolano sempre dalle rose.
"""
import logging

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models.competition import Competition, CompetitionStanding
from app.models.fanta_team import FantaRoster, FantaTeam
from app.models.player import Player
from app.models.season import Season

logger = logging.getLogger(__name__)

LEAGUES = ("GOLD", "BRONZE", "CARBON")
MIN_LEAGUE_GAMES = 30    # le stagioni storiche con meno partite registrate sono incomplete
MIN_SILVER_TOTAL = 1000  # nelle stagioni storiche incomplete il totale Silver e' un segnaposto (es. 1)
MAX_GOALS = 300          # oltre questo il campo contiene un punteggio, non un numero di reti
TOLERANCE = 1e-9


def _holder(team: str, season: str, value: float, detail: str = "") -> dict:
    return {"team_name": team, "season_label": season, "value": value, "detail": detail, "provisional": False}


# Detentori forniti dall'admin: valgono finche' i dati non li superano.
BASELINE: dict[str, list[dict]] = {
    "best_points": [_holder("FC Longo United", "2014-15", 76)],
    "best_silver": [_holder("TAMARINDO", "2022-23", 2864.5)],
    "most_goals_against": [
        _holder("DEPORTIVO LA CAROGNA", "2021-22", 79),
        _holder("Real Muraturi", "2022-23", 79),
    ],
    "most_goals_for": [_holder("Baby Team", "2023-24", 88)],
    "best_goal_diff": [_holder("Baby Team", "2023-24", 37)],
    "worst_goal_diff": [_holder("Birrareal", "2024-25", -37)],
    "worst_points": [_holder("Birrareal", "2024-25", 21)],
    "worst_silver": [_holder("Birrareal", "2024-25", 2360)],
}

# (chiave, etichetta, ambito, unita', estremo, metrica, vale_anche_a_stagione_in_corso)
# A stagione in corso contano solo i record che possono soltanto crescere: i "peggiori" e la
# differenza reti si valutano a stagione conclusa, altrimenti 5 giornate di punti bassi li batterebbero.
RECORDS = [
    ("best_points", "Miglior punteggio in campionato", "Gold, Bronze, Carbon", "punti", "max", "pts", True),
    ("best_silver", "Miglior punteggio Silver", "Silver", "punti", "max", "silver", True),
    ("most_goals_against", "Più reti subite in campionato", "Gold, Bronze, Carbon", "reti", "max", "ga", True),
    ("most_goals_for", "Più reti fatte in campionato", "Gold, Bronze, Carbon", "reti", "max", "gf", True),
    ("best_goal_diff", "Migliore differenza reti", "Gold, Bronze, Carbon", "reti", "max", "gd", False),
    ("worst_goal_diff", "Peggior differenza reti", "Gold, Bronze, Carbon", "reti", "min", "gd", False),
    ("worst_points", "Peggior punteggio in campionato", "Gold, Bronze, Carbon", "punti", "min", "pts", False),
    ("worst_silver", "Peggior punteggio Silver", "Silver", "punti", "min", "silver", False),
]


def _norm(name: str) -> str:
    return " ".join(name.lower().split())


def _row(team: str, season: str, comp_type: str, provisional: bool, **metrics) -> dict:
    return {
        "team_name": team, "season_label": season, "detail": comp_type.capitalize(), "provisional": provisional,
        "pts": None, "gf": None, "ga": None, "gd": None, "silver": None, **metrics,
    }


def _history_rows(db: Session) -> list[dict]:
    """Ultima riga di classifica di ogni squadra/competizione delle stagioni con classifica salvata."""
    latest = (
        db.query(
            CompetitionStanding.competition_id, CompetitionStanding.fanta_team_id,
            func.max(CompetitionStanding.match_day).label("md"),
        )
        .group_by(CompetitionStanding.competition_id, CompetitionStanding.fanta_team_id)
        .subquery()
    )
    query = (
        db.query(CompetitionStanding, Competition, Season, FantaTeam)
        .join(latest, and_(
            latest.c.competition_id == CompetitionStanding.competition_id,
            latest.c.fanta_team_id == CompetitionStanding.fanta_team_id,
            latest.c.md == CompetitionStanding.match_day,
        ))
        .join(Competition, Competition.id == CompetitionStanding.competition_id)
        .join(Season, Season.id == Competition.season_id)
        .join(FantaTeam, FantaTeam.id == CompetitionStanding.fanta_team_id)
    )
    rows = []
    for st, comp, season, team in query.all():
        comp_type = comp.type.value if hasattr(comp.type, "value") else comp.type
        if comp_type in LEAGUES:
            games = (st.wins or 0) + (st.draws or 0) + (st.losses or 0)
            gf, ga = st.goals_for, st.goals_against
            if games < MIN_LEAGUE_GAMES or gf is None or ga is None or gf > MAX_GOALS or ga > MAX_GOALS:
                continue
            rows.append(_row(team.name, season.label, comp_type, False, pts=st.pts, gf=gf, ga=ga, gd=gf - ga))
        elif comp_type == "SILVER" and (st.total_score or 0) > MIN_SILVER_TOTAL:
            rows.append(_row(team.name, season.label, comp_type, False, silver=st.total_score))
    return rows


def _live_rows(db: Session) -> list[dict]:
    """Stagioni senza classifica salvata (la corrente e le prossime concluse): si calcola dai risultati."""
    from app.routers.league import _live_standings  # import locale: evita il ciclo router -> servizio

    rows = []
    for comp, season in (
        db.query(Competition, Season).join(Season, Season.id == Competition.season_id).all()
    ):
        comp_type = comp.type.value if hasattr(comp.type, "value") else comp.type
        if comp_type not in LEAGUES + ("SILVER",):
            continue
        if db.query(CompetitionStanding.id).filter(CompetitionStanding.competition_id == comp.id).first():
            continue
        provisional = bool(season.is_current)
        for s in _live_standings(db, comp):
            name = s["fanta_team_name"]
            if comp_type == "SILVER":
                if s["total_score"] > 0:
                    rows.append(_row(name, season.label, comp_type, provisional, silver=s["total_score"]))
            elif (s["wins"] + s["draws"] + s["losses"]) > 0:
                rows.append(_row(name, season.label, comp_type, provisional, pts=s["pts"], gf=s["goals_for"],
                                 ga=s["goals_against"], gd=s["goals_for"] - s["goals_against"]))
    return rows


def _holders(baseline: list[dict], rows: list[dict], metric: str, extreme: str, monotonic: bool):
    """(valore, detentori) del record: baseline e dati insieme; a parita' compaiono tutti."""
    by_key: dict[tuple, dict] = {}
    candidates = [dict(h) for h in baseline]
    for r in rows:
        value = r.get(metric)
        if value is None or (r["provisional"] and not monotonic):
            continue
        candidates.append({"team_name": r["team_name"], "season_label": r["season_label"], "value": value,
                           "detail": r["detail"], "provisional": r["provisional"]})
    if not candidates:
        return None, []
    pick = max if extreme == "max" else min
    best = pick(c["value"] for c in candidates)
    for c in candidates:
        if abs(c["value"] - best) > TOLERANCE:
            continue
        key = (_norm(c["team_name"]), c["season_label"])
        previous = by_key.get(key)
        # la stessa squadra/stagione puo' venire dalla baseline e dai dati: tengo quella con piu' dettagli
        if previous is None or (c["detail"] and not previous["detail"]) or (previous["provisional"] and not c["provisional"]):
            by_key[key] = c
    holders = sorted(by_key.values(), key=lambda c: (c["season_label"], c["team_name"]))
    return best, [{k: h[k] for k in ("team_name", "season_label", "detail", "provisional")} for h in holders]


def _most_expensive(db: Session) -> dict:
    rows = (
        db.query(FantaRoster.purchase_price, Player.name, FantaTeam.name, Season.label)
        .join(Player, Player.id == FantaRoster.player_id)
        .join(FantaTeam, FantaTeam.id == FantaRoster.fanta_team_id)
        .join(Season, Season.id == FantaRoster.season_id)
        .order_by(FantaRoster.purchase_price.desc())
        .limit(50)
        .all()
    )
    best = rows[0][0] if rows else None
    holders = [
        {"team_name": team, "season_label": season, "detail": player, "provisional": False}
        for price, player, team, season in rows if best is not None and abs(price - best) < TOLERANCE
    ]
    return {"key": "most_expensive", "label": "Acquisto più oneroso", "scope": "Asta", "unit": "FM",
            "value": best, "holders": holders, "in_progress": False}


def _most_bought(db: Session) -> dict:
    """Stesso giocatore comprato piu' volte dalla stessa squadra (identita' di squadra tra stagioni: lineage)."""
    rows = (
        db.query(FantaTeam.lineage_id, FantaTeam.name, Player.id, Player.name, Season.label)
        .select_from(FantaRoster)
        .join(Player, Player.id == FantaRoster.player_id)
        .join(FantaTeam, FantaTeam.id == FantaRoster.fanta_team_id)
        .join(Season, Season.id == FantaRoster.season_id)
        .all()
    )
    agg: dict[tuple, dict] = {}
    for lineage, team, player_id, player, season in rows:
        key = (f"l{lineage}" if lineage else "n:" + _norm(team), player_id)
        a = agg.setdefault(key, {"seasons": set(), "team": team, "player": player, "last": season})
        a["seasons"].add(season)
        if season >= a["last"]:
            a["last"], a["team"] = season, team
    best = max((len(a["seasons"]) for a in agg.values()), default=None)
    holders = [
        {"team_name": a["team"], "season_label": None,
         "detail": f"{a['player']} · ultima volta nel {a['last']}", "provisional": False}
        for a in sorted(agg.values(), key=lambda a: (a["team"], a["player"])) if len(a["seasons"]) == best
    ]
    return {"key": "most_bought", "label": "Giocatore acquistato più volte", "scope": "Asta", "unit": "volte",
            "value": best, "holders": holders, "in_progress": False}


def compute_records(db: Session) -> list[dict]:
    rows = _history_rows(db) + _live_rows(db)
    final_rows = [r for r in rows if not r["provisional"]]
    out = []
    for key, label, scope, unit, extreme, metric, monotonic in RECORDS:
        baseline = BASELINE[key]
        value, holders = _holders(baseline, rows, metric, extreme, monotonic)
        data_value, _ = _holders([], final_rows, metric, extreme, monotonic)
        if data_value is not None and abs(data_value - baseline[0]["value"]) > TOLERANCE:
            logger.warning(
                "Record '%s': i dati danno %s, il valore di partenza era %s (aggiornato in base ai dati)",
                key, data_value, baseline[0]["value"],
            )
        out.append({
            "key": key, "label": label, "scope": scope, "unit": unit, "value": value, "holders": holders,
            "in_progress": any(h["provisional"] for h in holders),
        })
    out.append(_most_expensive(db))
    out.append(_most_bought(db))
    return out
