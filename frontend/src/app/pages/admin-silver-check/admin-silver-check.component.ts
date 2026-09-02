import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ButtonModule } from 'primeng/button';
import { SkeletonModule } from 'primeng/skeleton';
import { ApiService } from '../../core/services/api.service';

const KIND_LABELS: Record<string, string> = {
  mismatch: 'Valore diverso',
  missing_league: 'Manca nel campionato',
  missing_silver: 'Manca in Silver',
};

@Component({
  selector: 'app-admin-silver-check',
  standalone: true,
  imports: [CommonModule, ButtonModule, SkeletonModule],
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <h1 class="page-title">⚖️ Coerenza Silver</h1>
        <p class="text-secondary">
          Confronta il punteggio cumulato di ogni squadra nel proprio campionato (Gold/Bronze/Carbon) con
          quello registrato in Silver: qui vanno segnalate solo le discrepanze, la correzione si fa
          dall'editor "Modifica classifica" in Gestione Squadre.
        </p>
        <button pButton label="Ricontrolla" icon="pi pi-refresh" size="small" class="p-button-outlined" [loading]="loading()" (click)="load()"></button>
      </div>

      @if (loading()) {
        <p-skeleton height="44px" styleClass="mb-2" />
        <p-skeleton height="44px" styleClass="mb-2" />
        <p-skeleton height="44px" />
      } @else if (error()) {
        <div class="card status-msg error">{{ error() }}</div>
      } @else {
        <div class="card discrepancy-table">
          <div class="table-scroll">
            <div class="table-header">
              <span>Squadra</span>
              <span>Giornata</span>
              <span>Campionato</span>
              <span>Valore campionato</span>
              <span>Valore Silver</span>
              <span>Tipo</span>
            </div>
            @for (row of discrepancies(); track row.fanta_team_id + '-' + row.match_day) {
              <div class="table-row">
                <span>{{ row.fanta_team_name }}</span>
                <span>{{ row.match_day }}</span>
                <span>{{ row.league_type }}</span>
                <span>{{ row.league_value ?? '—' }}</span>
                <span>{{ row.silver_value ?? '—' }}</span>
                <span class="badge badge-red">{{ kindLabel(row.kind) }}</span>
              </div>
            }
            @empty {
              <p class="text-muted empty-state">✅ Nessuna discrepanza trovata.</p>
            }
          </div>
        </div>
      }
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1200px; margin: 0 auto; }
    .page-header { margin-bottom: 24px; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; }
    .page-header .text-secondary { margin-bottom: 12px; }
    .mb-2 { margin-bottom: 8px; }

    .status-msg { padding: 12px 16px; font-size: 13px; }
    .status-msg.error { color: var(--text-negative, #e05260); }

    .discrepancy-table { padding: 0; }
    .table-scroll { overflow-x: auto; }
    .table-header, .table-row {
      display: grid; grid-template-columns: 1.4fr 90px 1fr 1.2fr 1.2fr 1.2fr; gap: 12px;
      padding: 10px 16px; align-items: center; font-size: 13px; min-width: 700px;
    }
    .table-header { font-weight: 700; border-bottom: 1px solid var(--border-subtle); }
    .table-row { border-bottom: 1px solid var(--border-subtle); }
    .table-row:last-child { border-bottom: none; }
    .empty-state { padding: 20px; }
  `],
})
export class AdminSilverCheckComponent implements OnInit {
  loading = signal(true);
  error = signal('');
  discrepancies = signal<any[]>([]);

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.load();
  }

  load() {
    this.loading.set(true);
    this.error.set('');
    this.api.getSilverConsistency().subscribe({
      next: res => {
        this.discrepancies.set(res.discrepancies ?? []);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Errore nel controllo di coerenza.');
        this.loading.set(false);
      },
    });
  }

  kindLabel(kind: string): string {
    return KIND_LABELS[kind] || kind;
  }
}
