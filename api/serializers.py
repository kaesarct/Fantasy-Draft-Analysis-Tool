from rest_framework import serializers

from core.models import Stagione
from players.models import Calciatore, CalciatoreStagione
from fantacalcio.models import FantaSquadra, Ingaggio
from competizioni.models import Classifica, Formazione, FormazioneGiocatore
from infortuni.models import Infortunio
from mercato.models import Scambio, ScambioItem


class StagioneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stagione
        fields = ['id', 'nome', 'attiva', 'data_inizio_serie_a', 'data_fine_serie_a', 'crediti_default']


class CalciatoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Calciatore
        fields = ['id', 'fanta_id', 'nome', 'ruolo_base']


class FreeAgentSerializer(serializers.ModelSerializer):
    calciatore = serializers.CharField(source='calciatore.nome', read_only=True)
    squadra_reale = serializers.CharField(source='squadra_reale.nome', read_only=True)

    class Meta:
        model = CalciatoreStagione
        fields = ['id', 'calciatore', 'ruolo_stagione', 'squadra_reale', 'quotazione_iniziale']


class RosterItemSerializer(serializers.ModelSerializer):
    calciatore = serializers.CharField(source='calciatore_stagione.calciatore.nome', read_only=True)
    ruolo = serializers.CharField(source='calciatore_stagione.ruolo_stagione', read_only=True)

    class Meta:
        model = Ingaggio
        fields = ['id', 'calciatore', 'ruolo', 'costo_acquisto', 'tipo_acquisizione', 'attivo', 'data_acquisizione']


class FantaSquadraSerializer(serializers.ModelSerializer):
    lega = serializers.CharField(source='lega.nome', read_only=True)

    class Meta:
        model = FantaSquadra
        fields = ['id', 'nome', 'lega', 'stagione', 'franchise', 'crediti_iniziali', 'crediti_residui']


class ClassificaSerializer(serializers.ModelSerializer):
    squadra = serializers.CharField(source='squadra.nome', read_only=True)

    class Meta:
        model = Classifica
        fields = [
            'squadra', 'giocate', 'vinte', 'pareggiate', 'perse', 'punti',
            'gol_fatti', 'gol_subiti', 'totale_fanta_score',
        ]


class InfortunioSerializer(serializers.ModelSerializer):
    calciatore = serializers.CharField(source='calciatore_stagione.calciatore.nome', read_only=True)

    class Meta:
        model = Infortunio
        fields = [
            'id', 'calciatore', 'data_bollettino', 'rientro_stimato', 'rientro_possibile',
            'settimane_out', 'qualifica_sostituzione', 'rientro_effettivo',
        ]
        read_only_fields = ['settimane_out', 'qualifica_sostituzione']


class ScambioItemInputSerializer(serializers.Serializer):
    squadra_cedente = serializers.PrimaryKeyRelatedField(queryset=FantaSquadra.objects.all())
    ingaggio = serializers.PrimaryKeyRelatedField(queryset=Ingaggio.objects.all())


class ScambioSerializer(serializers.ModelSerializer):
    items = ScambioItemInputSerializer(many=True, write_only=True)

    class Meta:
        model = Scambio
        fields = ['id', 'stagione', 'squadra_a', 'squadra_b', 'stato', 'data_scambio', 'note', 'items']
        read_only_fields = ['stato']

    def validate(self, attrs):
        if attrs['squadra_a'].lega_id != attrs['squadra_b'].lega_id:
            raise serializers.ValidationError("Gli scambi sono ammessi solo tra squadre della stessa lega.")
        return attrs

    def create(self, validated_data):
        items = validated_data.pop('items')
        scambio = Scambio.objects.create(**validated_data)
        for item in items:
            ScambioItem.objects.create(scambio=scambio, **item)
        return scambio


class FormazioneGiocatoreInputSerializer(serializers.Serializer):
    ingaggio = serializers.PrimaryKeyRelatedField(queryset=Ingaggio.objects.all())
    posizione = serializers.ChoiceField(choices=FormazioneGiocatore.Posizione.choices)
    ordine_panchina = serializers.IntegerField(required=False, allow_null=True)


class FormazioneSerializer(serializers.ModelSerializer):
    giocatori = FormazioneGiocatoreInputSerializer(many=True, write_only=True)

    class Meta:
        model = Formazione
        fields = ['id', 'squadra', 'partita', 'giornata_serie_a', 'modulo', 'fonte', 'giocatori']

    def create(self, validated_data):
        giocatori = validated_data.pop('giocatori')
        formazione = Formazione.objects.create(**validated_data)
        for g in giocatori:
            FormazioneGiocatore.objects.create(formazione=formazione, **g)
        return formazione
