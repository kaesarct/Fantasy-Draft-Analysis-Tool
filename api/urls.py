from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views

router = DefaultRouter()
router.register('teams', views.FantaSquadraViewSet, basename='teams')
router.register('players', views.PlayerViewSet, basename='players')
router.register('swaps', views.ScambioViewSet, basename='swaps')
router.register('lineups', views.FormazioneViewSet, basename='lineups')

urlpatterns = [
    # Autenticazione JWT
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Endpoint custom
    path('seasons/current/', views.SeasonCurrentView.as_view(), name='season_current'),
    path('players/free-agents/', views.FreeAgentsView.as_view(), name='free_agents'),
    path('coaches/<int:telegram_id>/team/', views.CoachTeamView.as_view(), name='coach_team'),
    path('standings/', views.ClassificaView.as_view(), name='standings'),
    path('injuries/active/', views.InfortuniActiveView.as_view(), name='injuries_active'),
    path('injuries/recovered/', views.InfortuniRecoveredView.as_view(), name='injuries_recovered'),
    path('injuries/possible-returns/', views.PossibleReturnsView.as_view(), name='injuries_possible_returns'),
    path('competitions/next-matches/', views.NextMatchesView.as_view(), name='next_matches'),
    path('telegram/webhook/', views.TelegramWebhookView.as_view(), name='telegram_webhook'),

    # Router (teams, players, swaps, lineups)
    path('', include(router.urls)),
]
