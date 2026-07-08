"""Serie A scraper — next matches + injury data from fantacalcio.it."""
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from app.config import settings

import logging
logger = logging.getLogger(__name__)

DAY_MAP = {
    "Mon": "Lun", "Tue": "Mar", "Wed": "Mer",
    "Thu": "Gio", "Fri": "Ven", "Sat": "Sab", "Sun": "Dom",
}


def get_next_matches() -> list[dict]:
    url = f"{settings.fanta_base_url}live-serie-a"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logger.error("get_next_matches error: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    matches = soup.find_all("li", class_="match")
    result = []
    now = datetime.now()

    for m in matches:
        try:
            home = m.find("label", class_="team-home").get_text(strip=True).upper()
            away = m.find("label", class_="team-away").get_text(strip=True).upper()
            score_el = m.find("a", class_="match-score")
            score = score_el.get_text(strip=True).replace("\n", " ") if score_el else None
            raw_date = m.find("div", class_="match-date").get_text(strip=True)
            location_el = m.find("div", class_="match-location")
            location = location_el.get_text(strip=True) if location_el else ""

            date_obj = datetime.strptime(raw_date, "%d/%m%H:%M").replace(year=now.year)
            result.append({
                "home_team": home,
                "away_team": away,
                "match_date": date_obj.isoformat(),
                "score": score,
                "location": location,
                "is_played": date_obj < now,
            })
        except Exception as e:
            logger.warning("Match parse error: %s", e)

    return result


def get_probable_lineups() -> list[dict]:
    """Scrapa le formazioni probabili (usato per infortuni/recuperi)."""
    url = f"{settings.fanta_base_url}probabili-formazioni-serie-a"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logger.error("get_probable_lineups error: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    players_data = []
    for item in soup.find_all("li", class_="player-item pill"):
        try:
            link = item.find("a", class_="player-name player-link")
            name = link.find("span").text.strip()
            href = link["href"]
            fanta_id = int(href.strip("/").split("/")[-1])
            players_data.append({"name": name, "fanta_id": fanta_id})
        except Exception:
            pass

    return players_data
