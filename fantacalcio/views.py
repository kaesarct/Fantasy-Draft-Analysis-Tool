import logging
import pandas as pd
import numpy as np
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.conf import settings
import os

from core.models import Stagione
from players.models import Calciatore, CalciatoreStagione
from .models import Lega, FantaSquadra, Ingaggio
from .forms import LegaForm, FantaSquadraForm, RosaUploadForm

log = logging.getLogger('fantacalcio.views')


# ─────────────────────────────────────────────────────────────
# LEGHE
# ─────────────────────────────────────────────────────────────

@login_required
def lega_list(request):
    """Lista tutte le leghe + form creazione inline"""
    if request.method == 'POST':
        form = LegaForm(request.POST)
        if form.is_valid():
            lega = form.save()
            log.info("[FANTA] Lega creata: %s da %s", lega.nome, request.user)
            messages.success(request, f'Lega "{lega.nome}" creata con successo!')
            return redirect('lega_list')
    else:
        form = LegaForm()

    leghe = Lega.objects.prefetch_related('squadre').all().order_by('nome')
    return render(request, 'fantacalcio/lega_list.html', {
        'leghe': leghe,
        'form': form,
    })


@login_required
def lega_detail(request, lega_id):
    """Dettaglio lega: lista squadre per stagione selezionata"""
    lega = get_object_or_404(Lega, id=lega_id)
    stagioni = Stagione.objects.all().order_by('-nome')
    stagione_sel_id = request.GET.get('stagione')
    stagione_sel = None
    squadre = []

    if stagione_sel_id:
        stagione_sel = Stagione.objects.filter(id=stagione_sel_id).first()
        if stagione_sel:
            squadre = FantaSquadra.objects.filter(
                lega=lega, stagione=stagione_sel
            ).prefetch_related('presidenti', 'rosa__calciatore_stagione__calciatore')
    else:
        # Mostra la stagione più recente
        stagione_sel = stagioni.first()
        if stagione_sel:
            squadre = FantaSquadra.objects.filter(
                lega=lega, stagione=stagione_sel
            ).prefetch_related('presidenti', 'rosa__calciatore_stagione__calciatore')

    return render(request, 'fantacalcio/lega_detail.html', {
        'lega': lega,
        'stagioni': stagioni,
        'stagione_sel': stagione_sel,
        'squadre': squadre,
    })


# ─────────────────────────────────────────────────────────────
# FANTASQUADRE
# ─────────────────────────────────────────────────────────────

@login_required
def squadra_crea(request, lega_id):
    """Crea una nuova fantasquadra per la lega"""
    lega = get_object_or_404(Lega, id=lega_id)
    if request.method == 'POST':
        form = FantaSquadraForm(request.POST)
        if form.is_valid():
            squadra = form.save(commit=False)
            squadra.lega = lega
            squadra.save()
            form.save_m2m()
            log.info("[FANTA] Squadra creata: %s in lega %s da %s", squadra.nome, lega.nome, request.user)
            messages.success(request, f'Squadra "{squadra.nome}" creata!')
            return redirect('lega_detail', lega_id=lega.id)
    else:
        form = FantaSquadraForm()

    return render(request, 'fantacalcio/squadra_form.html', {
        'lega': lega,
        'form': form,
        'titolo': 'Crea Fantasquadra',
    })


@login_required
def squadra_edit(request, lega_id, squadra_id):
    """Modifica una fantasquadra esistente"""
    lega = get_object_or_404(Lega, id=lega_id)
    squadra = get_object_or_404(FantaSquadra, id=squadra_id, lega=lega)
    if request.method == 'POST':
        form = FantaSquadraForm(request.POST, instance=squadra)
        if form.is_valid():
            form.save()
            messages.success(request, f'Squadra "{squadra.nome}" aggiornata!')
            return redirect('lega_detail', lega_id=lega.id)
    else:
        form = FantaSquadraForm(instance=squadra)

    return render(request, 'fantacalcio/squadra_form.html', {
        'lega': lega,
        'squadra': squadra,
        'form': form,
        'titolo': f'Modifica {squadra.nome}',
    })


# ─────────────────────────────────────────────────────────────
# ROSA
# ─────────────────────────────────────────────────────────────

@login_required
def rosa_view(request, lega_id, squadra_id):
    """Visualizza la rosa di una fantasquadra con upload Excel"""
    lega = get_object_or_404(Lega, id=lega_id)
    squadra = get_object_or_404(FantaSquadra, id=squadra_id, lega=lega)
    ingaggi = Ingaggio.objects.filter(fantasquadra=squadra).select_related(
        'calciatore_stagione__calciatore',
        'calciatore_stagione__squadra_reale',
        'calciatore_stagione__statistiche_riassuntive',
    ).order_by('calciatore_stagione__ruolo_stagione', 'calciatore_stagione__calciatore__nome')

    upload_form = RosaUploadForm()
    errori_upload = []

    if request.method == 'POST':
        upload_form = RosaUploadForm(request.POST, request.FILES)
        if upload_form.is_valid():
            file_obj = request.FILES['file']
            stagione = upload_form.cleaned_data['stagione']

            try:
                df = pd.read_excel(file_obj)
                df = df.replace({np.nan: None})
                creati = 0
                non_trovati = []

                for _, row in df.iterrows():
                    cognome_raw = str(row.get('Calciatore') or row.get('Nome') or '').strip()
                    costo_raw = row.get('Costo') or row.get('Prezzo') or 0

                    if not cognome_raw:
                        continue

                    # Cerca CalciatoreStagione per nome + stagione
                    cs = CalciatoreStagione.objects.filter(
                        calciatore__nome__icontains=cognome_raw,
                        stagione=stagione
                    ).first()

                    if not cs:
                        non_trovati.append(cognome_raw)
                        continue

                    try:
                        costo = int(float(str(costo_raw).replace(',', '.').strip()))
                    except (ValueError, TypeError):
                        costo = 0

                    Ingaggio.objects.update_or_create(
                        fantasquadra=squadra,
                        calciatore_stagione=cs,
                        defaults={'costo_acquisto': costo}
                    )
                    creati += 1

                if non_trovati:
                    errori_upload = non_trovati
                    messages.warning(request, f'{creati} ingaggi caricati. {len(non_trovati)} giocatori non trovati nel DB.')
                else:
                    messages.success(request, f'{creati} ingaggi caricati con successo!')

                log.info("[FANTA] Upload rosa: %d ingaggi per squadra %s (stagione %s), non trovati: %s",
                         creati, squadra.nome, stagione, non_trovati)
                return redirect('rosa_view', lega_id=lega.id, squadra_id=squadra.id)

            except Exception as e:
                log.exception("[FANTA] Errore upload rosa: %s", e)
                messages.error(request, f'Errore nella lettura del file: {e}')

    totale_costo = sum(i.costo_acquisto for i in ingaggi)
    return render(request, 'fantacalcio/rosa.html', {
        'lega': lega,
        'squadra': squadra,
        'ingaggi': ingaggi,
        'upload_form': upload_form,
        'totale_costo': totale_costo,
        'errori_upload': errori_upload,
    })


@login_required
def ingaggio_rimuovi(request, lega_id, squadra_id, ingaggio_id):
    """Rimuove un giocatore dalla rosa"""
    ingaggio = get_object_or_404(Ingaggio, id=ingaggio_id, fantasquadra__id=squadra_id)
    nome = ingaggio.calciatore_stagione.calciatore.nome
    ingaggio.delete()
    messages.success(request, f'{nome} rimosso dalla rosa.')
    return redirect('rosa_view', lega_id=lega_id, squadra_id=squadra_id)
