import itertools

from django.test import TestCase, SimpleTestCase

from core.models import Stagione, SquadraReale
from players.models import Calciatore, CalciatoreStagione
from fantacalcio.models import Lega, FantaSquadra, Ingaggio
from services.scambi import calcola_prezzi_scambio, applica_prezzi_scambio
from .models import Scambio, ScambioItem


class PrezziScambioPureTests(SimpleTestCase):
    def test_assegnazione_incrociata_per_rango(self):
        # A cede prezzi [100, 30]; B cede [80, 50].
        items_a = [{'id': 'a1', 'prezzo': 100, 'quotazione': 20}, {'id': 'a2', 'prezzo': 30, 'quotazione': 5}]
        items_b = [{'id': 'b1', 'prezzo': 80, 'quotazione': 18}, {'id': 'b2', 'prezzo': 50, 'quotazione': 9}]
        prezzi = calcola_prezzi_scambio(items_a, items_b)
        # i giocatori di A assumono i prezzi di B per rango (80, 50); B assume quelli di A (100, 30)
        self.assertEqual(prezzi['a1'], 80)
        self.assertEqual(prezzi['a2'], 50)
        self.assertEqual(prezzi['b1'], 100)
        self.assertEqual(prezzi['b2'], 30)

    def test_tiebreaker_quotazione(self):
        # stesso prezzo: ordina per quotazione desc
        items_a = [{'id': 'a1', 'prezzo': 50, 'quotazione': 10}, {'id': 'a2', 'prezzo': 50, 'quotazione': 20}]
        items_b = [{'id': 'b1', 'prezzo': 90, 'quotazione': 1}, {'id': 'b2', 'prezzo': 10, 'quotazione': 1}]
        prezzi = calcola_prezzi_scambio(items_a, items_b)
        # a2 (quotazione 20) è in testa -> prende 90; a1 -> 10
        self.assertEqual(prezzi['a2'], 90)
        self.assertEqual(prezzi['a1'], 10)


class ScambioStessaLegaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.counter = itertools.count(1)
        cls.stagione = Stagione.objects.create(nome="2025/2026", attiva=True)
        cls.gold = Lega.objects.create(nome="GOLD")
        cls.bronze = Lega.objects.create(nome="BRONZE")
        cls.sqra = SquadraReale.objects.create(nome="Inter", sigla="INT")

    def _ingaggio(self, squadra, prezzo, quotazione=1):
        cal = Calciatore.objects.create(nome=f"G{next(self.counter)}", ruolo_base='C')
        cs = CalciatoreStagione.objects.create(
            calciatore=cal, stagione=self.stagione, squadra_reale=self.sqra,
            ruolo_stagione='C', quotazione_iniziale=quotazione,
        )
        return Ingaggio.objects.create(fantasquadra=squadra, calciatore_stagione=cs, costo_acquisto=prezzo)

    def test_scambio_lega_diversa_vietato(self):
        a = FantaSquadra.objects.create(nome="A", lega=self.gold, stagione=self.stagione)
        b = FantaSquadra.objects.create(nome="B", lega=self.bronze, stagione=self.stagione)
        scambio = Scambio.objects.create(stagione=self.stagione, squadra_a=a, squadra_b=b)
        with self.assertRaises(ValueError):
            applica_prezzi_scambio(scambio, salva=True)

    def test_applica_prezzi_salva(self):
        a = FantaSquadra.objects.create(nome="A", lega=self.gold, stagione=self.stagione)
        b = FantaSquadra.objects.create(nome="B", lega=self.gold, stagione=self.stagione)
        scambio = Scambio.objects.create(stagione=self.stagione, squadra_a=a, squadra_b=b)
        ia = self._ingaggio(a, 100)
        ib = self._ingaggio(b, 70)
        item_a = ScambioItem.objects.create(scambio=scambio, squadra_cedente=a, ingaggio=ia)
        item_b = ScambioItem.objects.create(scambio=scambio, squadra_cedente=b, ingaggio=ib)
        applica_prezzi_scambio(scambio, salva=True)
        item_a.refresh_from_db()
        item_b.refresh_from_db()
        self.assertEqual(item_a.prezzo_assegnato, 70)   # A prende il prezzo di B
        self.assertEqual(item_b.prezzo_assegnato, 100)  # B prende il prezzo di A
