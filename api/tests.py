from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from core.models import Stagione, SquadraReale
from players.models import Calciatore, CalciatoreStagione
from fantacalcio.models import Lega, FantaSquadra, Ingaggio

User = get_user_model()


class ApiAuthTests(APITestCase):
    def test_endpoint_richiede_autenticazione(self):
        resp = self.client.get('/api/seasons/current/')
        self.assertIn(resp.status_code, (401, 403))

    def test_seasons_current_autenticato(self):
        user = User.objects.create_user(username='bot', password='x')
        Stagione.objects.create(nome="2025/2026", attiva=True)
        self.client.force_authenticate(user=user)
        resp = self.client.get('/api/seasons/current/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['nome'], "2025/2026")


class ApiDatiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='bot', password='x')
        cls.stagione = Stagione.objects.create(nome="2025/2026", attiva=True)
        cls.lega = Lega.objects.create(nome="GOLD")
        cls.sqra_reale = SquadraReale.objects.create(nome="Inter", sigla="INT")
        cls.squadra = FantaSquadra.objects.create(nome="Dragoni", lega=cls.lega, stagione=cls.stagione)

        cls.cal_in = Calciatore.objects.create(nome="In Rosa", ruolo_base='A')
        cls.cs_in = CalciatoreStagione.objects.create(
            calciatore=cls.cal_in, stagione=cls.stagione, squadra_reale=cls.sqra_reale,
            ruolo_stagione='A', quotazione_iniziale=20,
        )
        Ingaggio.objects.create(fantasquadra=cls.squadra, calciatore_stagione=cls.cs_in, costo_acquisto=50)

        cls.cal_free = Calciatore.objects.create(nome="Svincolato", ruolo_base='C')
        cls.cs_free = CalciatoreStagione.objects.create(
            calciatore=cls.cal_free, stagione=cls.stagione, squadra_reale=cls.sqra_reale,
            ruolo_stagione='C', quotazione_iniziale=5,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_roster_solo_attivi(self):
        resp = self.client.get(f'/api/teams/{self.squadra.id}/roster/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['calciatore'], "In Rosa")

    def test_free_agents(self):
        resp = self.client.get(f'/api/players/free-agents/?stagione={self.stagione.id}')
        self.assertEqual(resp.status_code, 200)
        nomi = [r['calciatore'] for r in resp.data]
        self.assertIn("Svincolato", nomi)
        self.assertNotIn("In Rosa", nomi)

    def test_swap_lega_diversa_rifiutato(self):
        bronze = Lega.objects.create(nome="BRONZE")
        altra = FantaSquadra.objects.create(nome="Altri", lega=bronze, stagione=self.stagione)
        payload = {
            'stagione': self.stagione.id, 'squadra_a': self.squadra.id, 'squadra_b': altra.id,
            'items': [{'squadra_cedente': self.squadra.id, 'ingaggio': self.cs_in.ingaggi.first().id}],
        }
        resp = self.client.post('/api/swaps/', payload, format='json')
        self.assertEqual(resp.status_code, 400)


@override_settings(TELEGRAM_WEBHOOK_SECRET='segretissimo')
class WebhookTelegramTests(APITestCase):
    def test_secret_errato_rifiutato(self):
        resp = self.client.post('/api/telegram/webhook/', {}, format='json',
                                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='sbagliato')
        self.assertEqual(resp.status_code, 403)

    def test_secret_corretto_accettato(self):
        resp = self.client.post('/api/telegram/webhook/', {'update_id': 1}, format='json',
                                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='segretissimo')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {'ok': True})
