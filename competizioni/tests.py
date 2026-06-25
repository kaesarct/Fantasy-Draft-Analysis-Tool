import itertools
from decimal import Decimal

from django.test import TestCase, SimpleTestCase

from core.models import Stagione, SquadraReale
from players.models import Calciatore, CalciatoreStagione
from fantacalcio.models import Lega, FantaSquadra, Ingaggio
from stats.models import VotoPartita
from services import scoring
from services.classifiche import aggiorna_classifica
from .models import Competizione, Giornata, Partita, Formazione, FormazioneGiocatore, Classifica


class GolFantaPureTests(SimpleTestCase):
    def test_fascia_base_66(self):
        self.assertEqual(scoring._gol_da_punteggio(Decimal('66')), 1)
        self.assertEqual(scoring._gol_da_punteggio(Decimal('72')), 2)
        self.assertEqual(scoring._gol_da_punteggio(Decimal('65.99')), 0)

    def test_entrambe_sotto_soglia_distacco_sei(self):
        # 60 vs 50: entrambe < 66, distacco 10 >= 6 -> +1 alla casa; 10 non > 10
        self.assertEqual(scoring.calcola_gol_fanta(Decimal('60'), Decimal('50')), (1, 0))

    def test_entrambe_sotto_soglia_distacco_insufficiente(self):
        self.assertEqual(scoring.calcola_gol_fanta(Decimal('64'), Decimal('60')), (0, 0))

    def test_distacco_oltre_dieci_bonus_extra(self):
        # 80 vs 50: casa (80-66)//6+1 = 3 gol; distacco 30 > 10 -> +1 = 4; ospite 0
        self.assertEqual(scoring.calcola_gol_fanta(Decimal('80'), Decimal('50')), (4, 0))

    def test_pareggio(self):
        self.assertEqual(scoring.calcola_gol_fanta(Decimal('66'), Decimal('66')), (1, 1))


class ScoringDBTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.counter = itertools.count(1)
        cls.stagione = Stagione.objects.create(nome="2025/2026", attiva=True)
        cls.lega = Lega.objects.create(nome="GOLD")
        cls.sqra = SquadraReale.objects.create(nome="Inter", sigla="INT")

    def _giocatore(self, squadra, ruolo, voto_base=None, fanta_voto=None, giornata=1):
        cal = Calciatore.objects.create(nome=f"G{next(self.counter)}", ruolo_base=ruolo)
        cs = CalciatoreStagione.objects.create(
            calciatore=cal, stagione=self.stagione, squadra_reale=self.sqra,
            ruolo_stagione=ruolo, quotazione_iniziale=1,
        )
        ing = Ingaggio.objects.create(fantasquadra=squadra, calciatore_stagione=cs, costo_acquisto=1)
        if voto_base is not None:
            VotoPartita.objects.create(
                calciatore_stagione=cs, giornata=giornata,
                voto_base=Decimal(str(voto_base)), fanta_voto=Decimal(str(fanta_voto)),
            )
        return ing

    def _formazione(self, squadra, giornata=1):
        return Formazione.objects.create(squadra=squadra, giornata_serie_a=giornata)

    def _titolare(self, formazione, ingaggio):
        return FormazioneGiocatore.objects.create(
            formazione=formazione, ingaggio=ingaggio, posizione=FormazioneGiocatore.Posizione.TITOLARE,
        )

    def _panchina(self, formazione, ingaggio, ordine):
        return FormazioneGiocatore.objects.create(
            formazione=formazione, ingaggio=ingaggio, posizione=FormazioneGiocatore.Posizione.PANCHINA,
            ordine_panchina=ordine,
        )

    def test_modificatore_difesa_piu_tre(self):
        sq = FantaSquadra.objects.create(nome="A", lega=self.lega, stagione=self.stagione)
        form = self._formazione(sq)
        # P 6, D 7,7,6,5 -> top3 difensori 7,7,6 -> media (6+7+7+6)/4 = 6.5 -> +3
        for ruolo, vb in [('P', 6), ('D', 7), ('D', 7), ('D', 6), ('D', 5)]:
            self._titolare(form, self._giocatore(sq, ruolo, voto_base=vb, fanta_voto=vb))
        res = scoring.calcola_punteggio_squadra(form)
        self.assertEqual(res['modificatore'], 3)
        self.assertEqual(res['media_difesa'], Decimal('6.5'))
        # somma fanta (6+7+7+6+5=31) + modificatore 3
        self.assertEqual(res['totale'], Decimal('34'))

    def test_modificatore_richiede_quattro_difensori(self):
        sq = FantaSquadra.objects.create(nome="B", lega=self.lega, stagione=self.stagione)
        form = self._formazione(sq)
        for ruolo, vb in [('P', 7), ('D', 7), ('D', 7), ('D', 7)]:  # solo 3 difensori
            self._titolare(form, self._giocatore(sq, ruolo, voto_base=vb, fanta_voto=vb))
        res = scoring.calcola_punteggio_squadra(form)
        self.assertEqual(res['modificatore'], 0)

    def test_sostituzione_da_panchina(self):
        sq = FantaSquadra.objects.create(nome="C", lega=self.lega, stagione=self.stagione)
        form = self._formazione(sq)
        # titolare attaccante SENZA voto (sv) + panchinaro con voto 7
        self._titolare(form, self._giocatore(sq, 'A', voto_base=None))
        self._panchina(form, self._giocatore(sq, 'A', voto_base=7, fanta_voto=7), ordine=1)
        effettivi, sostituzioni = scoring.risolvi_formazione(form)
        self.assertEqual(len(sostituzioni), 1)
        self.assertTrue(effettivi[0]['subentrato'])
        res = scoring.calcola_punteggio_squadra(form)
        self.assertEqual(res['totale'], Decimal('7'))

    def test_titolare_senza_voto_senza_cambio_usa_dufficio(self):
        sq = FantaSquadra.objects.create(nome="D", lega=self.lega, stagione=self.stagione)
        form = self._formazione(sq)
        self._titolare(form, self._giocatore(sq, 'A', voto_base=None))  # sv, nessuna panchina
        res = scoring.calcola_punteggio_squadra(form)
        self.assertEqual(res['totale'], scoring.VOTO_DUFFICIO_SENZA_CAMBIO)

    def test_calcola_partita_e_classifica(self):
        casa = FantaSquadra.objects.create(nome="Casa", lega=self.lega, stagione=self.stagione)
        ospite = FantaSquadra.objects.create(nome="Ospite", lega=self.lega, stagione=self.stagione)
        comp = Competizione.objects.create(stagione=self.stagione, nome="GOLD")
        giornata = Giornata.objects.create(competizione=comp, numero=1, giornata_serie_a=1)
        partita = Partita.objects.create(giornata=giornata, squadra_casa=casa, squadra_ospite=ospite)

        form_casa = self._formazione(casa)
        form_casa.partita = partita
        form_casa.save()
        self._titolare(form_casa, self._giocatore(casa, 'A', voto_base=7, fanta_voto=70))

        form_ospite = self._formazione(ospite)
        form_ospite.partita = partita
        form_ospite.save()
        self._titolare(form_ospite, self._giocatore(ospite, 'A', voto_base=6, fanta_voto=50))

        scoring.calcola_partita(partita)
        partita.refresh_from_db()
        # casa 70 -> 1 gol; ospite 50 -> 0; distacco 20 > 10 -> casa +1 = 2
        self.assertEqual(partita.gol_casa, 2)
        self.assertEqual(partita.gol_ospite, 0)
        self.assertEqual(partita.risultato, Partita.Risultato.CASA)

        aggiorna_classifica(comp)
        riga_casa = Classifica.objects.get(competizione=comp, squadra=casa)
        riga_ospite = Classifica.objects.get(competizione=comp, squadra=ospite)
        self.assertEqual(riga_casa.punti, 3)
        self.assertEqual(riga_casa.vinte, 1)
        self.assertEqual(riga_casa.gol_fatti, 2)
        self.assertEqual(riga_ospite.punti, 0)
        self.assertEqual(riga_ospite.perse, 1)
