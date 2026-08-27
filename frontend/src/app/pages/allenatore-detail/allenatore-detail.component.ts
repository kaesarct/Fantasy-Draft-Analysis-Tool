import { Component, OnInit, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { DropdownModule } from 'primeng/dropdown';
import { ApiService } from '../../core/services/api.service';

const ROLE_ORDER = ['P', 'D', 'C', 'A'];

@Component({
  selector: 'app-allenatore-detail',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, DropdownModule],
  template: `
    <div class="page-container fade-up">
      @if (loading()) {
        <p class="text-muted">Caricamento...</p>
      } @else if (!allenatore()) {
        <p class="text-muted">Allenatore non trovato.</p>
      } @else {
        <a routerLink="/teams" class="back-link">← Allenatori</a>
        <div class="page-header">
          <div class="avatar">{{ allenatore().display_name[0] }}</div>
          <div>
            <h1 class="page-title">👤 {{ allenatore().display_name }}</h1>
            <p class="text-secondary">{{ '@' + allenatore().username }}</p>
          </div>
        </div>

        <div class="section-title">🛡️ Storico squadre ({{ allenatore().teams.length }})</div>
        <div class="card mb-4 teams-table">
          @for (t of allenatore().teams; track t.team_id) {
            <a [routerLink]="['/teams', t.team_id]" class="team-row">
              <span class="team-season">{{ t.season }}</span>
              <span class="team-name">{{ t.team_name }}</span>
              <span class="text-muted">{{ t.league }}</span>
              <span class="team-standings">
                @for (s of t.standings; track s.competition_id) {
                  <span class="standing-chip" [class.partial]="s.is_partial_data">
                    {{ s.competition_type === 'SILVER' ? 'Silver' : s.competition_type }}: {{ s.rank }}°/{{ s.total_teams }}
                    @if (s.is_partial_data) { <span title="Dati parziali per questa stagione: posizione non certa">⚠️</span> }
                  </span>
                }
              </span>
            </a>
          }
          @empty {
            <p class="text-muted" style="padding:14px 16px; margin:0;">Nessuna squadra gestita.</p>
          }
        </div>

        <div class="section-title">⚽ Giocatori acquistati ({{ players().length }})</div>
        <div class="card mb-4 players-panel">
          <div class="filters-bar">
            <p-dropdown
              [options]="seasonOptions()"
              [(ngModel)]="selectedSeasonId"
              placeholder="Tutte le stagioni"
              [showClear]="true"
              (ngModelChange)="loadPlayers()"
              styleClass="filter-drop"
            />
          </div>
          @if (loadingPlayers()) {
            <p class="text-muted" style="padding:14px 16px;">Caricamento...</p>
          } @else {
            <div class="players-table">
              @for (p of players(); track p.player_id) {
                <div class="player-row">
                  <span class="role-badge role-{{ p.role }}">{{ p.role }}</span>
                  <span class="player-name">{{ p.player_name }}</span>
                  <span class="player-acquisitions">
                    @for (acq of p.acquisitions; track acq.season_id + '-' + acq.team_id) {
                      <span class="acq-chip">
                        {{ acq.season_label }} — {{ acq.team_name }}: <strong>{{ acq.purchase_price }} FM</strong>
                      </span>
                    }
                  </span>
                </div>
              }
              @empty {
                <p class="text-muted" style="padding:14px 16px; margin:0;">Nessun giocatore acquistato.</p>
              }
            </div>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1100px; margin: 0 auto; }
    .back-link { display: inline-block; margin-bottom: 12px; font-size: 13px; color: var(--text-secondary); text-decoration: none; }
    .back-link:hover { text-decoration: underline; }
    .page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 2px; }
    .section-title { font-weight: 700; margin-bottom: 10px; }
    .mb-4 { margin-bottom: 24px; }

    .avatar {
      width: 56px; height: 56px; border-radius: 50%;
      background: linear-gradient(135deg, var(--accent-green), var(--accent-blue));
      display: flex; align-items: center; justify-content: center;
      font-size: 22px; font-weight: 800; color: #fff; flex-shrink: 0;
    }

    .teams-table { padding: 0; }
    .team-row {
      display: flex; align-items: center; gap: 14px; padding: 10px 16px;
      border-bottom: 1px solid var(--border-subtle); text-decoration: none; color: var(--text-primary);
      flex-wrap: wrap;
    }
    .team-row:last-child { border-bottom: none; }
    .team-row:hover { background: var(--bg-elevated); }
    .team-season { font-size: 12px; color: var(--text-muted); min-width: 60px; }
    .team-name { font-weight: 600; font-size: 13px; min-width: 140px; }
    .team-standings { display: flex; gap: 8px; flex-wrap: wrap; margin-left: auto; }
    .standing-chip { font-size: 11px; padding: 2px 8px; border-radius: 6px; background: var(--bg-elevated); }
    .standing-chip.partial { color: var(--text-muted); }

    .players-panel { padding: 0; }
    .filters-bar { padding: 14px 16px; border-bottom: 1px solid var(--border-subtle); }
    .filter-drop { min-width: 180px; }
    .players-table { padding: 0; }
    .player-row {
      display: flex; align-items: flex-start; gap: 10px; padding: 10px 16px;
      border-bottom: 1px solid var(--border-subtle); flex-wrap: wrap;
    }
    .player-row:last-child { border-bottom: none; }
    .player-name { font-weight: 600; font-size: 13px; min-width: 140px; }
    .player-acquisitions { display: flex; gap: 6px; flex-wrap: wrap; flex: 1; }
    .acq-chip {
      font-size: 12px; padding: 4px 10px; border-radius: 6px;
      background: var(--bg-elevated); border: 1px solid var(--border-color);
      color: var(--text-primary);
    }
    .acq-chip strong { color: var(--accent-green); }
  `],
})
export class AllenatoreDetailComponent implements OnInit {
  allenatore = signal<any>(null);
  loading = signal(true);
  players = signal<any[]>([]);
  loadingPlayers = signal(false);
  selectedSeasonId: number | null = null;

  private allenatoreId!: number;

  seasonOptions = computed(() => {
    const a = this.allenatore();
    if (!a) return [];
    const seen = new Map<number, string>();
    for (const t of a.teams) seen.set(t.season_id, t.season);
    return Array.from(seen.entries()).map(([value, label]) => ({ label, value }));
  });

  constructor(private route: ActivatedRoute, private api: ApiService) {}

  ngOnInit() {
    this.route.paramMap.subscribe(params => {
      this.allenatoreId = Number(params.get('id'));
      if (!this.allenatoreId) {
        this.loading.set(false);
        return;
      }
      this.loading.set(true);
      this.allenatore.set(null);
      this.selectedSeasonId = null;
      this.api.getAllenatore(this.allenatoreId).subscribe({
        next: a => {
          this.allenatore.set(a);
          this.loading.set(false);
          this.loadPlayers();
        },
        error: () => this.loading.set(false),
      });
    });
  }

  loadPlayers() {
    this.loadingPlayers.set(true);
    this.api.getAllenatorePlayers(this.allenatoreId, this.selectedSeasonId ?? undefined).subscribe({
      next: p => {
        const sorted = [...p].sort((a: any, b: any) =>
          ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role) || (a.player_name || '').localeCompare(b.player_name || '')
        );
        this.players.set(sorted);
        this.loadingPlayers.set(false);
      },
      error: () => this.loadingPlayers.set(false),
    });
  }
}
