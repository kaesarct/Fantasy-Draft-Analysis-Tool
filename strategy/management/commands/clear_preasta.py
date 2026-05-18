from django.core.management.base import BaseCommand
from strategy.models import AnalisiPreAsta
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Svuota i dati delle analisi pre-asta (AnalisiPreAsta)'

    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, help='Username dell\'utente per cui svuotare le analisi')
        parser.add_argument('--all', action='store_true', help='Svuota le analisi di tutti gli utenti')

    def handle(self, *args, **options):
        username = options.get('user')
        clear_all = options.get('all')
        
        if not username and not clear_all:
            self.stdout.write(self.style.ERROR("Devi specificare --user <username> oppure --all per svuotare tutti i dati."))
            return
            
        if clear_all:
            count, _ = AnalisiPreAsta.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f"Svuotamento completato: cancellati {count} record di AnalisiPreAsta per tutti gli utenti."))
        else:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Utente '{username}' non trovato"))
                return
                
            count, _ = AnalisiPreAsta.objects.filter(utente=user).delete()
            self.stdout.write(self.style.SUCCESS(f"Svuotamento completato: cancellati {count} record di AnalisiPreAsta per l'utente {username}."))
