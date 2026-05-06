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
        
        try:
            from strategy.utils.importer import PreastaImporter
            # We don't have season_id as argument, default to current settings
            from django.conf import settings
            season_id = getattr(settings, 'CURRENT_SEASON_ID', 20)
            
            importer = PreastaImporter()
            creati, aggiornati = importer.elabora_file(file_path, username, season_id)
            
            self.stdout.write(self.style.SUCCESS(f"Importazione completata: {creati} record creati, {aggiornati} record aggiornati."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(str(e)))
