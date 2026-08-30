import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
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

// L'import da pianetafanta copre solo 2006-07..2014-15 (fatto storico chiuso,
// non un confine che si sposta come la stagione corrente) — vedi
// backend/app/routers/history.py::_query_archive_stats.
const ARCHIVE_ONLY_MAX_YEAR_START = 2014;

const VOTES_COLUMNS = [
  { field: 'match_day', label: 'G' },
  { field: 'player_name', label: 'Giocatore' },
  { field: 'role', label: 'R' },
  { field: 'team', label: 'Squadra' },
  { field: 'vote', label: 'Voto' },
  { field: 'goals_scored', label: 'Gf' },
  { field: 'assists', label: 'Ass' },
  { field: 'yellow_cards', label: 'Amm' },
  { field: 'red_cards', label: 'Esp' },
  { field: 'own_goals', label: 'Au' },
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
        @if (dataType === 'votes') {
          <p-dropdown
            [options]="matchDayOptions"
            [(ngModel)]="selectedMatchDay"
            (ngModelChange)="loadData()"
            styleClass="filter-drop"
          />
        }
        <input
          pInputText
          class="filter-input"
          placeholder="🔍 Cerca giocatore..."
          [(ngModel)]="search"
          (ngModelChange)="applyFilter()"
        />
        @if (auth.isAuthenticated() && selectedSeasonId === currentSeasonId()) {
          <button
            pButton
            label="Importa da Fantacalcio"
            icon="pi pi-download"
            [loading]="importing()"
            [disabled]="!selectedSeasonId"
            (click)="importData()"
          ></button>
        }
        @if (dataType === 'votes') {
          <span class="text-muted" style="font-size:12px">⏱ i voti sono per giornata: l'import di una stagione può richiedere fino a un minuto</span>
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

      @if (loading()) {
        @for (i of [1,2,3,4,5,6]; track i) {
          <p-skeleton height="44px" styleClass="mb-2" />
        }
      } @else if (selectedSeasonId) {
        <div class="player-table card">
          <div class="table-scroll">
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
                @if (selectedSeasonId === currentSeasonId()) {
                  Nessun dato per questa stagione. Usa "Importa da Fantacalcio" per scaricarli.
                } @else if (isArchiveOnlySeason() && dataType !== 'stats') {
                  {{ dataType === 'prices' ? 'Le quotazioni' : 'I voti per giornata' }} non sono disponibili per questa stagione storica: è disponibile solo la scheda Statistiche.
                } @else {
                  Nessun dato per questa stagione.
                }
              </p>
            }
          </div>
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

    .player-table { padding: 0; overflow: hidden; }
    .table-scroll { overflow-x: auto; }
    .table-header {
      display: flex; align-items: center; gap: 8px;
      padding: 10px 16px; font-size: 11px; font-weight: 700;
      color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em;
      border-bottom: 1px solid var(--border-color);
      min-width: 900px;
    }
    .player-row {
      display: flex; align-items: center; gap: 8px;
      padding: 10px 16px; border-bottom: 1px solid var(--border-subtle);
      font-size: 13px;
      min-width: 900px;
    }
    .player-row:hover { background: var(--bg-elevated); }
    .row-num { width: 40px; font-size: 12px; }
    .mb-2 { margin-bottom: 8px; }
    .mb-4 { margin-bottom: 24px; }
  `],
})
export class HistoryComponent implements OnInit {
  seasonOptions = signal<any[]>([]);
  currentSeasonId = signal<number | null>(null);
  rows = signal<any[]>([]);
  filtered = signal<any[]>([]);
  loading = signal(false);
  importing = signal(false);
  message = signal('');
  messageIsError = signal(false);
  columns = signal(STATS_COLUMNS);

  matchDayOptions: { label: string; value: number | null }[] = [
    { label: 'Tutte le giornate', value: null },
    ...Array.from({ length: 38 }, (_, i) => ({ label: `Giornata ${i + 1}`, value: i + 1 })),
  ];

  selectedSeasonId: number | null = null;
  selectedMatchDay: number | null = null;
  dataType: 'stats' | 'prices' | 'votes' = 'stats';
  search = '';

  dataTypeOptions = [
    { label: 'Statistiche', value: 'stats' },
    { label: 'Quotazioni', value: 'prices' },
    { label: 'Voti', value: 'votes' },
  ];

  constructor(private api: ApiService, public auth: AuthService) {}

  ngOnInit() {
    this.api.getSeasons().subscribe({
      next: seasons => {
        this.seasonOptions.set(seasons.map(s => ({ label: s.label, value: s.id, year_start: s.year_start })));
        const current = seasons.find(s => s.is_current);
        this.currentSeasonId.set(current ? current.id : null);
      },
    });
  }

  loadData() {
    if (!this.selectedSeasonId) return;
    this.columns.set(
      this.dataType === 'stats' ? STATS_COLUMNS : this.dataType === 'prices' ? PRICES_COLUMNS : VOTES_COLUMNS
    );
    this.loading.set(true);
    this.message.set('');
    const req = this.dataType === 'stats'
      ? this.api.getSeasonStats(this.selectedSeasonId)
      : this.dataType === 'prices'
      ? this.api.getSeasonPrices(this.selectedSeasonId)
      : this.api.getSeasonVotes(this.selectedSeasonId, this.selectedMatchDay);
    req.subscribe({
      next: data => { this.rows.set(data); this.applyFilter(); this.loading.set(false); },
      error: () => {
        this.loading.set(false);
        this.setMessage('Errore nel caricamento dei dati.', true);
      },
    });
  }

  isArchiveOnlySeason(): boolean {
    const season = this.seasonOptions().find(s => s.value === this.selectedSeasonId);
    return !!season && season.year_start <= ARCHIVE_ONLY_MAX_YEAR_START;
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
    const matchDay = this.dataType === 'votes' ? this.selectedMatchDay : undefined;
    this.api.importSeasonHistory(this.selectedSeasonId, this.dataType, false, matchDay).subscribe({
      next: res => {
        this.importing.set(false);
        if (res.imported) {
          const skipped = res.skipped_match_days?.length
            ? ` (${res.skipped_match_days.length} giornate senza dati: ${res.skipped_match_days.join(', ')})`
            : '';
          const giornata = res.match_day ? ` (giornata ${res.match_day})` : '';
          this.setMessage(`Importate ${res.rows} righe per la stagione ${res.season}${giornata}.${skipped}`, false);
        } else {
          this.setMessage(res.message, false);
        }
        this.loadData();
      },
      error: err => {
        this.importing.set(false);
        this.setMessage(err.error?.detail || "Errore durante l'import.", true);
      },
    });
  }

  csvUrl(): string {
    return this.dataType === 'votes'
      ? this.api.getSeasonVotesCsvUrl(this.selectedSeasonId!, this.selectedMatchDay)
      : this.api.getSeasonHistoryCsvUrl(this.selectedSeasonId!, this.dataType);
  }

  private setMessage(text: string, isError: boolean) {
    this.message.set(text);
    this.messageIsError.set(isError);
  }
}
