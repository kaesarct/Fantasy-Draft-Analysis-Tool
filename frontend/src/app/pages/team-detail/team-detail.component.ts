import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';

const ROLE_ORDER = ['P', 'D', 'C', 'A'];

@Component({
  selector: 'app-team-detail',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <div class="page-container fade-up">
      @if (loading()) {
        <p class="text-muted">Caricamento...</p>
      } @else if (!team()) {
        <p class="text-muted">Squadra non trovata.</p>
      } @else {
        <div class="page-header">
          <div class="team-logo">
            @if (team().logo_url) {
              <img [src]="team().logo_url" [alt]="team().name" />
            } @else {
              <span>{{ team().name[0] }}</span>
            }
          </div>
          <div>
            <h1 class="page-title">🛡️ {{ team().name }}</h1>
            <p class="text-secondary">{{ team().season_label }}</p>
            @if (team().standings?.length) {
              <div class="standings-row">
                @for (s of team().standings; track s.competition_id) {
                  <span class="standing-chip">
                    {{ s.competition_type === 'SILVER' ? 'Silver' : s.competition_type }}: {{ s.rank }}°/{{ s.total_teams }}
                    @if (s.is_partial_data) {
                      <span class="text-muted" title="Per questa stagione abbiamo dati parziali (es. solo il vincitore noto): la posizione potrebbe non essere reale">⚠️</span>
                    }
                  </span>
                }
              </div>
            }
          </div>
        </div>

        <div class="section-title">👤 Allenatori</div>
        <div class="card mb-4 coach-list">
          @for (c of team().coaches; track c.id) {
            <a [routerLink]="['/allenatori', c.id]" class="assigned-chip" [class.primary]="c.primary">{{ c.primary ? '⭐' : '' }}{{ c.name }}</a>
          }
          @empty {
            <p class="text-muted" style="padding:14px 16px; margin:0;">Nessun allenatore assegnato.</p>
          }
        </div>

        @if (lineage().length > 1) {
          <div class="section-title">🔗 Storico nomi</div>
          <div class="card mb-4 lineage-list">
            @for (entry of lineage(); track entry.team_id) {
              @if (entry.team_id === team().id) {
                <div class="lineage-row current">
                  <span class="lineage-season">{{ entry.season_label }}</span>
                  <span class="lineage-name">{{ entry.name }}</span>
                  <span class="text-muted" style="font-size:11px;">(qui)</span>
                </div>
              } @else {
                <a class="lineage-row" [routerLink]="['/teams', entry.team_id]">
                  <span class="lineage-season">{{ entry.season_label }}</span>
                  <span class="lineage-name">{{ entry.name }}</span>
                </a>
              }
            }
          </div>
        }

        @if (rosterHistory().length) {
          <div class="section-title">📅 Storico mercato</div>
          <div class="card mb-4 history-list">
            @for (ev of rosterHistory(); track ev.date) {
              <div class="history-event">
                <div class="history-header">
                  <span class="history-date">{{ ev.date }}</span>
                  <span class="text-muted">
                    delta crediti: <strong [class.text-positive]="ev.credit_delta > 0" [class.text-negative]="ev.credit_delta < 0">{{ ev.credit_delta }}</strong>
                  </span>
                </div>
                @for (p of ev.acquired; track p.player_id) {
                  <div class="history-row acquired">
                    <span class="role-badge role-{{ p.role }}">{{ p.role }}</span>
                    <span>{{ p.player_name }}</span>
                    <span class="text-muted">acquistato — {{ p.price }} FM</span>
                  </div>
                }
                @for (p of ev.released; track p.player_id) {
                  <div class="history-row released">
                    <span class="role-badge role-{{ p.role }}">{{ p.role }}</span>
                    <span>{{ p.player_name }}</span>
                    <span class="text-muted">svincolato — rimborso {{ p.refund }} FM</span>
                  </div>
                }
              </div>
            }
          </div>
        }

        <div class="section-title">📋 Rosa ({{ team().roster.length }})</div>
        <div class="card mb-4 roster-table">
          @for (p of team().roster; track p.player_id) {
            <div class="roster-row">
              <span class="role-badge role-{{ p.role }}">{{ p.role }}</span>
              <span class="player-name">{{ p.player_name }}</span>
              <span class="text-muted">💰 {{ p.purchase_price }} FM</span>
            </div>
          }
          @empty {
            <p class="text-muted" style="padding:14px 16px; margin:0;">Nessun giocatore in rosa.</p>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 900px; margin: 0 auto; }
    .page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 2px; }
    .section-title { font-weight: 700; margin-bottom: 10px; }
    .mb-4 { margin-bottom: 24px; }

    .team-logo {
      width: 56px; height: 56px; border-radius: 50%; overflow: hidden;
      background: linear-gradient(135deg, var(--accent-gold), var(--accent-orange));
      display: flex; align-items: center; justify-content: center;
      font-size: 22px; font-weight: 800; color: #fff; flex-shrink: 0;
    }
    .team-logo img { width: 100%; height: 100%; object-fit: cover; }

    .coach-list { padding: 14px 16px; display: flex; flex-wrap: wrap; gap: 8px; }
    .assigned-chip {
      display: inline-flex; align-items: center; gap: 4px;
      background: var(--bg-elevated); border: 1px solid var(--border-color);
      border-radius: 999px; padding: 4px 12px; font-size: 13px;
      text-decoration: none; color: var(--text-primary);
    }
    .assigned-chip:hover { border-color: var(--accent-green); }
    .assigned-chip.primary { border-color: var(--accent-green); }

    .standings-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
    .standing-chip {
      font-size: 12px; padding: 2px 10px; border-radius: 999px;
      background: var(--bg-elevated); border: 1px solid var(--border-color);
    }

    .lineage-list { padding: 0; }
    .lineage-row {
      display: flex; align-items: center; gap: 12px; padding: 10px 16px;
      border-bottom: 1px solid var(--border-subtle); text-decoration: none; color: var(--text-primary);
    }
    .lineage-row:last-child { border-bottom: none; }
    .lineage-row:not(.current):hover { background: var(--bg-elevated); }
    .lineage-row.current { font-weight: 700; }
    .lineage-season { font-size: 12px; color: var(--text-muted); min-width: 70px; }

    .roster-table { padding: 0; }
    .roster-row {
      display: flex; align-items: center; gap: 12px; padding: 10px 16px;
      border-bottom: 1px solid var(--border-subtle);
    }
    .roster-row:last-child { border-bottom: none; }
    .player-name { font-weight: 600; font-size: 13px; flex: 1; }

    .history-list { padding: 0; }
    .history-event { padding: 12px 16px; border-bottom: 1px solid var(--border-subtle); }
    .history-event:last-child { border-bottom: none; }
    .history-header {
      display: flex; align-items: center; justify-content: space-between;
      font-weight: 700; font-size: 13px; margin-bottom: 8px;
    }
    .history-date { color: var(--text-secondary); }
    .history-row {
      display: flex; align-items: center; gap: 10px; padding: 4px 0; font-size: 13px;
    }
    .history-row.acquired > span:nth-child(2) { color: var(--accent-green); }
    .history-row.released > span:nth-child(2) { color: var(--text-muted); }
  `],
})
export class TeamDetailComponent implements OnInit {
  team = signal<any>(null);
  lineage = signal<any[]>([]);
  rosterHistory = signal<any[]>([]);
  loading = signal(true);

  constructor(private route: ActivatedRoute, private api: ApiService) {}

  ngOnInit() {
    this.route.paramMap.subscribe(params => {
      const id = Number(params.get('id'));
      if (!id) {
        this.loading.set(false);
        return;
      }
      this.loading.set(true);
      this.team.set(null);
      this.lineage.set([]);
      this.rosterHistory.set([]);
      this.api.getFantaTeam(id).subscribe({
        next: t => {
          t.roster = [...t.roster].sort((a: any, b: any) =>
            ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role) || a.player_name.localeCompare(b.player_name)
          );
          this.team.set(t);
          this.loading.set(false);
        },
        error: () => this.loading.set(false),
      });
      this.api.getTeamLineage(id).subscribe({ next: l => this.lineage.set(l) });
      this.api.getTeamRosterHistory(id).subscribe({ next: h => this.rosterHistory.set(h) });
    });
  }
}
