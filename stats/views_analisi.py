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
