"""Da eseguire sull'host (serve un browser visibile, mai nel container):
apre la pagina della lega, l'utente fa login a mano, salva lo storage_state
in tamarros_session.json. Col mount di docker-compose il file e' subito
visibile nel container backend."""

from playwright.sync_api import sync_playwright

from app.config import settings

if __name__ == "__main__":
    # Se fanta_lega_name non e' impostata sull'host, la homepage leghe basta per il login.
    url = (
        f"{settings.fanta_leghe_base_url}{settings.fanta_lega_name}"
        if settings.fanta_lega_name
        else settings.fanta_leghe_base_url
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)
        input("Fai login nel browser, poi premi INVIO qui per salvare la sessione...")
        context.storage_state(path=settings.fanta_session_file)
        browser.close()

    print(f"Sessione salvata in {settings.fanta_session_file}")
