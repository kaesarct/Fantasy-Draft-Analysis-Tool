from datetime import datetime

from django.test import SimpleTestCase

from integrations.serie_a import parse_prossime_partite, parse_rientri_possibili


class ParsingProssimePartiteTests(SimpleTestCase):
    HTML = """
    <ul>
      <li class="match">
        <label class="team-home">INT</label>
        <label class="team-away">MIL</label>
        <a class="match-score">2 - 1</a>
        <div class="match-date">15/0820:45</div>
        <div class="match-location">San Siro</div>
      </li>
      <li class="match">
        <label class="team-home">JUV</label>
        <label class="team-away">NAP</label>
        <div class="match-date">20/0818:00</div>
        <div class="match-location">Allianz Stadium</div>
      </li>
    </ul>
    """

    def test_mappa_abbreviazioni_e_campi(self):
        now = datetime(2025, 8, 18, 12, 0)
        partite = parse_prossime_partite(self.HTML, now=now)
        self.assertEqual(len(partite), 2)
        self.assertEqual(partite[0]['squadra_casa'], 'Inter')
        self.assertEqual(partite[0]['squadra_ospite'], 'Milan')
        self.assertEqual(partite[0]['score'], '2 - 1')
        self.assertTrue(partite[0]['giocata'])      # 15/08 < 18/08
        self.assertFalse(partite[1]['giocata'])     # 20/08 > 18/08
        self.assertEqual(partite[1]['squadra_casa'], 'Juventus')

    def test_partita_malformata_non_blocca(self):
        html = '<li class="match"><label class="team-home">INT</label></li>' + self.HTML
        partite = parse_prossime_partite(html, now=datetime(2025, 8, 18))
        # la prima (senza team-away) viene saltata, le altre due restano
        self.assertEqual(len(partite), 2)


class ParsingRientriPossibiliTests(SimpleTestCase):
    HTML = """
    <ul>
      <li class="player-item pill">
        <a class="player-name player-link" href="/serie-a/squadre/inter/lautaro-martinez/6410">
          <span>Lautaro Martinez</span>
        </a>
      </li>
      <li class="player-item pill">
        <a class="player-name player-link" href="/serie-a/squadre/milan/leao/5000">
          <span>Leao</span>
        </a>
      </li>
    </ul>
    """

    def test_estrae_nome_e_id(self):
        rientri = parse_rientri_possibili(self.HTML)
        self.assertEqual(rientri, [
            {'name': 'Lautaro Martinez', 'id': 6410},
            {'name': 'Leao', 'id': 5000},
        ])
