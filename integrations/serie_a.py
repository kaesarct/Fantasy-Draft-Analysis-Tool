"""Scraping dei dati "live" di Serie A da fantacalcio.it.

Portato dal bot Telegram (functions/seriea_function.py): prossime partite e
rientri possibili dai probabili schieramenti. Il fetch HTTP è separato dal
parsing in modo che il parsing sia testabile con fixture HTML.
"""

import logging
import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

log = logging.getLogger('integrations')

BASE_URL = os.environ.get('BASE_URL_SITE', 'https://www.fantacalcio.it/')

# Mappa abbreviazione -> nome squadra Serie A (usata nello scraping partite).
SQUADRE_SERIE_A = {
    'COM': 'Como', 'BOL': 'Bologna', 'CRE': 'Cremonese', 'JUV': 'Juventus',
    'MIL': 'Milan', 'SAS': 'Sassuolo', 'GEN': 'Genoa', 'ROM': 'Roma',
    'ATA': 'Atalanta', 'FIO': 'Fiorentina', 'TOR': 'Torino', 'LEC': 'Lecce',
    'CAG': 'Cagliari', 'NAP': 'Napoli', 'PIS': 'Pisa', 'INT': 'Inter',
    'PAR': 'Parma', 'UDI': 'Udinese', 'LAZ': 'Lazio', 'VER': 'Verona',
}

GIORNO_SETTIMANA = {
    'mon': 'lun', 'tue': 'mar', 'wed': 'mer', 'thu': 'gio',
    'fri': 'ven', 'sat': 'sab', 'sun': 'dom',
}


def _nome_squadra(abbr):
    return SQUADRE_SERIE_A.get(abbr.upper(), abbr.upper())


def parse_prossime_partite(html, now=None):
    """Estrae le partite dalla pagina live-serie-a. Ritorna una lista di dict."""
    now = now or datetime.now()
    soup = BeautifulSoup(html, 'html.parser')
    partite = []
    for match in soup.find_all('li', class_='match'):
        try:
            casa = match.find('label', class_='team-home').get_text(strip=True).upper()
            ospite = match.find('label', class_='team-away').get_text(strip=True).upper()
            score_el = match.find('a', class_='match-score')
            score = score_el.get_text(strip=True).replace('\n', ' ') if score_el else None
            data_el = match.find('div', class_='match-date')
            raw_date = data_el.get_text(strip=True) if data_el else ''
            luogo_el = match.find('div', class_='match-location')
            luogo = luogo_el.get_text(strip=True) if luogo_el else None

            data_iso, data_formattata, giocata = None, None, None
            try:
                dt = datetime.strptime(raw_date, '%d/%m%H:%M').replace(year=now.year)
                giorno = GIORNO_SETTIMANA.get(dt.strftime('%a').lower(), dt.strftime('%a').lower())
                data_iso = dt.isoformat()
                data_formattata = dt.strftime(f'{giorno} %d/%m %H:%M')
                giocata = dt < now
            except ValueError:
                log.debug("Data partita non interpretabile: %r", raw_date)

            partite.append({
                'squadra_casa': _nome_squadra(casa),
                'squadra_ospite': _nome_squadra(ospite),
                'score': score,
                'data': data_iso,
                'data_formattata': data_formattata,
                'luogo': luogo,
                'giocata': giocata,
            })
        except Exception as e:  # una partita malformata non deve bloccare le altre
            log.error("Errore elaborazione partita: %s", e)
    return partite


def prossime_partite():
    """Scarica e restituisce le prossime partite di Serie A."""
    url = f"{BASE_URL}live-serie-a"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return parse_prossime_partite(resp.text)


def parse_rientri_possibili(html):
    """Estrae i giocatori dai probabili schieramenti. Ritorna [{'name', 'id'}]."""
    soup = BeautifulSoup(html, 'html.parser')
    rientri = []
    for item in soup.find_all('li', class_='player-item pill'):
        try:
            link = item.find('a', class_='player-name player-link')
            nome = link.find('span').text.strip()
            codice = link['href'].strip('/').split('/')[-1]
            rientri.append({'name': nome, 'id': int(codice)})
        except (AttributeError, KeyError, ValueError) as e:
            log.debug("Voce probabili non interpretabile: %s", e)
    return rientri


def rientri_possibili():
    """Scarica e restituisce i giocatori dai probabili schieramenti."""
    url = f"{BASE_URL}probabili-formazioni-serie-a"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return parse_rientri_possibili(resp.text)


def ultima_giornata():
    """Numero dell'ultima giornata di Serie A conclusa (o -1 se non disponibile)."""
    url = f"{BASE_URL}live-serie-a"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        h1 = soup.find('h1', class_='pl-2 title w-100')
        if h1 and h1.find('small'):
            match = re.search(r'Giornata (\d+)', h1.find('small').get_text())
            if match:
                return int(match.group(1)) - 1
    except requests.exceptions.RequestException as e:
        log.error("Errore recupero ultima giornata: %s", e)
    return -1
