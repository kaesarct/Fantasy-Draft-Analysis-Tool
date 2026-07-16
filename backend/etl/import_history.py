"""ETL one-off: importa lo storico Tamarros (cartella STAGIONI) nel DB della piattaforma.

Copre le stagioni 2018-19 → 2024-25 (formati export leghe.fantacalcio.it/fantagazzetta):
- Classifica_*.xlsx  → Competition + CompetitionStanding (+ gironi Ciempions)
- Calendario_*.xlsx  → MatchResult
- Rose (xlsx/csv)    → Player + FantaTeam + FantaRoster
Le stagioni 2009-10 → 2017-18 vengono solo censite come Season (dati non strutturati).

Idempotente: ogni entita' e' upsert, lo script si puo' rieseguire.
Uso:  python -m etl.import_history --dir "<cartella STAGIONI>" [--years 2018 2019 ...]
"""
import argparse
import csv
import io
import re
import sys
from pathlib import Path

import pandas as pd

from app.database import SessionLocal, init_db
from app.models.competition import (
    Competition,
    CompetitionGroup,
    CompetitionGroupTeam,
    CompetitionPhase,
    CompetitionStanding,
    CompetitionType,
    MatchResult,
)
from app.models.fanta_team import FantaRoster, FantaTeam, League, LeagueLevel
from app.models.player import Player
from app.models.season import Season

FIRST_SEASON_YEAR = 2009
LAST_SEASON_YEAR = 2024
DEFAULT_ETL_YEARS = range(2018, 2025)

# Tipi competizione riconosciuti nei nomi file (Classifica_X / Calendario_X)
TYPE_ALIASES = {
    "GOLD": CompetitionType.GOLD,
    "BRONZE": CompetitionType.BRONZE,
    "CARBON": CompetitionType.CARBON,
    "SILVER": CompetitionType.SILVER,
    "CIEMPIONS": CompetitionType.CIEMPIONS,
    "UEFA": CompetitionType.UEFA,
    "COPPA-ITALIA": CompetitionType.COPPA_ITALIA,
    "ITALIA": CompetitionType.COPPA_ITALIA,
    "EURO-CUP": CompetitionType.EURO_CUP,
    "EUROCUP": CompetitionType.EURO_CUP,
}
MAIN_LEAGUE_TYPES = {
    CompetitionType.GOLD: LeagueLevel.GOLD,
    CompetitionType.BRONZE: LeagueLevel.BRONZE,
    CompetitionType.CARBON: LeagueLevel.CARBON,
}

# Squadre rinominate in corso di stagione: nome nel file rose → nome ufficiale
# nelle classifiche (mappature confermate dall'utente, per anno di inizio stagione).
TEAM_ALIASES = {
    (2020, "panuzzo"): "#PANEINGOLD",
    (2022, "new bombola fire"): "BOMBOLA X",
    (2022, "as vikings"): "VULCANIA FC",
    # 2023-24: il file rose CSV usa un nome diverso da classifiche/calendari
    # per queste 6 squadre (apostrofi, trattini, spazi, refusi) — norm()
    # normalizza solo spazi/maiuscole, non basta a farli convergere.
    (2023, "best player crew"): "bestplayerscrew",
    (2023, "facoceri's karma"): "Facoceris Karma",
    (2023, "real muratori"): "Real Muraturi",
    (2023, "al fizzy"): "AL-FIZZY",
    (2023, "nika football club"): "Nikafootballclub",
    (2023, "ser"): "SER - otto",
}

GIORNATA_RE = re.compile(r"(\d+)ª\s+Giornata\s+lega", re.IGNORECASE)
GOALS_RE = re.compile(r"^(\d+)\s*-\s*(\d+)$")
GIRONE_LETTER_RE = re.compile(r"^[A-Z]$")


def phase_from_label(text: str) -> CompetitionPhase | None:
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


def norm(name) -> str:
    """Chiave di confronto per nomi (squadre/giocatori) con spazi/case incoerenti tra file."""
    return re.sub(r"\s+", " ", str(name)).strip().casefold()


def is_blank(value) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


class SeasonImporter:
    """Stato e cache per l'import di una singola stagione."""

    def __init__(self, db, season: Season, folder: Path, report: dict):
        self.db = db
        self.season = season
        self.folder = folder
        self.report = report
        self.leagues: dict[LeagueLevel, League] = {}
        self.teams: dict[str, FantaTeam] = {
            norm(t.name): t
            for t in db.query(FantaTeam).filter(FantaTeam.season_id == season.id)
        }
        self.competitions: dict[CompetitionType, Competition] = {
            c.type: c
            for c in db.query(Competition).filter(Competition.season_id == season.id)
        }

    # ── Entita' base ────────────────────────────────────────────────

    def get_league(self, level: LeagueLevel) -> League:
        if level not in self.leagues:
            league = (
                self.db.query(League)
                .filter(League.season_id == self.season.id, League.level == level)
                .first()
            )
            if not league:
                league = League(season_id=self.season.id, level=level)
                self.db.add(league)
                self.db.flush()
            self.leagues[level] = league
        return self.leagues[level]

    def get_team(self, raw_name, level: LeagueLevel | None = None) -> FantaTeam | None:
        """Squadra per nome normalizzato; la crea solo se e' nota la lega di appartenenza."""
        key = norm(raw_name)
        alias = TEAM_ALIASES.get((self.season.year_start, key))
        if alias:
            key = norm(alias)
            raw_name = alias
        if key in self.teams:
            return self.teams[key]
        if level is None:
            self.report["squadre_non_trovate"].add(str(raw_name).strip())
            return None
        team = FantaTeam(
            name=re.sub(r"\s+", " ", str(raw_name)).strip(),
            season_id=self.season.id,
            league_id=self.get_league(level).id,
        )
        self.db.add(team)
        self.db.flush()
        self.teams[key] = team
        return team

    def get_competition(self, comp_type: CompetitionType) -> Competition:
        if comp_type not in self.competitions:
            comp = Competition(
                season_id=self.season.id,
                type=comp_type,
                name=f"{comp_type.value.title()} {self.season.label}",
                is_active=False,
            )
            self.db.add(comp)
            self.db.flush()
            self.competitions[comp_type] = comp
        return self.competitions[comp_type]

    # ── Classifiche ─────────────────────────────────────────────────

    def _files_by_priority(self, pattern: str) -> list[tuple[Path, CompetitionType]]:
        """File tipizzati, con le leghe principali prima delle coppe: le coppe
        referenziano squadre che devono gia' esistere con la loro lega."""
        typed = []
        for path in sorted(self.folder.glob(pattern)):
            comp_type = self._type_from_filename(path.name)
            if comp_type is None:
                self.report["file_saltati"].append(path.name)
                continue
            typed.append((path, comp_type))
        return sorted(typed, key=lambda pc: 0 if pc[1] in MAIN_LEAGUE_TYPES else 1)

    def import_classifiche(self):
        # Anche i calendari delle leghe principali vanno prima delle classifiche
        # delle coppe: quando manca una Classifica (es. Carbon 2024) le squadre
        # nascono dal calendario.
        classifiche = self._files_by_priority("Classifica*.xls*")
        calendari_main = [
            (p, t) for p, t in self._files_by_priority("Calendario*.xls*")
            if t in MAIN_LEAGUE_TYPES
        ]
        for path, comp_type in [pc for pc in classifiche if pc[1] in MAIN_LEAGUE_TYPES]:
            self.report["standings"] += self._import_classifica_sheet(
                pd.read_excel(path, header=None), comp_type
            )
        for path, comp_type in calendari_main:
            self._register_teams_from_calendario(pd.read_excel(path, header=None), comp_type)
        for path, comp_type in [pc for pc in classifiche if pc[1] not in MAIN_LEAGUE_TYPES]:
            self.report["standings"] += self._import_classifica_sheet(
                pd.read_excel(path, header=None), comp_type
            )

    def _register_teams_from_calendario(self, df: pd.DataFrame, comp_type: CompetitionType):
        level = MAIN_LEAGUE_TYPES[comp_type]
        for idx in range(len(df)):
            for col in range(df.shape[1]):
                cell = df.iat[idx, col]
                if isinstance(cell, str) and GIORNATA_RE.search(cell):
                    for ridx in range(idx + 1, len(df)):
                        home = df.iat[ridx, col]
                        if is_blank(home) or (isinstance(home, str) and GIORNATA_RE.search(home)):
                            break
                        shift = 1 if isinstance(home, str) and GIRONE_LETTER_RE.match(home.strip()) else 0
                        for offset in (shift, shift + 3):
                            if col + offset >= df.shape[1]:
                                continue
                            value = df.iat[ridx, col + offset]
                            if isinstance(value, str) and value.strip() and not re.fullmatch(r"[\d.,\-]+", value.strip()):
                                self.get_team(value, level)

    def _type_from_filename(self, filename: str) -> CompetitionType | None:
        match = re.match(r"(?:Classifica|Calendario)[_ ]?(.+?)\.(?:xlsx?|csv)$", filename, re.IGNORECASE)
        if not match:
            return None
        return TYPE_ALIASES.get(match.group(1).strip().upper())

    def _import_classifica_sheet(self, df: pd.DataFrame, comp_type: CompetitionType) -> int:
        comp = self.get_competition(comp_type)
        level = MAIN_LEAGUE_TYPES.get(comp_type)
        count = 0
        current_group = None

        for idx in range(len(df)):
            first = df.iat[idx, 0]
            if isinstance(first, str) and first.strip().lower().startswith("classifica gruppo"):
                group_name = first.strip()[len("Classifica "):]
                current_group = self._get_group(comp, group_name)
                continue
            if isinstance(first, str) and first.strip() == "Pos":
                header = [str(v).strip() if not is_blank(v) else None for v in df.iloc[idx]]
                count += self._import_standing_rows(df, idx + 1, header, comp, level, current_group)
        return count

    def _get_group(self, comp: Competition, name: str) -> CompetitionGroup:
        group = (
            self.db.query(CompetitionGroup)
            .filter(CompetitionGroup.competition_id == comp.id, CompetitionGroup.name == name)
            .first()
        )
        if not group:
            group = CompetitionGroup(competition_id=comp.id, name=name)
            self.db.add(group)
            self.db.flush()
        return group

    def _import_standing_rows(self, df, start, header, comp, level, group) -> int:
        col = {label: i for i, label in enumerate(header) if label}
        count = 0
        for idx in range(start, len(df)):
            pos = df.iat[idx, 0]
            if is_blank(pos) or not str(pos).strip().replace(".0", "").isdigit():
                break
            team = self.get_team(df.iat[idx, col["Squadra"]], level)
            if not team:
                continue

            def num(label, default=0):
                if label not in col or is_blank(df.iat[idx, col[label]]):
                    return default
                return float(df.iat[idx, col[label]])

            played = int(num("G"))
            values = dict(
                played=played,
                wins=int(num("V")),
                draws=int(num("N")),
                losses=int(num("P")),
                goals_for=num("Gf"),
                goals_against=num("Gs"),
                pts=int(num("Pt.")),
                total_score=num("Pt. Totali"),
            )
            standing = (
                self.db.query(CompetitionStanding)
                .filter(
                    CompetitionStanding.competition_id == comp.id,
                    CompetitionStanding.fanta_team_id == team.id,
                    CompetitionStanding.match_day == played,
                )
                .first()
            )
            if standing:
                for k, v in values.items():
                    setattr(standing, k, v)
            else:
                self.db.add(CompetitionStanding(
                    competition_id=comp.id, fanta_team_id=team.id, match_day=played, **values
                ))
                self.db.flush()
            if group:
                self._add_group_team(group, team)
            count += 1
        return count

    def _add_group_team(self, group: CompetitionGroup, team: FantaTeam):
        exists = (
            self.db.query(CompetitionGroupTeam)
            .filter(
                CompetitionGroupTeam.group_id == group.id,
                CompetitionGroupTeam.fanta_team_id == team.id,
            )
            .first()
        )
        if not exists:
            self.db.add(CompetitionGroupTeam(group_id=group.id, fanta_team_id=team.id))
            self.db.flush()

    # ── Calendari / risultati ───────────────────────────────────────

    def import_calendari(self):
        for path, comp_type in self._files_by_priority("Calendario*.xls*"):
            df = pd.read_excel(path, header=None)
            count = self._import_calendario_sheet(df, comp_type)
            if count == 0:
                self.report["file_saltati"].append(f"{path.name} (nessuna partita riconosciuta)")
            self.report["partite"] += count

    def _import_calendario_sheet(self, df: pd.DataFrame, comp_type: CompetitionType) -> int:
        comp = self.get_competition(comp_type)
        level = MAIN_LEAGUE_TYPES.get(comp_type)
        count = 0
        current_phase = CompetitionPhase.REGULAR if level else CompetitionPhase.GROUP
        # Blocchi affiancati: l'intestazione "Nª Giornata lega" appare su piu' colonne
        # della stessa riga; le partite del blocco seguono fino alla prossima intestazione.
        # Nelle coppe righe come "Quarti"/"Semifinali"/"Finale" marcano la fase.
        for idx in range(len(df)):
            first = df.iat[idx, 0]
            if isinstance(first, str) and not GIORNATA_RE.search(first):
                label_phase = phase_from_label(first)
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
                count += self._import_block(df, idx + 1, col, match_day, comp, level, current_phase)
        return count

    def _import_block(self, df, start, col, match_day, comp, level, phase) -> int:
        count = 0
        for idx in range(start, len(df)):
            home = df.iat[idx, col]
            if is_blank(home) or (isinstance(home, str) and GIORNATA_RE.search(home)):
                break
            # Nel Ciempions (fase a gironi) la prima colonna del blocco e' la
            # lettera del girone: tutti gli offset slittano di uno.
            shift = 1 if isinstance(home, str) and GIRONE_LETTER_RE.match(home.strip()) else 0
            if col + shift + 4 >= df.shape[1]:
                break
            home = df.iat[idx, col + shift]
            away = df.iat[idx, col + shift + 3]
            goals = df.iat[idx, col + shift + 4]
            if is_blank(home) or is_blank(away):
                break
            goals_match = GOALS_RE.match(str(goals).strip()) if not is_blank(goals) else None

            home_team = self.get_team(home, level)
            away_team = self.get_team(away, level)
            if not home_team or not away_team:
                continue

            score_home = None if is_blank(df.iat[idx, col + shift + 1]) else float(df.iat[idx, col + shift + 1])
            score_away = None if is_blank(df.iat[idx, col + shift + 2]) else float(df.iat[idx, col + shift + 2])
            goals_home = int(goals_match.group(1)) if goals_match else 0
            goals_away = int(goals_match.group(2)) if goals_match else 0
            if goals_match:
                pts_home, pts_away = (3, 0) if goals_home > goals_away else (
                    (0, 3) if goals_home < goals_away else (1, 1)
                )
            else:
                pts_home = pts_away = 0

            values = dict(
                score_home=score_home, score_away=score_away,
                goals_home=goals_home, goals_away=goals_away,
                pts_home=pts_home, pts_away=pts_away,
                phase=phase,
            )
            existing = (
                self.db.query(MatchResult)
                .filter(
                    MatchResult.competition_id == comp.id,
                    MatchResult.match_day == match_day,
                    MatchResult.fanta_team_home_id == home_team.id,
                    MatchResult.fanta_team_away_id == away_team.id,
                )
                .first()
            )
            if existing:
                for k, v in values.items():
                    setattr(existing, k, v)
            else:
                self.db.add(MatchResult(
                    competition_id=comp.id, match_day=match_day,
                    fanta_team_home_id=home_team.id, fanta_team_away_id=away_team.id,
                    **values,
                ))
                self.db.flush()
            count += 1
        return count

    # ── Rose ────────────────────────────────────────────────────────

    def import_rose(self):
        year = self.season.year_start
        if year == 2018:
            self._import_rose_flat_2018()
        elif year == 2019:
            self._import_rose_sheets_2019()
        elif year == 2020:
            self._import_rose_pdf_2020()
        elif year in (2021, 2022, 2024):
            self._import_rose_blocks(year)
        elif year == 2023:
            self._import_rose_csv_2023()
        else:
            self.report["file_saltati"].append(f"rose {self.season.label}: nessuna fonte strutturata")

    def _get_player(self, raw_name, role, fanta_id=None) -> Player | None:
        name = re.sub(r"\s+", " ", str(raw_name)).strip()
        if not name:
            return None
        player = None
        if fanta_id:
            player = self.db.query(Player).filter(Player.fanta_id == int(fanta_id)).first()
        if not player:
            player = self.db.query(Player).filter(Player.name.ilike(name)).first()
        if not player:
            player = Player(name=name, role=str(role).strip()[:2] or "?", fanta_id=int(fanta_id) if fanta_id else None)
            self.db.add(player)
            self.db.flush()
        elif fanta_id and player.fanta_id is None:
            player.fanta_id = int(fanta_id)
        return player

    def _upsert_roster(self, team: FantaTeam, player: Player, price) -> None:
        entry = (
            self.db.query(FantaRoster)
            .filter(
                FantaRoster.fanta_team_id == team.id,
                FantaRoster.player_id == player.id,
                FantaRoster.season_id == self.season.id,
            )
            .first()
        )
        price = float(price) if not is_blank(price) else 0.0
        if entry:
            entry.purchase_price = price
        else:
            self.db.add(FantaRoster(
                fanta_team_id=team.id, player_id=player.id,
                season_id=self.season.id, purchase_price=price,
            ))
            self.db.flush()
        self.report["roster"] += 1

    def _import_rose_flat_2018(self):
        path = self.folder / "Rose_fantacalcio-tamarros.xlsx"
        if not path.exists():
            self.report["file_saltati"].append(f"rose {self.season.label}: file mancante")
            return
        df = pd.read_excel(path, sheet_name="TutteLeRose")
        for _, row in df.iterrows():
            if is_blank(row.get("GIOCATORE")) or is_blank(row.get("FANTA SQUADRA")):
                continue
            level = getattr(LeagueLevel, str(row.get("lega", "")).strip().upper(), None)
            team = self.get_team(row["FANTA SQUADRA"], level)
            player = self._get_player(row["GIOCATORE"], row.get("RUOLO", "?"))
            if team and player:
                self._upsert_roster(team, player, row.get("MILIONI"))

    def _import_rose_sheets_2019(self):
        path = self.folder / "Rose_fantacalcio-tamarros.xlsx"
        if not path.exists():
            self.report["file_saltati"].append(f"rose {self.season.label}: file mancante")
            return
        for sheet in ("Gold", "Bronze", "Carbon"):
            df = pd.read_excel(path, sheet_name=sheet)
            level = getattr(LeagueLevel, sheet.upper())
            for _, row in df.iterrows():
                if is_blank(row.get("NOME")) or is_blank(row.get("SQUADRA")):
                    continue
                team = self.get_team(row["SQUADRA"], level)
                player = self._get_player(row["NOME"], row.get("RUOLO", "?"))
                if team and player:
                    self._upsert_roster(team, player, row.get("CREDITI"))

    def _import_rose_pdf_2020(self):
        """Il 2020-21 ha le rose solo in PDF: una riga di testo per acquisto,
        formato 'Giocatore prezzo FantaSquadra'. Senza ruolo nel file, i giocatori
        mai visti altrove vengono creati con ruolo '?' e conteggiati nel report."""
        path = self.folder / "Rose_fantacalcio-tamarros.pdf"
        if not path.exists():
            self.report["file_saltati"].append(f"rose {self.season.label}: file mancante")
            return
        try:
            import pdfplumber
        except ImportError:
            self.report["file_saltati"].append(
                f"rose {self.season.label}: serve pdfplumber (pip install pdfplumber)"
            )
            return

        row_re = re.compile(r"^(.+?)\s+(\d+)\s+(.+)$")
        unknown_role = 0
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                for line in (page.extract_text() or "").splitlines():
                    match = row_re.match(line.strip())
                    if not match:
                        continue
                    name, price, team_name = match.groups()
                    team = self.get_team(team_name)
                    if not team:
                        continue
                    existed = self.db.query(Player).filter(Player.name.ilike(name.strip())).first()
                    player = self._get_player(name, "?")
                    if player and not existed and player.role == "?":
                        unknown_role += 1
                    if player:
                        self._upsert_roster(team, player, price)
        if unknown_role:
            self.report["file_saltati"].append(
                f"rose {self.season.label}: {unknown_role} giocatori creati con ruolo '?' (non presente nel PDF)"
            )

    def _import_rose_blocks(self, year: int):
        """Layout TutteLeRose a blocchi affiancati: riga col nome squadra, header
        Ruolo/Calciatore/Squadra/Costo, poi i giocatori."""
        path = (
            self.folder / "doc asta" / "Rose_fantacalcio-tamarros.xlsx"
            if year == 2021
            else self.folder / "Rose_fantacalcio-tamarros.xlsx"
        )
        if not path.exists():
            self.report["file_saltati"].append(f"rose {self.season.label}: file mancante")
            return
        df = pd.read_excel(path, sheet_name="TutteLeRose", header=None)
        for idx in range(len(df)):
            for col in range(df.shape[1]):
                if str(df.iat[idx, col]).strip() != "Ruolo":
                    continue
                # Header trovato: il nome squadra e' nella riga sopra, i giocatori sotto.
                team_name = df.iat[idx - 1, col] if idx > 0 else None
                if is_blank(team_name):
                    continue
                team = self.get_team(team_name)
                if not team:
                    continue
                for ridx in range(idx + 1, len(df)):
                    role = df.iat[ridx, col]
                    name = df.iat[ridx, col + 1] if col + 1 < df.shape[1] else None
                    if is_blank(role) or is_blank(name) or str(role).strip() == "Ruolo":
                        break
                    price = df.iat[ridx, col + 3] if col + 3 < df.shape[1] else None
                    player = self._get_player(name, role)
                    if player:
                        self._upsert_roster(team, player, price)

    def _import_rose_csv_2023(self):
        for pattern, level in (("gold_rose.csv", LeagueLevel.GOLD),
                               ("bronze_rose.csv", LeagueLevel.BRONZE),
                               ("CARBON_rose.csv", LeagueLevel.CARBON)):
            path = self.folder / pattern
            if not path.exists():
                self.report["file_saltati"].append(f"rose {self.season.label}: {pattern} mancante")
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                header = next(reader)
                for row in reader:
                    # Ogni riga dati e' un unico campo quotato contenente a sua volta un CSV.
                    if len(row) == 1:
                        row = next(csv.reader(io.StringIO(row[0])))
                    if len(row) < len(header):
                        continue
                    record = dict(zip(header, row))
                    team = self.get_team(record["Squadra"], level)
                    player = self._get_player(
                        record["Nome"], record.get("Ruolo", "?"),
                        fanta_id=record.get("Fantacalcio_Id") or None,
                    )
                    if team and player:
                        self._upsert_roster(team, player, record.get("Prezzo"))


def seed_seasons(db) -> dict[int, Season]:
    seasons = {}
    for year in range(FIRST_SEASON_YEAR, LAST_SEASON_YEAR + 1):
        label = f"{year}-{str(year + 1)[2:]}"
        season = db.query(Season).filter(Season.label == label).first()
        if not season:
            season = Season(label=label, year_start=year, year_end=year + 1, is_current=False)
            db.add(season)
            db.flush()
        seasons[year] = season
    return seasons


def run(stagioni_dir: Path, years: list[int]) -> None:
    init_db()
    db = SessionLocal()
    try:
        seasons = seed_seasons(db)
        db.commit()
        print(f"Stagioni censite: {FIRST_SEASON_YEAR}-{LAST_SEASON_YEAR + 1} "
              f"({len(seasons)} righe Season)")

        for year in years:
            folder = stagioni_dir / str(year)
            if not folder.is_dir():
                print(f"\n[{year}] cartella non trovata, salto")
                continue
            season = seasons[year]
            report = {
                "standings": 0, "partite": 0, "roster": 0,
                "squadre_non_trovate": set(), "file_saltati": [],
            }
            importer = SeasonImporter(db, season, folder, report)
            importer.import_classifiche()
            importer.import_calendari()
            importer.import_rose()
            db.commit()

            print(f"\n[{season.label}] standings: {report['standings']} | "
                  f"partite: {report['partite']} | righe rosa: {report['roster']}")
            if report["squadre_non_trovate"]:
                print(f"  squadre non riconosciute (saltate): {sorted(report['squadre_non_trovate'])}")
            if report["file_saltati"]:
                print(f"  file/fonti saltate: {report['file_saltati']}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, help="Cartella STAGIONI")
    parser.add_argument("--years", nargs="*", type=int, default=list(DEFAULT_ETL_YEARS))
    args = parser.parse_args()

    stagioni = Path(args.dir)
    if not stagioni.is_dir():
        sys.exit(f"Cartella non trovata: {stagioni}")
    run(stagioni, args.years)
