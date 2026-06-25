import logging

import requests
from django.conf import settings
from django.utils import timezone
from rest_framework import status, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Stagione
from players.models import Calciatore, CalciatoreStagione
from fantacalcio.models import FantaSquadra, Ingaggio
from competizioni.models import Classifica, Formazione
from infortuni.models import Infortunio
from mercato.models import Scambio
from .permissions import utente_e_presidente
from .serializers import (
    StagioneSerializer, CalciatoreSerializer, FreeAgentSerializer, RosterItemSerializer,
    FantaSquadraSerializer, ClassificaSerializer, InfortunioSerializer,
    ScambioSerializer, FormazioneSerializer,
)

log = logging.getLogger('api')


class SeasonCurrentView(APIView):
    def get(self, request):
        stagione = Stagione.objects.filter(attiva=True).first()
        if stagione is None:
            return Response({'detail': 'Nessuna stagione attiva.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(StagioneSerializer(stagione).data)


class PlayerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CalciatoreSerializer
    queryset = Calciatore.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        ruolo = self.request.query_params.get('ruolo')
        if ruolo:
            qs = qs.filter(ruolo_base=ruolo)
        return qs


class FreeAgentsView(APIView):
    def get(self, request):
        stagione_id = request.query_params.get('stagione')
        if not stagione_id:
            return Response({'detail': "Parametro 'stagione' obbligatorio."}, status=status.HTTP_400_BAD_REQUEST)
        qs = (
            CalciatoreStagione.objects
            .filter(stagione_id=stagione_id)
            .exclude(ingaggi__attivo=True)
            .select_related('calciatore', 'squadra_reale')
        )
        return Response(FreeAgentSerializer(qs, many=True).data)


class FantaSquadraViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FantaSquadraSerializer
    queryset = FantaSquadra.objects.select_related('lega').all()

    def get_queryset(self):
        qs = super().get_queryset()
        stagione = self.request.query_params.get('stagione')
        lega = self.request.query_params.get('lega')
        if stagione:
            qs = qs.filter(stagione_id=stagione)
        if lega:
            qs = qs.filter(lega__nome__iexact=lega)
        return qs

    @action(detail=True, methods=['get'])
    def roster(self, request, pk=None):
        squadra = self.get_object()
        rosa = squadra.rosa.filter(attivo=True).select_related('calciatore_stagione__calciatore')
        return Response(RosterItemSerializer(rosa, many=True).data)


class CoachTeamView(APIView):
    """Squadre del presidente identificato dal telegram_user_id (usato dal bot)."""
    def get(self, request, telegram_id):
        squadre = FantaSquadra.objects.filter(presidenti__telegram_user_id=telegram_id).select_related('lega')
        return Response(FantaSquadraSerializer(squadre, many=True).data)


class ClassificaView(APIView):
    def get(self, request):
        competizione_id = request.query_params.get('competizione')
        if not competizione_id:
            return Response({'detail': "Parametro 'competizione' obbligatorio."}, status=status.HTTP_400_BAD_REQUEST)
        qs = Classifica.objects.filter(competizione_id=competizione_id).select_related('squadra')
        return Response(ClassificaSerializer(qs, many=True).data)


class InfortuniActiveView(APIView):
    def get(self, request):
        qs = Infortunio.objects.filter(rientro_effettivo__isnull=True).select_related('calciatore_stagione__calciatore')
        stagione = request.query_params.get('stagione')
        if stagione:
            qs = qs.filter(calciatore_stagione__stagione_id=stagione)
        return Response(InfortunioSerializer(qs, many=True).data)


class InfortuniRecoveredView(APIView):
    def get(self, request):
        qs = Infortunio.objects.filter(rientro_effettivo__isnull=False).select_related('calciatore_stagione__calciatore')
        stagione = request.query_params.get('stagione')
        if stagione:
            qs = qs.filter(calciatore_stagione__stagione_id=stagione)
        return Response(InfortunioSerializer(qs, many=True).data)


class ScambioViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                     mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = ScambioSerializer
    queryset = Scambio.objects.all()

    @action(detail=True, methods=['patch'])
    def confirm(self, request, pk=None):
        scambio = self.get_object()
        if scambio.stato != Scambio.Stato.PROPOSTO:
            return Response({'detail': 'Solo gli scambi in stato PROPOSTO possono essere confermati.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not utente_e_presidente(request.user, scambio.squadra_b):
            return Response({'detail': 'Solo un presidente della squadra controparte può confermare lo scambio.'},
                            status=status.HTTP_403_FORBIDDEN)
        scambio.stato = Scambio.Stato.CONFERMATO
        scambio.confermato_il = timezone.now()
        scambio.save(update_fields=['stato', 'confermato_il'])
        return Response(self.get_serializer(scambio).data)


class FormazioneViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = FormazioneSerializer
    queryset = Formazione.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        squadra = self.request.query_params.get('team')
        giornata = self.request.query_params.get('match_day')
        if squadra:
            qs = qs.filter(squadra_id=squadra)
        if giornata:
            qs = qs.filter(giornata_serie_a=giornata)
        return qs


class TelegramWebhookView(APIView):
    """Riceve gli aggiornamenti Telegram. Protetto dal secret token in header.

    Per policy GDPR non logga il contenuto dei messaggi.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        secret = settings.TELEGRAM_WEBHOOK_SECRET
        header = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if not secret or header != secret:
            log.warning("Webhook Telegram rifiutato: secret token mancante o errato.")
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        # TODO: instradare l'update ai handler del bot. Nessun log del contenuto.
        return Response({'ok': True})


class NextMatchesView(APIView):
    """Prossime partite di Serie A (scraping live). Mappa il comando bot /nextmatch."""
    def get(self, request):
        from integrations.serie_a import prossime_partite
        try:
            return Response(prossime_partite())
        except requests.RequestException as e:
            log.error("Errore scraping prossime partite: %s", e)
            return Response({'detail': 'Sorgente dati non raggiungibile.'},
                            status=status.HTTP_502_BAD_GATEWAY)


class PossibleReturnsView(APIView):
    """Giocatori nei probabili schieramenti (per rientri possibili da infortunio)."""
    def get(self, request):
        from integrations.serie_a import rientri_possibili
        try:
            return Response(rientri_possibili())
        except requests.RequestException as e:
            log.error("Errore scraping rientri possibili: %s", e)
            return Response({'detail': 'Sorgente dati non raggiungibile.'},
                            status=status.HTTP_502_BAD_GATEWAY)
