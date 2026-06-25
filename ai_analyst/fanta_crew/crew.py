from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import (
    FileReadTool, 
    DirectoryReadTool, 
    MDXSearchTool,
    VisionTool # Per leggere immagini
)

class FallbackLLM(LLM):
    def __new__(cls, models_fallback_list: list = None, **kwargs):
        # Bypassa il routing del provider nativo di CrewAI per rimanere un'istanza di FallbackLLM
        return object.__new__(cls)
        
    def __init__(self, models_fallback_list: list = None, **kwargs):
        model_to_use = models_fallback_list[0] if models_fallback_list else kwargs.get("model", "gemini/gemini-2.5-flash-lite")
        super().__init__(model=model_to_use, **kwargs)
        
        self.__dict__['models_fallback_list'] = models_fallback_list or [model_to_use]
        self.__dict__['current_idx'] = 0
        self.__dict__['_llm_args'] = kwargs
        self.__dict__['_current_llm'] = None
        self._init_current_llm()
        
    def _init_current_llm(self):
        model = self.models_fallback_list[self.current_idx]
        import logging
        logging.info(f"FallbackLLM: Inizializzo modello interno {model}...")
        self.__dict__['_current_llm'] = LLM(model=model, **self._llm_args)
        # Sincronizza il campo model visibile a Pydantic/CrewAI
        self.model = model
        
    def call(self, messages, *args, **kwargs):
        last_error = None
        start_idx = self.current_idx
        while True:
            try:
                import logging
                logging.info(f"FallbackLLM: Tentativo di chiamata con modello interno {self._current_llm.model}...")
                return self._current_llm.call(messages, *args, **kwargs)
            except Exception as e:
                last_error = e
                import logging
                logging.warning(f"FallbackLLM: Chiamata fallita con modello {self.models_fallback_list[self.current_idx]}. Errore: {e}")
                
                # Passa al modello successivo
                new_idx = (self.current_idx + 1) % len(self.models_fallback_list)
                self.__dict__['current_idx'] = new_idx
                
                if new_idx == start_idx:
                    raise last_error
                
                self._init_current_llm()

    def supports_multimodal(self) -> bool:
        return self._current_llm.supports_multimodal()

    def supports_function_calling(self) -> bool:
        if hasattr(self._current_llm, 'supports_function_calling'):
            return self._current_llm.supports_function_calling()
        return super().supports_function_calling()

    def supports_stop_words(self) -> bool:
        if hasattr(self._current_llm, 'supports_stop_words'):
            return self._current_llm.supports_stop_words()
        return super().supports_stop_words()

    def get_context_window_size(self) -> int:
        if hasattr(self._current_llm, 'get_context_window_size'):
            return self._current_llm.get_context_window_size()
        return super().get_context_window_size()

# Modelli da utilizzare in fallback per evitare limiti di quota (RPM/TPM/RPD)
gemini_fallback_list = [
    "gemini/gemini-2.5-flash-lite", # Prima scelta (10 RPM, 20 RPD)
    "gemini/gemini-3.1-flash-lite", # Seconda scelta (15 RPM, 500 RPD)
    "gemini/gemini-2.5-flash",      # Terza scelta (5 RPM, 20 RPD)
    "gemini/gemini-3.0-flash",      # Quarta scelta (5 RPM, 20 RPD)
    "gemini/gemini-1.5-flash",      # Quinta scelta (15 RPM, 1500 RPD)
    "gemini/gemini-1.5-flash-8b",   # Sesta scelta (15 RPM, 1500 RPD)
]

llm_pro = FallbackLLM(models_fallback_list=gemini_fallback_list, num_retries=5)
llm_flash = FallbackLLM(models_fallback_list=gemini_fallback_list, num_retries=5)

import os
# Costruiamo il percorso assoluto alla cartella dati_scaricati
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dati_dir = os.path.join(base_dir, 'dati_scaricati')

# Inizializziamo i tool per leggere i file
directory_read_tool = DirectoryReadTool(directory=dati_dir)
vision_tool = VisionTool()

from crewai.tools import tool

@tool("Leggi dati database e documenti infortuni")
def leggi_database_e_documenti_ia() -> str:
    """Carica la lista dei calciatori dal database in formato JSON compatto con chiavi abbreviate (legenda chiavi: n=nome, r=ruolo, s=squadra, q=quotazione, pv=partite a voto, mv=media voto, fm=fanta-media, gf=gol fatti, gs=gol subiti, as=assist, am=ammonizioni, es=espulsioni). Legge inoltre le ultime notizie sugli infortuni dai documenti caricati nella cartella documenti_ia, filtrando i contenuti irrilevanti per ottimizzare l'uso dei token. Restituisce un JSON compatto."""
    import os
    import json
    import re
    from django.conf import settings
    # Importiamo i modelli Django
    from players.models import CalciatoreStagione
    from stats.models import StatisticaCalciatore
    import pdfplumber
    import docx
    
    # 1. Carica i dati dal DB
    lista_giocatori = []
    try:
        from django.db.models import Q
        # Filtra i calciatori che hanno giocato almeno 1 partita per evitare record vuoti
        qs = CalciatoreStagione.objects.select_related('calciatore', 'squadra_reale', 'statistiche_riassuntive').filter(
            statistiche_riassuntive__partite_a_voto__gte=1
        )
        
        # Seleziona i top 30 per ruolo (per evitare di intasare il contesto dell'LLM)
        ruoli = ['P', 'D', 'C', 'A']
        selected_pks = []
        for r in ruoli:
            role_qs = qs.filter(ruolo_stagione=r).order_by('-statistiche_riassuntive__fanta_media')[:30]
            selected_pks.extend([item.pk for item in role_qs])
            
        # Aggiunge anche i marcatori o assist-man extra
        extra_qs = qs.filter(
            Q(statistiche_riassuntive__gol_fatti__gt=0) | Q(statistiche_riassuntive__assist__gt=0)
        ).exclude(pk__in=selected_pks)[:20]
        selected_pks.extend([item.pk for item in extra_qs])
        
        final_qs = CalciatoreStagione.objects.filter(pk__in=selected_pks).select_related('calciatore', 'squadra_reale', 'statistiche_riassuntive')
        
        for cs in final_qs:
            st = getattr(cs, 'statistiche_riassuntive', None)
            lista_giocatori.append({
                'n': cs.calciatore.nome,
                'r': cs.ruolo_stagione,
                's': cs.squadra_reale.nome if cs.squadra_reale else "N/D",
                'q': cs.quotazione_iniziale,
                'pv': st.partite_a_voto if st else 0,
                'mv': float(st.media_voto) if st else 0.0,
                'fm': float(st.fanta_media) if st else 0.0,
                'gf': st.gol_fatti if st else 0,
                'gs': st.gol_subiti if st else 0,
                'as': st.assist if st else 0,
                'am': st.ammonizioni if st else 0,
                'es': st.espulsioni if st else 0
            })
    except Exception as e:
        lista_giocatori = f"Errore query DB: {e}"
        
    # 2. Legge notizie infortuni/formazioni da documenti_ia
    notizie_ia = []
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    doc_dir = os.path.join(base_dir, 'dati_scaricati', 'documenti_ia')
    
    if os.path.exists(doc_dir):
        for filename in os.listdir(doc_dir):
            if filename == '.gitkeep':
                continue
            file_path = os.path.join(doc_dir, filename)
            ext = os.path.splitext(filename)[1].lower()
            try:
                content = ""
                if ext == '.pdf':
                    with pdfplumber.open(file_path) as pdf:
                        content = "\n".join([page.extract_text() or "" for page in pdf.pages])
                elif ext == '.docx':
                    doc = docx.Document(file_path)
                    content = "\n".join([p.text for p in doc.paragraphs])
                elif ext in ['.txt', '.json']:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                
                if content:
                    # Filtra solo i paragrafi o righe contenenti parole chiave rilevanti per risparmiare token
                    lines = content.split('\n')
                    keywords = re.compile(r'infort|lesion|squalific|rientr|recuper|stop|indispon|formazion|fermo', re.IGNORECASE)
                    filtered_lines = [line.strip() for line in lines if keywords.search(line)]
                    filtered_content = "\n".join(filtered_lines)
                    
                    # Se non ci sono righe filtrate, usa i primi 1000 caratteri come fallback
                    if not filtered_content.strip():
                        filtered_content = content[:1000] + "... [TRONCATO]"
                    elif len(filtered_content) > 3000:
                        filtered_content = filtered_content[:3000] + "... [TRONCATO]"
                        
                    notizie_ia.append({
                        'fonte': filename,
                        'testo': filtered_content
                    })
            except Exception as e:
                notizie_ia.append({
                    'fonte': filename,
                    'errore': str(e)
                })
                
    output = {
        'database_calciatori': lista_giocatori,
        'notizie_e_infortuni_ia': notizie_ia
    }
    
    return json.dumps(output, ensure_ascii=False)

@CrewBase
class FantaAnalystCrew():
    """FantaDash Data Analysis Crew"""
    
    @agent
    def fanta_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['fanta_analyst'],
            tools=[directory_read_tool, leggi_database_e_documenti_ia, vision_tool],
            llm=llm_pro, 
            verbose=True,
            max_iter=3,
            cache=False
        )

    @task
    def analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config['analysis_task'],
            output_file='report_analisi_avanzata.md'
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            cache=False
        )
