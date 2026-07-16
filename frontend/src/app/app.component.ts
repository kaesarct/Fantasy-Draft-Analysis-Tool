import { Component, OnInit } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { CommonModule } from '@angular/common';
import { AuthService } from './core/services/auth.service';

interface NavItem {
  label: string;
  route: string;
  icon: string;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <div class="app-shell">
      <!-- Sidebar -->
      <nav class="sidebar">
        <div class="sidebar-header">
          <div class="logo">
            <span class="logo-icon">⚽</span>
            <div>
              <div class="logo-title">FT Platform</div>
              <div class="logo-sub">Fantacalcio Tamarros</div>
            </div>
          </div>
        </div>

        <ul class="nav-list">
          @for (item of visibleNavItems(); track item.route) {
            <li>
              <a [routerLink]="item.route" routerLinkActive="active" class="nav-link">
                <span class="nav-icon">{{ item.icon }}</span>
                <span class="nav-label">{{ item.label }}</span>
              </a>
            </li>
          }
        </ul>

        <div class="sidebar-footer">
          @if (auth.isAuthenticated()) {
            <div class="auth-status">
              <span class="text-muted" style="font-size:12px">👤 {{ auth.username() }}</span>
              <a class="nav-link auth-link" (click)="logout()">🚪 Esci</a>
            </div>
          } @else {
            <a class="nav-link auth-link" routerLink="/login">🔒 Accedi</a>
          }
          <div class="sidebar-version">v1.0.0</div>
        </div>
      </nav>

      <!-- Main content -->
      <main class="main-content">
        <router-outlet />
      </main>
    </div>
  `,
  styles: [`
    .app-shell {
      display: flex;
      height: 100vh;
      overflow: hidden;
    }

    /* ── Sidebar ──────────────────────────────────────────── */
    .sidebar {
      width: 240px;
      min-width: 240px;
      background: var(--bg-surface);
      border-right: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      padding: 0;
      overflow-y: auto;
    }

    .sidebar-header {
      padding: 20px 16px 16px;
      border-bottom: 1px solid var(--border-color);
    }

    .logo {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .logo-icon {
      font-size: 28px;
      filter: drop-shadow(0 0 8px rgba(63,185,80,.5));
    }

    .logo-title {
      font-size: 15px;
      font-weight: 800;
      color: var(--text-primary);
      letter-spacing: -0.02em;
    }

    .logo-sub {
      font-size: 10px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .nav-list {
      list-style: none;
      padding: 12px 8px;
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .nav-link {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 9px 12px;
      border-radius: var(--radius-sm);
      color: var(--text-secondary);
      text-decoration: none;
      font-size: 13px;
      font-weight: 500;
      transition: all var(--transition);
    }

    .nav-link:hover {
      background: var(--bg-elevated);
      color: var(--text-primary);
    }

    .nav-link.active {
      background: rgba(63,185,80,.12);
      color: var(--accent-green);
      font-weight: 600;
    }

    .nav-icon { font-size: 16px; width: 20px; text-align: center; }

    .sidebar-footer {
      padding: 12px 16px;
      border-top: 1px solid var(--border-color);
    }

    .sidebar-version {
      font-size: 11px;
      color: var(--text-muted);
    }

    .auth-status {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-bottom: 10px;
    }

    .auth-link {
      cursor: pointer;
      padding: 6px 12px;
    }

    /* ── Main content ─────────────────────────────────────── */
    .main-content {
      flex: 1;
      overflow-y: auto;
      background: var(--bg-base);
    }
  `],
})
export class AppComponent implements OnInit {
  navItems: NavItem[] = [
    { label: 'Dashboard',   route: '/dashboard',  icon: '🏠' },
    { label: 'Classifica',  route: '/league',     icon: '🏆' },
    { label: 'Squadre',     route: '/teams',      icon: '🛡️'  },
    { label: 'Allenatori',  route: '/allenatori', icon: '👤' },
    { label: 'Giocatori',   route: '/players',    icon: '⚽' },
    { label: 'Partite',     route: '/matches',    icon: '📅' },
    { label: 'Infortuni',   route: '/injuries',   icon: '🏥' },
    { label: 'Storico',     route: '/history',    icon: '📊' },
    { label: 'Admin',       route: '/admin',      icon: '⚙️'  },
    { label: 'Gestione Squadre', route: '/admin/squadre', icon: '🛡️' },
  ];

  constructor(public auth: AuthService) {}

  ngOnInit() {
    this.auth.checkAuth();
  }

  visibleNavItems(): NavItem[] {
    return this.auth.isAuthenticated()
      ? this.navItems
      : this.navItems.filter(item => !item.route.startsWith('/admin'));
  }

  logout() {
    this.auth.logout();
  }
}
