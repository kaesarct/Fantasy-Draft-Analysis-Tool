"""Fantacalcio.it API client — login, download prices, votes."""
import re
import os
import requests
from bs4 import BeautifulSoup
from app.config import settings

import logging
logger = logging.getLogger(__name__)

URL_API = f"{settings.fanta_base_url}{settings.fanta_api}"


class FantaClient:
    def __init__(self):
        self._session: requests.Session | None = None

    def login(self) -> bool:
        url = f"{URL_API}User/login"
        payload = {
            "username": settings.fanta_username,
            "password": settings.fanta_password,
        }
        self._session = requests.Session()
        try:
            resp = self._session.post(url, json=payload, timeout=15)
            # L'API risponde 200 anche a credenziali errate: fa fede il flag success.
            if resp.status_code == 200 and resp.json().get("success", True):
                logger.info("Login fantacalcio.it OK")
                return True
            logger.error("Login failed: status=%s", resp.status_code)
            self._session = None
            return False
        except Exception as e:
            logger.error("Login exception: %s", e)
            return False

    def _ensure_session(self) -> bool:
        if self._session is None:
            return self.login()
        return True

    # ── Last matchday ───────────────────────────────────────────────────
    def get_last_matchday(self) -> int:
        url = f"{settings.fanta_base_url}live-serie-a"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error("get_last_matchday error: %s", e)
            return -1

        soup = BeautifulSoup(resp.text, "html.parser")
        h1 = soup.find("h1", class_="pl-2 title w-100")
        if h1:
            small = h1.find("small")
            if small:
                match = re.search(r"Giornata (\d+)", small.get_text())
                if match:
                    return int(match.group(1)) - 1
        return -1

    # ── Download prices Excel ──────────────────────────────────────────
    def download_prices(self) -> str | None:
        if not self._ensure_session():
            return None
        url = f"{URL_API}Excel/prices/{settings.fanta_year_quotazioni}/1"
        try:
            resp = self._session.get(url, stream=True, timeout=30)
            if resp.status_code == 200:
                os.makedirs(settings.download_folder, exist_ok=True)
                path = os.path.join(settings.download_folder, "quotazioni.xlsx")
                with open(path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                logger.info("Prices downloaded → %s", path)
                return path
            logger.error("Download prices failed: %s", resp.status_code)
        except Exception as e:
            logger.error("Download prices exception: %s", e)
        return None

    # ── Download votes Excel ───────────────────────────────────────────
    def download_votes(self, match_day: int | None = None) -> str | None:
        if not self._ensure_session():
            return None
        day = match_day or self.get_last_matchday()
        if day < 0:
            return None
        url = f"{URL_API}Excel/votes/{settings.fanta_year_quotazioni}/{day}"
        try:
            resp = self._session.get(url, stream=True, timeout=30)
            if resp.status_code == 200:
                os.makedirs(settings.download_folder, exist_ok=True)
                path = os.path.join(settings.download_folder, f"voti_g{day}.xlsx")
                with open(path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                logger.info("Votes g%s downloaded → %s", day, path)
                return path
            logger.error("Download votes failed: %s", resp.status_code)
        except Exception as e:
            logger.error("Download votes exception: %s", e)
        return None

    # ── Download Excel per stagione arbitraria (import storico) ────────
    def _download_season_excel(self, kind: str, season_code: int, dest_dir: str) -> str | None:
        """Scarica l'Excel `kind` ("stats" | "prices") per un season_code
        fantacalcio (= anno_inizio - 2005) in dest_dir. Ritorna il path o None."""
        if not self._ensure_session():
            return None
        url = f"{URL_API}Excel/{kind}/{season_code}/1"
        try:
            resp = self._session.get(url, stream=True, timeout=30)
            if resp.status_code == 200:
                path = os.path.join(dest_dir, f"{kind}.xlsx")
                with open(path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                logger.info("%s season_code=%s downloaded → %s", kind, season_code, path)
                return path
            logger.error("Download %s failed: %s", kind, resp.status_code)
        except Exception as e:
            logger.error("Download %s exception: %s", kind, e)
        return None

    def download_stats_excel(self, season_code: int, dest_dir: str) -> str | None:
        return self._download_season_excel("stats", season_code, dest_dir)

    def download_prices_excel(self, season_code: int, dest_dir: str) -> str | None:
        return self._download_season_excel("prices", season_code, dest_dir)


# Singleton
fanta_client = FantaClient()
