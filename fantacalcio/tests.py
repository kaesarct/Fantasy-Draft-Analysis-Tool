from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import Stagione, SquadraReale
from players.models import Calciatore, CalciatoreStagione
from .models import Lega, Franchise, FantaSquadra, Ingaggio


class FondamentaDominioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stagione = Stagione.objects.create(nome="2025/2026", attiva=True)
        cls.lega = Lega.objects.create(nome="GOLD")
        cls.sqra = SquadraReale.objects.create(nome="Inter", sigla="INT")
        cls.calciatore = Calciatore.objects.create(nome="Lautaro Martinez", ruolo_base="A")
        cls.cs = CalciatoreStagione.objects.create(
            calciatore=cls.calciatore, stagione=cls.stagione,
            squadra_reale=cls.sqra, ruolo_stagione="A", quotazione_iniziale=30,
        )

    def test_stagione_nuovi_campi(self):
        self.stagione.crediti_default = 350
        self.stagione.data_inizio_serie_a = date(2025, 8, 24)
        self.stagione.full_clean()
        self.assertEqual(self.stagione.crediti_default, 350)

    def test_franchise_e_squadra(self):
        franchise = Franchise.objects.create(nome="I Dragoni", stagione_fondazione=self.stagione)
        squadra = FantaSquadra.objects.create(
            nome="Dragoni 25", lega=self.lega, stagione=self.stagione, franchise=franchise,
        )
        self.assertEqual(squadra.franchise.nome, "I Dragoni")
        self.assertEqual(squadra.crediti_iniziali, 350)

    def test_due_ingaggi_attivi_stesso_giocatore_vietati(self):
        squadra = FantaSquadra.objects.create(nome="A", lega=self.lega, stagione=self.stagione)
        Ingaggio.objects.create(fantasquadra=squadra, calciatore_stagione=self.cs, costo_acquisto=100)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Ingaggio.objects.create(fantasquadra=squadra, calciatore_stagione=self.cs, costo_acquisto=50)

    def test_riacquisto_dopo_cessione_consentito(self):
        squadra = FantaSquadra.objects.create(nome="B", lega=self.lega, stagione=self.stagione)
        primo = Ingaggio.objects.create(
            fantasquadra=squadra, calciatore_stagione=self.cs, costo_acquisto=100,
            attivo=False, data_cessione=date(2026, 1, 15),
        )
        secondo = Ingaggio.objects.create(
            fantasquadra=squadra, calciatore_stagione=self.cs, costo_acquisto=80,
            tipo_acquisizione=Ingaggio.TipoAcquisizione.RIPARAZIONE,
        )
        self.assertFalse(primo.attivo)
        self.assertTrue(secondo.attivo)
        self.assertEqual(squadra.rosa.filter(attivo=True).count(), 1)
