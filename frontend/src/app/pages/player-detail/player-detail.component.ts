import { Component, OnInit, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { DropdownModule } from 'primeng/dropdown';
import { SkeletonModule } from 'primeng/skeleton';
import { ChartModule } from 'primeng/chart';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-player-detail',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, DropdownModule, SkeletonModule, ChartModule],
  template: `
    <div class="page-container fade-up">
      <a routerLink="/players" class="back-link">← Torna ai giocatori</a>

      @if (loading()) {
        <p-skeleton height="80px" styleClass="mb-4" />
        <p-skeleton height="260px" styleClass="mb-4" />
        <p-skeleton height="200px" />
      } @else if (!player()) {
        <div class="empty-state">
          <p>Giocatore non trovato.</p>
        </div>
      } @else {
        <div class="page-header player-header">
          <div>
            <h1 class="page-title">
              ⚽ {{ player().name }}
              <span class="role-badge role-{{ player().role }}">{{ player().role }}</span>
            </h1>
            <p class="text-secondary">{{ player().serie_a_team_name ?? 'Squadra non assegnata' }}</p>
          </div>
          <p-dropdown
            [options]="seasonOptions()"
            [(ngModel)]="selectedSeasonId"
            (ngModelChange)="onSeasonChange()"
            placeholder="Stagione"
            styleClass="filter-drop"
          />
        </div>

        <div class="section-title">📈 Andamento quotazione</div>
        <div class="card mb-4 chart-card">
          @if (loadingData()) {
            <p-skeleton height="220px" />
          } @else if (history().length) {
            <p-chart type="line" [data]="priceChartData()" [options]="chartOptions" height="240px" />
          } @else {
            <p class="text-muted">Nessuno storico quotazioni disponibile per questa stagione.</p>
          }
        </div>

        <div class="section-title">🗳️ Voti e bonus/malus</div>
        @if (loadingData()) {
          <p-skeleton height="120px" />
        } @else if (scores().length) {
          <div class="player-table card">
            <div class="table-header">
              <span style="width:60px">Giornata</span>
              <span style="width:70px;text-align:right">Voto</span>
              <span style="width:50px;text-align:right">Gol</span>
              <span style="width:50px;text-align:right">Ass.</span>
              <span style="width:50px;text-align:right">Amm.</span>
              <span style="width:50px;text-align:right">Esp.</span>
              <span style="width:80px;text-align:right">Bonus</span>
              <span style="width:80px;text-align:right">Malus</span>
              <span style="width:70px;text-align:right">Finale</span>
            </div>
            @for (s of scores(); track s.match_day) {
              <div class="score-row">
                <span style="width:60px">{{ s.match_day }}</span>
                <span style="width:70px;text-align:right">{{ s.vote ?? '—' }}</span>
                <span style="width:50px;text-align:right">{{ s.goals }}</span>
                <span style="width:50px;text-align:right">{{ s.assists }}</span>
                <span style="width:50px;text-align:right">{{ s.yellow_cards }}</span>
                <span style="width:50px;text-align:right">{{ s.red_cards }}</span>
                <span style="width:80px;text-align:right" class="text-positive">{{ s.bonus_total || '—' }}</span>
                <span style="width:80px;text-align:right" class="text-negative">{{ s.malus_total || '—' }}</span>
                <span style="width:70px;text-align:right;font-weight:700">{{ s.total_score ?? '—' }}</span>
              </div>
            }
          </div>
        } @else {
          <p class="text-muted">Nessun voto disponibile per questa stagione.</p>
        }
      }
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1280px; margin: 0 auto; }
    .back-link { display: inline-block; margin-bottom: 16px; color: var(--text-secondary); text-decoration: none; font-size: 13px; }
    .back-link:hover { color: var(--text-primary); }

    .page-header { margin-bottom: 24px; }
    .player-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; display: flex; align-items: center; gap: 10px; }
    .filter-drop { min-width: 140px; }

    .section-title { font-size: 13px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: .05em; margin: 0 0 10px; }
    .chart-card { padding: 16px; }

    .player-table { padding: 0; overflow: hidden; }
    .table-header, .score-row {
      display: flex; align-items: center; gap: 8px;
      padding: 10px 16px;
    }
    .table-header {
      font-size: 11px; font-weight: 700; color: var(--text-muted);
      text-transform: uppercase; letter-spacing: .05em;
      border-bottom: 1px solid var(--border-color);
    }
    .score-row { font-size: 13px; border-bottom: 1px solid var(--border-subtle); }
    .score-row:last-child { border-bottom: none; }

    .empty-state { padding: 40px; text-align: center; color: var(--text-muted); }
    .mb-4 { margin-bottom: 24px; }
  `],
})
export class PlayerDetailComponent implements OnInit {
  player = signal<any>(null);
  loading = signal(true);
  loadingData = signal(true);

  seasons = signal<any[]>([]);
  selectedSeasonId: number | null = null;

  history = signal<any[]>([]);
  scores = signal<any[]>([]);

  seasonOptions = computed(() =>
    this.seasons().map(s => ({ label: s.label, value: s.id }))
  );

  chartOptions = {
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: '#8b949e' }, grid: { color: '#21262d' } },
      y: { ticks: { color: '#8b949e' }, grid: { color: '#21262d' } },
    },
  };

  private playerId!: number;

  constructor(private route: ActivatedRoute, private api: ApiService) {}

  ngOnInit() {
    this.playerId = Number(this.route.snapshot.paramMap.get('id'));

    this.api.getPlayer(this.playerId).subscribe({
      next: player => {
        this.player.set(player);
        this.loading.set(false);
      },
      error: () => {
        this.player.set(null);
        this.loading.set(false);
      },
    });

    this.api.getSeasons().subscribe(seasons => {
      this.seasons.set(seasons);
      const current = seasons.find((s: any) => s.is_current) ?? seasons[0];
      this.selectedSeasonId = current?.id ?? null;
      this.loadSeasonData();
    });
  }

  onSeasonChange() {
    this.loadSeasonData();
  }

  private loadSeasonData() {
    if (!this.selectedSeasonId) {
      this.history.set([]);
      this.scores.set([]);
      this.loadingData.set(false);
      return;
    }
    this.loadingData.set(true);
    this.api.getPlayerHistory(this.playerId, this.selectedSeasonId).subscribe(history => {
      this.history.set(history);
      this.loadingData.set(false);
    });
    this.api.getPlayerScores(this.playerId, this.selectedSeasonId).subscribe(scores => {
      this.scores.set(scores);
    });
  }

  priceChartData() {
    const h = this.history();
    return {
      labels: h.map(s => `G${s.match_day}`),
      datasets: [
        {
          label: 'Quotazione',
          data: h.map(s => s.price),
          borderColor: '#3fb950',
          backgroundColor: 'rgba(63,185,80,.15)',
          tension: 0.3,
          fill: true,
        },
      ],
    };
  }
}
