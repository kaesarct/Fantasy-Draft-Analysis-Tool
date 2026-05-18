from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
import threading
import time
import logging
from core.models import ImportTask
from stats.utils.downloader import FantaDownloader
from stats.utils.importer import FantaImporter
from strategy.utils.importer import PreastaImporter

log = logging.getLogger('stats.views')

def run_download_stats(task_id):
    log.info("[VIEW] Thread avviato: run_download_stats (task_id=%s)", task_id)
    t0 = time.perf_counter()
    downloader = FantaDownloader(task_id)
    downloader.download_all_historical_stats()
    log.info("[VIEW] run_download_stats completato in %.2fs", time.perf_counter() - t0)

def run_import_stats(task_id):
    log.info("[VIEW] Thread avviato: run_import_stats (task_id=%s)", task_id)
    t0 = time.perf_counter()
    importer = FantaImporter(task_id)
    importer.import_all_stats()
    log.info("[VIEW] run_import_stats completato in %.2fs", time.perf_counter() - t0)

def run_download_voti(task_id):
    log.info("[VIEW] Thread avviato: run_download_voti (task_id=%s)", task_id)
    t0 = time.perf_counter()
    downloader = FantaDownloader(task_id)
    downloader.download_all_historical_voti()
    log.info("[VIEW] run_download_voti completato in %.2fs", time.perf_counter() - t0)

def run_import_voti(task_id):
    log.info("[VIEW] Thread avviato: run_import_voti (task_id=%s)", task_id)
    t0 = time.perf_counter()
    importer = FantaImporter(task_id)
    importer.import_all_voti()
    log.info("[VIEW] run_import_voti completato in %.2fs", time.perf_counter() - t0)

def run_import_preasta(task_id, file_path, username, season_id):
    log.info("[VIEW] Thread avviato: run_import_preasta (task_id=%s, season=%s, user=%s)", task_id, season_id, username)
    t0 = time.perf_counter()
    importer = PreastaImporter(task_id)
    try:
        importer.elabora_file(file_path, username, season_id)
        log.info("[VIEW] run_import_preasta completato in %.2fs", time.perf_counter() - t0)
    except Exception as e:
        log.exception("[VIEW] Errore in run_import_preasta: %s", e)
        task = ImportTask.objects.filter(id=task_id).first()
        if task:
            task.status = 'ERROR'
            task.error_message = str(e)
            task.save()

@staff_member_required
def dashboard_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'download_stats':
            log.info("[VIEW] Action 'download_stats' richiesta da %s", request.user)
            task = ImportTask.objects.create(task_name="Download Storico Statistiche", total_items=1, status='PENDING')
            threading.Thread(target=run_download_stats, args=(task.id,)).start()
            return JsonResponse({'status': 'ok', 'task_id': task.id})
        elif action == 'import_stats':
            log.info("[VIEW] Action 'import_stats' richiesta da %s", request.user)
            task = ImportTask.objects.create(task_name="Import Storico Statistiche", total_items=1, status='PENDING')
            threading.Thread(target=run_import_stats, args=(task.id,)).start()
            return JsonResponse({'status': 'ok', 'task_id': task.id})
        elif action == 'download_voti':
            log.info("[VIEW] Action 'download_voti' richiesta da %s", request.user)
            task = ImportTask.objects.create(task_name="Download Storico Voti", total_items=1, status='PENDING')
            threading.Thread(target=run_download_voti, args=(task.id,)).start()
            return JsonResponse({'status': 'ok', 'task_id': task.id})
        elif action == 'import_voti':
            log.info("[VIEW] Action 'import_voti' richiesta da %s", request.user)
            task = ImportTask.objects.create(task_name="Import Storico Voti", total_items=1, status='PENDING')
            threading.Thread(target=run_import_voti, args=(task.id,)).start()
            return JsonResponse({'status': 'ok', 'task_id': task.id})
        elif action == 'import_preasta':
            log.info("[VIEW] Action 'import_preasta' richiesta da %s", request.user)
            file_obj = request.FILES.get('file')
            season_id = request.POST.get('season_id', '20')
            if not file_obj:
                return JsonResponse({'status': 'error', 'message': 'Nessun file caricato'}, status=400)
            
            from django.core.files.storage import FileSystemStorage
            from django.conf import settings
            import os
            
            # Salva il file
            upload_dir = os.path.join(settings.BASE_DIR, 'dati_scaricati', 'preasta')
            os.makedirs(upload_dir, exist_ok=True)
            fs = FileSystemStorage(location=upload_dir)
            
            # Sovrascriviamo se esiste
            filename = f"preasta_stagione_{season_id}.xlsx"
            file_path = os.path.join(upload_dir, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
            fs.save(filename, file_obj)
            
            # Lancia il task
            task = ImportTask.objects.create(task_name=f"Import Pre-Asta (Stagione {season_id})", total_items=1, status='PENDING')
            threading.Thread(target=run_import_preasta, args=(task.id, file_path, request.user.username, season_id)).start()
            
            return JsonResponse({'status': 'ok', 'task_id': task.id})
        elif action == 'clear_preasta':
            log.warning("[VIEW] Action 'clear_preasta' eseguita da %s", request.user)
            from strategy.models import AnalisiPreAsta
            count, _ = AnalisiPreAsta.objects.filter(utente=request.user).delete()
            log.warning("[VIEW] %d record di AnalisiPreAsta eliminati da %s", count, request.user)
            return JsonResponse({'status': 'deleted', 'message': f'Eliminati {count} record pre-asta.'})
        elif action == 'delete_all_data':
            log.warning("[VIEW] Action 'delete_all_data' eseguita da %s", request.user)
            from players.models import Calciatore
            from core.models import SquadraReale, Stagione
            
            Calciatore.objects.all().delete()
            SquadraReale.objects.all().delete()
            Stagione.objects.all().delete()
            log.warning("[VIEW] Database svuotato da %s", request.user)
            return JsonResponse({'status': 'deleted'})

    tasks = ImportTask.objects.order_by('-created_at')[:10]
    return render(request, 'admin/import_dashboard.html', {'tasks': tasks})

@staff_member_required
def task_status(request, task_id):
    task = ImportTask.objects.filter(id=task_id).first()
    if task:
        return JsonResponse({
            'status': task.status,
            'processed': task.processed_items,
            'total': task.total_items,
            'status_display': task.get_status_display(),
            'error': task.error_message
        })
    return JsonResponse({'status': 'NOT_FOUND'}, status=404)
