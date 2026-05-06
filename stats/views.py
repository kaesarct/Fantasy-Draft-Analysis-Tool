from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
import threading
from core.models import ImportTask
from stats.utils.downloader import FantaDownloader
from stats.utils.importer import FantaImporter

def run_download_stats(task_id):
    downloader = FantaDownloader(task_id)
    downloader.download_all_historical_stats()

def run_import_stats(task_id):
    importer = FantaImporter(task_id)
    importer.import_all_stats()

def run_download_voti(task_id):
    downloader = FantaDownloader(task_id)
    downloader.download_all_historical_voti()

def run_import_voti(task_id):
    importer = FantaImporter(task_id)
    importer.import_all_voti()

@staff_member_required
def dashboard_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'download_stats':
            task = ImportTask.objects.create(task_name="Download Storico Statistiche", total_items=1, status='PENDING')
            threading.Thread(target=run_download_stats, args=(task.id,)).start()
            return JsonResponse({'status': 'ok', 'task_id': task.id})
        elif action == 'import_stats':
            task = ImportTask.objects.create(task_name="Import Storico Statistiche", total_items=1, status='PENDING')
            threading.Thread(target=run_import_stats, args=(task.id,)).start()
            return JsonResponse({'status': 'ok', 'task_id': task.id})
        elif action == 'download_voti':
            task = ImportTask.objects.create(task_name="Download Storico Voti", total_items=1, status='PENDING')
            threading.Thread(target=run_download_voti, args=(task.id,)).start()
            return JsonResponse({'status': 'ok', 'task_id': task.id})
        elif action == 'import_voti':
            task = ImportTask.objects.create(task_name="Import Storico Voti", total_items=1, status='PENDING')
            threading.Thread(target=run_import_voti, args=(task.id,)).start()
            return JsonResponse({'status': 'ok', 'task_id': task.id})
        elif action == 'delete_all_data':
            from players.models import Calciatore
            from core.models import SquadraReale, Stagione
            
            Calciatore.objects.all().delete()
            SquadraReale.objects.all().delete()
            Stagione.objects.all().delete()
            
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
