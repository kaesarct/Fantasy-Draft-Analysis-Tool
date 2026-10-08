import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-teams',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <div>
          <h1 class="page-title">👤 Allenatori</h1>
          <p class="text-secondary">Ogni allenatore raccoglie le sue squadre stagione per stagione</p>
        </div>
      </div>

      @if (globalStats()) {
        <div class="stats-grid mb-4">
          <div class="card stats-card">
            <h4>🏆 Record Acquisti (Singolo Allenatore)</h4>
            <div class="stats-roles">
              @for (role of ['P', 'D', 'C', 'A']; track role) {
                @if (globalStats().most_bought_per_role[role]) {
                  <div class="stats-role-group">
                    <div class="role-badge role-{{role}}">{{role}}</div>
                    <div class="stats-info">
                      <div class="player-name">{{ globalStats().most_bought_per_role[role].player_name }} <span class="stats-val">({{ globalStats().most_bought_per_role[role].count }}x)</span></div>
                      <div class="al-name text-muted" style="font-size: 11px;">by {{ globalStats().most_bought_per_role[role].al_name }}</div>
                    </div>
                  </div>
                }
              }
            </div>
          </div>
          <div class="card stats-card">
            <h4>💸 Acquisti più costosi</h4>
            <div class="stats-roles">
              @for (role of ['P', 'D', 'C', 'A']; track role) {
                @if (globalStats().most_expensive_per_role[role]) {
                  <div class="stats-role-group">
                    <div class="role-badge role-{{role}}">{{role}}</div>
                    <div class="stats-info">
                      <div class="player-name">{{ globalStats().most_expensive_per_role[role].player_name }} <span class="stats-val">{{ globalStats().most_expensive_per_role[role].max_price }} FM</span></div>
                      <div class="al-name text-muted" style="font-size: 11px;">by {{ globalStats().most_expensive_per_role[role].al_name }}</div>
                    </div>
                  </div>
                }
              }
            </div>
          </div>
        </div>
      }

      <div class="allenatori-grid">
        @for (a of allenatori(); track a.id) {
          <a [routerLink]="['/allenatori', a.id]" class="allenatore-card">
            <div class="avatar">{{ a.display_name[0] }}</div>
            <div class="al-info">
              <div class="al-name">{{ a.display_name }}</div>
              <div class="al-username text-muted">{{ '@' + a.username }}</div>
            </div>
            <span class="badge" [class]="a.is_active ? 'badge-green' : 'badge-carbon'">
              {{ a.is_active ? 'Attivo' : 'Inattivo' }}
            </span>
          </a>
        }
        @empty {
          <p class="text-muted">Nessun allenatore registrato.</p>
        }
      </div>
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1280px; margin: 0 auto; }
    .page-header { margin-bottom: 24px; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; }
    .allenatori-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
    .allenatore-card {
      background: var(--bg-card); border: 1px solid var(--border-color);
      border-radius: var(--radius-md); padding: 16px 20px;
      display: flex; align-items: center; gap: 14px;
      text-decoration: none; color: var(--text-primary);
      transition: border-color var(--transition), transform var(--transition);
    }
    .allenatore-card:hover { border-color: var(--accent-blue); transform: translateY(-2px); }
    .avatar {
      width: 44px; height: 44px; border-radius: 50%;
      background: linear-gradient(135deg, var(--accent-green), var(--accent-blue));
      display: flex; align-items: center; justify-content: center;
      font-size: 18px; font-weight: 800; color: #fff; flex-shrink: 0;
    }
    .al-info { flex: 1; }
    .al-name { font-weight: 700; font-size: 14px; }
    .al-username { font-size: 12px; }

    .mb-4 { margin-bottom: 24px; }
    .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media (max-width: 768px) { .stats-grid { grid-template-columns: 1fr; } }
    .stats-card { padding: 16px; }
    .stats-card h4 { margin-top: 0; margin-bottom: 16px; font-size: 15px; font-weight: 700; color: var(--text-primary); }
    .stats-roles { display: flex; flex-direction: column; gap: 14px; }
    .stats-role-group { display: flex; gap: 12px; align-items: flex-start; font-size: 13px; }
    .stats-info { display: flex; flex-direction: column; gap: 2px; }
    .player-name { font-weight: 600; display: flex; align-items: center; gap: 6px; }
    .stats-val { color: var(--text-muted); font-size: 12px; font-weight: 600; }
  `],
})
export class TeamsComponent implements OnInit {
  allenatori = signal<any[]>([]);
  globalStats = signal<any>(null);

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.getAllenatori().subscribe({ next: d => this.allenatori.set(d) });
    this.api.getGlobalAllenatoriStats().subscribe({ next: d => this.globalStats.set(d) });
  }
}
