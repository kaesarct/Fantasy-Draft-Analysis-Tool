from sqlalchemy.orm import Session

from app.models.competition import CompetitionMatchday


def serie_a_days(db: Session, competition_id: int) -> dict[int, int]:
    """Giornata di lega -> giornata di Serie A di una competizione, dal Calendario."""
    return {
        row.match_day: row.serie_a_day
        for row in db.query(CompetitionMatchday).filter(CompetitionMatchday.competition_id == competition_id)
    }
