"""Servizio di calcolo punteggio Live per la competizione SILVER (senza bot).

Integra la logica di live_score.py:
  1. apileague.fantacalcio.it -> gaming/v1/teamLineup per la competizione SILVER
  2. fantacalcio.it -> flusso Protobuf live ufficiale (/api/v1/SignedUri + .dat)
     con fallback automatico sull'archivio HTML voti-fantacalcio-serie-a
  3. apileague.fantacalcio.it -> onboarding/v1/league/players & settings
  4. Simulazione live di:
     - Fantavoto calciatori con tutti i bonus/malus di lega (bnMls)
     - Sostituzioni automatiche (Tradizionale, Ibrido, Dinamico + Riserva d'ufficio)
     - Voto base provvisorio 6.0 ⏳ per i calciatori la cui squadra deve ancora giocare / è in corso
     - Modificatore Difesa (smodd)
     - Fasce Gol di squadra (step)
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import logging
import re
import struct
import threading
import time

import requests
from sqlalchemy.orm import Session

from app.config import settings
from app.models.fanta_allenatore import FantaAllenatore
from app.models.fanta_team import FantaTeam, FantaTeamCoach, League
from app.models.season import Season
from app.services.leghe_client import BROWSER_HEADERS, LEGHE_DISABLED_MESSAGE, LegheClient, LegheDisabledError

logger = logging.getLogger(__name__)

FANTA_BASE = "https://www.fantacalcio.it/"

# Regolamento Tamarros: al massimo 3 sostituzioni, solo sullo stesso ruolo; senza
# sostituto che prende voto si prende 4 d'ufficio (se restano sostituzioni libere), se no 0.
MAX_SUBSTITUTIONS = 3
OFFICE_VOTE = 4.0

MATCH_EVENT_INFO = {
    1: {"name": "Ammonizione", "symbol": "🟨", "pts": -0.5},
    2: {"name": "Espulsione", "symbol": "🟥", "pts": -1.0},
    3: {"name": "Gol segnato", "symbol": "⚽", "pts": +3.0},
    4: {"name": "Gol subito", "symbol": "🥅", "pts": -1.0},
    7: {"name": "Rigore parato", "symbol": "🧤", "pts": +3.0},
    8: {"name": "Rigore sbagliato", "symbol": "❌", "pts": -3.0},
    9: {"name": "Rigore segnato", "symbol": "⚽(R)", "pts": +3.0},
    10: {"name": "Autogol", "symbol": "🤦", "pts": -2.0},
    21: {"name": "Assist", "symbol": "🎯", "pts": +1.0},
    22: {"name": "Assist da fermo", "symbol": "🎯", "pts": +1.0},
    23: {"name": "Assist Gold", "symbol": "🎯", "pts": +1.0},
    16: {"name": "Player of the match", "symbol": "⭐(MVP)", "pts": +1.0},
}


# ===========================================================================
# 1. PARSER PROTOBUF SERIE A LIVE + FALLBACK ARCHIVIO VOTI
# ===========================================================================

def _parse_varint(buf: bytes, pos: int) -> tuple[int, int]:
    res = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        res |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return res, pos


def _parse_raw_proto(buf: bytes, pos: int = 0, end: int | None = None) -> list[tuple[int, str, int | bytes]]:
    if end is None:
        end = len(buf)
    fields = []
    while pos < end:
        tag, pos = _parse_varint(buf, pos)
        wire_type = tag & 7
        field_num = tag >> 3
        if wire_type == 0:
            val, pos = _parse_varint(buf, pos)
            fields.append((field_num, "varint", val))
        elif wire_type == 1:
            val = buf[pos : pos + 8]
            pos += 8
            fields.append((field_num, "64bit", val))
        elif wire_type == 2:
            length, pos = _parse_varint(buf, pos)
            val = buf[pos : pos + length]
            pos += length
            fields.append((field_num, "len", val))
        elif wire_type == 5:
            val = buf[pos : pos + 4]
            pos += 4
            fields.append((field_num, "32bit", val))
        else:
            break
    return fields


def fetch_serie_a_voti_archive(giornata: int) -> tuple[dict[int, dict], dict[str, int]]:
    """Fallback quando il flusso Protobuf live è concluso/disattivato:
    recupera la tabella voti ufficiale da https://www.fantacalcio.it/voti-fantacalcio-serie-a."""
    headers = {
        "User-Agent": BROWSER_HEADERS["user-agent"],
        "Referer": f"{FANTA_BASE}voti-fantacalcio-serie-a",
    }
    main_url = f"{FANTA_BASE}voti-fantacalcio-serie-a"
    try:
        r_main = requests.get(main_url, headers=headers, timeout=12)
        r_main.raise_for_status()
        html = r_main.text
    except Exception as e:
        logger.warning("Impossibile recuperare pagina voti archivio: %s", e)
        return {}, {}

    m_season = re.search(r'<select[^>]*id="season"[^>]*>.*?<option[^>]*value="([^"]*)"', html, re.DOTALL)
    season_slug = m_season.group(1).replace("/", "-") if m_season else "2026-27"

    m_cur_mw = re.search(r'<select[^>]*id="matchweek"[^>]*>.*?<option[^>]*selected[^>]*value="(\d+)"', html, re.DOTALL)
    cur_matchweek = int(m_cur_mw.group(1)) if m_cur_mw else None

    if cur_matchweek and giornata > cur_matchweek:
        return {}, {}

    if cur_matchweek != giornata:
        round_url = f"{FANTA_BASE}voti-fantacalcio-serie-a/{season_slug}/{giornata}"
        try:
            r_round = requests.get(round_url, headers=headers, timeout=12)
            if r_round.status_code == 200 and "grades-table" in r_round.text:
                html = r_round.text
            else:
                return {}, {}
        except Exception:
            return {}, {}
    else:
        if "grades-table" not in html:
            return {}, {}

    def parse_float(val_str: str) -> float | None:
        if not val_str or val_str.lower() in ["-", "*", "s.v.", "sv", ""]:
            return None
        val_str = val_str.replace(",", ".").strip()
        try:
            val = float(val_str)
            if val >= 50:
                return None
            return val
        except ValueError:
            return None

    players: dict[int, dict] = {}
    teams_status: dict[str, int] = {}

    team_names = re.findall(r'<img[^>]*class="team-badge"[^>]*title="([^"]+)"', html)
    for tm in team_names:
        if tm:
            teams_status[tm.upper()] = 4

    for chunk in html.split("<tr"):
        if "player-link" not in chunk:
            continue
        m_id = re.search(r'/squadre/[^/]+/[^/]+/(\d+)', chunk)
        if not m_id:
            m_id = re.search(r'href="[^"]*/(\d+)(?:/\d{4}-\d{2})?"', chunk)
        if not m_id:
            continue
        pid = int(m_id.group(1))

        m_name = re.search(r'class="player-name[^"]*"[^>]*>\s*<span>(.*?)</span>', chunk)
        pname = m_name.group(1).strip() if m_name else f"ID:{pid}"

        m_v = re.search(r'class="player-grade\s*"[^>]*data-value="([^"]*)"', chunk)
        v = parse_float(m_v.group(1)) if m_v else None

        m_fv = re.search(r'class="player-fanta-grade\s*"[^>]*data-value="([^"]*)"', chunk)
        fv = parse_float(m_fv.group(1)) if m_fv else None

        if fv is None and v is not None:
            fv = v

        has_yellow = "yellow-card" in chunk
        has_red = "red-card" in chunk

        events_dict = {
            "yellow": 1 if has_yellow else 0,
            "red": 1 if has_red else 0,
            "goals": 0,
            "conceded": 0,
            "pen_scored": 0,
            "pen_missed": 0,
            "pen_saved": 0,
            "autogol": 0,
            "assist": 0,
            "assist_fermo": 0,
            "assist_gold": 0,
            "motm": 0,
            "clean_sheet": 0,
        }

        for b_elem in re.finditer(
            r'<span[^>]*class="player-bonus[^"]*"[^>]*data-value="(\d+)"[^>]*title="([^"]*)"', chunk
        ):
            cnt = int(b_elem.group(1))
            title = b_elem.group(2).strip()
            if cnt > 0:
                if title == "Gol segnati":
                    events_dict["goals"] += cnt
                elif title == "Gol subiti":
                    events_dict["conceded"] += cnt
                elif title == "Autoreti":
                    events_dict["autogol"] += cnt
                elif title == "Rigori segnati":
                    events_dict["pen_scored"] += cnt
                elif title == "Rigori sbagliati":
                    events_dict["pen_missed"] += cnt
                elif title == "Rigori parati":
                    events_dict["pen_saved"] += cnt
                elif title == "Assist":
                    events_dict["assist"] += cnt
                elif title == "Player of the match":
                    events_dict["motm"] += cnt

        m_role = re.search(r'<span[^>]*class="role"[^>]*data-value="([^"]*)"', chunk)
        role_char = m_role.group(1).upper() if m_role else ""

        if role_char == "P" and v is not None and events_dict["conceded"] == 0:
            events_dict["clean_sheet"] = 1

        ev_symbols = []
        if events_dict["goals"] > 0:
            ev_symbols.append("⚽" if events_dict["goals"] == 1 else f"⚽x{events_dict['goals']}")
        if events_dict["pen_scored"] > 0:
            ev_symbols.append("⚽(R)" if events_dict["pen_scored"] == 1 else f"⚽(R)x{events_dict['pen_scored']}")
        if events_dict["assist"] > 0:
            ev_symbols.append("🎯" if events_dict["assist"] == 1 else f"🎯x{events_dict['assist']}")
        if events_dict["pen_saved"] > 0:
            ev_symbols.append("🧤" if events_dict["pen_saved"] == 1 else f"🧤x{events_dict['pen_saved']}")
        if events_dict["clean_sheet"] > 0:
            ev_symbols.append("🧤(CS)")
        if events_dict["conceded"] > 0:
            ev_symbols.append("🥅" if events_dict["conceded"] == 1 else f"🥅x{events_dict['conceded']}")
        if events_dict["yellow"] > 0:
            ev_symbols.append("🟨")
        if events_dict["red"] > 0:
            ev_symbols.append("🟥")
        if events_dict["pen_missed"] > 0:
            ev_symbols.append("❌" if events_dict["pen_missed"] == 1 else f"❌x{events_dict['pen_missed']}")
        if events_dict["autogol"] > 0:
            ev_symbols.append("🤦" if events_dict["autogol"] == 1 else f"🤦x{events_dict['autogol']}")
        if events_dict["motm"] > 0:
            ev_symbols.append("⭐(MVP)")

        ev_formatted = " ".join(ev_symbols)

        players[pid] = {
            "id": pid,
            "name": pname,
            "role": role_char,
            "vote": v,
            "fanta_vote": fv,
            "events": None,
            "events_dict": events_dict,
            "events_formatted": ev_formatted,
        }

    return players, teams_status


def fetch_serie_a_live_votes(giornata: int, season_id: int | None = None) -> tuple[dict[int, dict], dict[str, int]]:
    """Recupera i voti live ufficiali della Serie A tramite SignedUri Fantacalcio (.dat).
    Se la giornata è conclusa e lo stream live non è attivo, effettua il fallback su voti-fantacalcio-serie-a."""
    if season_id is None:
        try:
            season_id = int(settings.fanta_year_quotazioni)
        except (ValueError, TypeError):
            season_id = 21

    headers = {
        "User-Agent": BROWSER_HEADERS["user-agent"],
        "Referer": f"{FANTA_BASE}live-serie-a",
        "Origin": "https://www.fantacalcio.it",
        "Content-Type": "application/json",
    }
    resource = f"https://api.fantacalcio.it/v1/st/{season_id}/matches/live/{giornata}.dat"
    try:
        r_sign = requests.post(
            f"{FANTA_BASE}api/v1/SignedUri",
            json={"resourcesUri": [resource]},
            headers=headers,
            timeout=10,
        )
        r_sign.raise_for_status()
        s_uri = r_sign.json()[resource]["resources"][0]["signedUri"]
        r_dat = requests.get(s_uri, headers=headers, timeout=10)
        r_dat.raise_for_status()
        buf = r_dat.content
    except Exception as e:
        logger.info("Stream Protobuf live non disponibile (%s). Recupero archivio voti...", e)
        arch_players, arch_status = fetch_serie_a_voti_archive(giornata)
        if arch_players:
            return arch_players, arch_status
        return {}, {}

    raw = _parse_raw_proto(buf)
    matches_raw = [v for fn, wt, v in raw if fn == 1 and wt == "len"]

    players: dict[int, dict] = {}
    teams_status: dict[str, int] = {}

    for m_raw in matches_raw:
        m_fields = _parse_raw_proto(m_raw)
        m_info = {fn: v for fn, wt, v in m_fields}
        home = m_info.get(13, b"")
        away = m_info.get(14, b"")
        home_str = home.decode("utf-8", errors="ignore") if isinstance(home, bytes) else str(home or "")
        away_str = away.decode("utf-8", errors="ignore") if isinstance(away, bytes) else str(away or "")
        status = m_info.get(10, 0)
        if home_str:
            teams_status[home_str.upper()] = status
        if away_str:
            teams_status[away_str.upper()] = status

        for fn, wt, v in m_fields:
            if fn in (15, 16) and wt == "len":
                p_fields = _parse_raw_proto(v)
                p_dict = {}
                for p_fn, p_wt, p_val in p_fields:
                    if p_fn == 1:
                        p_dict["id"] = p_val
                    elif p_fn == 2:
                        p_dict["name"] = p_val.decode("utf-8", errors="ignore")
                    elif p_fn == 3:
                        p_dict["role"] = p_val.decode("utf-8", errors="ignore")
                    elif p_fn == 4 and p_wt == "64bit":
                        v_num = round(struct.unpack("<d", p_val)[0], 2)
                        p_dict["vote"] = v_num
                    elif p_fn == 5:
                        p_dict["events"] = p_val
                    elif p_fn == 12 and p_wt == "64bit":
                        fv_num = round(struct.unpack("<d", p_val)[0], 2)
                        p_dict["fanta_vote"] = fv_num

                pid = p_dict.get("id")
                if pid:
                    raw_v = p_dict.get("vote")
                    ev_bytes = p_dict.get("events")
                    ev_list = list(ev_bytes) if isinstance(ev_bytes, (bytes, bytearray)) else list(ev_bytes or [])
                    role_str = (p_dict.get("role") or "").upper()
                    conceded_cnt = ev_list.count(4)

                    events_dict = {
                        "yellow": ev_list.count(1),
                        "red": ev_list.count(2),
                        "goals": ev_list.count(3),
                        "conceded": conceded_cnt,
                        "pen_saved": ev_list.count(7),
                        "pen_missed": ev_list.count(8),
                        "pen_scored": ev_list.count(9),
                        "autogol": ev_list.count(10),
                        "assist": ev_list.count(21),
                        "assist_fermo": ev_list.count(22),
                        "assist_gold": ev_list.count(23),
                        "motm": ev_list.count(16),
                        "clean_sheet": 1 if (role_str == "P" and conceded_cnt == 0 and raw_v is not None) else 0,
                    }
                    p_dict["events_dict"] = events_dict

                    if raw_v is not None and 0 < raw_v <= 10 and p_dict.get("fanta_vote") is None:
                        p_dict["fanta_vote"] = raw_v
                    players[pid] = p_dict

    return players, teams_status


def get_current_matchday() -> int:
    """Rileva la giornata corrente di Serie A da fantacalcio.it."""
    url = f"{FANTA_BASE}live-serie-a"
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": BROWSER_HEADERS["user-agent"]})
        resp.raise_for_status()
        m = re.search(r"Giornata\s+(\d+)", resp.text, re.I)
        if m:
            return int(m.group(1))
    except Exception as e:
        logger.warning("Impossibile rilevare giornata corrente: %s", e)
    return 1


# ===========================================================================
# 2. FORMATTazione EVENTI E CALCOLO FANTAVOTO / SOSTITUZIONI / MODIFICATORE / GOL
# ===========================================================================

def format_player_events(events_raw: bytes | bytearray | list | None) -> str:
    """Formatta gli eventi bonus/malus del calciatore in simboli grafici compatti."""
    if not events_raw:
        return ""
    ev_list = list(events_raw) if isinstance(events_raw, (bytes, bytearray)) else list(events_raw)
    counts: dict[int, int] = {}
    for code in ev_list:
        if code in MATCH_EVENT_INFO:
            counts[code] = counts.get(code, 0) + 1

    parts = []
    order = [3, 9, 21, 22, 23, 7, 4, 1, 2, 8, 10, 16]
    for code in order:
        cnt = counts.get(code, 0)
        if cnt <= 0:
            continue
        sym = MATCH_EVENT_INFO[code]["symbol"]
        if cnt > 1:
            parts.append(f"{sym}x{cnt}")
        else:
            parts.append(sym)

    return " ".join(parts)


def format_b_events(b_str: str | None) -> str:
    """Formatta la stringa b ufficiale di Fantacalcio (16 campi separati da ;) in simboli grafici."""
    if not b_str:
        return ""
    parts = b_str.split(";")
    if len(parts) < 16:
        return ""
    try:
        vals = [int(p) for p in parts]
    except Exception:
        return ""

    symbols = []
    if vals[2] > 0:
        symbols.append("⚽" if vals[2] == 1 else f"⚽x{vals[2]}")
    if vals[6] > 0:
        symbols.append("⚽(R)" if vals[6] == 1 else f"⚽(R)x{vals[6]}")
    assists = vals[12] + vals[13] + vals[14]
    if assists > 0:
        symbols.append("🎯" if assists == 1 else f"🎯x{assists}")
    if vals[4] > 0:
        symbols.append("🧤" if vals[4] == 1 else f"🧤x{vals[4]}")
    if vals[10] > 0:
        symbols.append("🧤(CS)" if vals[10] == 1 else f"🧤(CS)x{vals[10]}")
    if vals[3] > 0:
        symbols.append("🥅" if vals[3] == 1 else f"🥅x{vals[3]}")
    if vals[0] > 0:
        symbols.append("🟨" if vals[0] == 1 else f"🟨x{vals[0]}")
    if vals[1] > 0:
        symbols.append("🟥" if vals[1] == 1 else f"🟥x{vals[1]}")
    if vals[5] > 0:
        symbols.append("❌" if vals[5] == 1 else f"❌x{vals[5]}")
    if vals[7] > 0:
        symbols.append("🤦" if vals[7] == 1 else f"🤦x{vals[7]}")
    if vals[8] > 0:
        symbols.append("⭐(GV)")
    if vals[9] > 0:
        symbols.append("⭐(GP)")
    if vals[15] > 0:
        symbols.append("⭐(MVP)" if vals[15] == 1 else f"⭐(MVP)x{vals[15]}")
    return " ".join(symbols)


def calculate_player_fanta_vote(
    pure_vote: float | None,
    role: str,
    events_dict: dict | None,
    league_settings: dict | None,
    fallback_fv: float | None = None,
) -> tuple[float | None, list[str]]:
    """Calcola il Fantavoto applicando tutte le regole e bonus/malus specifici della lega (bnMls)."""
    bnMls = ((league_settings or {}).get("lcnps") or {}).get("bnMls") or {}
    role_idx = {"P": 0, "D": 1, "C": 2, "A": 3}.get(role.upper(), 0)

    ev = events_dict or {}
    yellow = ev.get("yellow", 0)

    if pure_vote is None and yellow > 0:
        bmycsv = float(bnMls.get("bmycsv", 0))
        if bmycsv > 0:
            pure_vote = bmycsv

    if pure_vote is None:
        return None, []

    bmgs = (bnMls.get("bmgs") or [3, 3, 3, 3])[role_idx]
    bmgc = (bnMls.get("bmgc") or [-1, -1, -1, -1])[role_idx]
    bmpsc = (bnMls.get("bmpsc") or [3, 3, 3, 3])[role_idx]
    bmpns = (bnMls.get("bmpns") or [-3, -3, -3, -3])[role_idx]
    bmpsa = (bnMls.get("bmpsa") or [3, 3, 3, 3])[role_idx]
    bmyc = (bnMls.get("bmyc") or [-0.5, -0.5, -0.5, -0.5])[role_idx]
    bmrc = (bnMls.get("bmrc") or [-1, -1, -1, -1])[role_idx]
    bmog = (bnMls.get("bmog") or [-2, -2, -2, -2])[role_idx]
    bmass = (bnMls.get("bmass") or [1, 1, 1, 1])[role_idx]
    bmasf = (bnMls.get("bmasf") or [1, 1, 1, 1])[role_idx]
    bmasg = (bnMls.get("bmasg") or [1, 1, 1, 1])[role_idx]
    motm = (bnMls.get("motm") or [0, 0, 0, 0])[role_idx]
    bmcsh = float(bnMls.get("bmcsh", 0))

    bonus = 0.0
    symbols = []

    goals = ev.get("goals", 0)
    if goals > 0:
        bonus += goals * bmgs
        symbols.append("⚽" if goals == 1 else f"⚽x{goals}")

    pen_scored = ev.get("pen_scored", 0)
    if pen_scored > 0:
        bonus += pen_scored * bmpsc
        symbols.append("⚽(R)" if pen_scored == 1 else f"⚽(R)x{pen_scored}")

    assist_std = ev.get("assist", 0)
    assist_fermo = ev.get("assist_fermo", 0)
    assist_gold = ev.get("assist_gold", 0)
    tot_assists = assist_std + assist_fermo + assist_gold
    if tot_assists > 0:
        bonus += assist_std * bmass + assist_fermo * bmasf + assist_gold * bmasg
        symbols.append("🎯" if tot_assists == 1 else f"🎯x{tot_assists}")

    pen_saved = ev.get("pen_saved", 0)
    if pen_saved > 0:
        bonus += pen_saved * bmpsa
        symbols.append("🧤" if pen_saved == 1 else f"🧤x{pen_saved}")

    conceded = ev.get("conceded", 0)
    if conceded > 0:
        bonus += conceded * bmgc
        symbols.append("🥅" if conceded == 1 else f"🥅x{conceded}")

    clean_sheet = ev.get("clean_sheet", 0)
    is_clean = (clean_sheet > 0) or (conceded == 0 and pure_vote is not None and 0 < pure_vote <= 10)
    if role.upper() == "P" and is_clean and bmcsh > 0:
        bonus += bmcsh
        symbols.append("🧤(CS)")

    if yellow > 0:
        bonus += yellow * bmyc
        symbols.append("🟨" if yellow == 1 else f"🟨x{yellow}")

    red = ev.get("red", 0)
    if red > 0:
        bonus += red * bmrc
        symbols.append("🟥" if red == 1 else f"🟥x{red}")

    pen_missed = ev.get("pen_missed", 0)
    if pen_missed > 0:
        bonus += pen_missed * bmpns
        symbols.append("❌" if pen_missed == 1 else f"❌x{pen_missed}")

    autogol = ev.get("autogol", 0)
    if autogol > 0:
        bonus += autogol * bmog
        symbols.append("🤦" if autogol == 1 else f"🤦x{autogol}")

    motm_cnt = ev.get("motm", 0)
    if motm_cnt > 0:
        bonus += motm_cnt * motm
        symbols.append("⭐(MVP)" if motm_cnt == 1 else f"⭐(MVP)x{motm_cnt}")

    calc_fv = round(pure_vote + bonus, 2)
    return calc_fv, symbols


def _substitution_record(out_name: str, out_role: str, entry: dict) -> dict:
    return {
        "out_name": out_name,
        "in_name": entry["name"],
        "role": out_role,
        "out_role": out_role,
        "in_role": entry.get("in_role", out_role),
        "vote": entry["vote"],
        "fanta_vote": entry["fanta_vote"],
        "is_base_vote": entry.get("is_base_vote", False),
        "events_formatted": entry.get("events_formatted", ""),
    }


def calculate_substitutions(
    starts: list[dict],
    bench: list[dict],
    master_players: dict[int, dict],
    live_votes: dict[int, dict],
    teams_status: dict[str, int],
    league_settings: dict | None = None,
    initial_module: str = "",
) -> tuple[list[dict], list[dict], str]:
    """Sostituzioni secondo il regolamento Tamarros, indipendenti dalle impostazioni di leghe:
    al massimo MAX_SUBSTITUTIONS, solo sullo stesso ruolo (nessun cambio modulo) e con i
    sostituti in ordine di panchina. Chi non gioca e non ha un sostituto che prende voto
    prende OFFICE_VOTE d'ufficio se restano sostituzioni libere (quelle vere hanno la
    priorita'), altrimenti 0."""

    def describe(entry: dict) -> dict:
        pid = entry.get("pid")
        master = master_players.get(pid, {})
        live = live_votes.get(pid, {})
        return {
            "pid": pid,
            "live": live,
            "name": master.get("name") or live.get("name") or entry.get("pn") or f"ID:{pid}",
            "role": master.get("role") or live.get("role") or entry.get("r") or "?",
            "club": master.get("club", "-"),
            "match_status": teams_status.get(master.get("tname", "").upper(), None),
        }

    def has_vote(live: dict) -> bool:
        vote = live.get("vote")
        return vote is not None and 0 < vote <= 10

    def voted(p: dict, **extra) -> dict:
        live = p["live"]
        fv, symbols = calculate_player_fanta_vote(
            pure_vote=live.get("vote"),
            role=p["role"],
            events_dict=live.get("events_dict"),
            league_settings=league_settings,
            fallback_fv=live.get("fanta_vote"),
        )
        return {
            "pid": p["pid"], "name": p["name"], "role": p["role"], "club": p["club"],
            "vote": live.get("vote"),
            "fanta_vote": fv if fv is not None else (live.get("fanta_vote") or live.get("vote")),
            "events_formatted": " ".join(symbols) if symbols else live.get("events_formatted", ""),
            "is_sub": False, "is_base_vote": False, "status": "Votato",
            **extra,
        }

    def provisional(p: dict, **extra) -> dict:
        """Voto base 6.0 per chi non ha ancora giocato (la squadra deve giocare o e' in corso)."""
        base_vote = 6.0
        base_fv = base_vote
        events = ""
        if p["role"].upper() == "P":
            bnMls = ((league_settings or {}).get("lcnps") or {}).get("bnMls") or {}
            bmcsh = float(bnMls.get("bmcsh", 0))
            if bmcsh > 0:
                base_fv = round(base_vote + bmcsh, 2)
                events = "🧤(CS)"
        return {
            "pid": p["pid"], "name": p["name"], "role": p["role"], "club": p["club"],
            "vote": base_vote, "fanta_vote": base_fv, "events_formatted": events,
            "is_sub": False, "is_base_vote": True,
            "status": "in corso" if p["match_status"] == 3 else "in attesa",
            **extra,
        }

    starters = [describe(s) for s in starts]
    field_players: list[dict | None] = []
    for p in starters:
        if has_vote(p["live"]):
            field_players.append(voted(p))
        elif p["match_status"] == 4:
            field_players.append(None)  # partita finita senza voto: da sostituire
        else:
            field_players.append(provisional(p))

    substitutions_done: list[dict] = []

    # 1. Sostituti veri, in ordine di panchina, fino al massimo consentito
    for b in bench:
        if len(substitutions_done) >= MAX_SUBSTITUTIONS:
            break
        sub = describe(b)
        sub_has_vote = has_vote(sub["live"])
        if sub["match_status"] == 4 and not sub_has_vote:
            continue
        slot = next(
            (i for i, p in enumerate(starters) if field_players[i] is None and p["role"] == sub["role"]),
            None,
        )
        if slot is None:
            continue
        out = starters[slot]
        extra = {"is_sub": True, "replaced_name": out["name"], "out_role": out["role"], "in_role": sub["role"]}
        if sub_has_vote:
            entry = voted(sub, status=f"SUB IN (per {out['name']})", **extra)
        else:
            entry = provisional(sub, **extra)
        field_players[slot] = entry
        substitutions_done.append(_substitution_record(out["name"], out["role"], entry))

    # 2. Chi e' rimasto scoperto: 4 d'ufficio se restano sostituzioni libere, altrimenti 0.
    # Finche' un titolare deve ancora giocare il 4 e' provvisorio: se quel titolare resta
    # senza voto consuma una sostituzione e il 4 puo' diventare 0.
    day_open = any(e is not None and e["is_base_vote"] and not e["is_sub"] for e in field_players)
    for i, p in enumerate(starters):
        if field_players[i] is not None:
            continue
        if len(substitutions_done) < MAX_SUBSTITUTIONS:
            entry = {
                "pid": p["pid"], "name": f"Riserva d'ufficio [{p['role']}]", "role": p["role"], "club": "-",
                "vote": OFFICE_VOTE, "fanta_vote": OFFICE_VOTE, "events_formatted": "",
                "is_sub": True, "is_base_vote": False, "is_default_reserve": True,
                "replaced_name": p["name"], "out_role": p["role"], "in_role": p["role"],
                "status": f"Voto d'ufficio ({OFFICE_VOTE:.1f})" + (" provvisorio" if day_open else ""),
            }
            field_players[i] = entry
            substitutions_done.append(_substitution_record(p["name"], p["role"], entry))
        else:
            field_players[i] = {
                "pid": p["pid"], "name": p["name"], "role": p["role"], "club": p["club"],
                "vote": None, "fanta_vote": None, "events_formatted": "",
                "is_sub": False, "is_base_vote": False,
                "status": f"0 (oltre le {MAX_SUBSTITUTIONS} sostituzioni)",
            }

    counts = {"D": 0, "C": 0, "A": 0}
    for p in starters:
        if p["role"] in counts:
            counts[p["role"]] += 1
    module = initial_module or f"{counts['D']}{counts['C']}{counts['A']}"
    return field_players, substitutions_done, module


def calculate_defense_modifier(
    field_players: list[dict],
    smodd: dict | None,
) -> tuple[float, str]:
    """Calcola il Modificatore Difesa in base alle regole di lega (smodd)."""
    if not smodd or not smodd.get("smodva"):
        return 0.0, "Disattivato"

    # La riserva d'ufficio non conta: e' come aver schierato un difensore in meno
    real_players = [p for p in field_players if not p.get("is_default_reserve")]
    gk = next(
        (p for p in real_players if p.get("role") == "P" and p.get("vote") is not None and 0 < p.get("vote") <= 10),
        None,
    )
    defenders = [
        p for p in real_players if p.get("role") == "D" and p.get("vote") is not None and 0 < p.get("vote") <= 10
    ]

    include_gk = smodd.get("smoddg", True)

    if len(defenders) < 4:
        return 0.0, f"Meno di 4 difensori a voto in campo ({len(defenders)}/4)"

    if include_gk and gk is None:
        return 0.0, "Portiere senza voto (richiesto per il modificatore)"

    def_sorted = sorted(defenders, key=lambda x: x["vote"], reverse=True)
    if include_gk:
        top_def = def_sorted[:3]
        avg_votes = [gk["vote"]] + [d["vote"] for d in top_def]
        avg_desc = f"{gk['name']} ({gk['vote']:.1f}) + " + ", ".join(f"{d['name']} ({d['vote']:.1f})" for d in top_def)
    else:
        top_def = def_sorted[:4]
        avg_votes = [d["vote"] for d in top_def]
        avg_desc = ", ".join(f"{d['name']} ({d['vote']:.1f})" for d in top_def)

    avg = round(sum(avg_votes) / len(avg_votes), 3)

    points_table = smodd.get("smodva", [0, 1, 1, 3, 3, 5])
    low = float(smodd.get("smodld", 6.0))

    if avg < low:
        mod_pts = float(points_table[0])
    else:
        step = int((avg - low) // 0.25) + 1
        step_idx = min(step, len(points_table) - 1)
        mod_pts = float(points_table[step_idx])

    sign = f"+{mod_pts:.1f}" if mod_pts > 0 else f"{mod_pts:.1f}"
    detail = f"Media {avg:.2f} [{avg_desc}] -> {sign} pt"
    return mod_pts, detail


def calculate_team_goals(score: float | None, step_settings: dict | None = None) -> tuple[int, str]:
    """Calcola i gol segnati dalla squadra in base al punteggio totale e alle soglie di lega."""
    if score is None:
        return 0, "Punteggio non disponibile"
    stlmt = float((step_settings or {}).get("stlmt", 66))
    stgoal = (step_settings or {}).get("stgoal", [4])
    step = float(stgoal[0]) if stgoal else 4.0

    if score < stlmt:
        diff_next = round(stlmt - score, 2)
        return 0, f"0 gol (1° gol a {stlmt:.1f} pt: mancano {diff_next:.1f} pt)"

    goals = 1 + int((score - stlmt) // step)
    next_goal_at = stlmt + (goals * step)
    diff_next = round(next_goal_at - score, 2)
    current_threshold = stlmt + ((goals - 1) * step)
    detail = f"{goals} gol (soglia: {current_threshold:.1f} pt | prossimo gol a {next_goal_at:.1f} pt: mancano {diff_next:.1f} pt)"
    return goals, detail


def process_team_lineup(
    team_raw: dict,
    team_name: str,
    is_calculated: bool,
    master_players: dict[int, dict],
    live_votes: dict[int, dict],
    teams_status: dict[str, int],
    league_settings: dict,
) -> dict:
    """Elabora una singola squadra e calcola punteggio live, sostituzioni, modificatore e gol."""
    tid = team_raw.get("tid")
    mdl = str(team_raw.get("mdl") or "?")
    tot_official = team_raw.get("tot")
    starts = team_raw.get("starts") or []
    bench = team_raw.get("bench") or []

    smodd = (league_settings.get("lcnps") or {}).get("smodd")
    step_settings = (league_settings.get("lcnps") or {}).get("step") or {}

    if is_calculated:
        field_players = []
        substitutions = []

        bench_in = []
        for b in bench:
            if b.get("ptype") == "E":
                b_pid = b.get("pid")
                b_master = master_players.get(b_pid, {})
                b_name = b_master.get("name") or b.get("pn") or f"ID:{b_pid}"
                b_role = b_master.get("role") or b.get("r") or "?"
                b_club = b_master.get("club", "-")
                b_cscr = b.get("cscr")
                b_scr = b.get("scr")
                b_v = b_scr if b_scr is not None and b_scr < 50 else b_cscr
                b_fv = b_cscr if b_cscr is not None and b_cscr < 50 else b_v
                b_ev_str = format_b_events(b.get("b"))
                bench_in.append({
                    "pid": b_pid,
                    "role": b_role,
                    "name": b_name,
                    "club": b_club,
                    "vote": b_v,
                    "fanta_vote": b_fv,
                    "events_formatted": b_ev_str,
                    "is_sub": True,
                    "is_base_vote": False,
                    "status": "SUB IN",
                    "used": False,
                })

        for s in starts:
            pid = s.get("pid")
            master = master_players.get(pid, {})
            pname = master.get("name") or s.get("pn") or f"ID:{pid}"
            prole = master.get("role") or s.get("r") or "?"
            pclub = master.get("club", "-")
            ptype = s.get("ptype", "-")
            cscr = s.get("cscr")
            scr = s.get("scr")
            s_ev_str = format_b_events(s.get("b"))

            if ptype == "U":
                matching_sub = next((b for b in bench_in if not b["used"] and b["role"] == prole), None)
                if not matching_sub:
                    matching_sub = next((b for b in bench_in if not b["used"]), None)

                if matching_sub:
                    matching_sub["used"] = True
                    matching_sub["replaced_name"] = pname
                    field_players.append(matching_sub)
                    substitutions.append({
                        "out_name": pname,
                        "in_name": matching_sub["name"],
                        "role": prole,
                        "out_role": prole,
                        "in_role": matching_sub["role"],
                        "vote": matching_sub["vote"],
                        "fanta_vote": matching_sub["fanta_vote"],
                        "is_base_vote": False,
                        "events_formatted": matching_sub.get("events_formatted", ""),
                    })
                else:
                    v_num = scr if scr is not None and scr < 50 else None
                    fv_num = cscr if cscr is not None and cscr < 50 else None
                    field_players.append({
                        "pid": pid,
                        "role": prole,
                        "name": pname,
                        "club": pclub,
                        "vote": v_num,
                        "fanta_vote": fv_num,
                        "events_formatted": s_ev_str,
                        "is_sub": False,
                        "is_base_vote": False,
                        "status": "S.V. (non sostituito)",
                    })
            else:
                if cscr is not None and cscr < 50:
                    v_num = scr if scr is not None else cscr
                    fv_num = cscr
                    stat = "Refertato"
                else:
                    v_num, fv_num = None, None
                    stat = "S.V."
                field_players.append({
                    "pid": pid,
                    "role": prole,
                    "name": pname,
                    "club": pclub,
                    "vote": v_num,
                    "fanta_vote": fv_num,
                    "events_formatted": s_ev_str,
                    "is_sub": False,
                    "is_base_vote": False,
                    "status": stat,
                })

        for b in bench_in:
            if not b["used"]:
                b["used"] = True
                field_players.append(b)

        tbon_str = team_raw.get("tbon") or ""
        tbon_parts = [float(x) for x in tbon_str.split(";") if x] if tbon_str else []
        if len(tbon_parts) > 2 and tbon_parts[2] != 0:
            mod_pts = tbon_parts[2]
            mod_desc = f"+{mod_pts:.1f} pt" if mod_pts > 0 else f"{mod_pts:.1f} pt"
        else:
            mod_pts, mod_desc = 0.0, "0.0 pt"

        if len(tbon_parts) > 9 and tbon_parts[9] > 0:
            dft_pts = tbon_parts[9]
            sv_player = next((p for p in field_players if p.get("vote") is None or p.get("vote") == 0), None)
            if sv_player:
                sv_player["vote"] = dft_pts
                sv_player["fanta_vote"] = dft_pts
                sv_player["status"] = f"Riserva d'ufficio ({dft_pts:.1f})"
                substitutions.append({
                    "out_name": sv_player["name"],
                    "in_name": f"Riserva d'ufficio [{sv_player['role']}]",
                    "role": sv_player["role"],
                    "out_role": sv_player["role"],
                    "in_role": sv_player["role"],
                    "vote": dft_pts,
                    "fanta_vote": dft_pts,
                    "is_base_vote": False,
                    "events_formatted": "",
                })

        tot_field_votes = round(sum(p["fanta_vote"] for p in field_players if p.get("fanta_vote") is not None), 2)
        tot_pure_votes = round(sum(p["vote"] for p in field_players if p.get("vote") is not None), 2)
        tot_bonus_malus = round(tot_field_votes - tot_pure_votes, 2)
        tot_simulated = round(tot_official if tot_official is not None else (tot_field_votes + mod_pts), 2)
        active_module = mdl
    else:
        field_players, subs_done, active_module = calculate_substitutions(
            starts=starts,
            bench=bench,
            master_players=master_players,
            live_votes=live_votes,
            teams_status=teams_status,
            league_settings=league_settings,
            initial_module=mdl,
        )
        substitutions = list(subs_done)
        tot_pure_votes = round(sum(p["vote"] for p in field_players if p.get("vote") is not None), 2)
        tot_field_votes = round(sum(p["fanta_vote"] for p in field_players if p.get("fanta_vote") is not None), 2)
        tot_bonus_malus = round(tot_field_votes - tot_pure_votes, 2)
        mod_pts, mod_desc = calculate_defense_modifier(field_players, smodd)
        tot_simulated = round(tot_field_votes + mod_pts, 2)

    goals, goals_desc = calculate_team_goals(tot_simulated, step_settings)

    bench_players = []
    for b in bench:
        pid = b.get("pid")
        master = master_players.get(pid, {})
        live = live_votes.get(pid, {})
        b_name = master.get("name") or live.get("name") or b.get("pn") or f"ID:{pid}"
        b_role = master.get("role") or live.get("role") or b.get("r") or "?"
        b_club = master.get("club", "-")
        b_tname = master.get("tname", "").upper()
        b_match_status = teams_status.get(b_tname, None)
        b_v = live.get("vote")
        b_fv = live.get("fanta_vote", b_v)
        if is_calculated:
            b_ev = format_b_events(b.get("b"))
            if b.get("cscr") is not None and b.get("cscr") < 50:
                b_fv = b.get("cscr")
                b_v = b.get("scr", b_fv)
            else:
                b_v, b_fv = None, None
            b_stat = "SUB IN" if b.get("ptype") == "E" else ("Votato" if b_v is not None else "S.V.")
        else:
            b_calc_fv, b_syms = calculate_player_fanta_vote(
                pure_vote=b_v,
                role=b_role,
                events_dict=live.get("events_dict"),
                league_settings=league_settings,
                fallback_fv=live.get("fanta_vote"),
            )
            b_fv = b_calc_fv if b_calc_fv is not None else (live.get("fanta_vote") or b_v)
            b_ev = " ".join(b_syms) if b_syms else (live.get("events_formatted") or format_player_events(live.get("events")))
            if b_v is not None and 0 < b_v <= 10:
                b_stat = "Votato"
            elif b_match_status == 4:
                b_stat = "S.V."
            elif b_match_status == 3:
                b_stat = "in corso"
            else:
                b_stat = "in attesa"

        bench_players.append({
            "pid": pid,
            "name": b_name,
            "role": b_role,
            "club": b_club,
            "vote": b_v,
            "fanta_vote": b_fv,
            "events_formatted": b_ev,
            "status": b_stat,
        })

    real_voted_count = sum(
        1 for p in field_players if p.get("fanta_vote") is not None and not p.get("is_base_vote")
    )
    playing_count = sum(1 for p in field_players if p.get("status") == "in corso")
    waiting_count = sum(1 for p in field_players if p.get("is_base_vote"))

    return {
        "tid": tid,
        "name": team_name,
        "has_lineup": True,
        "module": active_module,
        "orig_module": mdl,
        "tot_official": tot_official,
        "tot_pure_votes": tot_pure_votes,
        "tot_field_votes": tot_field_votes,
        "tot_bonus_malus": tot_bonus_malus,
        "mod_points": mod_pts,
        "mod_desc": mod_desc,
        "tot_simulated": tot_simulated,
        "goals": goals,
        "goals_desc": goals_desc,
        "voted_count": real_voted_count,
        "playing_count": playing_count,
        "waiting_count": waiting_count,
        "field_players": field_players,
        "substitutions": substitutions,
        "bench_players": bench_players,
    }


# ===========================================================================
# 3. CACHE & ORCHESTRAZIONE LIVE SILVER
# ===========================================================================

_lock = threading.Lock()
_cached_client: LegheClient | None = None
_cached_client_ts: float = 0.0
_cached_settings: dict | None = None
_cached_results: dict[int, tuple[float, dict]] = {}

CLIENT_TTL_SECONDS = 600.0  # 10 minuti per JWT lega, anagrafica calciatori e settings
RESULT_TTL_SECONDS = 15.0   # 15 secondi per evitare flood di richieste concorrenti


def _get_authenticated_client(force_refresh: bool = False) -> tuple[LegheClient, dict[int, dict], dict]:
    global _cached_client, _cached_client_ts, _cached_settings
    now = time.time()
    with _lock:
        if (
            not force_refresh
            and _cached_client is not None
            and (now - _cached_client_ts) < CLIENT_TTL_SECONDS
            and _cached_settings is not None
        ):
            return _cached_client, _cached_client.get_league_players(), _cached_settings

    client = LegheClient()
    client.login()
    master_players = client.get_league_players()
    league_settings = client.get_league_settings()

    with _lock:
        _cached_client = client
        _cached_client_ts = time.time()
        _cached_settings = league_settings

    return client, master_players, league_settings


def _detect_silver_round(client: LegheClient, silver_id: int, calendar: list[dict]) -> tuple[int, int]:
    """Ritorna (comp_round, serie_a_day) attivo per Silver:
    - Cerca la prima giornata non ancora calcolata.
    - Se almeno una squadra ha già formazione visibile, la usa (turno live/imminente).
    - Altrimenti ripiega sulla giornata precedente (appena conclusa)."""
    if not calendar:
        md = get_current_matchday()
        return md, md

    uncalc_idx = None
    for i, day in enumerate(calendar):
        if not day.get("calculated"):
            uncalc_idx = i
            break

    if uncalc_idx is None:
        last = calendar[-1]
        return int(last.get("matchDay", 1)), int(last.get("championshipMatchDay", 1))

    d_uncalc = calendar[uncalc_idx]
    matches = d_uncalc.get("matches") or []
    comp_r = int(d_uncalc.get("matchDay", 1))
    sa_day = int(d_uncalc.get("championshipMatchDay", comp_r))

    if uncalc_idx > 0 and matches:
        first_m = matches[0]
        lineup, _ = client.get_match_lineup(
            id_comp=silver_id,
            comp_round=comp_r,
            giornata=sa_day,
            home_id=int(first_m.get("tIdH", 0)),
            away_id=0,
        )
        if not lineup:
            prev = calendar[uncalc_idx - 1]
            return int(prev.get("matchDay", 1)), int(prev.get("championshipMatchDay", 1))

    return comp_r, sa_day


def get_silver_live_data(
    db: Session,
    serie_a_day: int | None = None,
    force_refresh: bool = False,
) -> dict:
    """Calcola la classifica e il dettaglio formazioni Live per la competizione SILVER."""
    if not settings.leghe_api_enabled:
        # Le formazioni di lega esistono solo su leghe.fantacalcio.it: senza, il Live non ha di che calcolare.
        raise LegheDisabledError(LEGHE_DISABLED_MESSAGE)
    cache_key = serie_a_day or 0
    now = time.time()
    if not force_refresh and cache_key in _cached_results:
        ts, cached_payload = _cached_results[cache_key]
        if (now - ts) < RESULT_TTL_SECONDS:
            return cached_payload

    try:
        client, master_players, league_settings = _get_authenticated_client(force_refresh=force_refresh)
        competitions = client.list_competitions()
    except Exception:
        # In caso di JWT scaduto, forza un nuovo login
        client, master_players, league_settings = _get_authenticated_client(force_refresh=True)
        competitions = client.list_competitions()

    silver_comp = next(
        (c for c in competitions if not c.get("del") and (c.get("name") or "").strip().upper() == "SILVER"),
        None,
    )
    if not silver_comp:
        raise RuntimeError("Competizione SILVER non trovata su leghe.fantacalcio.it")

    silver_id = int(silver_comp["id"])
    calendar = client.get_competition_calendar(silver_id, force_refresh=force_refresh)

    if serie_a_day is None:
        comp_round, target_sa_day = _detect_silver_round(client, silver_id, calendar)
    else:
        day_entry = next((d for d in calendar if d.get("championshipMatchDay") == serie_a_day), None)
        if not day_entry:
            day_entry = next((d for d in calendar if d.get("matchDay") == serie_a_day), None)
        if day_entry:
            comp_round = int(day_entry.get("matchDay", 1))
            target_sa_day = int(day_entry.get("championshipMatchDay", serie_a_day))
        else:
            s_day = int(silver_comp.get("sDay", 1) or 1)
            comp_round = max(1, serie_a_day - s_day + 1)
            target_sa_day = serie_a_day

    day_meta = next((d for d in calendar if d.get("championshipMatchDay") == target_sa_day), None)
    is_day_calculated = bool(day_meta.get("calculated", False)) if day_meta else False

    available_days = [
        {
            "comp_round": int(d.get("matchDay", 1)),
            "serie_a_day": int(d.get("championshipMatchDay", 1)),
            "is_calculated": bool(d.get("calculated", False)),
        }
        for d in calendar
    ]

    teams_map = client.list_competition_teams(silver_id)
    live_votes, teams_status = fetch_serie_a_live_votes(target_sa_day)

    # Mappa informazioni extra dal nostro DB (campionato Gold/Bronze/Carbon, id squadra interno, allenatori)
    db_team_info: dict[int, dict] = {}
    current_season = db.query(Season).filter(Season.is_current == True).first() if db is not None else None
    if current_season:
        leagues_by_id = {
            lg.id: (lg.level.value if hasattr(lg.level, "value") else lg.level)
            for lg in db.query(League).filter(League.season_id == current_season.id).all()
        }
        coaches_rows = (
            db.query(FantaTeamCoach.fanta_team_id, FantaAllenatore.display_name)
            .join(FantaAllenatore, FantaAllenatore.id == FantaTeamCoach.allenatore_id)
            .order_by(FantaTeamCoach.is_primary.desc(), FantaAllenatore.display_name)
            .all()
        )
        coaches_by_team: dict[int, list[str]] = {}
        for ft_id, disp_name in coaches_rows:
            coaches_by_team.setdefault(ft_id, []).append(disp_name)

        for ft in db.query(FantaTeam).filter(FantaTeam.season_id == current_season.id).all():
            if ft.leghe_team_id:
                db_team_info[int(ft.leghe_team_id)] = {
                    "fanta_team_id": ft.id,
                    "name": ft.name,
                    "league_level": leagues_by_id.get(ft.league_id),
                    "coaches": coaches_by_team.get(ft.id, []),
                }

    # Determina l'elenco dei team_id partecipanti
    if day_meta and day_meta.get("matches"):
        team_ids = [int(m["tIdH"]) for m in day_meta["matches"] if m.get("tIdH")]
    else:
        team_ids = [int(tid) for tid in (silver_comp.get("tmids") or teams_map.keys())]

    def _fetch_one(tid: int) -> dict:
        t_name = (db_team_info.get(tid) or {}).get("name") or teams_map.get(tid, f"ID:{tid}")
        extra = db_team_info.get(tid) or {}
        match_data, err = client.get_match_lineup(
            id_comp=silver_id,
            comp_round=comp_round,
            giornata=target_sa_day,
            home_id=tid,
            away_id=0,
        )
        if err or not match_data or not match_data.get("home"):
            return {
                "tid": tid,
                "fanta_team_id": extra.get("fanta_team_id"),
                "name": t_name,
                "league_level": extra.get("league_level"),
                "coaches": extra.get("coaches", []),
                "has_lineup": False,
                "error": err or "Formazione non disponibile",
                "module": "-",
                "orig_module": "-",
                "tot_official": None,
                "tot_pure_votes": 0.0,
                "tot_field_votes": 0.0,
                "tot_bonus_malus": 0.0,
                "mod_points": 0.0,
                "mod_desc": "-",
                "tot_simulated": 0.0,
                "goals": 0,
                "goals_desc": "-",
                "voted_count": 0,
                "playing_count": 0,
                "waiting_count": 0,
                "field_players": [],
                "substitutions": [],
                "bench_players": [],
            }

        cal = bool(match_data.get("cal", False)) or is_day_calculated
        card = process_team_lineup(
            team_raw=match_data["home"],
            team_name=t_name,
            is_calculated=cal,
            master_players=master_players,
            live_votes=live_votes,
            teams_status=teams_status,
            league_settings=league_settings,
        )
        card["fanta_team_id"] = extra.get("fanta_team_id")
        card["league_level"] = extra.get("league_level")
        card["coaches"] = extra.get("coaches", [])
        card["is_calculated"] = cal
        return card

    standings: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_one, tid): tid for tid in team_ids}
        for fut in as_completed(futures):
            standings.append(fut.result())

    # Ordina per punteggio live decrescente (le squadre con formazione prima di quelle senza)
    standings.sort(key=lambda x: (1 if x.get("has_lineup") else 0, x.get("tot_simulated", 0.0), x.get("name", "")), reverse=True)

    with_lineup_scores = [s["tot_simulated"] for s in standings if s.get("has_lineup")]
    max_score = max(with_lineup_scores) if with_lineup_scores else None
    min_score = min(with_lineup_scores) if with_lineup_scores else None

    for idx, item in enumerate(standings, start=1):
        item["position"] = idx
        item["is_top_score"] = bool(item.get("has_lineup") and max_score is not None and item["tot_simulated"] == max_score)
        item["is_low_score"] = bool(
            item.get("has_lineup")
            and min_score is not None
            and max_score != min_score
            and item["tot_simulated"] == min_score
        )

    step_settings = (league_settings.get("lcnps") or {}).get("step") or {}
    smodd = (league_settings.get("lcnps") or {}).get("smodd")

    finished_teams = sorted(k for k, v in teams_status.items() if v == 4)
    playing_teams = sorted(k for k, v in teams_status.items() if v == 3)

    any_calculated = is_day_calculated or any(s.get("is_calculated") for s in standings if s.get("has_lineup"))

    result = {
        "competition_id": silver_id,
        "competition_name": "SILVER",
        "comp_round": comp_round,
        "serie_a_day": target_sa_day,
        "is_calculated": any_calculated,
        "updated_at": datetime.now().strftime("%H:%M:%S"),
        "available_days": available_days,
        "serie_a_status": {
            "finished_count": len(finished_teams),
            "playing_count": len(playing_teams),
            "finished_teams": finished_teams,
            "playing_teams": playing_teams,
            "votes_loaded": len(live_votes),
        },
        "league_rules": {
            "first_goal_threshold": float(step_settings.get("stlmt", 66)),
            "goal_step": float((step_settings.get("stgoal") or [4])[0]),
            "defense_modifier_active": bool(smodd and smodd.get("smodva")),
            "max_substitutions": MAX_SUBSTITUTIONS,
        },
        "standings": standings,
    }

    with _lock:
        _cached_results[cache_key] = (time.time(), result)
        _cached_results[target_sa_day] = (time.time(), result)

    return result
