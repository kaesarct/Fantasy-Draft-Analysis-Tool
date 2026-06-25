"""Motore di calcolo del punteggio di giornata.

Fonte dati per-giocatore: ``stats.VotoPartita.fanta_voto``, già calcolato in fase
di import con la tabella bonus/malus standard. Questo modulo NON ricalcola i
bonus/malus del singolo giocatore: somma i fantavoti degli effettivi, applica il
modificatore di difesa e converte il punteggio squadra in gol fanta.

Tutte le soglie del regolamento sono costanti modificabili in un unico punto.
"""

from decimal import Decimal

# --- Parametri regolamento (modificare qui) --------------------------------

# Voto d'ufficio a un titolare senza voto che NON può essere sostituito dalla
# panchina. L'analisi indica "4 d'ufficio … o 0": impostare a 0 se la lega non
# prevede il voto d'ufficio.
VOTO_DUFFICIO_SENZA_CAMBIO = Decimal('4')

# Modificatore di difesa: (media minima, bonus). Valutate in ordine decrescente.
SOGLIE_MODIFICATORE_DIFESA = [
    (Decimal('7'), 6),
    (Decimal('6.5'), 3),
    (Decimal('6'), 1),
]
MIN_DIFENSORI_CON_VOTO = 4   # servono portiere + almeno 4 difensori con voto
N_DIFENSORI_MEDIA = 3        # media calcolata su portiere + migliori 3 difensori

# Gol fanta
SOGLIA_PRIMO_GOL = Decimal('66')
PUNTI_PER_GOL = Decimal('6')
DISTACCO_PAREGGIO = Decimal('6')   # entrambe < soglia: +1 a chi stacca >= 6
DISTACCO_EXTRA = Decimal('10')     # distacco > 10: +1 in più a chi ha più punti


def _voto_giocatore(ingaggio, giornata_serie_a):
    """VotoPartita del giocatore per la giornata, o None se senza voto/non importato."""
    from stats.models import VotoPartita
    return (
        VotoPartita.objects
        .filter(calciatore_stagione=ingaggio.calciatore_stagione, giornata=giornata_serie_a)
        .first()
    )


def _ruolo(ingaggio):
    return ingaggio.calciatore_stagione.ruolo_stagione


def _fanta_voto(voto):
    if voto.fanta_voto is not None:
        return Decimal(voto.fanta_voto)
    return Decimal(voto.voto_base or 0)


def risolvi_formazione(formazione):
    """Determina gli 11 effettivi applicando le sostituzioni da panchina.

    I titolari senza voto vengono sostituiti, nell'ordine di panchina, dal primo
    panchinaro disponibile che ha un voto (sostituzione role-agnostic).
    Restituisce ``(effettivi, sostituzioni)`` dove ogni effettivo è un dict
    ``{fg, voto, subentrato, al_posto_di}``.
    """
    giornata = formazione.giornata_serie_a
    titolari = list(formazione.giocatori.filter(posizione='TITOLARE'))
    panchina = list(formazione.giocatori.filter(posizione='PANCHINA').order_by('ordine_panchina'))

    voti = {fg.id: _voto_giocatore(fg.ingaggio, giornata) for fg in titolari + panchina}
    panchina_disponibile = [p for p in panchina if voti[p.id] is not None]

    effettivi, sostituzioni = [], []
    idx = 0
    for tit in titolari:
        if voti[tit.id] is not None:
            effettivi.append({'fg': tit, 'voto': voti[tit.id], 'subentrato': False, 'al_posto_di': None})
        elif idx < len(panchina_disponibile):
            sub = panchina_disponibile[idx]
            idx += 1
            effettivi.append({'fg': sub, 'voto': voti[sub.id], 'subentrato': True, 'al_posto_di': tit})
            sostituzioni.append((tit, sub))
        else:
            effettivi.append({'fg': tit, 'voto': None, 'subentrato': False, 'al_posto_di': None})
    return effettivi, sostituzioni


def calcola_modificatore_difesa(effettivi):
    """Bonus difesa e media reparto. Esclude le riserve d'ufficio dal conteggio."""
    validi = [
        e for e in effettivi
        if e['voto'] is not None and e['voto'].voto_base is not None and not e['fg'].is_riserva_ufficio
    ]
    portiere = next((e for e in validi if _ruolo(e['fg'].ingaggio) == 'P'), None)
    difensori = [e for e in validi if _ruolo(e['fg'].ingaggio) == 'D']
    if portiere is None or len(difensori) < MIN_DIFENSORI_CON_VOTO:
        return 0, None

    migliori = sorted(difensori, key=lambda e: e['voto'].voto_base, reverse=True)[:N_DIFENSORI_MEDIA]
    voti_base = [portiere['voto'].voto_base] + [d['voto'].voto_base for d in migliori]
    media = sum(voti_base, Decimal('0')) / Decimal(len(voti_base))
    for soglia, bonus in SOGLIE_MODIFICATORE_DIFESA:
        if media >= soglia:
            return bonus, media
    return 0, media


def calcola_punteggio_squadra(formazione):
    """Punteggio totale di una squadra per la giornata della formazione."""
    effettivi, sostituzioni = risolvi_formazione(formazione)

    totale = Decimal('0')
    for e in effettivi:
        totale += _fanta_voto(e['voto']) if e['voto'] is not None else VOTO_DUFFICIO_SENZA_CAMBIO

    modificatore, media = calcola_modificatore_difesa(effettivi)
    totale += Decimal(modificatore)

    dettagli = {
        'modificatore_difesa': modificatore,
        'media_difesa': float(media) if media is not None else None,
        'sostituzioni': [
            {'titolare': str(t.ingaggio), 'subentrato': str(s.ingaggio)}
            for t, s in sostituzioni
        ],
        'titolari_senza_cambio': sum(1 for e in effettivi if e['voto'] is None),
    }
    return {'totale': totale, 'modificatore': modificatore, 'media_difesa': media, 'dettagli': dettagli}


def _gol_da_punteggio(score):
    if score >= SOGLIA_PRIMO_GOL:
        return int((score - SOGLIA_PRIMO_GOL) // PUNTI_PER_GOL) + 1
    return 0


def calcola_gol_fanta(score_casa, score_ospite):
    """Converte i punteggi squadra in gol fanta secondo il regolamento."""
    score_casa = Decimal(score_casa)
    score_ospite = Decimal(score_ospite)
    gol_casa = _gol_da_punteggio(score_casa)
    gol_ospite = _gol_da_punteggio(score_ospite)
    distacco = abs(score_casa - score_ospite)

    if score_casa < SOGLIA_PRIMO_GOL and score_ospite < SOGLIA_PRIMO_GOL and distacco >= DISTACCO_PAREGGIO:
        if score_casa > score_ospite:
            gol_casa += 1
        elif score_ospite > score_casa:
            gol_ospite += 1

    if distacco > DISTACCO_EXTRA:
        if score_casa > score_ospite:
            gol_casa += 1
        elif score_ospite > score_casa:
            gol_ospite += 1

    return gol_casa, gol_ospite


def _trova_formazione(squadra, partita):
    from competizioni.models import Formazione
    diretta = partita.formazioni.filter(squadra=squadra).first()
    if diretta:
        return diretta
    return (
        Formazione.objects
        .filter(squadra=squadra, giornata_serie_a=partita.giornata.giornata_serie_a)
        .order_by('-inviata_il')
        .first()
    )


def calcola_partita(partita):
    """Calcola punteggi, gol fanta e risultato di una partita.

    Scrive ``PunteggioSquadraPartita`` per ogni squadra e aggiorna la ``Partita``.
    In caso di turno di riposo (squadra ospite assente) calcola solo la squadra di casa.
    """
    from django.db import transaction
    from competizioni.models import Partita, PunteggioSquadraPartita

    def _punteggio(squadra):
        formazione = _trova_formazione(squadra, partita)
        if formazione is None:
            return {'totale': Decimal('0'), 'modificatore': 0, 'media_difesa': None,
                    'dettagli': {'errore': 'formazione mancante'}}
        return calcola_punteggio_squadra(formazione)

    with transaction.atomic():
        ris_casa = _punteggio(partita.squadra_casa)
        PunteggioSquadraPartita.objects.update_or_create(
            partita=partita, squadra=partita.squadra_casa,
            defaults={'totale_score': ris_casa['totale'], 'modificatore_difesa': ris_casa['modificatore'],
                      'dettagli': ris_casa['dettagli']},
        )
        partita.punteggio_casa = ris_casa['totale']

        if partita.squadra_ospite is None:
            partita.gol_casa = _gol_da_punteggio(ris_casa['totale'])
            partita.gol_ospite = None
            partita.punteggio_ospite = None
            partita.risultato = None
            partita.save()
            return partita

        ris_ospite = _punteggio(partita.squadra_ospite)
        PunteggioSquadraPartita.objects.update_or_create(
            partita=partita, squadra=partita.squadra_ospite,
            defaults={'totale_score': ris_ospite['totale'], 'modificatore_difesa': ris_ospite['modificatore'],
                      'dettagli': ris_ospite['dettagli']},
        )
        partita.punteggio_ospite = ris_ospite['totale']

        gol_casa, gol_ospite = calcola_gol_fanta(ris_casa['totale'], ris_ospite['totale'])
        partita.gol_casa = gol_casa
        partita.gol_ospite = gol_ospite
        if gol_casa > gol_ospite:
            partita.risultato = Partita.Risultato.CASA
        elif gol_ospite > gol_casa:
            partita.risultato = Partita.Risultato.OSPITE
        else:
            partita.risultato = Partita.Risultato.PAREGGIO

        # aggiorna i gol fanta nei dettagli punteggio
        PunteggioSquadraPartita.objects.filter(partita=partita, squadra=partita.squadra_casa).update(gol_fanta=gol_casa)
        PunteggioSquadraPartita.objects.filter(partita=partita, squadra=partita.squadra_ospite).update(gol_fanta=gol_ospite)

        partita.save()
        return partita
