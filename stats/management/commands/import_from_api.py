from datetime import datetime
import os
import re
import pandas as pd
import requests
import numpy as np
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.conf import settings

from players.models import Calciatore, CalciatoreStagione
from core.models import SquadraReale, Stagione
from stats.models import VotoPartita, StatisticaCalciatore

# Credenziali API
FANTA_USERNAME = os.environ.get("FANTA_USERNAME", "")
FANTA_PASSWORD = os.environ.get("FANTA_PASSWORD", "")
BASE_URL = os.environ.get("BASE_URL", "https://api.fantacalcio.it/")
BASE_API = os.environ.get("BASE_API", "v1/")
URL_API = f"{BASE_URL}{BASE_API}"

# Assicuriamoci di salvare i file nella cartella corretta
DOWNLOAD_FOLDER = os.path.join(settings.BASE_DIR, "dati_scaricati")

class Command(BaseCommand):
    help = 'Esegue lo scraping/API di Leghe Fantacalcio per scaricare e importare Quotazioni e Voti.'

    def add_arguments(self, parser):
        parser.add_argument('--type', type=str, choices=['voti', 'quotazioni', 'stats'], help='Tipo di import (voti, quotazioni o stats)', required=True)
        parser.add_argument('--season-id', type=int, help=f'ID stagione Fantacalcio (es. {settings.CURRENT_SEASON_ID} per anno corrente)', default=settings.CURRENT_SEASON_ID)

    def login_in_fanta(self):
        url_login = f"{URL_API}User/login"
        payload_login = {"username": FANTA_USERNAME, "password": FANTA_PASSWORD}
        session = requests.Session()
        
        try:
            res = session.post(url_login, json=payload_login)
            if res.status_code == 200:
                self.stdout.write(self.style.SUCCESS("Login API Fantacalcio effettuato con successo."))
                return session
            else:
                self.stdout.write(self.style.ERROR(f"Errore nel login: {res.status_code} - {res.text}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Eccezione durante il login: {e}"))
        return None

    def get_last_matchday(self):
        url = f"{BASE_URL}live-serie-a"
        try:
            res = requests.get(url)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")
            h1_element = soup.find("h1", class_="pl-2 title w-100")
            if h1_element:
                small_element = h1_element.find("small")
                if small_element:
                    text = small_element.get_text()
                    match = re.search(r"Giornata (\d+)", text)
                    if match:
                        giornata = int(match.group(1)) - 1
                        self.stdout.write(self.style.SUCCESS(f"Ultima giornata giocata: {giornata}"))
                        return giornata
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Errore recupero giornata dal sito live-serie-a: {e}"))
        return -1

    def handle(self, *args, **options):
        # Assicura che esista la cartella di download
        os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
        
        tipo = options['type']
        season_id = options.get('season_id', settings.CURRENT_SEASON_ID)
        
        if not FANTA_USERNAME or not FANTA_PASSWORD:
            self.stdout.write(self.style.ERROR("ATTENZIONE: Credenziali FANTA_USERNAME o FANTA_PASSWORD mancanti. Compila il file .env!"))
            return

        session = self.login_in_fanta()
        if not session:
            return

        if tipo == 'quotazioni':
            url_get = f"{URL_API}Excel/prices/{season_id}/1"
            filepath = os.path.join(DOWNLOAD_FOLDER, "quotazioni.xlsx")
        elif tipo == 'voti':
            day = self.get_last_matchday()
            if day <= 0:
                self.stdout.write(self.style.WARNING("Impossibile determinare la giornata. L'importazione si interrompe."))
                return
            url_get = f"{URL_API}Excel/votes/{season_id}/{day}"
            filepath = os.path.join(DOWNLOAD_FOLDER, f"voti_giornata_{day}.xlsx")
        elif tipo == 'stats':
            url_get = f"{URL_API}Excel/stats/{season_id}/1"
            filepath = os.path.join(DOWNLOAD_FOLDER, f"statistiche_{season_id}.xlsx")

        self.stdout.write(f"Scaricando file da {url_get} ...")
        
        # Download in Streaming per non sovraccaricare la RAM
        get_response = session.get(url_get, stream=True)
        if get_response.status_code == 200:
            with open(filepath, "wb") as f:
                for chunk in get_response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            self.stdout.write(self.style.SUCCESS(f"File salvato in locale con successo: {filepath}"))
            
            # -----------------------------------------------
            # Esecuzione dei parser nativi Django (Pandas)
            # -----------------------------------------------
            if tipo == 'voti':
                self.importa_voti_in_db(filepath, day)
            elif tipo == 'quotazioni':
                self.importa_quotazioni_in_db(filepath)
            elif tipo == 'stats':
                self.importa_statistiche_in_db(filepath, season_id)
                
        else:
            self.stdout.write(self.style.ERROR(f"Errore HTTP {get_response.status_code} durante il download dal sito."))

    def importa_voti_in_db(self, file_path, giornata):
        self.stdout.write(f"Avvio elaborazione voti (Pandas) per la giornata {giornata}...")
        try:
            # Assumendo che il file voti ufficiale abbia l'header alla prima o seconda riga
            df = pd.read_excel(file_path, skiprows=1) 
            df = df.replace({np.nan: None})
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Errore lettura Excel: {e}"))
            return
        


        stagione_attiva = Stagione.objects.filter(attiva=True).first()
        if not stagione_attiva:
            #prendi la stagione in corso
            today = datetime.now()
            if today.month >= 8:
                # Se siamo da agosto in poi, la stagione è quella corrente (es. 2025/2026)
                start_year = today.year
            else:
                # Se siamo prima di agosto, la stagione è quella precedente (es. 2024/2025)
                start_year = today.year - 1
            end_year = start_year + 1
            nome_stagione_attiva = f"{start_year}/{end_year}"
            stagione_attiva, _ = Stagione.objects.get_or_create(nome=nome_stagione_attiva)
            stagione_attiva.attiva = True
            stagione_attiva.save()
        
        inseriti = 0
        for index, row in df.iterrows():
            nome_giocatore = str(row.get('Nome', '')).strip()
            if not nome_giocatore:
                continue
            
            fanta_id = row.get('Cod.') if 'Cod.' in row else row.get('Id')
            if pd.isna(fanta_id):
                continue
            fanta_id = int(fanta_id)
                
            calciatore = Calciatore.objects.filter(fanta_id=fanta_id).first()
            if not calciatore:
                calciatore = Calciatore.objects.filter(nome__iexact=nome_giocatore).first()
                if not calciatore:
                    possibili = list(Calciatore.objects.filter(nome__icontains=nome_giocatore))
                    if len(possibili) == 1:
                        calciatore = possibili[0]
                
                if calciatore:
                    calciatore.fanta_id = fanta_id
                    calciatore.save()
                else:
                    continue
            
            try:
                cs = CalciatoreStagione.objects.get(calciatore=calciatore, stagione=stagione_attiva)
            except CalciatoreStagione.DoesNotExist:
                continue
                
            voto = row.get('Voto')
            # Scarta i senza voto per non inquinare i dati (se vuoi mantenerli metti 0.0 o salva un flag SV)
            if str(voto).lower() in ['sv', 's.v.', 'none', '-', '']:
                continue
                
            try:
                voto_float = float(str(voto).replace(',', '.'))
            except ValueError:
                continue

            # Inserimento o aggiornamento del DB
            VotoPartita.objects.update_or_create(
                calciatore_stagione=cs,
                giornata=giornata,
                defaults={
                    'voto_base': voto_float,
                    'fanta_voto': float(str(row.get('Fv', voto_float)).replace(',', '.')), 
                    'gol_fatti': row.get('Gf') or 0,
                    'gol_subiti': row.get('Gs') or 0,
                    'rigori_parati': row.get('Rp') or 0,
                    'rigori_sbagliati': row.get('Rs') or 0,
                    'rigori_fatti': row.get('Rf') or 0,
                    'autogol': row.get('Au') or 0,
                    'ammonizioni': row.get('Amm') or 0,
                    'espulsioni': row.get('Esp') or 0,
                    'assist': row.get('Ass') or 0,
                }
            )
            inseriti += 1
            
        self.stdout.write(self.style.SUCCESS(f"Voti elaborati e importati con successo nel DB! Totale processati: {inseriti}"))

    def importa_quotazioni_in_db(self, file_path):
        self.stdout.write(self.style.WARNING("Parser Listone Quotazioni: DA IMPLEMENTARE. Puoi aggiungere logica Pandas simile alla scheda preasta per scansionare le righe."))
        pass

    def importa_statistiche_in_db(self, file_path, season_id):
        self.stdout.write(f"Avvio elaborazione Statistiche per l'ID Stagione {season_id}...")
        
        # Calcolo dinamico nome stagione (es. 19 -> 2024/2025)
        anno_inizio = 2005 + season_id
        nome_stagione = f"{anno_inizio}/{anno_inizio+1}"
        
        try:
            # Di solito gli export Fantacalcio hanno l'intestazione sfasata di una riga
            df = pd.read_excel(file_path, skiprows=1) 
            df = df.replace({np.nan: None})
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Errore lettura Excel: {e}"))
            return
            
        stagione_obj, _ = Stagione.objects.get_or_create(nome=nome_stagione)
        if not stagione_obj.attiva:
            # Opzionale: impostarla come attiva se è l'ultima
            pass
            
        inseriti = 0
        for index, row in df.iterrows():
            nome_giocatore = str(row.get('Nome', '')).strip()
            team_nome = str(row.get('Squadra', '')).strip() # Spesso è 'Squadra' o 'Team'
            
            if not nome_giocatore:
                continue

            # Troviamo o Creiamo la Squadra Reale
            squadra = None
            if team_nome and team_nome != 'None':
                squadra, _ = SquadraReale.objects.get_or_create(
                    nome=team_nome,
                    defaults={'sigla': team_nome[:3].upper()}
                )

            # Trova o Crea Calciatore basato su ID
            fanta_id = row.get('Cod.') if 'Cod.' in row else row.get('Id')
            if pd.isna(fanta_id):
                continue
            fanta_id = int(fanta_id)
            
            calciatore = Calciatore.objects.filter(fanta_id=fanta_id).first()
            if not calciatore:
                calciatore = Calciatore.objects.filter(nome__iexact=nome_giocatore).first()
                if not calciatore:
                    possibili = list(Calciatore.objects.filter(nome__icontains=nome_giocatore))
                    if len(possibili) == 1:
                        calciatore = possibili[0]
                
                if calciatore:
                    calciatore.fanta_id = fanta_id
                    calciatore.save()
                else:
                    calciatore, _ = Calciatore.objects.get_or_create(
                        fanta_id=fanta_id,
                        defaults={
                            'nome': nome_giocatore,
                            'ruolo_base': str(row.get('R', row.get('Ruolo', 'C')))
                        }
                    )

            # Trova o Crea CalciatoreStagione
            cs_defaults = {
                'ruolo_stagione': str(row.get('R', row.get('Ruolo', 'C'))),
                'quotazione_iniziale': row.get('Qt.I') or 1  # Qt.A/Qt.I a seconda dell'excel
            }
            if squadra:
                cs_defaults['squadra_reale'] = squadra
                
            # Assicuriamo che esista prima di salvare la statistica
            cs, _ = CalciatoreStagione.objects.get_or_create(
                calciatore=calciatore,
                stagione=stagione_obj,
                defaults=cs_defaults
            )

            # Helper per conversione stringhe con virgola a float
            def to_float(val):
                if val is None or str(val).strip() in ['', '-', 'sv', 'n.d.']:
                    return 0.0
                try:
                    return float(str(val).replace(',', '.'))
                except ValueError:
                    return 0.0

            # Salva i Dati nel Modello (sovrascrivendo grazie ad update_or_create)
            StatisticaCalciatore.objects.update_or_create(
                calciatore_stagione=cs,
                defaults={
                    'partite_a_voto': row.get('Pv') or 0,
                    'media_voto': to_float(row.get('Mv')),
                    'fanta_media': to_float(row.get('Fm')),
                    'gol_fatti': row.get('Gf') or 0,
                    'gol_subiti': row.get('Gs') or 0,
                    'rigori_parati': row.get('Rp') or 0,
                    'rigori_calciati': row.get('Rc') or 0,
                    'rigori_fatti': row.get('R+') or 0,
                    'rigori_sbagliati': row.get('R-') or 0,
                    'assist': row.get('Ass') or 0,
                    'ammonizioni': row.get('Amm') or 0,
                    'espulsioni': row.get('Esp') or 0,
                    'autogol': row.get('Au') or 0,
                }
            )
            inseriti += 1

        self.stdout.write(self.style.SUCCESS(f"Statistiche della stagione {nome_stagione} importate con successo! Totale: {inseriti}"))

