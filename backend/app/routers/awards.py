"""Premio Goku/Oscar (punteggio più alto/basso di giornata) e coerenza Silver."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.season import Season
from app.models.competition import Competition, CompetitionMatchdayScore, CompetitionPhase, CompetitionStanding, CompetitionType, MatchResult, SeasonAward
from app.models.fanta_team import FantaTeam, League
from app.services.auth_service import require_admin
from app.services.competition_provisioning import MAIN_LEAGUE_TYPES
from app.services.matchdays import serie_a_days

router = APIRouter(tags=["awards"])

# Silver esclusa: deve limitarsi a rispecchiare il campionato di appartenenza
# (Gold/Bronze/Carbon), non va sommata a parte per non duplicare i punteggi.
_AWARD_COMPETITION_TYPES = [
    "GOLD", "BRONZE", "CARBON", "CIEMPIONS", "UEFA", "COPPA_ITALIA", "EURO_CUP",
]

_SILVER_TOLERANCE = 0.01


_PHASE_LABELS = {
    CompetitionPhase.ROUND_OF_16: "ottavi di finale",
    CompetitionPhase.QUARTER_FINAL: "quarti di finale",
    CompetitionPhase.SEMI_FINAL: "semifinale",
    CompetitionPhase.FINAL: "finale",
}


def _round_label(phase, match_day: int) -> str:
    label = _PHASE_LABELS.get(phase)
    return label if label else f"{match_day}ª giornata"


def _matchday_scores_from_lineup_sync(
    db: Session, comp: Competition, comp_type: str, to_league_day: dict[int, int]
) -> list[dict]:
    """Punteggio reale di giornata, da CompetitionMatchdayScore (sincronizzato
    da leghe.fantacalcio.it via teamLineup — vedi POST /leghe-sync/sync-matchday-scores).
    Fonte preferita: funziona anche per competizioni senza scontri diretti
    (es. Silver), ma non porta l'informazione di fase — per le coppe mostra
    sempre "Nª giornata" invece di "semifinale" ecc. (quella richiede anche
    un MatchResult sincronizzato dall'Excel Calendario per la stessa
    competizione).

    I punteggi sono salvati sulla giornata di Serie A; l'etichetta usa la
    giornata di lega (come i MatchResult) quando il Calendario la conosce."""
    rows = (
        db.query(CompetitionMatchdayScore, FantaTeam.name)
        .join(FantaTeam, FantaTeam.id == CompetitionMatchdayScore.fanta_team_id)
        .filter(CompetitionMatchdayScore.competition_id == comp.id)
        .all()
    )
    return [
        {
            "fanta_team_id": s.fanta_team_id, "fanta_team_name": team_name,
            "competition_type": comp_type, "serie_a_day": s.match_day,
            "match_day": to_league_day.get(s.match_day, s.match_day),
            "round_label": _round_label(None, to_league_day.get(s.match_day, s.match_day)),
            "score": s.score,
        }
        for s, team_name in rows
    ]


def _matchday_scores_from_match_results(
    db: Session, comp: Competition, comp_type: str, to_serie_a_day: dict[int, int]
) -> list[dict]:
    """Punteggio reale di singola partita, da MatchResult (sincronizzato da
    leghe.fantacalcio.it — vedi POST /leghe-sync/sync-results)."""
    matches = db.query(MatchResult).filter(MatchResult.competition_id == comp.id).all()
    team_ids = {m.fanta_team_home_id for m in matches} | {m.fanta_team_away_id for m in matches}
    names = {t.id: t.name for t in db.query(FantaTeam).filter(FantaTeam.id.in_(team_ids))}

    performances = []
    for m in matches:
        round_label = _round_label(m.phase, m.match_day)
        for team_id, score in ((m.fanta_team_home_id, m.score_home), (m.fanta_team_away_id, m.score_away)):
            if score is None:
                continue
            performances.append({
                "fanta_team_id": team_id, "fanta_team_name": names.get(team_id, "?"),
                "competition_type": comp_type, "match_day": m.match_day, "round_label": round_label,
                "serie_a_day": to_serie_a_day.get(m.match_day),
                "score": score,
            })
    return performances


def _matchday_scores_from_standings(db: Session, comp: Competition, comp_type: str) -> list[dict]:
    """Ripiego quando la competizione non ha ancora nessun MatchResult
    sincronizzato: punteggio di giornata ricavato come differenza tra il
    `total_score` cumulato ("Pt. Totali", il fantapunteggio di squadra — non
    va confuso con `goals_for`, i gol calcolati dalle fasce) di due righe
    CompetitionStanding consecutive, inserite a mano nell'editor classifica
    di Gestione Squadre (PUT /competitions/{id}/standings)."""
    rows = (
        db.query(CompetitionStanding, FantaTeam.name)
        .join(FantaTeam, FantaTeam.id == CompetitionStanding.fanta_team_id)
        .filter(CompetitionStanding.competition_id == comp.id)
        .order_by(CompetitionStanding.fanta_team_id, CompetitionStanding.match_day)
        .all()
    )

    performances = []
    prev_team_id = None
    prev_cumulative = 0.0
    for standing, team_name in rows:
        if standing.fanta_team_id != prev_team_id:
            prev_cumulative = 0.0
        delta = round(standing.total_score - prev_cumulative, 2)
        performances.append({
            "fanta_team_id": standing.fanta_team_id, "fanta_team_name": team_name,
            "competition_type": comp_type, "match_day": standing.match_day,
            "round_label": _round_label(None, standing.match_day),
            "score": delta,
        })
        prev_cumulative = standing.total_score
        prev_team_id = standing.fanta_team_id
    return performances


def _merge_lineup_and_results(from_lineup: list[dict], from_results: list[dict]) -> list[dict]:
    """Unisce le due fonti senza contare due volte lo stesso turno: i punteggi
    da formazione hanno la precedenza, i risultati aggiungono i turni che le
    formazioni non coprono. Il turno e' lo stesso se coincide la giornata di
    Serie A; senza corrispondenza nel Calendario ripiego sul punteggio uguale."""
    covered_days = {(p["fanta_team_id"], p["serie_a_day"]) for p in from_lineup}
    covered_scores = {(p["fanta_team_id"], p["score"]) for p in from_lineup}
    def already_covered(p: dict) -> bool:
        if p["serie_a_day"] is not None:
            return (p["fanta_team_id"], p["serie_a_day"]) in covered_days
        return (p["fanta_team_id"], p["score"]) in covered_scores

    return from_lineup + [p for p in from_results if not already_covered(p)]


def _matchday_scores(db: Session, season_id: int, comp_types: list[str]) -> list[dict]:
    """Punteggio di ogni squadra per singola giornata/partita, per tutte le
    competizioni della stagione tra quelle passate. Fonti: CompetitionMatchdayScore
    (formazioni/teamLineup, universale) e MatchResult (Excel Calendario, porta
    anche la fase per le coppe), unite turno per turno; se non c'e' nessuna delle
    due, ripiego a classifica cumulativa — cosi' una competizione senza ancora
    nessun dato non sparisce dal conteggio."""
    performances = []
    for comp in db.query(Competition).filter(
        Competition.season_id == season_id, Competition.type.in_(comp_types)
    ):
        comp_type = comp.type.value if hasattr(comp.type, "value") else comp.type
        to_serie_a_day = serie_a_days(db, comp.id)
        from_lineup = _matchday_scores_from_lineup_sync(
            db, comp, comp_type, {v: k for k, v in to_serie_a_day.items()}
        )
        from_results = _matchday_scores_from_match_results(db, comp, comp_type, to_serie_a_day)
        merged = _merge_lineup_and_results(from_lineup, from_results)
        performances.extend(merged if merged else _matchday_scores_from_standings(db, comp, comp_type))
    for p in performances:
        p.pop("serie_a_day", None)
    return _drop_cup_duplicates(performances)


def _drop_cup_duplicates(performances: list[dict]) -> list[dict]:
    """Una giornata di coppa si gioca con la stessa formazione di quella di
    campionato, quindi stesso punteggio: se una prestazione di coppa coincide
    (stessa squadra, stesso punteggio) con una di Gold/Bronze/Carbon, vale
    quella della lega e la copia di coppa viene scartata, per non
    duplicare il risultato in Goku/Oscar."""
    league_keys = {
        (p["fanta_team_id"], p["score"]) for p in performances if p["competition_type"] in MAIN_LEAGUE_TYPES
    }
    return [
        p for p in performances
        if p["competition_type"] in MAIN_LEAGUE_TYPES or (p["fanta_team_id"], p["score"]) not in league_keys
    ]


def _absolute_record(
    history: list[dict], current_performances: list[dict], award_type: str,
    current_season_label: str | None, pick_max: bool,
) -> dict | None:
    hist_rows = [h for h in history if h["award_type"] == award_type]
    candidates = []
    if hist_rows:
        best_hist = (max if pick_max else min)(hist_rows, key=lambda h: h["score"])
        candidates.append({
            "source": "storico", "season_label": best_hist["season_label"],
            "team_name": best_hist["team_name"], "score": best_hist["score"], "detail": best_hist["detail"],
        })
    if current_performances:
        best_current = (max if pick_max else min)(current_performances, key=lambda p: p["score"])
        candidates.append({
            "source": "stagione_corrente", "season_label": current_season_label,
            "team_name": best_current["fanta_team_name"], "score": best_current["score"],
            "detail": f"{best_current['competition_type']} — {best_current['round_label']}",
        })
    if not candidates:
        return None
    return (max if pick_max else min)(candidates, key=lambda c: c["score"])


def _current_goku_oscar(db: Session, season: Season) -> tuple[list[dict], list[dict]]:
    performances = _matchday_scores(db, season.id, _AWARD_COMPETITION_TYPES)
    if not performances:
        return [], []
    max_score = max(p["score"] for p in performances)
    min_score = min(p["score"] for p in performances)
    return (
        [p for p in performances if p["score"] == max_score],
        [p for p in performances if p["score"] == min_score],
    )


@router.get("/awards/overview")
def get_awards_overview(db: Session = Depends(get_db)):
    current_season = db.query(Season).filter(Season.is_current == True).first()
    current_season_label = current_season.label if current_season else None

    goku_current, oscar_current = _current_goku_oscar(db, current_season) if current_season else ([], [])

    history = [
        {
            "season_label": a.season_label,
            "award_type": a.award_type.value if hasattr(a.award_type, "value") else a.award_type,
            "team_name": a.team_name, "score": a.score, "detail": a.detail,
        }
        for a in db.query(SeasonAward).order_by(SeasonAward.season_label.desc()).all()
    ]

    return {
        "current_season_label": current_season_label,
        "goku_current": goku_current,
        "oscar_current": oscar_current,
        "history": history,
        "absolute_goku": _absolute_record(history, goku_current, "GOKU", current_season_label, pick_max=True),
        "absolute_oscar": _absolute_record(history, oscar_current, "OSCAR", current_season_label, pick_max=False),
    }


def _season_or_404(db: Session, season_id: int | None) -> Season:
    season = (
        db.query(Season).filter(Season.id == season_id).first()
        if season_id else
        db.query(Season).filter(Season.is_current == True).first()
    )
    if not season:
        raise HTTPException(404, "Stagione non trovata")
    return season


def _silver_discrepancies(db: Session, season: Season) -> tuple[list[dict], int]:
    """Differenze tra Silver e il campionato di appartenenza, e quanti
    confronti giornata-per-squadra sono stati fatti con entrambi i valori."""
    checked = 0
    silver_comp = db.query(Competition).filter(
        Competition.season_id == season.id, Competition.type == CompetitionType.SILVER
    ).first()

    discrepancies = []
    for team in db.query(FantaTeam).filter(FantaTeam.season_id == season.id):
        league = db.query(League).filter(League.id == team.league_id).first()
        if not league:
            continue
        level = league.level.value if hasattr(league.level, "value") else league.level
        league_comp = db.query(Competition).filter(
            Competition.season_id == season.id, Competition.type == level
        ).first()
        if not league_comp:
            continue

        # Preferita: confronto diretto giornata-per-giornata sui punteggi reali
        # sincronizzati da teamLineup (CompetitionMatchdayScore) — una
        # discrepanza isolata non si perde in una somma cumulata. Ripiego al
        # confronto cumulativo su CompetitionStanding.total_score quando
        # mancano dati sincronizzati per una delle due parti.
        league_lineup = {
            s.match_day: s.score
            for s in db.query(CompetitionMatchdayScore).filter(
                CompetitionMatchdayScore.competition_id == league_comp.id,
                CompetitionMatchdayScore.fanta_team_id == team.id,
            )
        }
        silver_lineup = {
            s.match_day: s.score
            for s in db.query(CompetitionMatchdayScore).filter(
                CompetitionMatchdayScore.competition_id == silver_comp.id,
                CompetitionMatchdayScore.fanta_team_id == team.id,
            )
        } if silver_comp else {}

        if league_lineup and silver_lineup:
            league_by_day, silver_by_day = league_lineup, silver_lineup
        else:
            league_by_day = {
                s.match_day: s.total_score
                for s in db.query(CompetitionStanding).filter(
                    CompetitionStanding.competition_id == league_comp.id,
                    CompetitionStanding.fanta_team_id == team.id,
                )
            }
            silver_by_day = {}
            if silver_comp:
                silver_by_day = {
                    s.match_day: s.total_score
                    for s in db.query(CompetitionStanding).filter(
                        CompetitionStanding.competition_id == silver_comp.id,
                        CompetitionStanding.fanta_team_id == team.id,
                    )
                }

        for match_day in sorted(set(league_by_day) | set(silver_by_day)):
            league_value = league_by_day.get(match_day)
            silver_value = silver_by_day.get(match_day)
            if league_value is None:
                kind = "missing_league"
            elif silver_value is None:
                kind = "missing_silver"
            else:
                checked += 1
                if abs(league_value - silver_value) <= _SILVER_TOLERANCE:
                    continue
                kind = "mismatch"
            discrepancies.append({
                "fanta_team_id": team.id, "fanta_team_name": team.name, "match_day": match_day,
                "league_type": level, "league_value": league_value, "silver_value": silver_value,
                "kind": kind,
            })

    return discrepancies, checked


def build_consistency_report(db: Session, season: Season) -> dict:
    silver, silver_checked = _silver_discrepancies(db, season)
    goku, oscar = _current_goku_oscar(db, season)
    return {
        "season_label": season.label,
        "silver": {"checked": silver_checked, "discrepancies": silver},
        "goku": goku, "oscar": oscar,
    }


@router.get("/awards/silver-consistency")
def get_silver_consistency(
    season_id: int | None = None, db: Session = Depends(get_db), _admin: str = Depends(require_admin)
):
    season = _season_or_404(db, season_id)
    discrepancies, _ = _silver_discrepancies(db, season)
    return {"season_label": season.label, "discrepancies": discrepancies}


@router.get("/awards/consistency-check")
def get_consistency_check(
    season_id: int | None = None, db: Session = Depends(get_db), _admin: str = Depends(require_admin)
):
    """Controllo dopo un caricamento di file: Silver contro campionati (devono
    coincidere; le coppe possono avere una formazione diversa) e Goku/Oscar attuali."""
    return build_consistency_report(db, _season_or_404(db, season_id))
