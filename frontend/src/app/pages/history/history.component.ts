import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { InputTextModule } from 'primeng/inputtext';
import { DropdownModule } from 'primeng/dropdown';
import { ButtonModule } from 'primeng/button';
import { SkeletonModule } from 'primeng/skeleton';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';

const STATS_COLUMNS = [
  { field: 'player_name', label: 'Giocatore' },
  { field: 'role', label: 'R' },
  { field: 'team', label: 'Squadra' },
  { field: 'matches_played', label: 'Pv' },
  { field: 'average_vote', label: 'Mv' },
  { field: 'fantasy_average', label: 'Fm' },
  { field: 'goals_scored', label: 'Gf' },
  { field: 'assists', label: 'Ass' },
  { field: 'yellow_cards', label: 'Amm' },
  { field: 'red_cards', label: 'Esp' },
];

const PRICES_COLUMNS = [
  { field: 'player_name', label: 'Giocatore' },
  { field: 'role', label: 'R' },
  { field: 'team', label: 'Squadra' },
  { field: 'market_value_i', label: 'Qt.I' },
  { field: 'market_value_a', label: 'Qt.A' },
  { field: 'difference', label: 'Diff.' },
  { field: 'fvm', label: 'FVM' },
];

@Component({
  selector: 'app-history',
  standalone: true,
  imports: [CommonModule, FormsModule, InputTextModule, DropdownModule, ButtonModule, SkeletonModule],
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <h1 class="page-title">📊 Storico Stagioni</h1>
        <p class="text-secondary">Statistiche e quotazioni delle stagioni passate importate da fantacalcio.it</p>
      </div>

      <div class="filters-bar card mb-4">
        <p-dropdown
          [options]="seasonOptions()"
          [(ngModel)]="selectedSeasonId"
          placeholder="Stagione"
          (ngModelChange)="loadData()"
          styleClass="filter-drop"
        />
        <p-dropdown
          [options]="dataTypeOptions"
          [(ngModel)]="dataType"
          (ngModelChange)="loadData()"
          styleClass="filter-drop"
        />
        <input
          pInputText
          class="filter-input"
          placeholder="🔍 Cerca giocatore..."
          [(ngModel)]="search"
          (ngModelChange)="applyFilter()"
        />
        @if (auth.isAuthenticated()) {
          <button
            pButton
            label="Importa da Fantacalcio"
            icon="pi pi-download"
            [loading]="importing()"
            [disabled]="!selectedSeasonId || importingAll()"
            (click)="importData()"
          ></button>
          <button
            pButton
            severity="secondary"
            [label]="importingAll() ? 'Importazione ' + bulkProgress() : 'Importa tutto'"
            icon="pi pi-cloud-download"
            [loading]="importingAll()"
            [disabled]="importing() || !seasonOptions().length"
            (click)="importAll()"
          ></button>
        }
        <a
          *ngIf="selectedSeasonId && filtered().length"
          class="csv-link"
          [href]="csvUrl()"
          download
        >⬇ CSV</a>
      </div>

      @if (message()) {
        <div class="card mb-4 status-msg" [class.error]="messageIsError()">{{ message() }}</div>
      }

      @if (bulkResults().length) {
        <div class="card mb-4 bulk-report">
          @for (r of bulkResults(); track r.key) {
            <div class="bulk-row" [class.error]="!r.ok">
              <span class="bulk-label">{{ r.label }}</span>
              <span class="text-muted">{{ r.detail }}</span>
            </div>
          }
        </div>
      }

      @if (loading()) {
        @for (i of [1,2,3,4,5,6]; track i) {
          <p-skeleton height="44px" styleClass="mb-2" />
        }
      } @else if (selectedSeasonId) {
        <div class="player-table card">
          <div class="table-header">
            <span style="width:40px">#</span>
            @for (col of columns(); track col.field) {
              <span [style.flex]="col.field === 'player_name' ? '1' : null"
                    [style.width]="col.field === 'player_name' ? null : '80px'"
                    [style.text-align]="col.field === 'player_name' ? null : 'right'">
                {{ col.label }}
              </span>
            }
          </div>
          @for (row of filtered(); track row.fanta_player_id; let i = $index) {
            <div class="player-row">
              <span class="row-num text-muted">{{ i + 1 }}</span>
              @for (col of columns(); track col.field) {
                <span [style.flex]="col.field === 'player_name' ? '1' : null"
                      [style.width]="col.field === 'player_name' ? null : '80px'"
                      [style.text-align]="col.field === 'player_name' ? null : 'right'"
                      [style.font-weight]="col.field === 'player_name' ? '600' : null">
                  {{ row[col.field] ?? '—' }}
                </span>
              }
            </div>
          }
          @empty {
            <p class="text-muted" style="padding:20px;">
              Nessun dato per questa stagione. Usa "Importa da Fantacalcio" per scaricarli.
            </p>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1280px; margin: 0 auto; }
    .page-header { margin-bottom: 24px; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; }

    .filters-bar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 14px 16px; }
    .filter-input { flex: 1; min-width: 180px; }
    .filter-drop { min-width: 140px; }
    .csv-link { font-size: 13px; font-weight: 600; color: var(--accent-blue); text-decoration: none; }

    .status-msg { padding: 12px 16px; font-size: 13px; }
    .status-msg.error { color: var(--text-negative, #e05260); }

    .bulk-report { padding: 8px 16px; }
    .bulk-row {
      display: flex; align-items: baseline; gap: 12px;
      padding: 6px 0; font-size: 13px;
      border-bottom: 1px solid var(--border-subtle);
    }
    .bulk-row:last-child { border-bottom: none; }
    .bulk-row.error .bulk-label { color: var(--text-negative, #e05260); }
    .bulk-label { font-weight: 700; min-width: 200px; }

    .player-table { padding: 0; overflow: hidden; }
    .table-header {
      display: flex; align-items: center; gap: 8px;
      padding: 10px 16px; font-size: 11px; font-weight: 700;
      color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em;
      border-bottom: 1px solid var(--border-color);
    }
    .player-row {
      display: flex; align-items: center; gap: 8px;
      padding: 10px 16px; border-bottom: 1px solid var(--border-subtle);
      font-size: 13px;
    }
    .player-row:hover { background: var(--bg-elevated); }
    .row-num { width: 40px; font-size: 12px; }
    .mb-2 { margin-bottom: 8px; }
    .mb-4 { margin-bottom: 24px; }
  `],
})
export class HistoryComponent implements OnInit {
  seasonOptions = signal<any[]>([]);
  rows = signal<any[]>([]);
  filtered = signal<any[]>([]);
  loading = signal(false);
  importing = signal(false);
  importingAll = signal(false);
  bulkProgress = signal('');
  bulkResults = signal<{ key: string; label: string; ok: boolean; detail: string }[]>([]);
  message = signal('');
  messageIsError = signal(false);
  columns = signal(STATS_COLUMNS);

  selectedSeasonId: number | null = null;
  dataType: 'stats' | 'prices' = 'stats';
  search = '';

  dataTypeOptions = [
    { label: 'Statistiche', value: 'stats' },
    { label: 'Quotazioni', value: 'prices' },
  ];

  constructor(private api: ApiService, public auth: AuthService) {}

  ngOnInit() {
    this.api.getSeasons().subscribe({
      next: seasons => this.seasonOptions.set(
        seasons.map(s => ({ label: s.label, value: s.id }))
      ),
    });
  }

  loadData() {
    if (!this.selectedSeasonId) return;
    this.columns.set(this.dataType === 'stats' ? STATS_COLUMNS : PRICES_COLUMNS);
    this.loading.set(true);
    this.message.set('');
    const req = this.dataType === 'stats'
      ? this.api.getSeasonStats(this.selectedSeasonId)
      : this.api.getSeasonPrices(this.selectedSeasonId);
    req.subscribe({
      next: data => { this.rows.set(data); this.applyFilter(); this.loading.set(false); },
      error: () => {
        this.loading.set(false);
        this.setMessage('Errore nel caricamento dei dati.', true);
      },
    });
  }

  applyFilter() {
    const term = this.search.trim().toLowerCase();
    this.filtered.set(
      term
        ? this.rows().filter(r => (r.player_name || '').toLowerCase().includes(term))
        : this.rows()
    );
  }

  importData() {
    if (!this.selectedSeasonId) return;
    this.importing.set(true);
    this.message.set('');
    this.api.importSeasonHistory(this.selectedSeasonId, this.dataType).subscribe({
      next: res => {
        this.importing.set(false);
        this.setMessage(
          res.imported ? `Importate ${res.rows} righe per la stagione ${res.season}.` : res.message,
          false
        );
        this.loadData();
      },
      error: err => {
        this.importing.set(false);
        this.setMessage(err.error?.detail || "Errore durante l'import.", true);
      },
    });
  }

  async importAll() {
    const seasons = this.seasonOptions();
    const types: ('stats' | 'prices')[] = ['stats', 'prices'];
    const total = seasons.length * types.length;
    let done = 0;

    this.importingAll.set(true);
    this.message.set('');
    this.bulkResults.set([]);

    for (const season of seasons) {
      for (const type of types) {
        this.bulkProgress.set(`${done + 1}/${total}`);
        const label = `${season.label} · ${type === 'stats' ? 'statistiche' : 'quotazioni'}`;
        try {
          const res = await firstValueFrom(this.api.importSeasonHistory(season.value, type));
          this.bulkResults.update(r => [...r, {
            key: `${season.value}-${type}`,
            label,
            ok: true,
            detail: res.imported ? `${res.rows} righe importate` : res.message,
          }]);
        } catch (err: any) {
          this.bulkResults.update(r => [...r, {
            key: `${season.value}-${type}`,
            label,
            ok: false,
            detail: err?.error?.detail || 'Errore durante l\'import',
          }]);
        }
        done++;
      }
    }

    this.importingAll.set(false);
    this.bulkProgress.set('');
    if (this.selectedSeasonId) this.loadData();
  }

  csvUrl(): string {
    return this.api.getSeasonHistoryCsvUrl(this.selectedSeasonId!, this.dataType);
  }

  private setMessage(text: string, isError: boolean) {
    this.message.set(text);
    this.messageIsError.set(isError);
  }
}
