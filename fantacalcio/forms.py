from django import forms
from django.conf import settings
from .models import Lega, FantaSquadra

User = settings.AUTH_USER_MODEL


class LegaForm(forms.ModelForm):
    class Meta:
        model = Lega
        fields = ['nome']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Es. Lega degli Amici'}),
        }


class FantaSquadraForm(forms.ModelForm):
    from django.contrib.auth import get_user_model
    
    class Meta:
        model = FantaSquadra
        fields = ['nome', 'stagione', 'presidenti', 'crediti_residui']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Nome squadra'}),
            'stagione': forms.Select(attrs={'class': 'form-select'}),
            'presidenti': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
            'crediti_residui': forms.NumberInput(attrs={'class': 'form-input'}),
        }


class RosaUploadForm(forms.Form):
    """Upload Excel della rosa con colonne: Calciatore (cognome), Costo"""
    file = forms.FileField(
        label='File Excel Rosa (.xlsx)',
        widget=forms.FileInput(attrs={'class': 'form-input', 'accept': '.xlsx,.xls'})
    )
    stagione = forms.ModelChoiceField(
        queryset=None,  # viene impostato nella view
        label='Stagione',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        from core.models import Stagione
        super().__init__(*args, **kwargs)
        self.fields['stagione'].queryset = Stagione.objects.all().order_by('-nome')
