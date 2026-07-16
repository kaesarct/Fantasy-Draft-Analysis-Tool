"""Players router."""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.player import Player, PlayerSnapshot, PlayerMatchScore
from app.models.season import Season
from app.models.season_data import PlayerSeasonStat, PlayerSeasonPrice, PlayerSeasonVote

router = APIRouter(prefix="/players", tags=["players"])


@router.get("")
def list_players(
    search: str | None = Query(None),
    role: str | None = Query(None),
    team_id: int | None = Query(None),
    season_id: int | None = Query(None, description="Limita ai giocatori presenti nelle quotazioni di questa stagione"),
    db: Session = Depends(get_db),
):
    q = db.query(Player)
    if search:
        q = q.filter(Player.name.ilike(f"%{search}%"))
    if role:
        q = q.filter(Player.role == role.upper())
    if team_id:
        q = q.filter(Player.serie_a_team_id == team_id)

    # Quotazioni: PlayerSnapshot e' il sync live (solo per la stagione in
    # corso), PlayerSeasonPrice e' l'import storico (stagioni concluse) — le
    # due tabelle non hanno mai dati per la stessa stagione contemporaneamente,
    # quindi si usa quella con righe per la stagione richiesta.
    latest_snapshot_by_player: dict[int, PlayerSnapshot] = {}
    historical_price_by_fanta_id: dict[int, PlayerSeasonPrice] = {}
    hist_range_by_fanta_id: dict[int, tuple] = {}
    live_range_by_player: dict[int, tuple] = {}
    roles_by_fanta_id: dict[int, set] = {}

    if season_id:
        snaps = (
            db.query(PlayerSnapshot)
            .filter(PlayerSnapshot.season_id == season_id)
            .order_by(PlayerSnapshot.match_day)
            .all()
        )
        for snap in snaps:
            latest_snapshot_by_player[snap.player_id] = snap

        if latest_snapshot_by_player:
            q = q.filter(Player.id.in_(latest_snapshot_by_player.keys()))
        else:
            prices = (
                db.query(PlayerSeasonPrice)
                .filter(PlayerSeasonPrice.season_id == season_id)
                .all()
            )
            historical_price_by_fanta_id = {pr.fanta_player_id: pr for pr in prices}
            q = q.filter(
                Player.fanta_id.isnot(None),
                Player.fanta_id.in_(historical_price_by_fanta_id.keys()),
            )
    else:
        # "Tutte le stagioni": min/max mai ottenuto, aggregati in una sola
        # query per fonte (non per giocatore, per evitare N+1 su ~1100 righe).
        # func.nullif(fvm, 0): nelle stagioni precedenti al tracciamento del
        # FVM il campo vale letteralmente 0 (non NULL) — un placeholder, non
        # un vero minimo/massimo, va escluso dall'aggregazione.
        hist_range_by_fanta_id = {
            row.fanta_player_id: (row.min_price, row.max_price, row.min_fvm, row.max_fvm, row.min_diff, row.max_diff)
            for row in db.query(
                PlayerSeasonPrice.fanta_player_id,
                func.min(PlayerSeasonPrice.market_value_a).label("min_price"),
                func.max(PlayerSeasonPrice.market_value_a).label("max_price"),
                func.min(func.nullif(PlayerSeasonPrice.fvm, 0)).label("min_fvm"),
                func.max(func.nullif(PlayerSeasonPrice.fvm, 0)).label("max_fvm"),
                func.min(PlayerSeasonPrice.difference).label("min_diff"),
                func.max(PlayerSeasonPrice.difference).label("max_diff"),
            ).group_by(PlayerSeasonPrice.fanta_player_id).all()
        }
        live_range_by_player = {
            row.player_id: (row.min_price, row.max_price, row.min_fvm, row.max_fvm, row.min_diff, row.max_diff)
            for row in db.query(
                PlayerSnapshot.player_id,
                func.min(PlayerSnapshot.price).label("min_price"),
                func.max(PlayerSnapshot.price).label("max_price"),
                func.min(func.nullif(PlayerSnapshot.fvm, 0)).label("min_fvm"),
                func.max(func.nullif(PlayerSnapshot.fvm, 0)).label("max_fvm"),
                func.min(PlayerSnapshot.price_diff).label("min_diff"),
                func.max(PlayerSnapshot.price_diff).label("max_diff"),
            ).group_by(PlayerSnapshot.player_id).all()
        }
        for row in db.query(PlayerSeasonStat.fanta_player_id, PlayerSeasonStat.role).filter(PlayerSeasonStat.role.isnot(None)).distinct().all():
            roles_by_fanta_id.setdefault(row[0], set()).add(row[1])
        for row in db.query(PlayerSeasonPrice.fanta_player_id, PlayerSeasonPrice.role).filter(PlayerSeasonPrice.role.isnot(None)).distinct().all():
            roles_by_fanta_id.setdefault(row[0], set()).add(row[1])

    players = q.order_by(Player.name).all()
    result = []
    for p in players:
        entry = {
            "id": p.id,
            "fanta_id": p.fanta_id,
            "name": p.name,
            "roles": [p.role] if p.role else [],
            "secondary_role": p.secondary_role,
            "serie_a_team_id": p.serie_a_team_id,
            "price": None, "price_diff": None, "fvm": None,
            "price_min": None, "price_max": None,
            "fvm_min": None, "fvm_max": None,
            "diff_min": None, "diff_max": None,
        }

        if season_id:
            snap = latest_snapshot_by_player.get(p.id)
            hist_price = historical_price_by_fanta_id.get(p.fanta_id) if p.fanta_id else None
            if snap:
                entry["price"], entry["price_diff"], entry["fvm"] = snap.price, snap.price_diff, snap.fvm
            elif hist_price:
                entry["price"] = hist_price.market_value_a
                entry["price_diff"] = hist_price.difference
                entry["fvm"] = hist_price.fvm
                if hist_price.role:
                    entry["roles"] = [hist_price.role]
        else:
            if p.fanta_id and p.fanta_id in roles_by_fanta_id:
                entry["roles"] = sorted(roles_by_fanta_id[p.fanta_id] | set(entry["roles"]))
            ranges = []
            if p.fanta_id and p.fanta_id in hist_range_by_fanta_id:
                ranges.append(hist_range_by_fanta_id[p.fanta_id])
            if p.id in live_range_by_player:
                ranges.append(live_range_by_player[p.id])
            for idx, (min_key, max_key) in enumerate([("price_min", "price_max"), ("fvm_min", "fvm_max"), ("diff_min", "diff_max")]):
                values_min = [r[idx * 2] for r in ranges if r[idx * 2] is not None]
                values_max = [r[idx * 2 + 1] for r in ranges if r[idx * 2 + 1] is not None]
                entry[min_key] = min(values_min) if values_min else None
                entry[max_key] = max(values_max) if values_max else None

        result.append(entry)
    return result


@router.get("/{player_id}")
def get_player(player_id: int, db: Session = Depends(get_db)):
    p = db.query(Player).filter(Player.id == player_id).first()
    if not p:
        raise HTTPException(404, "Player not found")
    return {
        "id": p.id, "fanta_id": p.fanta_id, "name": p.name,
        "role": p.role, "secondary_role": p.secondary_role,
        "serie_a_team_id": p.serie_a_team_id,
        "serie_a_team_name": p.serie_a_team.name if p.serie_a_team else None,
    }


@router.get("/{player_id}/history")
def get_player_history(player_id: int, season_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(PlayerSnapshot).filter(PlayerSnapshot.player_id == player_id)
    if season_id:
        q = q.filter(PlayerSnapshot.season_id == season_id)
    snaps = q.order_by(PlayerSnapshot.season_id, PlayerSnapshot.match_day).all()
    return [
        {
            "match_day": s.match_day, "season_id": s.season_id,
            "price": s.price, "price_diff": s.price_diff,
            "fvm": s.fvm, "fvm_mantra": s.fvm_mantra,
        }
        for s in snaps
    ]


@router.get("/{player_id}/scores")
def get_player_scores(player_id: int, season_id: int | None = None, db: Session = Depends(get_db)):
    p = db.query(Player).filter(Player.id == player_id).first()
    if not p:
        raise HTTPException(404, "Player not found")

    q = db.query(PlayerMatchScore).filter(PlayerMatchScore.player_id == player_id)
    if season_id:
        q = q.filter(PlayerMatchScore.season_id == season_id)
    scores = q.order_by(PlayerMatchScore.season_id, PlayerMatchScore.match_day).all()

    if season_id and p.fanta_id:
        historical = (
            db.query(PlayerSeasonVote)
            .filter(
                PlayerSeasonVote.season_id == season_id,
                PlayerSeasonVote.fanta_player_id == p.fanta_id,
            )
            .order_by(PlayerSeasonVote.match_day)
            .all()
        )
        if len(historical) > len(scores):
            return [
                {
                    "match_day": h.match_day, "season_id": season_id,
                    "vote": h.vote, "goals": h.goals_scored, "assists": h.assists,
                    "yellow_cards": h.yellow_cards, "red_cards": h.red_cards,
                    "bonus_total": None, "malus_total": None, "total_score": None,
                }
                for h in historical
            ]

    return [
        {
            "match_day": s.match_day, "season_id": s.season_id,
            "vote": s.vote, "goals": s.goals, "assists": s.assists,
            "yellow_cards": s.yellow_cards, "red_cards": s.red_cards,
            "bonus_total": s.bonus_total, "malus_total": s.malus_total,
            "total_score": s.total_score,
        }
        for s in scores
    ]


@router.get("/{player_id}/season-history")
def get_player_season_history(player_id: int, db: Session = Depends(get_db)):
    from app.models.fanta_team import FantaRoster, FantaTeam

    p = db.query(Player).filter(Player.id == player_id).first()
    if not p:
        raise HTTPException(404, "Player not found")
    if not p.fanta_id:
        return []

    stats = {
        s.season_id: s
        for s in db.query(PlayerSeasonStat).filter(PlayerSeasonStat.fanta_player_id == p.fanta_id).all()
    }
    prices = {
        pr.season_id: pr
        for pr in db.query(PlayerSeasonPrice).filter(PlayerSeasonPrice.fanta_player_id == p.fanta_id).all()
    }

    fanta_teams_by_season: dict[int, list] = {}
    for season_id, team_name in (
        db.query(FantaRoster.season_id, FantaTeam.name)
        .join(FantaTeam, FantaTeam.id == FantaRoster.fanta_team_id)
        .filter(FantaRoster.player_id == player_id)
        .distinct()
        .all()
    ):
        fanta_teams_by_season.setdefault(season_id, []).append(team_name)

    season_ids = set(stats) | set(prices) | set(fanta_teams_by_season)
    if not season_ids:
        return []

    labels = {
        s.id: s.label
        for s in db.query(Season).filter(Season.id.in_(season_ids)).all()
    }

    result = []
    for sid in season_ids:
        st = stats.get(sid)
        pr = prices.get(sid)
        # fvm=0 e' un placeholder per le stagioni precedenti al tracciamento
        # del FVM (vedi list_players), non un valore reale.
        fvm = pr.fvm if pr and pr.fvm else None
        result.append({
            "season_id": sid,
            "season_label": labels.get(sid),
            "role": (st.role if st else None) or (pr.role if pr else None),
            "team": (st.team if st else None) or (pr.team if pr else None),
            "fanta_teams": sorted(fanta_teams_by_season.get(sid, [])),
            "matches_played": st.matches_played if st else None,
            "average_vote": st.average_vote if st else None,
            "fantasy_average": st.fantasy_average if st else None,
            "goals_scored": st.goals_scored if st else None,
            "assists": st.assists if st else None,
            "yellow_cards": st.yellow_cards if st else None,
            "red_cards": st.red_cards if st else None,
            "market_value_i": pr.market_value_i if pr else None,
            "market_value_a": pr.market_value_a if pr else None,
            "difference": pr.difference if pr else None,
            "fvm": fvm,
        })
    result.sort(key=lambda r: r["season_id"], reverse=True)
    return result
