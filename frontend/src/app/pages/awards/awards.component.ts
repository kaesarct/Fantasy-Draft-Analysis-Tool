import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SkeletonModule } from 'primeng/skeleton';
import { ApiService } from '../../core/services/api.service';

const COMPETITION_LABELS: Record<string, string> = {
  GOLD: 'Gold', BRONZE: 'Bronze', CARBON: 'Carbon',
  CIEMPIONS: 'Ciempions', UEFA: 'UEFA', COPPA_ITALIA: 'Coppa Italia', EURO_CUP: 'Euro Cup',
};

@Component({
  selector: 'app-awards',
  standalone: true,
  imports: [CommonModule, SkeletonModule],
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <h1 class="page-title">🏆 Premio Goku &amp; Premio Oscar</h1>
        <p class="text-secondary">Il punteggio più alto e più basso fatto da una squadra in una singola giornata, tra campionati e coppe</p>
      </div>

      @if (data(); as d) {
        <div class="awards-grid mb-4">
          <div class="card award-card">
            <img class="award-logo" src="/logo_Goku.png" alt="Premio Goku">
            <div class="award-title">Premio Goku — Stagione {{ d.current_season_label || '—' }}</div>
            @if (d.goku_current.length) {
              @for (p of d.goku_current; track p.fanta_team_id + '-' + p.match_day) {
                <div class="award-entry">
                  <span class="award-team">{{ p.fanta_team_name }}</span>
                  <span class="award-score">{{ p.score }}</span>
                  <span class="text-muted award-meta">{{ competitionLabel(p.competition_type) }} — {{ p.round_label }}</span>
                </div>
              }
            } @else {
              <p class="text-muted">Nessun dato ancora disponibile per questa stagione.</p>
            }
          </div>

          <div class="card award-card">
            <img class="award-logo" src="/logo_Oscar.png" alt="Premio Oscar">
            <div class="award-title">Premio Oscar — Stagione {{ d.current_season_label || '—' }}</div>
            @if (d.oscar_current.length) {
              @for (p of d.oscar_current; track p.fanta_team_id + '-' + p.match_day) {
                <div class="award-entry">
                  <span class="award-team">{{ p.fanta_team_name }}</span>
                  <span class="award-score">{{ p.score }}</span>
                  <span class="text-muted award-meta">{{ competitionLabel(p.competition_type) }} — {{ p.round_label }}</span>
                </div>
              }
            } @else {
              <p class="text-muted">Nessun dato ancora disponibile per questa stagione.</p>
            }
          </div>
        </div>

        <div class="card mb-4 record-panel">
          <div class="section-title">🥇 Record assoluto</div>
          <div class="record-grid">
            @if (d.absolute_goku; as r) {
              <div class="record-entry">
                <span class="record-label">Goku</span>
                <span class="record-value">{{ r.team_name }} — {{ r.score }}</span>
                <span class="text-muted">{{ r.season_label }} · {{ r.detail }}</span>
              </div>
            }
            @if (d.absolute_oscar; as r) {
              <div class="record-entry">
                <span class="record-label">Oscar</span>
                <span class="record-value">{{ r.team_name }} — {{ r.score }}</span>
                <span class="text-muted">{{ r.season_label }} · {{ r.detail }}</span>
              </div>
            }
          </div>
        </div>

        <div class="section-title">📜 Storico</div>
        <div class="card history-table">
          <div class="table-scroll">
            <div class="table-header">
              <span class="col-season">Stagione</span>
              <span class="col-award">Goku</span>
              <span class="col-award">Oscar</span>
            </div>
            @for (row of historyBySeason(); track row.season_label) {
              <div class="table-row">
                <span class="col-season">{{ row.season_label }}</span>
                <span class="col-award">
                  @if (row.goku) {
                    {{ row.goku.team_name }} — {{ row.goku.score }} <span class="text-muted">({{ row.goku.detail }})</span>
                  }
                </span>
                <span class="col-award">
                  @if (row.oscar) {
                    {{ row.oscar.team_name }} — {{ row.oscar.score }} <span class="text-muted">({{ row.oscar.detail }})</span>
                  }
                </span>
              </div>
            }
          </div>
        </div>
      } @else if (loading()) {
        <div class="awards-grid">
          <p-skeleton height="160px" />
          <p-skeleton height="160px" />
        </div>
      } @else {
        <p class="text-muted">Impossibile caricare i premi al momento.</p>
      }
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1100px; margin: 0 auto; }
    .page-header { margin-bottom: 24px; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; }
    .section-title { font-weight: 700; margin-bottom: 10px; }
    .mb-4 { margin-bottom: 24px; }

    .awards-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media (max-width: 640px) { .awards-grid { grid-template-columns: 1fr; } }

    .award-card { padding: 20px; text-align: center; }
    .award-logo { width: 72px; height: 72px; object-fit: contain; margin-bottom: 8px; }
    .award-title { font-weight: 700; margin-bottom: 10px; }
    .award-entry { display: flex; flex-direction: column; gap: 2px; padding: 6px 0; }
    .award-team { font-weight: 600; }
    .award-score { font-size: 22px; font-weight: 800; }
    .award-meta { font-size: 12px; }

    .record-panel { padding: 16px 20px; }
    .record-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media (max-width: 640px) { .record-grid { grid-template-columns: 1fr; } }
    .record-entry { display: flex; flex-direction: column; gap: 2px; }
    .record-label { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; opacity: .7; }
    .record-value { font-weight: 700; font-size: 15px; }

    .history-table { padding: 0; }
    .table-scroll { overflow-x: auto; }
    .table-header, .table-row {
      display: grid; grid-template-columns: 100px 1fr 1fr; gap: 12px;
      padding: 10px 16px; align-items: center; font-size: 13px;
    }
    .table-header { font-weight: 700; border-bottom: 1px solid var(--border-subtle); }
    .table-row { border-bottom: 1px solid var(--border-subtle); }
    .table-row:last-child { border-bottom: none; }
  `],
})
export class AwardsComponent implements OnInit {
  loading = signal(true);
  data = signal<any>(null);

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.getAwardsOverview().subscribe({
      next: res => {
        this.data.set(res);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  competitionLabel(type: string): string {
    return COMPETITION_LABELS[type] || type;
  }

  historyBySeason(): { season_label: string; goku: any; oscar: any }[] {
    const history: any[] = this.data()?.history ?? [];
    const bySeason = new Map<string, { season_label: string; goku: any; oscar: any }>();
    for (const row of history) {
      if (!bySeason.has(row.season_label)) {
        bySeason.set(row.season_label, { season_label: row.season_label, goku: null, oscar: null });
      }
      const entry = bySeason.get(row.season_label)!;
      if (row.award_type === 'GOKU') entry.goku = row;
      else entry.oscar = row;
    }
    return Array.from(bySeason.values());
  }
}
