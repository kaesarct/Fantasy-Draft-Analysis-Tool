import pandas as pd
import numpy as np
import time
import logging
from players.models import Calciatore, CalciatoreStagione
from core.models import Stagione, SquadraReale, ImportTask
from strategy.models import AnalisiPreAsta
from django.contrib.auth import get_user_model

log = logging.getLogger('strategy.importer')
User = get_user_model()


def _to_decimal(val):
    """Converte un valore in Decimal, gestendo il simbolo % e valori None/vuoti.
    Es: '8.6%' -> Decimal('8.6'), 0.086 -> Decimal('0.086'), None -> None
    """
    if val is None:
        return None
    s = str(val).strip().replace('%', '').replace(',', '.')
    if s in ('', '-', 'None', 'nan'):
        return None
    try:
        from decimal import Decimal
        return Decimal(s)
    except Exception:
        return None


def _to_int(val):
    """Converte un valore in intero, restituisce None se non convertibile."""
    if val is None:
        return None
    s = str(val).strip().replace('%', '').replace(',', '.').split('.')[0]
    if s in ('', '-', 'None', 'nan'):
        return None
    try:
        return int(s)
    except Exception:
        return None

class PreastaImporter:
    def __init__(self, task_id=None):
        self.task = None
        if task_id:
            self.task = ImportTask.objects.filter(id=task_id).first()

    def _get_or_create_squadra(self, nome):
        """Crea una SquadraReale con una sigla univoca.
        
        Se i primi 3 caratteri collidono con una sigla già esistente,
        aggiunge un suffisso numerico (INT, IN2, IN3, ...) finché trova
        una sigla libera.
        """
        from django.db import IntegrityError
        base_sigla = nome[:3].upper()
        sigla = base_sigla
        counter = 2
        while True:
            try:
                squadra = SquadraReale.objects.create(nome=nome, sigla=sigla)
                log.debug(f"[PREASTA] Nuova squadra creata: {nome} ({sigla})")
                return squadra
            except IntegrityError:
                # La sigla esiste già: riprova con suffisso numerico
                # oppure il nome è già stato creato da un'altra riga concorrente
                existing = SquadraReale.objects.filter(nome=nome).first()
                if existing:
                    return existing
                # Sigla in conflitto: genera una nuova
                sigla = f"{base_sigla[:2]}{counter}"
                counter += 1
                if counter > 99:
                    raise Exception(f"Impossibile generare sigla unica per squadra '{nome}'")

    def elabora_file(self, file_path, username, season_id):
        t_total = time.perf_counter()
        log.info(f"[PREASTA] Avvio elaborazione file={file_path} user={username} season_id={season_id}")
        try:
            if self.task:
                self.task.status = 'RUNNING'
                self.task.save()
                
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                log.error("[PREASTA] Utente '%s' non trovato", username)
                raise Exception(f"Utente '{username}' non trovato")
                
            anno_inizio = 2005 + int(season_id)
            nome_stagione = f"{anno_inizio}/{anno_inizio+1}"
            stagione_attiva, _ = Stagione.objects.get_or_create(nome=nome_stagione)
            
            try:
                df = pd.read_excel(file_path)
                df = df.replace({np.nan: None})
            except Exception as e:
                log.error("[PREASTA] Errore lettura Excel %s: %s", file_path, e)
                raise Exception(f"Errore nella lettura del file Excel: {e}")

            if self.task:
                self.task.total_items = len(df)
                self.task.save()

            creati = 0
            aggiornati = 0

            for index, row in df.iterrows():
                nome_completo = str(row.get('Nome', '')).strip()
                team_nome = str(row.get('Team', '')).strip()
                
                if not nome_completo or nome_completo == 'None':
                    continue

                # 1. Trova o Crea Squadra Reale
                # Usiamo filter().first() + creazione manuale per evitare
                # l'IntegrityError UNIQUE su sigla quando due nomi diversi
                # hanno gli stessi primi 3 caratteri (es. "Inter" e "Internazionale").
                squadra = SquadraReale.objects.filter(nome=team_nome).first()
                if not squadra:
                    squadra = self._get_or_create_squadra(team_nome)

                # 2. Trova o Crea Anagrafica Calciatore
                parti = nome_completo.rsplit(' ', 1)
                cognome_excel = parti[0].strip()
                nome_excel = parti[1].strip() if len(parti) > 1 else ""

                calciatore = Calciatore.objects.filter(cognome__iexact=cognome_excel).first()
                if not calciatore:
                    calciatore, _ = Calciatore.objects.get_or_create(
                        cognome=cognome_excel,
                        nome=nome_excel,
                        defaults={'ruolo_base': str(row.get('Ruolo', 'C'))}
                    )

                # 3. Assicura che esista il Calciatore legato alla Stagione
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
                        'fascia': str(row.get('Fascia', '') or '').strip() or None,
                        'prezzo_massimo': _to_int(row.get('Prezzo')) or 0,
                        'budget_percentuale': _to_decimal(row.get('Budget')),
                        'pma': _to_decimal(row.get('PMA')),
                        'quotazione': _to_int(row.get('Quo')) or 0,
                        
                        'titolarita': _to_int(row.get('Titolarità')),
                        'affidabilita': _to_int(row.get('Affidabilità')),
                        'integrita': _to_int(row.get('Integrità')),
                        
                        'commento': str(row.get('Commento', '')) if row.get('Commento') else '',
                        'nota_1': str(row.get('Nota 1', ''))[:255] if row.get('Nota 1') else '',
                        'nota_2': str(row.get('Nota 2', ''))[:255] if row.get('Nota 2') else '',
                        'nota_3': str(row.get('Nota 3', ''))[:255] if row.get('Nota 3') else '',
                        'nota_4': str(row.get('Nota 4', ''))[:255] if row.get('Nota 4') else '',
                        'nota_5': str(row.get('Nota 5', ''))[:255] if row.get('Nota 5') else '',
                        
                        # Dati predittivi
                        'fmv_exp': _to_decimal(row.get('FMV Exp.')),
                        'pt_tit': _to_decimal(row.get('Pt. Tit.')),
                        'minuti': _to_int(row.get('Minuti')),
                        'pt_inf': _to_decimal(row.get('Pt. Inf.')),
                    }
                )
                
                if created:
                    creati += 1
                else:
                    aggiornati += 1

                if self.task:
                    self.task.processed_items += 1
                    if self.task.processed_items % 10 == 0:
                        log.debug("[PREASTA] Progresso: %d/%d", self.task.processed_items, self.task.total_items)
                        self.task.save()
            
            if self.task:
                self.task.status = 'COMPLETED'
                self.task.save()

            elapsed = time.perf_counter() - t_total
            log.info("[PREASTA] Completato: %d creati, %d aggiornati in %.2fs", creati, aggiornati, elapsed)
            return creati, aggiornati

        except Exception as e:
            log.exception("[PREASTA] Errore durante elaborazione: %s", e)
            if self.task:
                self.task.status = 'ERROR'
                self.task.error_message = str(e)
                self.task.save()
            raise e
