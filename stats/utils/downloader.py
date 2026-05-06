import os
import requests
from bs4 import BeautifulSoup
import re
import time
from django.conf import settings
from core.models import ImportTask

DOWNLOAD_FOLDER = os.path.join(settings.BASE_DIR, "dati_scaricati")

class FantaDownloader:
    def __init__(self, task_id=None):
        self.task = None
        if task_id:
            self.task = ImportTask.objects.filter(id=task_id).first()
            
        self.base_url = os.environ.get("BASE_URL", "https://api.fantacalcio.it/")
        self.base_api = os.environ.get("BASE_API", "v1/")
        self.url_api = f"{self.base_url}{self.base_api}"
        self.username = os.environ.get("FANTA_USERNAME", "")
        self.password = os.environ.get("FANTA_PASSWORD", "")
        self.session = None

    def login(self):
        url_login = f"{self.url_api}User/login"
        payload = {"username": self.username, "password": self.password}
        self.session = requests.Session()
        res = self.session.post(url_login, json=payload)
        return res.status_code == 200

    def get_last_matchday(self):
        try:
            res = requests.get(f"{self.base_url}live-serie-a")
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")
            h1 = soup.find("h1", class_="pl-2 title w-100")
            if h1 and h1.find("small"):
                match = re.search(r"Giornata (\d+)", h1.find("small").get_text())
                if match:
                    return int(match.group(1)) - 1
        except Exception:
            pass
        return 0

    def download_stats(self, season_id, force=False):
        if not self.session:
            if not self.login():
                raise Exception("Login fallito")
                
        os.makedirs(os.path.join(DOWNLOAD_FOLDER, "stats"), exist_ok=True)
        url = f"{self.url_api}Excel/stats/{season_id}/1"
        filepath = os.path.join(DOWNLOAD_FOLDER, "stats", f"statistiche_{season_id}.xlsx")
        
        # Skip if file already exists and we are not forcing download
        if not force and os.path.exists(filepath):
            return filepath
        
        res = self.session.get(url, stream=True)
        if res.status_code == 200:
            with open(filepath, "wb") as f:
                for chunk in res.iter_content(chunk_size=8192):
                    f.write(chunk)
            return filepath
        raise Exception(f"Download fallito: HTTP {res.status_code}")

    def download_voti(self, season_id, matchday, force=False):
        if not self.session:
            if not self.login():
                raise Exception("Login fallito")
                
        os.makedirs(os.path.join(DOWNLOAD_FOLDER, "voti", str(season_id)), exist_ok=True)
        url = f"{self.url_api}Excel/votes/{season_id}/{matchday}"
        filepath = os.path.join(DOWNLOAD_FOLDER, "voti", str(season_id), f"giornata_{matchday}.xlsx")
        
        # Skip if file already exists and we are not forcing download
        if not force and os.path.exists(filepath):
            return filepath
        
        res = self.session.get(url, stream=True)
        if res.status_code == 200:
            with open(filepath, "wb") as f:
                for chunk in res.iter_content(chunk_size=8192):
                    f.write(chunk)
            return filepath
        raise Exception(f"Download fallito: HTTP {res.status_code}")

    def download_all_historical_voti(self, start_season=10, end_season=None):
        try:
            if end_season is None:
                end_season = getattr(settings, 'CURRENT_SEASON_ID', 20)
                
            if self.task:
                self.task.status = 'RUNNING'
                # Stima approssimativa: 38 giornate per ogni stagione
                self.task.total_items = (end_season - start_season + 1) * 38
                self.task.save()
                
            last_day = self.get_last_matchday()
            
            for s_id in range(start_season, end_season + 1):
                max_day = 38 if s_id < end_season else last_day
                for day in range(1, max_day + 1):
                    is_current_season_last_day = (s_id == end_season and day == last_day)
                    try:
                        self.download_voti(s_id, day, force=is_current_season_last_day)
                    except Exception:
                        pass
                    
                    if self.task:
                        self.task.processed_items += 1
                        self.task.save()
                    time.sleep(1) # Previene blocchi per troppe richieste

            if self.task:
                self.task.status = 'COMPLETED'
                self.task.save()
        except Exception as e:
            if self.task:
                self.task.status = 'ERROR'
                self.task.error_message = str(e)
                self.task.save()

    def download_all_historical_stats(self, start_season=10, end_season=None):
        try:
            if end_season is None:
                end_season = getattr(settings, 'CURRENT_SEASON_ID', 20)
                
            if self.task:
                self.task.status = 'RUNNING'
                self.task.total_items = (end_season - start_season + 1)
                self.task.save()
                
            for s_id in range(start_season, end_season + 1):
                is_current_season = (s_id == end_season)
                try:
                    self.download_stats(s_id, force=is_current_season)
                except Exception:
                    pass
                
                if self.task:
                    self.task.processed_items += 1
                    self.task.save()
                time.sleep(1)

            if self.task:
                self.task.status = 'COMPLETED'
                self.task.save()
        except Exception as e:
            if self.task:
                self.task.status = 'ERROR'
                self.task.error_message = str(e)
                self.task.save()
