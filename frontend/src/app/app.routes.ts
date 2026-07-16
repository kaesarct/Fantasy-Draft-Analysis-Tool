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
    path: 'allenatori',
    loadComponent: () =>
      import('./pages/allenatori/allenatori.component').then(m => m.AllenatoriComponent),
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
    path: 'admin',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./pages/admin/admin.component').then(m => m.AdminComponent),
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
