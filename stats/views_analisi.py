import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q

from core.models import Stagione
from players.models import Calciatore, CalciatoreStagione
from stats.models import StatisticaCalciatore, VotoPartita
from strategy.models import AnalisiPreAsta

log = logging.getLogger('stats.analisi')


# ─────────────────────────────────────────────────────────────
# HOME DASHBOARD
# ─────────────────────────────────────────────────────────────

@login_required
def home_view(request):
    from players.models import Calciatore
    from stats.models import VotoPartita
    return render(request, 'home.html', {
        'n_calciatori': Calciatore.objects.count(),
        'n_stagioni': Stagione.objects.count(),
        'n_voti': VotoPartita.objects.count(),
        'n_preasta': AnalisiPreAsta.objects.filter(utente=request.user).count(),
    })


# ─────────────────────────────────────────────────────────────
# SCHEDA GIOCATORE — incrocio storico + pre-asta
# ─────────────────────────────────────────────────────────────

@login_required
def giocatore_view(request):
    query = request.GET.get('q', '').strip()
    stagione_id = request.GET.get('stagione')
    calciatore = None
    storico = []
    voti_stagione = []
    preasta = None
    stagioni = Stagione.objects.all().order_by('-nome')

    if query:
        calciatore = (
            Calciatore.objects.filter(
                nome__icontains=query
            ).first()
        )

    if calciatore:
        # Storico annuale: statistiche per ogni stagione
        stagioni_cs = CalciatoreStagione.objects.filter(
            calciatore=calciatore
        ).select_related(
            'stagione', 'squadra_reale', 'statistiche_riassuntive'
        ).order_by('-stagione__nome')

        for cs in stagioni_cs:
            stat = getattr(cs, 'statistiche_riassuntive', None)
            storico.append({
                'stagione': cs.stagione,
                'squadra': cs.squadra_reale,
                'ruolo': cs.get_ruolo_stagione_display(),
                'quotazione': cs.quotazione_iniziale,
                'pv': stat.partite_a_voto if stat else '-',
                'mv': stat.media_voto if stat else '-',
                'fm': stat.fanta_media if stat else '-',
                'gf': stat.gol_fatti if stat else 0,
                'ass': stat.assist if stat else 0,
                'amm': stat.ammonizioni if stat else 0,
                'esp': stat.espulsioni if stat else 0,
            })

        # Voti giornata per giornata (stagione selezionata o ultima)
        stagione_corrente = None
        if stagione_id:
            stagione_corrente = Stagione.objects.filter(id=stagione_id).first()
        if not stagione_corrente and stagioni_cs.exists():
            stagione_corrente = stagioni_cs.first().stagione

        if stagione_corrente:
            cs_corrente = CalciatoreStagione.objects.filter(
                calciatore=calciatore, stagione=stagione_corrente
            ).first()
            if cs_corrente:
                voti_stagione = VotoPartita.objects.filter(
                    calciatore_stagione=cs_corrente
                ).order_by('giornata')

        # Analisi pre-asta dell'utente corrente
        if request.user.is_authenticated and stagioni_cs.exists():
            cs_last = stagioni_cs.first()
            preasta = AnalisiPreAsta.objects.filter(
                calciatore_stagione=cs_last,
                utente=request.user
            ).first()

    return render(request, 'analisi/giocatore.html', {
        'query': query,
        'calciatore': calciatore,
        'storico': storico,
        'voti_stagione': voti_stagione,
        'preasta': preasta,
        'stagioni': stagioni,
        'stagione_id': int(stagione_id) if stagione_id else None,
    })


# ─────────────────────────────────────────────────────────────
# CLASSIFICA — per stagione e ruolo
# ─────────────────────────────────────────────────────────────

@login_required
def classifica_view(request):
    stagioni = Stagione.objects.all().order_by('-nome')
    stagione_id = request.GET.get('stagione')
    ruolo = request.GET.get('ruolo', '')
    order_by = request.GET.get('order', 'fanta_media')

    # Campi ordinabili sicuri
    ORDER_FIELDS = {
        'fanta_media': '-statistiche_riassuntive__fanta_media',
        'media_voto': '-statistiche_riassuntive__media_voto',
        'gol': '-statistiche_riassuntive__gol_fatti',
        'assist': '-statistiche_riassuntive__assist',
        'pv': '-statistiche_riassuntive__partite_a_voto',
    }
    order_field = ORDER_FIELDS.get(order_by, '-statistiche_riassuntive__fanta_media')

    stagione_sel = None
    if stagione_id:
        stagione_sel = Stagione.objects.filter(id=stagione_id).first()
    if not stagione_sel:
        stagione_sel = stagioni.first()

    qs = CalciatoreStagione.objects.filter(
        stagione=stagione_sel
    ).select_related(
        'calciatore', 'squadra_reale', 'statistiche_riassuntive'
    ).exclude(statistiche_riassuntive=None)

    if ruolo:
        qs = qs.filter(ruolo_stagione=ruolo)

    qs = qs.order_by(order_field)[:100]

    return render(request, 'analisi/classifica.html', {
        'stagioni': stagioni,
        'stagione_sel': stagione_sel,
        'ruolo': ruolo,
        'order_by': order_by,
        'calciatori': qs,
    })


# ─────────────────────────────────────────────────────────────
# CONFRONTO — 2 giocatori side-by-side
# ─────────────────────────────────────────────────────────────

@login_required
def confronto_view(request):
    q1 = request.GET.get('q1', '').strip()
    q2 = request.GET.get('q2', '').strip()

    def cerca(query):
        if not query:
            return None, []
        c = Calciatore.objects.filter(
            nome__icontains=query
        ).first()
        if not c:
            return None, []
        storico = []
        for cs in CalciatoreStagione.objects.filter(calciatore=c).select_related(
            'stagione', 'squadra_reale', 'statistiche_riassuntive'
        ).order_by('-stagione__nome'):
            stat = getattr(cs, 'statistiche_riassuntive', None)
            storico.append({
                'stagione': cs.stagione.nome,
                'squadra': cs.squadra_reale.nome if cs.squadra_reale else '-',
                'ruolo': cs.get_ruolo_stagione_display(),
                'pv': stat.partite_a_voto if stat else '-',
                'mv': float(stat.media_voto) if stat else 0,
                'fm': float(stat.fanta_media) if stat else 0,
                'gf': stat.gol_fatti if stat else 0,
                'ass': stat.assist if stat else 0,
            })
        return c, storico

    calc1, storico1 = cerca(q1)
    calc2, storico2 = cerca(q2)

    return render(request, 'analisi/confronto.html', {
        'q1': q1, 'q2': q2,
        'calc1': calc1, 'storico1': storico1,
        'calc2': calc2, 'storico2': storico2,
    })


# ─────────────────────────────────────────────────────────────
# AI ANALYSIS VIEW — run crewai in background thread
# ─────────────────────────────────────────────────────────────

@login_required
def run_ai_analysis(request):
    if request.method == 'POST':
        import threading
        import os
        from django.conf import settings
        from django.http import JsonResponse
        from ai_analyst.fanta_crew.crew import FantaAnalystCrew

        def _run_crew():
            log.info("[AI ANALYSIS] Inizio elaborazione CrewAI in background thread.")
            report_path = os.path.join(settings.BASE_DIR, 'report_analisi_avanzata.md')
            try:
                # Assicuriamoci che la cartella esista
                doc_dir = os.path.join(settings.BASE_DIR, 'dati_scaricati', 'documenti_ia')
                os.makedirs(doc_dir, exist_ok=True)

                # Reset del cache di CrewAI per forzare una nuova esecuzione ad ogni richiesta
                from crewai.utilities.task_output_storage_handler import TaskOutputStorageHandler
                try:
                    TaskOutputStorageHandler().reset()
                    log.info("[AI ANALYSIS] Cache di CrewAI resettata prima del kickoff.")
                except Exception as cache_err:
                    log.warning("[AI ANALYSIS] Impossibile resettare la cache di CrewAI: %s", cache_err)

                crew_instance = FantaAnalystCrew()
                inputs = {
                    'topic': 'Analisi incrociata tra le probabili formazioni (PDF/Immagini) e le quotazioni attuali (Excel).'
                }
                result = crew_instance.crew().kickoff(inputs=inputs)
                log.info("[AI ANALYSIS] CrewAI completata con successo.")
            except Exception as e:
                log.exception("[AI ANALYSIS] Errore nell'esecuzione della CrewAI, avvio generazione report fallback: %s", e)
                try:
                    genera_report_fallback(report_path, str(e))
                    log.info("[AI ANALYSIS] Report di fallback generato con successo.")
                except Exception as ex:
                    log.exception("[AI ANALYSIS] Errore nella generazione del report di fallback: %s", ex)

        thread = threading.Thread(target=_run_crew)
        thread.start()
        
        return JsonResponse({"status": "Analisi IA avviata in background!"})
    
    from django.http import JsonResponse
    return JsonResponse({"error": "Metodo non consentito"}, status=405)


def genera_report_fallback(report_path, errore_originale):
    from players.models import CalciatoreStagione
    import os

    # 1. Recupera i migliori per ruolo (almeno 3 partite)
    def get_top_role(ruolo, limit=10):
        return CalciatoreStagione.objects.filter(
            ruolo_stagione=ruolo,
            statistiche_riassuntive__partite_a_voto__gte=3
        ).select_related('calciatore', 'squadra_reale', 'statistiche_riassuntive').order_by('-statistiche_riassuntive__fanta_media')[:limit]

    def get_top_scorers(limit=10):
        return CalciatoreStagione.objects.filter(
            statistiche_riassuntive__partite_a_voto__gte=3
        ).select_related('calciatore', 'squadra_reale', 'statistiche_riassuntive').order_by('-statistiche_riassuntive__gol_fatti')[:limit]

    def get_top_assist(limit=10):
        return CalciatoreStagione.objects.filter(
            statistiche_riassuntive__partite_a_voto__gte=3
        ).select_related('calciatore', 'squadra_reale', 'statistiche_riassuntive').order_by('-statistiche_riassuntive__assist')[:limit]

    # Prendi i dati
    top_p = get_top_role('P', 5)
    top_d = get_top_role('D', 10)
    top_c = get_top_role('C', 10)
    top_a = get_top_role('A', 10)
    bomber = get_top_scorers(10)
    assistman = get_top_assist(10)

    # Leggi infortuni da documenti_ia per estrarre parole chiave
    infortuni_rilevati = []
    base_dir = os.path.dirname(report_path)
    doc_dir = os.path.join(base_dir, 'dati_scaricati', 'documenti_ia')
    if os.path.exists(doc_dir):
        for filename in os.listdir(doc_dir):
            if filename == '.gitkeep':
                continue
            infortuni_rilevati.append(f"- Letto file notizie: `{filename}`")

    # Costruisci il markdown
    md = []
    md.append("# 📋 Report Analisi Fantacalcio (Modalità Fallback)")
    md.append(f"\n> ⚠️ **Nota:** Questo report è stato generato in modalità di fallback locale poiché la chiave API Gemini ha esaurito i crediti o la quota giornaliera gratuita ({errore_originale}). I dati presentati qui sotto sono reali e provengono dal tuo database locale aggiornato.\n")

    md.append("## 📈 Top Player per Ruolo (Miglior Fanta-Media, min. 3 presenze)")

    # Portieri
    md.append("\n### 🧤 Portieri")
    md.append("| Giocatore | Squadra | FM | MV | PV | GS |")
    md.append("|---|---|---|---|---|---|")
    for p in top_p:
        st = p.statistiche_riassuntive
        md.append(f"| **{p.calciatore.nome}** | {p.squadra_reale.nome} | {st.fanta_media:.2f} | {st.media_voto:.2f} | {st.partite_a_voto} | {st.gol_subiti} |")

    # Difensori
    md.append("\n### 🛡️ Difensori")
    md.append("| Giocatore | Squadra | FM | MV | PV | Gol | Assist |")
    md.append("|---|---|---|---|---|---|---|")
    for d in top_d:
        st = d.statistiche_riassuntive
        md.append(f"| **{d.calciatore.nome}** | {d.squadra_reale.nome} | {st.fanta_media:.2f} | {st.media_voto:.2f} | {st.partite_a_voto} | {st.gol_fatti} | {st.assist} |")

    # Centrocampisti
    md.append("\n### 🪄 Centrocampisti")
    md.append("| Giocatore | Squadra | FM | MV | PV | Gol | Assist |")
    md.append("|---|---|---|---|---|---|---|")
    for c in top_c:
        st = c.statistiche_riassuntive
        md.append(f"| **{c.calciatore.nome}** | {c.squadra_reale.nome} | {st.fanta_media:.2f} | {st.media_voto:.2f} | {st.partite_a_voto} | {st.gol_fatti} | {st.assist} |")

    # Attaccanti
    md.append("\n### ⚽ Attaccanti")
    md.append("| Giocatore | Squadra | FM | MV | PV | Gol | Assist |")
    md.append("|---|---|---|---|---|---|---|")
    for a in top_a:
        st = a.statistiche_riassuntive
        md.append(f"| **{a.calciatore.nome}** | {a.squadra_reale.nome} | {st.fanta_media:.2f} | {st.media_voto:.2f} | {st.partite_a_voto} | {st.gol_fatti} | {st.assist} |")

    md.append("\n## 🔥 Classifiche di Rendimento")

    md.append("\n### 🎯 I Migliori Marcatori")
    md.append("| Giocatore | Squadra | Gol | PV | FM |")
    md.append("|---|---|---|---|---|")
    for p in bomber:
        st = p.statistiche_riassuntive
        md.append(f"| **{p.calciatore.nome}** | {p.squadra_reale.nome} | {st.gol_fatti} | {st.partite_a_voto} | {st.fanta_media:.2f} |")

    md.append("\n### 🅰️ I Migliori Assistman")
    md.append("| Giocatore | Squadra | Assist | PV | FM |")
    md.append("|---|---|---|---|---|")
    for p in assistman:
        st = p.statistiche_riassuntive
        md.append(f"| **{p.calciatore.nome}** | {p.squadra_reale.nome} | {st.assist} | {st.partite_a_voto} | {st.fanta_media:.2f} |")

    md.append("\n## 🏥 Notizie ed Infortuni Rilevati")
    if infortuni_rilevati:
        md.extend(infortuni_rilevati)
        md.append("\n*Controlla la cartella `dati_scaricati/documenti_ia/` per i dettagli completi dei file sopra indicati.*")
    else:
        md.append("\nNessun file di notizie o infortunio rilevato in `dati_scaricati/documenti_ia/`.")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(md))


@login_required
def visualizza_report(request):
    import os
    from django.conf import settings
    
    report_path = os.path.join(settings.BASE_DIR, 'report_analisi_avanzata.md')
    content = ""
    exists = False
    
    if os.path.exists(report_path):
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                content = f.read()
            exists = True
        except Exception as e:
            content = f"Errore durante la lettura del report: {e}"
    else:
        content = "Nessun report generato. Clicca su 'Rigenera Report' per avviare l'analisi."
        
    return render(request, 'analisi/report.html', {
        'content': content,
        'exists': exists
    })
