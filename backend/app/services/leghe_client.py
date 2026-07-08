"""Leghe.fantacalcio.it client — login API + fetch formazioni via Playwright.

L'endpoint V1_LegheFormazioni/Pagina rifiuta le chiamate HTTP dirette (anche con
i cookie di sessione copiati a mano): serve un browser autenticato reale. Si riusa
lo storage_state salvato da capture_login_session.py (da eseguire sull'host).
"""
import os
import re

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from app.config import settings

import logging
logger = logging.getLogger(__name__)


class SessionFileMissing(Exception):
    """Il file di sessione Playwright non esiste: va rigenerato con capture_login_session.py."""


class SessionExpired(Exception):
    """La sessione salvata non e' piu' valida: va rigenerata con capture_login_session.py."""


class LegheClient:
    LOGIN_URL = "https://apileague.fantacalcio.it/onboarding/v1/login"
    COMPETIZIONE_RE = re.compile(
        r'<a href="#" data-isin="(?:true|false)" data-id="(\d+)"><span[^>]*></span>([^<]+)</a>'
    )

    def __init__(self, alias_lega: str | None = None, app_key: str | None = None, headless: bool = True):
        self.alias_lega = alias_lega or settings.fanta_lega_name
        self.lega_page_url = f"{settings.fanta_leghe_base_url}{self.alias_lega}"
        self.leghe_base_url = f"{settings.fanta_leghe_base_url}servizi"
        self.headless = headless
        self.session = requests.Session()
        self.session.headers.update(
            {
                "app_key": app_key or self._discover_app_key(),
                "accept": "application/json",
                "content-type": "application/json",
            }
        )
        self.utente = None

    def _discover_app_key(self) -> str:
        # authAppKey e' iniettato dal server nell'HTML (script#serverBridge), non nei bundle JS:
        # piu' stabile da leggere da li' che affidarsi a una chiave fissa nel codice.
        try:
            res = self.session.get(self.lega_page_url, timeout=10)
            match = re.search(r'authAppKey"?\s*:\s*"([^"]+)"', res.text)
            if match:
                return match.group(1)
        except requests.RequestException as e:
            logger.warning("Discovery app_key fallita, uso il fallback: %s", e)
        return settings.fanta_app_key_fallback

    def login(self, username: str | None = None, password: str | None = None) -> dict:
        username = username or settings.fanta_username
        password = password or settings.fanta_password
        if not username or not password:
            raise ValueError(
                "Credenziali mancanti: passa username/password o imposta FANTA_USERNAME/FANTA_PASSWORD"
            )

        res = self.session.post(
            self.LOGIN_URL, json={"username": username, "password": password}, timeout=15
        )
        res.raise_for_status()
        data = res.json()
        if not data.get("success"):
            raise RuntimeError(f"Login fallito: {data}")

        self.utente = data["data"]["utente"]
        logger.debug("Login leghe avvenuto con successo")
        return self.utente

    @classmethod
    def _estrai_competizioni(cls, html: str) -> dict[str, int]:
        return {
            nome.strip().lower().replace(" ", "_"): int(id_comp)
            for id_comp, nome in cls.COMPETIZIONE_RE.findall(html)
        }

    def discover_competizioni(self, timeout_ms: int = 15000) -> dict[str, int]:
        # Il dropdown competizioni e' renderizzato lato server nell'HTML della dashboard,
        # non c'e' una chiamata servizi/ dedicata: va letto da li' con un browser autenticato.
        self._check_session_file()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(storage_state=settings.fanta_session_file)
            page = context.new_page()
            page.goto(self.lega_page_url, timeout=timeout_ms)
            page.wait_for_timeout(timeout_ms)
            html = page.content()
            browser.close()
        competizioni = self._estrai_competizioni(html)
        if not competizioni:
            raise SessionExpired(
                "Nessuna competizione trovata nella dashboard: sessione scaduta o HTML cambiato."
            )
        return competizioni

    def _naviga_e_intercetta_formazioni(self, page, id_comp: int, timeout_ms: int) -> dict:
        url = f"{self.lega_page_url}/formazioni?id={id_comp}"
        matcher = (
            lambda r: "V1_LegheFormazioni/Pagina" in r.url
            and f"id_comp={id_comp}" in r.url
        )
        with page.expect_response(matcher, timeout=timeout_ms) as response_info:
            page.goto(url, timeout=timeout_ms)

        response = response_info.value
        # Ogni competizione puo' essere a una giornata diversa: la pagina la decide da sola,
        # non e' nel corpo della risposta ma nella query string della chiamata che fa.
        match = re.search(r"[?&]r=(\d+)", response.url)
        return {
            "giornata": int(match.group(1)) if match else None,
            "dati": response.json(),
        }

    def get_formazioni(self, id_comp: int, timeout_ms: int = 15000) -> dict:
        self._check_session_file()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(storage_state=settings.fanta_session_file)
            page = context.new_page()
            try:
                return self._naviga_e_intercetta_formazioni(page, id_comp, timeout_ms)
            except PlaywrightTimeoutError:
                raise SessionExpired(
                    f"Nessuna risposta V1_LegheFormazioni/Pagina per id_comp={id_comp}. "
                    "La sessione salvata potrebbe essere scaduta: riesegui capture_login_session.py."
                )
            finally:
                browser.close()

    def get_tutte_le_formazioni(
        self, timeout_ms: int = 15000, competizioni: dict[str, int] | None = None
    ) -> dict:
        self._check_session_file()
        risultati = {}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(storage_state=settings.fanta_session_file)
            page = context.new_page()

            if competizioni is None:
                page.goto(self.lega_page_url, timeout=timeout_ms)
                page.wait_for_timeout(timeout_ms)
                competizioni = self._estrai_competizioni(page.content())

            if not competizioni:
                browser.close()
                raise SessionExpired(
                    "Nessuna competizione trovata nella dashboard: sessione scaduta o HTML cambiato."
                )

            for nome_comp, id_comp in competizioni.items():
                try:
                    risultati[nome_comp] = {
                        "id_comp": id_comp,
                        **self._naviga_e_intercetta_formazioni(page, id_comp, timeout_ms),
                    }
                except PlaywrightTimeoutError:
                    logger.warning(
                        "Timeout formazioni per competizione '%s' (id_comp=%s)", nome_comp, id_comp
                    )
                    risultati[nome_comp] = None

            browser.close()

        return risultati

    def _check_session_file(self):
        if not os.path.exists(settings.fanta_session_file):
            raise SessionFileMissing(
                f"{settings.fanta_session_file} non trovato: esegui prima capture_login_session.py"
            )
