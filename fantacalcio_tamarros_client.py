import os
import re
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


class TamarrosClient:
    LOGIN_URL = "https://apileague.fantacalcio.it/onboarding/v1/login"
    LEGHE_BASE_URL = "https://leghe.fantacalcio.it/servizi"
    LEGA_PAGE_URL = "https://leghe.fantacalcio.it/fantacalcio-tamarros"
    APP_KEY_FALLBACK = "bZ2FAQDZYYBVEehhFuM9pAsJ3waL0Vsg"
    SESSION_FILE = os.path.join(os.path.dirname(__file__), "tamarros_session.json")
    COMPETIZIONE_RE = re.compile(
        r'<a href="#" data-isin="(?:true|false)" data-id="(\d+)"><span[^>]*></span>([^<]+)</a>'
    )

    def __init__(self, alias_lega="fantacalcio-tamarros", app_key=None, headless=True):
        self.alias_lega = alias_lega
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

    def _discover_app_key(self):
        # authAppKey è iniettato dal server nell'HTML (script#serverBridge), non nei bundle JS:
        # più stabile da leggere da lì che affidarsi a una chiave fissa nel codice.
        try:
            res = self.session.get(self.LEGA_PAGE_URL, timeout=10)
            match = re.search(r'authAppKey"?\s*:\s*"([^"]+)"', res.text)
            if match:
                return match.group(1)
        except requests.RequestException:
            pass
        return self.APP_KEY_FALLBACK

    def login(self, username=None, password=None):
        username = username or os.environ.get("FANTA_USERNAME", "")
        password = password or os.environ.get("FANTA_PASSWORD", "")
        if not username or not password:
            raise ValueError(
                "Credenziali mancanti: passa username/password o imposta FANTA_USERNAME/FANTA_PASSWORD"
            )

        res = self.session.post(
            self.LOGIN_URL, json={"username": username, "password": password}
        )
        res.raise_for_status()
        data = res.json()
        if not data.get("success"):
            raise RuntimeError(f"Login fallito: {data}")

        self.utente = data["data"]["utente"]
        return self.utente

    def _get_servizio(self, servizio, azione, params=None, referer=None):
        url = f"{self.LEGHE_BASE_URL}/{servizio}/{azione}"
        req_params = {"alias_lega": self.alias_lega, **(params or {})}
        headers = {"x-requested-with": "XMLHttpRequest"}
        if referer:
            headers["referer"] = referer
        res = self.session.get(url, params=req_params, headers=headers)
        res.raise_for_status()
        return res.json()

    @classmethod
    def _estrai_competizioni(cls, html):
        return {
            nome.strip().lower().replace(" ", "_"): int(id_comp)
            for id_comp, nome in cls.COMPETIZIONE_RE.findall(html)
        }

    def discover_competizioni(self, timeout_ms=15000):
        # Il dropdown competizioni è renderizzato lato server nell'HTML della dashboard,
        # non c'è una chiamata servizi/ dedicata: va letto da lì con un browser autenticato.
        self._check_session_file()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(storage_state=self.SESSION_FILE)
            page = context.new_page()
            page.goto(self.LEGA_PAGE_URL)
            page.wait_for_timeout(timeout_ms)
            html = page.content()
            browser.close()
        return self._estrai_competizioni(html)

    def _naviga_e_intercetta_formazioni(self, page, id_comp, timeout_ms):
        url = f"{self.LEGA_PAGE_URL}/formazioni?id={id_comp}"
        matcher = (
            lambda r: "V1_LegheFormazioni/Pagina" in r.url
            and f"id_comp={id_comp}" in r.url
        )
        with page.expect_response(matcher, timeout=timeout_ms) as response_info:
            page.goto(url)

        response = response_info.value
        # Ogni competizione può essere a una giornata diversa: la pagina la decide da sola,
        # non è nel corpo della risposta ma nella query string della chiamata che fa.
        match = re.search(r"[?&]r=(\d+)", response.url)
        return {
            "giornata": int(match.group(1)) if match else None,
            "dati": response.json(),
        }

    def get_formazioni(self, id_comp, timeout_ms=15000):
        # V1_LegheFormazioni/Pagina rifiuta le chiamate HTTP dirette (con o senza cookie di
        # sessione copiati a mano): serve un browser autenticato reale. Riusiamo la sessione
        # salvata da capture_login_session.py e intercettiamo la risposta di rete.
        self._check_session_file()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(storage_state=self.SESSION_FILE)
            page = context.new_page()
            try:
                return self._naviga_e_intercetta_formazioni(page, id_comp, timeout_ms)
            except PlaywrightTimeoutError:
                raise RuntimeError(
                    f"Nessuna risposta V1_LegheFormazioni/Pagina per id_comp={id_comp}. "
                    "La sessione salvata potrebbe essere scaduta: riesegui capture_login_session.py."
                )
            finally:
                browser.close()

    def get_tutte_le_formazioni(self, timeout_ms=15000, competizioni=None):
        self._check_session_file()
        risultati = {}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(storage_state=self.SESSION_FILE)
            page = context.new_page()

            if competizioni is None:
                page.goto(self.LEGA_PAGE_URL)
                page.wait_for_timeout(timeout_ms)
                competizioni = self._estrai_competizioni(page.content())

            for nome_comp, id_comp in competizioni.items():
                try:
                    risultati[nome_comp] = self._naviga_e_intercetta_formazioni(
                        page, id_comp, timeout_ms
                    )
                except PlaywrightTimeoutError:
                    risultati[nome_comp] = None

            browser.close()

        return risultati

    def _check_session_file(self):
        if not os.path.exists(self.SESSION_FILE):
            raise FileNotFoundError(
                f"{self.SESSION_FILE} non trovato: esegui prima capture_login_session.py"
            )


if __name__ == "__main__":
    client = TamarrosClient()
    client.login()
    formazioni = client.get_tutte_le_formazioni()
    for nome_comp, risultato in formazioni.items():
        if risultato is None:
            print(nome_comp, "NESSUN DATO")
        else:
            stato = "OK" if risultato["dati"].get("success") else "KO"
            print(nome_comp, f"giornata {risultato['giornata']}", stato)
