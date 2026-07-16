"""Models package — import all so SQLAlchemy Base knows about all tables."""
from app.models.season import Season  # noqa
from app.models.serie_a_team import SerieATeam  # noqa
from app.models.player import Player, PlayerSnapshot, PlayerMatchScore  # noqa
from app.models.fanta_allenatore import FantaAllenatore  # noqa
from app.models.fanta_team import (  # noqa
    League, LeagueLevel,
    FantaTeam, FantaTeamCoach, FantaTeamLogo,
    FantaRoster, FantaRosterTempSub,
)
from app.models.competition import (  # noqa
    Competition, CompetitionType, CompetitionPhase,
    CompetitionGroup, CompetitionGroupTeam,
    MatchResult, CompetitionStanding,
)
from app.models.injury import InjuryPlayer  # noqa
from app.models.serie_a_injury import (  # noqa
    SerieAInjuryReport, SerieAInjuryArchive, SerieAInjuryDescription,
)
from app.models.lineup import LineupSubmission, LineupPlayer  # noqa
from app.models.lineup_import import LineupRawImport  # noqa
from app.models.season_data import ImportedSeasonData, PlayerSeasonStat, PlayerSeasonPrice, PlayerSeasonVote  # noqa
from app.models.trade import Trade, TradeItem  # noqa
from app.models.auction import Auction, AuctionBid, AuctionStatus  # noqa
