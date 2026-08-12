"""Salva la sessione autenticata di leghe.fantacalcio.it (storage_state Playwright).

Il form di login non ha captcha ne' 2FA, quindi di default il login e' automatico
e headless: si puo' eseguire nel container.

    docker compose exec backend python capture_login_session.py

Con --manual apre un browser visibile e aspetta che il login lo faccia l'utente:
serve solo se il sito introduce un captcha o cambia il form. Richiede un display,
quindi va eseguito sull'host, non nel container.

    python capture_login_session.py --manual
"""
import os
import re
import sys

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from app.config import settings

LOGIN_URL = "https://leghe.fantacalcio.it/login"
# Il banner cookie (PubTech CMP) si carica in ritardo e intercetta i click sul
# form: "Continua senza accettare" (#pt-close) lo chiude senza scrivere consensi
# pubblicitari nella sessione salvata.
COOKIE_BANNER = "#pubtech-cmp"
COOKIE_BANNER_BUTTONS = ("#pt-close", "#pt-accept-all")


def _chiudi_banner_cookie(page, timeout_ms: int) -> None:
    try:
        page.wait_for_selector(COOKIE_BANNER, timeout=timeout_ms)
    except PlaywrightTimeoutError:
        return  # nessun banner: niente da chiudere
    for selector in COOKIE_BANNER_BUTTONS:
        pulsante = page.query_selector(selector)
        if pulsante and pulsante.is_visible():
            pulsante.click()
            page.wait_for_selector(COOKIE_BANNER, state="hidden", timeout=timeout_ms)
            return


def _dashboard_url() -> str:
    if settings.fanta_lega_name:
        return f"{settings.fanta_leghe_base_url}{settings.fanta_lega_name}"
    return settings.fanta_leghe_base_url


def _salva(context) -> str:
    path = settings.fanta_session_file
    if os.path.isdir(path):
        raise RuntimeError(
            f"{path} e' una directory (creata da un bind mount su file inesistente): "
            "rimuovila e riavvia il container prima di rigenerare la sessione."
        )
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    context.storage_state(path=path)
    return path


def capture_auto(timeout_ms: int = 30000) -> str:
    if not settings.fanta_username or not settings.fanta_password:
        raise ValueError("FANTA_USERNAME/FANTA_PASSWORD non configurate")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="it-IT")
        page = context.new_page()
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            _chiudi_banner_cookie(page, timeout_ms=10000)

            # Gli input del form di login non hanno name ne' id: si identificano dal type.
            page.fill("input[type=text]", settings.fanta_username, timeout=timeout_ms)
            page.fill("input[type=password]", settings.fanta_password)
            page.get_by_role("button", name=re.compile("^login$", re.I)).click()

            try:
                page.wait_for_url(re.compile(r"/view/"), timeout=timeout_ms)
            except PlaywrightTimeoutError:
                raise RuntimeError(
                    f"Login non completato (URL: {page.url}). Credenziali errate "
                    "oppure il form e' cambiato: riprova con --manual."
                )
            return _salva(context)
        finally:
            browser.close()


def capture_manual() -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="it-IT")
        page = context.new_page()
        page.goto(_dashboard_url())
        input("Fai login nel browser, poi premi INVIO qui per salvare la sessione...")
        try:
            return _salva(context)
        finally:
            browser.close()


if __name__ == "__main__":
    manuale = "--manual" in sys.argv
    try:
        path = capture_manual() if manuale else capture_auto()
    except Exception as e:
        print(f"Sessione NON salvata: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Sessione salvata in {path}")
