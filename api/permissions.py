"""Controlli di autorizzazione a livello di oggetto per l'API.

Il "possesso" di una squadra è definito dalla M2M ``FantaSquadra.presidenti``.
Lo staff (is_staff) ha accesso pieno tramite l'admin e bypassa i controlli.
"""


def utente_e_presidente(user, squadra):
    """True se l'utente gestisce la squadra (o è staff)."""
    if user is None or not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    return squadra.presidenti.filter(pk=user.pk).exists()
