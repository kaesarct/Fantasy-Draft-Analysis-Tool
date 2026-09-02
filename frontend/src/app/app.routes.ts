import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'dashboard',
    pathMatch: 'full',
  },
  {
    path: 'dashboard',
    loadComponent: () =>
      import('./pages/dashboard/dashboard.component').then(m => m.DashboardComponent),
  },
  {
    path: 'players',
    loadComponent: () =>
      import('./pages/players/players.component').then(m => m.PlayersComponent),
  },
  {
    path: 'players/:id',
    loadComponent: () =>
      import('./pages/player-detail/player-detail.component').then(m => m.PlayerDetailComponent),
  },
  {
    path: 'teams',
    loadComponent: () =>
      import('./pages/teams/teams.component').then(m => m.TeamsComponent),
  },
  {
    path: 'teams/:id',
    loadComponent: () =>
      import('./pages/team-detail/team-detail.component').then(m => m.TeamDetailComponent),
  },
  {
    path: 'allenatori/:id',
    loadComponent: () =>
      import('./pages/allenatore-detail/allenatore-detail.component').then(m => m.AllenatoreDetailComponent),
  },
  {
    path: 'league',
    loadComponent: () =>
      import('./pages/league/league.component').then(m => m.LeagueComponent),
  },
  {
    path: 'matches',
    loadComponent: () =>
      import('./pages/matches/matches.component').then(m => m.MatchesComponent),
  },
  {
    path: 'injuries',
    loadComponent: () =>
      import('./pages/injuries/injuries.component').then(m => m.InjuriesComponent),
  },
  {
    path: 'history',
    loadComponent: () =>
      import('./pages/history/history.component').then(m => m.HistoryComponent),
  },
  {
    path: 'awards',
    loadComponent: () =>
      import('./pages/awards/awards.component').then(m => m.AwardsComponent),
  },
  {
    path: 'admin',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./pages/admin/admin.component').then(m => m.AdminComponent),
  },
  {
    path: 'admin/squadre',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./pages/admin-teams/admin-teams.component').then(m => m.AdminTeamsComponent),
  },
  {
    path: 'admin/mercato',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./pages/admin-market/admin-market.component').then(m => m.AdminMarketComponent),
  },
  {
    path: 'admin/coerenza-silver',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./pages/admin-silver-check/admin-silver-check.component').then(m => m.AdminSilverCheckComponent),
  },
  {
    path: 'login',
    loadComponent: () =>
      import('./pages/login/login.component').then(m => m.LoginComponent),
  },
  {
    path: '**',
    redirectTo: 'dashboard',
  },
];
