import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { DropdownModule } from 'primeng/dropdown';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';

const LEAGUE_LEVELS = [
  { label: 'Tutte', value: null },
  { label: '🥇 Gold',    value: 'GOLD' },
  { label: '🥉 Bronze',  value: 'BRONZE' },
  { label: '⚫ Carbon',   value: 'CARBON' },
];

@Component({
  selector: 'app-teams',
  standalone: true,
  imports: [CommonModule, RouterLink, DropdownModule, FormsModule],
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <div>
          <h1 class="page-title">🛡️ Squadre</h1>
          <p class="text-secondary">Tutte le fanta-squadre della lega</p>
        </div>
        <p-dropdown [options]="leagueLevels" [(ngModel)]="selectedLevel"
          optionLabel="label" optionValue="value"
          (ngModelChange)="onLevelChange()" styleClass="filter-drop" />
      </div>

      <div class="teams-grid">
        @for (t of teams(); track t.id) {
          <a [routerLink]="['/teams', t.id]" class="team-card">
            <div class="team-logo">
              @if (t.logo_url) {
                <img [src]="t.logo_url" [alt]="t.name" />
              } @else {
                <span>{{ t.name[0] }}</span>
              }
            </div>
            <div class="team-info">
              <div class="team-name">{{ t.name }}</div>
              <div class="team-coaches text-muted">
                @for (c of t.coaches; track c.id) { {{ c.name }} }
              </div>
            </div>
            <div class="team-meta">
              <span class="badge" [ngClass]="leagueClass(t.league_id)">
                {{ leagueLabel(t.league_id) }}
              </span>
              <div class="credits text-muted">
                💰 {{ t.remaining_credits }} FM
              </div>
            </div>
          </a>
        }
        @empty {
          <p class="text-muted">Nessuna squadra trovata.</p>
        }
      </div>
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1280px; margin: 0 auto; }
    .page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 24px; gap: 16px; flex-wrap: wrap; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; }
    .filter-drop { min-width: 160px; }
    .teams-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
    .team-card {
      background: var(--bg-card); border: 1px solid var(--border-color);
      border-radius: var(--radius-md); padding: 16px 20px;
      display: flex; align-items: center; gap: 14px;
      text-decoration: none; color: var(--text-primary);
      transition: border-color var(--transition), transform var(--transition);
    }
    .team-card:hover { border-color: var(--accent-green); transform: translateY(-2px); }
    .team-logo {
      width: 48px; height: 48px; border-radius: 50%; overflow: hidden;
      background: linear-gradient(135deg, var(--accent-gold), var(--accent-orange));
      display: flex; align-items: center; justify-content: center;
      font-size: 20px; font-weight: 800; color: #fff; flex-shrink: 0;
    }
    .team-logo img { width: 100%; height: 100%; object-fit: cover; }
    .team-info { flex: 1; }
    .team-name { font-weight: 700; font-size: 14px; }
    .team-coaches { font-size: 12px; margin-top: 2px; }
    .team-meta { text-align: right; }
    .credits { font-size: 12px; margin-top: 6px; }
  `],
})
export class TeamsComponent implements OnInit {
  teams = signal<any[]>([]);
  leagueLevels = LEAGUE_LEVELS;
  selectedLevel: string | null = null;

  constructor(private api: ApiService) {}

  ngOnInit() { this.loadTeams(); }
  onLevelChange() { this.loadTeams(); }

  loadTeams() {
    this.api.getFantaTeams(undefined, this.selectedLevel ?? undefined).subscribe({
      next: d => this.teams.set(d),
    });
  }

  leagueClass(id: number) { return 'badge-gold'; } // TODO: resolve from competition
  leagueLabel(id: number) { return 'Gold'; }        // TODO: resolve from competition
}
