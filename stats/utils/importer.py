import os
import glob
import time
import logging
import pandas as pd
import numpy as np
from django.conf import settings
from core.models import ImportTask, SquadraReale, Stagione
from players.models import Calciatore, CalciatoreStagione
from stats.models import VotoPartita, StatisticaCalciatore

log = logging.getLogger('stats.importer')

DOWNLOAD_FOLDER = os.path.join(settings.BASE_DIR, "dati_scaricati")

def to_float(val):
    if val is None or str(val).strip() in ['', '-', 'sv', 'n.d.', 'None']:
        return 0.0
    try:
        return float(str(val).replace(',', '.'))
    except ValueError:
        return 0.0

class FantaImporter:
    def __init__(self, task_id=None):
        self.task = None
        if task_id:
            self.task = ImportTask.objects.filter(id=task_id).first()

    def elabora_file_statistiche(self, file_path, season_id):
        t0 = time.perf_counter()
        anno_inizio = 2005 + season_id
        nome_stagione = f"{anno_inizio}/{anno_inizio+1}"
        log.debug("[STATS] Inizio elaborazione %s (stagione %s)", os.path.basename(file_path), nome_stagione)
        
        try:
            df = pd.read_excel(file_path, skiprows=1) 
            df = df.replace({np.nan: None})
        except Exception as e:
            log.error("[STATS] Errore lettura Excel %s: %s", file_path, e)
            return
            
        stagione_obj, _ = Stagione.objects.get_or_create(nome=nome_stagione)
        
        for index, row in df.iterrows():
            nome_giocatore = str(row.get('Nome', '')).strip()
            team_nome = str(row.get('Squadra', '')).strip()
            if not nome_giocatore or nome_giocatore == 'None':
                continue

            squadra = None
            if team_nome and team_nome != 'None':
                squadra, _ = SquadraReale.objects.get_or_create(
                    nome=team_nome,
                    defaults={'sigla': team_nome[:3].upper()}
                )

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

            cs_defaults = {'ruolo_stagione': str(row.get('R', row.get('Ruolo', 'C'))), 'quotazione_iniziale': row.get('Qt.I') or 1}
            if squadra:
                cs_defaults['squadra_reale'] = squadra
                
            cs, _ = CalciatoreStagione.objects.get_or_create(
                calciatore=calciatore, stagione=stagione_obj, defaults=cs_defaults
            )

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

        elapsed = time.perf_counter() - t0
        log.info("[STATS] Completata %s: %d righe in %.2fs", os.path.basename(file_path), len(df), elapsed)

    def import_all_stats(self):
        t_total = time.perf_counter()
        log.info("[STATS] Avvio import_all_stats")
        try:
            files = glob.glob(os.path.join(DOWNLOAD_FOLDER, "stats", "*.xlsx"))
            log.info("[STATS] Trovati %d file statistiche", len(files))
            if self.task:
                self.task.status = 'RUNNING'
                self.task.total_items = len(files)
                self.task.save()

            for filepath in files:
                filename = os.path.basename(filepath)
                season_id_str = filename.replace("statistiche_", "").replace(".xlsx", "")
                if season_id_str.isdigit():
                    self.elabora_file_statistiche(filepath, int(season_id_str))
                
                if self.task:
                    self.task.processed_items += 1
                    self.task.save()

            if self.task:
                self.task.status = 'COMPLETED'
                self.task.save()
            log.info("[STATS] import_all_stats completato in %.2fs", time.perf_counter() - t_total)
        except Exception as e:
            log.exception("[STATS] Errore in import_all_stats: %s", e)
            if self.task:
                self.task.status = 'ERROR'
                self.task.error_message = str(e)
                self.task.save()

    def elabora_file_voti(self, file_path, season_id, giornata):
        t0 = time.perf_counter()
        anno_inizio = 2005 + season_id
        nome_stagione = f"{anno_inizio}/{anno_inizio+1}"
        log.debug("[VOTI] Inizio elaborazione %s (stagione %s, giornata %d)", os.path.basename(file_path), nome_stagione, giornata)
        
        try:
            df = pd.read_excel(file_path, header=None) 
            df = df.replace({np.nan: None})
        except Exception as e:
            log.error("[VOTI] Errore lettura Excel %s: %s", file_path, e)
            return
            
        stagione_obj, _ = Stagione.objects.get_or_create(nome=nome_stagione)
        
        def to_int(val):
            try:
                return int(val)
            except:
                return 0

        for index, row in df.iterrows():
            ruolo = str(row[1]).strip()
            # Ignoriamo righe vuote, intestazioni di squadra o allenatori
            if ruolo not in ['P', 'D', 'C', 'A']:
                continue
                
            nome_giocatore = str(row[2]).strip()
            if not nome_giocatore:
                continue
                
            fanta_id = row[0]
            if pd.isna(fanta_id):
                continue
            try:
                fanta_id = int(fanta_id)
            except ValueError:
                continue

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
                cs = CalciatoreStagione.objects.get(calciatore=calciatore, stagione=stagione_obj)
            except CalciatoreStagione.DoesNotExist:
                continue
                
            voto = str(row[3]).replace('*', '').strip()
            if voto.lower() in ['sv', 's.v.', 'none', '-', '']:
                continue
                
            try:
                voto_float = float(voto.replace(',', '.'))
            except ValueError:
                continue

            gf = to_int(row[4])
            gs = to_int(row[5])
            rp = to_int(row[6])
            rs = to_int(row[7])
            rf = to_int(row[8])
            au = to_int(row[9])
            amm = to_int(row[10])
            esp = to_int(row[11])
            ass = to_int(row[12])

            fanta_voto = voto_float + (3 * gf) - gs + (3 * rp) - (3 * rs) + (3 * rf) - (2 * au) - (0.5 * amm) - esp + ass

            VotoPartita.objects.update_or_create(
                calciatore_stagione=cs,
                giornata=giornata,
                defaults={
                    'voto_base': voto_float,
                    'fanta_voto': fanta_voto, 
                    'gol_fatti': gf,
                    'gol_subiti': gs,
                    'rigori_parati': rp,
                    'rigori_sbagliati': rs,
                    'rigori_fatti': rf,
                    'autogol': au,
                    'ammonizioni': amm,
                    'espulsioni': esp,
                    'assist': ass,
                }
            )

        elapsed = time.perf_counter() - t0
        log.debug("[VOTI] Completata giornata %d stagione %s in %.2fs", giornata, nome_stagione, elapsed)

    def import_all_voti(self):
        t_total = time.perf_counter()
        log.info("[VOTI] Avvio import_all_voti")
        try:
            files = glob.glob(os.path.join(DOWNLOAD_FOLDER, "voti", "*", "*.xlsx"))
            log.info("[VOTI] Trovati %d file voti", len(files))
            if self.task:
                self.task.status = 'RUNNING'
                self.task.total_items = len(files)
                self.task.save()

            for filepath in files:
                parts = filepath.split(os.sep)
                season_id_str = parts[-2]
                giornata_str = parts[-1].replace("giornata_", "").replace(".xlsx", "")
                
                if season_id_str.isdigit() and giornata_str.isdigit():
                    self.elabora_file_voti(filepath, int(season_id_str), int(giornata_str))
                
                if self.task:
                    self.task.processed_items += 1
                    self.task.save()

            if self.task:
                self.task.status = 'COMPLETED'
                self.task.save()
            log.info("[VOTI] import_all_voti completato in %.2fs", time.perf_counter() - t_total)
        except Exception as e:
            log.exception("[VOTI] Errore in import_all_voti: %s", e)
            if self.task:
                self.task.status = 'ERROR'
                self.task.error_message = str(e)
                self.task.save()
