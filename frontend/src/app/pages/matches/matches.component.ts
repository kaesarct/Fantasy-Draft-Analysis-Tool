import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ButtonModule } from 'primeng/button';
import { SkeletonModule } from 'primeng/skeleton';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-matches',
  standalone: true,
  imports: [CommonModule, ButtonModule, SkeletonModule],
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <div class="header-row">
          <div>
            <h1 class="page-title">📅 Partite Serie A</h1>
            <p class="text-secondary">Prossime partite e risultati</p>
          </div>
          <button
            pButton
            label="Sync formazioni"
            icon="pi pi-refresh"
            [loading]="syncing()"
            [disabled]="!currentSeasonId()"
            (click)="syncFormazioni()"
          ></button>
        </div>
      </div>

      @if (syncMessage()) {
        <div class="card sync-msg" [class.error]="syncIsError()">{{ syncMessage() }}</div>
      }
      @if (syncReport().length) {
        <div class="card sync-report">
          @for (r of syncReport(); track r.name) {
            <div class="sync-report-row" [class.error]="!r.ok">
              <span class="comp-name">{{ r.name }}</span>
              <span class="text-muted">{{ r.detail }}</span>
            </div>
          }
        </div>
      }

      @if (loading()) {
        <div class="matches-grid">
          @for (i of [1,2,3,4,5,6,7,8,9,10]; track i) {
            <p-skeleton height="90px" />
          }
        </div>
      } @else {
        <div class="matches-grid">
          @for (m of matches(); track m.home_team + m.away_team) {
            <div class="match-card" [class.played]="m.is_played">
              <div class="match-body">
                <span class="team home">{{ m.home_team }}</span>
                <div class="score-block">
                  <span class="score">{{ m.score || 'vs' }}</span>
                  <span class="match-date text-muted">{{ m.match_date | date:'EEE d MMM HH:mm' }}</span>
                </div>
                <span class="team away">{{ m.away_team }}</span>
              </div>
              @if (m.location) {
                <div class="match-location text-muted">📍 {{ m.location }}</div>
              }
            </div>
          }
          @empty {
            <div class="empty-state">
              <p>Nessuna partita trovata.</p>
              <p class="text-muted" style="font-size:12px">Controlla la connessione a fantacalcio.it</p>
            </div>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1280px; margin: 0 auto; }
    .page-header { margin-bottom: 24px; }
    .page-title  { font-size: 24px; font-weight: 800; margin-bottom: 4px; }
    .header-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }

    .sync-msg { padding: 12px 16px; font-size: 13px; margin-bottom: 16px; }
    .sync-msg.error { color: var(--text-negative, #e05260); }
    .sync-report { padding: 8px 16px; margin-bottom: 16px; }
    .sync-report-row {
      display: flex; align-items: baseline; gap: 12px;
      padding: 6px 0; font-size: 13px;
      border-bottom: 1px solid var(--border-subtle);
    }
    .sync-report-row:last-child { border-bottom: none; }
    .sync-report-row.error .comp-name { color: var(--text-negative, #e05260); }
    .comp-name { font-weight: 700; min-width: 160px; }
    .matches-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }

    .match-card {
      background: var(--bg-card); border: 1px solid var(--border-color);
      border-radius: var(--radius-md); padding: 16px 20px;
      transition: border-color var(--transition), transform var(--transition);
    }
    .match-card:hover { border-color: var(--accent-blue); transform: translateY(-2px); }
    .match-card.played { opacity: 0.65; }

    .match-body { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .team { font-weight: 700; font-size: 14px; flex: 1; }
    .home { text-align: right; }
    .away { text-align: left; }
    .score-block { text-align: center; flex-shrink: 0; }
    .score {
      display: block; font-size: 16px; font-weight: 800;
      background: var(--bg-elevated); padding: 6px 14px;
      border-radius: var(--radius-sm); margin-bottom: 4px;
    }
    .match-date { font-size: 11px; }
    .match-location { margin-top: 10px; font-size: 11px; text-align: center; }
    .empty-state { grid-column: 1/-1; text-align: center; padding: 48px; color: var(--text-secondary); }
  `],
})
export class MatchesComponent implements OnInit {
  matches = signal<any[]>([]);
  loading = signal(true);
  currentSeasonId = signal<number | null>(null);
  syncing = signal(false);
  syncMessage = signal('');
  syncIsError = signal(false);
  syncReport = signal<{ name: string; ok: boolean; detail: string }[]>([]);

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.getNextMatches().subscribe({
      next: data => { this.matches.set(data); this.loading.set(false); },
      error: ()  => this.loading.set(false),
    });
    this.api.getSeasons().subscribe({
      next: seasons => {
        const current = seasons.find(s => s.is_current);
        this.currentSeasonId.set(current ? current.id : null);
      },
    });
  }

  syncFormazioni() {
    const seasonId = this.currentSeasonId();
    if (!seasonId) return;
    this.syncing.set(true);
    this.syncMessage.set('');
    this.syncReport.set([]);
    this.api.syncFormazioni(seasonId).subscribe({
      next: res => {
        this.syncing.set(false);
        this.syncMessage.set('Sync formazioni completato.');
        this.syncIsError.set(false);
        this.syncReport.set(
          Object.entries(res.competitions || {}).map(([name, r]: [string, any]) => ({
            name,
            ok: r.ok,
            detail: this.describeCompetition(r),
          }))
        );
      },
      error: err => {
        this.syncing.set(false);
        this.syncIsError.set(true);
        this.syncMessage.set(err.error?.detail || 'Errore durante il sync formazioni.');
      },
    });
  }

  private describeCompetition(r: any): string {
    if (r.message) return r.message;
    const parts = [`giornata ${r.match_day}`, `${r.lineups} formazioni`, `${r.players_imported} giocatori`];
    if (r.unmatched_teams?.length) parts.push(`team non riconosciuti: ${r.unmatched_teams.join(', ')}`);
    if (r.unmatched_players_count) parts.push(`${r.unmatched_players_count} giocatori non riconosciuti`);
    return parts.join(' · ');
  }
}
