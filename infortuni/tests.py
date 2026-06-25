from datetime import date

from django.test import TestCase

from core.models import Stagione, SquadraReale
from players.models import Calciatore, CalciatoreStagione
from services.infortuni import data_da_periodo_mese, settimane_tra
from .models import Infortunio


class LogicaOttoSettimaneTests(TestCase):
    def _infortunio(self, data_bollettino, rientro_stimato, data_fine_serie_a=None):
        stagione = Stagione.objects.create(nome="2025/2026", attiva=True, data_fine_serie_a=data_fine_serie_a)
        sqra = SquadraReale.objects.create(nome="Inter", sigla="INT")
        cal = Calciatore.objects.create(nome="Infortunato", ruolo_base='A')
        cs = CalciatoreStagione.objects.create(
            calciatore=cal, stagione=stagione, squadra_reale=sqra, ruolo_stagione='A', quotazione_iniziale=1,
        )
        return Infortunio.objects.create(
            calciatore_stagione=cs, data_bollettino=data_bollettino, rientro_stimato=rientro_stimato,
        )

    def test_helper_periodo_mese(self):
        self.assertEqual(data_da_periodo_mese(2026, 2, 'inizio'), date(2026, 2, 1))
        self.assertEqual(data_da_periodo_mese(2026, 2, 'meta'), date(2026, 2, 16))
        self.assertEqual(data_da_periodo_mese(2026, 2, 'fine'), date(2026, 2, 28))  # 2026 non bisestile

    def test_settimane_tra(self):
        self.assertEqual(settimane_tra(date(2026, 1, 1), date(2026, 2, 26)), 8)  # 56 giorni

    def test_otto_settimane_qualifica(self):
        inf = self._infortunio(date(2026, 1, 1), date(2026, 2, 26))  # 8 settimane esatte
        qualifica = inf.calcola_qualifica_sostituzione()
        self.assertEqual(inf.settimane_out, 8)
        self.assertTrue(qualifica)

    def test_sotto_otto_settimane_non_qualifica(self):
        inf = self._infortunio(date(2026, 1, 1), date(2026, 2, 12))  # ~6 settimane
        self.assertFalse(inf.calcola_qualifica_sostituzione())

    def test_stop_ultime_otto_settimane(self):
        # infortunio lungo (>=8 sett) ma segnalato nelle ultime 8 settimane di campionato
        inf = self._infortunio(
            data_bollettino=date(2026, 4, 20),
            rientro_stimato=date(2026, 6, 20),
            data_fine_serie_a=date(2026, 5, 24),
        )
        self.assertFalse(inf.calcola_qualifica_sostituzione())
