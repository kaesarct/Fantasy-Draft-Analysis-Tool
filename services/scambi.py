"""Calcolo dei prezzi post-scambio.

Regola (analisi §5.3): si ordinano i giocatori ceduti da ciascuna squadra per
prezzo decrescente; il giocatore col prezzo più alto di una squadra assume il
prezzo più alto dell'altra squadra (assegnazione incrociata per rango). In caso
di parità di prezzo si usa la quotazione Fantacalcio come spareggio.

Se le due liste hanno lunghezza diversa, i giocatori oltre il rango comune
mantengono il proprio prezzo originale (caso non standard: viene segnalato).
"""


def _ordina(items):
    # items: lista di dict {id, prezzo, quotazione}; ordina per prezzo desc, poi quotazione desc
    return sorted(items, key=lambda i: (i['prezzo'], i['quotazione']), reverse=True)


def calcola_prezzi_scambio(items_a, items_b):
    """Restituisce {item_id: prezzo_assegnato} per entrambe le squadre.

    ``items_a``/``items_b`` sono liste di dict ``{'id', 'prezzo', 'quotazione'}``
    (i giocatori ceduti rispettivamente da A e da B).
    """
    a_sorted = _ordina(items_a)
    b_sorted = _ordina(items_b)
    prezzi_a = [i['prezzo'] for i in a_sorted]
    prezzi_b = [i['prezzo'] for i in b_sorted]

    risultato = {}
    # I giocatori di A (che vanno in B) assumono i prezzi di B per rango, e viceversa.
    for rango, item in enumerate(a_sorted):
        risultato[item['id']] = prezzi_b[rango] if rango < len(prezzi_b) else item['prezzo']
    for rango, item in enumerate(b_sorted):
        risultato[item['id']] = prezzi_a[rango] if rango < len(prezzi_a) else item['prezzo']
    return risultato


def applica_prezzi_scambio(scambio, salva=False):
    """Calcola e (opz.) salva ``prezzo_assegnato`` sugli ScambioItem dello scambio.

    Valida che le due squadre siano della stessa lega. Restituisce {item_id: prezzo}.
    """
    if scambio.squadra_a.lega_id != scambio.squadra_b.lega_id:
        raise ValueError("Gli scambi sono ammessi solo tra squadre della stessa lega.")

    def to_items(squadra):
        out = []
        for item in scambio.items.filter(squadra_cedente=squadra).select_related('ingaggio__calciatore_stagione'):
            out.append({
                'id': item.id,
                'prezzo': item.ingaggio.costo_acquisto,
                'quotazione': item.ingaggio.calciatore_stagione.quotazione_iniziale,
            })
        return out

    prezzi = calcola_prezzi_scambio(to_items(scambio.squadra_a), to_items(scambio.squadra_b))

    if salva:
        for item in scambio.items.all():
            if item.id in prezzi:
                item.prezzo_assegnato = prezzi[item.id]
                item.save(update_fields=['prezzo_assegnato'])
    return prezzi
