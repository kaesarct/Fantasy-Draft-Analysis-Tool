"""Ricalcolo della classifica di una competizione a partire dalle partite giocate.

Regole punti: vittoria 3, pareggio 1, sconfitta 0. I turni di riposo (squadra
ospite assente) non concorrono. Idempotente: ricostruisce la classifica da zero
scommando solo le partite con risultato valorizzato.
"""

PUNTI_VITTORIA = 3
PUNTI_PAREGGIO = 1
PUNTI_SCONFITTA = 0


def aggiorna_classifica(competizione):
    """Ricostruisce le righe Classifica della competizione dalle partite con risultato."""
    from decimal import Decimal
    from django.db import transaction
    from competizioni.models import Partita, Classifica

    partite = (
        Partita.objects
        .filter(giornata__competizione=competizione, risultato__isnull=False, squadra_ospite__isnull=False)
        .select_related('squadra_casa', 'squadra_ospite')
    )

    stat = {}  # squadra_id -> dict aggregato

    def riga(squadra):
        return stat.setdefault(squadra.id, {
            'squadra': squadra, 'giocate': 0, 'vinte': 0, 'pareggiate': 0, 'perse': 0,
            'punti': 0, 'totale_fanta_score': Decimal('0'), 'gol_fatti': 0, 'gol_subiti': 0,
        })

    for p in partite:
        casa = riga(p.squadra_casa)
        ospite = riga(p.squadra_ospite)

        casa['giocate'] += 1
        ospite['giocate'] += 1
        casa['gol_fatti'] += p.gol_casa or 0
        casa['gol_subiti'] += p.gol_ospite or 0
        ospite['gol_fatti'] += p.gol_ospite or 0
        ospite['gol_subiti'] += p.gol_casa or 0
        casa['totale_fanta_score'] += p.punteggio_casa or Decimal('0')
        ospite['totale_fanta_score'] += p.punteggio_ospite or Decimal('0')

        if p.risultato == Partita.Risultato.CASA:
            casa['vinte'] += 1
            casa['punti'] += PUNTI_VITTORIA
            ospite['perse'] += 1
        elif p.risultato == Partita.Risultato.OSPITE:
            ospite['vinte'] += 1
            ospite['punti'] += PUNTI_VITTORIA
            casa['perse'] += 1
        else:
            casa['pareggiate'] += 1
            ospite['pareggiate'] += 1
            casa['punti'] += PUNTI_PAREGGIO
            ospite['punti'] += PUNTI_PAREGGIO

    with transaction.atomic():
        for dati in stat.values():
            squadra = dati.pop('squadra')
            Classifica.objects.update_or_create(
                competizione=competizione, squadra=squadra, defaults=dati,
            )
    return stat
