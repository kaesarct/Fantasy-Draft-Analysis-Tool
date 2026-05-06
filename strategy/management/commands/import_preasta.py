from django.core.management.base import BaseCommand
import pandas as pd
import numpy as np
from players.models import Calciatore, CalciatoreStagione
from core.models import Stagione, SquadraReale
from strategy.models import AnalisiPreAsta
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Importa l\'analisi pre-asta da un file Excel personalizzato'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, help='Percorso del file Excel')
        parser.add_argument('--user', type=str, help='Username dell\'utente a cui associare le analisi')

    def handle(self, *args, **options):
        file_path = options['file']
        username = options['user']
        
        if not file_path or not username:
            self.stdout.write(self.style.ERROR("Devi specificare --file e --user"))
            return
            
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Utente '{username}' non trovato"))
            return
            
        self.stdout.write(self.style.SUCCESS(f"Iniziando l'importazione da {file_path} per l'utente {username}..."))
        
        # Recupera la stagione attiva o ne crea una di default
        stagione_attiva, _ = Stagione.objects.get_or_create(attiva=True, defaults={'nome': '2024/2025'})

        try:
            df = pd.read_excel(file_path)
            # Convertiamo i NaN di pandas in None per non rompere il DB
            df = df.replace({np.nan: None})
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Errore nella lettura del file Excel: {e}"))
            return

        creati = 0
        aggiornati = 0

        for index, row in df.iterrows():
            nome_completo = str(row.get('Nome', '')).strip()
            team_nome = str(row.get('Team', '')).strip()
            
            if not nome_completo or nome_completo == 'None':
                continue

            # 1. Trova o Crea Squadra Reale
            squadra, _ = SquadraReale.objects.get_or_create(
                nome=team_nome,
                defaults={'sigla': team_nome[:3].upper()}
            )

            # 2. Trova o Crea Anagrafica Calciatore
            # Molti Excel fanta uniscono nome e cognome. Una divisione basilare:
            parti = nome_completo.split(' ', 1)
            if len(parti) > 1:
                nome_gioc, cognome_gioc = parti[1], parti[0] # Di solito è "Cognome Nome"
            else:
                nome_gioc, cognome_gioc = "", nome_completo
                
            calciatore, _ = Calciatore.objects.get_or_create(
                cognome=cognome_gioc,
                nome=nome_gioc,
                defaults={'ruolo_base': str(row.get('Ruolo', 'C'))}
            )

            # 3. Assicura che esista il Calciatore legato alla Stagione attiva
            cs, _ = CalciatoreStagione.objects.get_or_create(
                calciatore=calciatore,
                stagione=stagione_attiva,
                defaults={
                    'squadra_reale': squadra,
                    'ruolo_stagione': str(row.get('Ruolo', 'C')),
                    'quotazione_iniziale': row.get('Quo', 1) or 1
                }
            )

            # 4. Crea o Aggiorna la scheda strategica
            obj, created = AnalisiPreAsta.objects.update_or_create(
                calciatore_stagione=cs,
                utente=user,
                defaults={
                    'obiettivo': str(row.get('Obiett.', ''))[:50] if row.get('Obiett.') else '',
                    'fascia': row.get('Fascia'),
                    'prezzo_massimo': row.get('Prezzo') or 0,
                    'budget_percentuale': row.get('Budget'),
                    'pma': row.get('PMA'),
                    'quotazione': row.get('Quo') or 0,
                    
                    'titolarita': row.get('Titolarità'),
                    'affidabilita': row.get('Affidabilità'),
                    'integrita': row.get('Integrità'),
                    
                    'commento': str(row.get('Commento', '')) if row.get('Commento') else '',
                    'nota_1': str(row.get('Nota 1', ''))[:255] if row.get('Nota 1') else '',
                    'nota_2': str(row.get('Nota 2', ''))[:255] if row.get('Nota 2') else '',
                    'nota_3': str(row.get('Nota 3', ''))[:255] if row.get('Nota 3') else '',
                    'nota_4': str(row.get('Nota 4', ''))[:255] if row.get('Nota 4') else '',
                    'nota_5': str(row.get('Nota 5', ''))[:255] if row.get('Nota 5') else '',
                    
                    # Dati predittivi
                    'fmv_exp': row.get('FMV Exp.'),
                    'pt_tit': row.get('Pt. Tit.'),
                    'minuti': row.get('Minuti'),
                    'pt_inf': row.get('Pt. Inf.'),
                }
            )
            
            if created:
                creati += 1
            else:
                aggiornati += 1

        self.stdout.write(self.style.SUCCESS(f"Importazione completata: {creati} record creati, {aggiornati} record aggiornati."))
