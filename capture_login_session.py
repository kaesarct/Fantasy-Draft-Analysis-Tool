import os
from playwright.sync_api import sync_playwright

SESSION_FILE = os.path.join(os.path.dirname(__file__), "tamarros_session.json")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://leghe.fantacalcio.it/fantacalcio-tamarros")

        print("Fai login e apri la pagina Formazioni di una competizione qualsiasi,")
        print("verifica che i dati carichino correttamente, poi torna qui e premi Invio.")
        input()

        context.storage_state(path=SESSION_FILE)
        print(f"Sessione salvata in {SESSION_FILE}")
        browser.close()


if __name__ == "__main__":
    main()
