import { Component, OnInit, signal } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { CommonModule } from '@angular/common';
import { AuthService } from './core/services/auth.service';
import { ApiService } from './core/services/api.service';

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
      <!-- Barra mobile: solo sotto il breakpoint -->
      <div class="mobile-topbar">
        <button class="hamburger-btn" (click)="mobileMenuOpen.set(true)" aria-label="Apri menu">☰</button>
        <div class="mobile-topbar-title"><img class="logo-icon" src="logo.png" alt="Logo"> FT Platform</div>
      </div>

      @if (mobileMenuOpen()) {
        <div class="sidebar-overlay" (click)="mobileMenuOpen.set(false)"></div>
      }

      <!-- Sidebar -->
      <nav class="sidebar" [class.mobile-open]="mobileMenuOpen()">
        <div class="sidebar-header">
          <div class="logo">
            <img class="logo-icon" src="logo.png" alt="Logo">
            <div>
              <div class="logo-title">FT Platform</div>
              <div class="logo-sub">Fantacalcio Tamarros</div>
            </div>
          </div>
        </div>

        <ul class="nav-list">
          @for (item of visibleNavItems(); track item.route) {
            <li>
              <a [routerLink]="item.route" routerLinkActive="active" class="nav-link" (click)="mobileMenuOpen.set(false)">
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
              <a class="nav-link auth-link" (click)="logout(); mobileMenuOpen.set(false)">🚪 Esci</a>
            </div>
          } @else {
            <a class="nav-link auth-link" routerLink="/login" (click)="mobileMenuOpen.set(false)">🔒 Accedi</a>
          }
          <div class="sidebar-version">{{ version() }}</div>
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
      width: 32px;
      height: 32px;
      object-fit: contain;
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

    /* ── Barra mobile + overlay: nascosti su desktop ────────── */
    .mobile-topbar { display: none; }
    .sidebar-overlay {
      display: none;
    }

    /* ── Sotto 768px: sidebar diventa un drawer a scomparsa ─── */
    @media (max-width: 768px) {
      .mobile-topbar {
        display: flex;
        align-items: center;
        gap: 12px;
        height: 52px;
        padding: 0 12px;
        background: var(--bg-surface);
        border-bottom: 1px solid var(--border-color);
        position: fixed;
        top: 0; left: 0; right: 0;
        z-index: 300;
      }

      .hamburger-btn {
        background: none;
        border: none;
        color: var(--text-primary);
        font-size: 22px;
        line-height: 1;
        padding: 4px 8px;
        cursor: pointer;
      }

      .mobile-topbar-title {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 14px;
        font-weight: 800;
        color: var(--text-primary);
      }

      .sidebar-overlay {
        display: block;
        position: fixed;
        inset: 0;
        background: rgba(0,0,0,.5);
        z-index: 200;
      }

      .sidebar {
        position: fixed;
        top: 0; left: 0;
        height: 100vh;
        z-index: 250;
        transform: translateX(-100%);
        transition: transform .25s ease;
        padding-top: 52px; /* spazio per la barra fissa, evita di sovrapporre l'header della sidebar */
      }

      .sidebar .sidebar-header { display: none; }

      .sidebar.mobile-open {
        transform: translateX(0);
      }

      .main-content {
        padding-top: 52px;
      }
    }
  `],
})
export class AppComponent implements OnInit {
  navItems: NavItem[] = [
    { label: 'Dashboard',   route: '/dashboard',  icon: '🏠' },
    { label: 'Classifica',  route: '/league',     icon: '🏆' },
    { label: 'Allenatori',  route: '/teams',      icon: '👤' },
    { label: 'Giocatori',   route: '/players',    icon: '⚽' },
    { label: 'Partite',     route: '/matches',    icon: '📅' },
    { label: 'Infortuni',   route: '/injuries',   icon: '🏥' },
    { label: 'Storico',     route: '/history',    icon: '📊' },
    { label: 'Goku & Oscar', route: '/awards',    icon: '🏆' },
    { label: 'Admin',       route: '/admin',      icon: '⚙️'  },
    { label: 'Gestione Squadre', route: '/admin/squadre', icon: '🛡️' },
    { label: 'Mercato',     route: '/admin/mercato', icon: '🔄' },
    { label: 'Coerenza Silver', route: '/admin/coerenza-silver', icon: '⚖️' },
    { label: 'Sync leghe.fc.it', route: '/admin/leghe-sync', icon: '🔗' },
  ];

  version = signal('…');
  mobileMenuOpen = signal(false);

  constructor(public auth: AuthService, private api: ApiService) {}

  ngOnInit() {
    this.auth.checkAuth();
    this.api.getHealth().subscribe({
      next: res => this.version.set(res.version),
      error: () => this.version.set('dev'),
    });
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
