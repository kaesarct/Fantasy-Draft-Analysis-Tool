"""Logica delle 8 settimane per la sostituzione da infortunio (analisi §5.2).

- Se la durata dell'indisponibilità è >= 8 settimane -> sostituzione concessa.
- È prevista la finestra di stop: niente sostituzioni nelle ultime 8 settimane di
  campionato (se la data di fine stagione è nota).

La conversione testuale dei bollettini ("inizio/metà/fine mese") in una data è
fornita dall'helper ``data_da_periodo_mese``; il parsing del testo del bollettino
resta a carico di chi inserisce il dato (admin/bot).
"""

import calendar
import math
from datetime import date, timedelta

SETTIMANE_QUALIFICA = 8
STOP_SETTIMANE_FINE = 8


def data_da_periodo_mese(anno, mese, periodo):
    """Converte 'inizio'/'meta'/'fine' di un mese nel 1°, 16° o ultimo giorno."""
    p = periodo.strip().lower()
    if p in ('inizio', 'inizio_mese'):
        return date(anno, mese, 1)
    if p in ('meta', 'metà', 'meta_mese', 'metà_mese'):
        return date(anno, mese, 16)
    if p in ('fine', 'fine_mese'):
        return date(anno, mese, calendar.monthrange(anno, mese)[1])
    raise ValueError(f"Periodo non riconosciuto: {periodo!r}")


def settimane_tra(data_inizio, data_fine):
    """Numero di settimane (arrotondate per eccesso) tra due date, mai negativo."""
    return max(0, math.ceil((data_fine - data_inizio).days / 7))


def valuta_infortunio(infortunio):
    """Restituisce ``(settimane_out, qualifica_sostituzione)`` per un Infortunio."""
    if infortunio.rientro_stimato is not None:
        settimane = settimane_tra(infortunio.data_bollettino, infortunio.rientro_stimato)
    elif infortunio.settimane_out is not None:
        settimane = infortunio.settimane_out
    else:
        settimane = 0

    qualifica = settimane >= SETTIMANE_QUALIFICA

    fine_campionato = infortunio.calciatore_stagione.stagione.data_fine_serie_a
    if qualifica and fine_campionato is not None:
        limite = fine_campionato - timedelta(weeks=STOP_SETTIMANE_FINE)
        if infortunio.data_bollettino >= limite:
            qualifica = False

    return settimane, qualifica
