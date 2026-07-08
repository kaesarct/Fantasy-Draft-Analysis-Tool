import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { CardModule } from 'primeng/card';
import { TagModule } from 'primeng/tag';
import { ButtonModule } from 'primeng/button';
import { SkeletonModule } from 'primeng/skeleton';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, RouterLink, CardModule, TagModule, ButtonModule, SkeletonModule],
  template: `
    <div class="page-container fade-up">
      <!-- Hero -->
      <div class="hero-card hero-gradient card mb-4">
        <div class="hero-layout">
          <div>
            <div class="hero-badge badge badge-gold mb-2">🏆 Lega Tamarros</div>
            <h1 class="hero-title">Fantacalcio Platform</h1>
            <p class="hero-sub text-secondary">
              Dashboard della stagione corrente · 24 squadre · Gold / Bronze / Carbon / Silver
            </p>
          </div>
          <div class="hero-actions">
            <button class="btn-primary" routerLink="/league">Classifica</button>
            <button class="btn-outline" routerLink="/players">Giocatori</button>
          </div>
        </div>
      </div>

      <!-- Quick stats -->
      <div class="stats-grid mb-4">
        @for (stat of quickStats(); track stat.label) {
          <div class="stat-card">
            <div class="stat-icon">{{ stat.icon }}</div>
            <div class="stat-value">{{ stat.value ?? '—' }}</div>
            <div class="stat-label text-muted">{{ stat.label }}</div>
          </div>
        }
      </div>

      <!-- Sync -->
      <div class="section-title">🔄 Sincronizzazione dati</div>
      <div class="sync-bar card mb-4">
        <button
          pButton
          label="Sync quotazioni"
          icon="pi pi-euro"
          [loading]="syncingPrices()"
          [disabled]="!currentSeasonId() || syncingVotes()"
          (click)="runSyncPrices()"
        ></button>
        <button
          pButton
          severity="secondary"
          label="Sync voti"
          icon="pi pi-star"
          [loading]="syncingVotes()"
          [disabled]="!currentSeasonId() || syncingPrices()"
          (click)="runSyncVotes()"
        ></button>
        @if (!currentSeasonId()) {
          <span class="text-muted" style="font-size:12px">Nessuna stagione corrente configurata</span>
        }
        @if (syncMessage()) {
          <span class="sync-msg" [class.error]="syncIsError()">{{ syncMessage() }}</span>
        }
      </div>

      <!-- Next matches -->
      <div class="section-title">📅 Prossima giornata Serie A</div>
      @if (loadingMatches()) {
        <div class="matches-grid">
          @for (i of [1,2,3,4]; track i) {
            <p-skeleton height="80px" styleClass="mb-2" />
          }
        </div>
      } @else {
        <div class="matches-grid">
          @for (m of matches(); track m.home_team) {
            <div class="match-card" [class.played]="m.is_played">
              <span class="match-team">{{ m.home_team }}</span>
              <span class="match-score">{{ m.score || 'vs' }}</span>
              <span class="match-team">{{ m.away_team }}</span>
            </div>
          }
          @empty {
            <p class="text-muted">Nessuna partita trovata.</p>
          }
        </div>
      }

      <!-- Injury summary -->
      <div class="section-title mt-4">🏥 Ultimi infortuni</div>
      @if (injuries().length) {
        <div class="injuries-list">
          @for (inj of injuries().slice(0, 6); track inj.id) {
            <div class="injury-chip">
              <span class="injury-name">{{ inj.player_name ?? 'Giocatore #' + inj.player_id }}</span>
              @if (inj.qualifies_for_temp_sub) {
                <span class="badge badge-red" title="Sostituzione temporanea disponibile">≥8 sett.</span>
              }
              @if (inj.expected_return) {
                <span class="text-muted" style="font-size:11px">rientro: {{ inj.expected_return }}</span>
              }
            </div>
          }
        </div>
      } @else {
        <p class="text-muted">Nessun giocatore infortunato.</p>
      }
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1280px; margin: 0 auto; }

    .hero-card { padding: 28px 32px; }
    .hero-layout { display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap; }
    .hero-badge { margin-bottom: 8px; display: inline-block; }
    .hero-title { font-size: 28px; font-weight: 800; letter-spacing: -0.03em; margin-bottom: 6px; }
    .hero-sub { font-size: 14px; }
    .hero-actions { display: flex; gap: 10px; flex-shrink: 0; }

    .btn-primary {
      background: var(--accent-green); color: #fff; border: none;
      padding: 9px 20px; border-radius: var(--radius-sm); font-weight: 600; cursor: pointer;
      transition: opacity var(--transition);
    }
    .btn-primary:hover { opacity: 0.85; }
    .btn-outline {
      background: transparent; color: var(--text-primary);
      border: 1px solid var(--border-color);
      padding: 9px 20px; border-radius: var(--radius-sm); font-weight: 600; cursor: pointer;
      transition: border-color var(--transition);
    }
    .btn-outline:hover { border-color: var(--accent-blue); }

    .sync-bar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 14px 16px; }
    .sync-msg { font-size: 13px; }
    .sync-msg.error { color: var(--text-negative, #e05260); }

    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; }
    .stat-card { text-align: center; }
    .stat-icon { font-size: 24px; margin-bottom: 8px; }
    .stat-value { font-size: 28px; font-weight: 800; color: var(--accent-green); }
    .stat-label { font-size: 12px; margin-top: 4px; }

    .matches-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
    .match-card {
      background: var(--bg-card); border: 1px solid var(--border-color);
      border-radius: var(--radius-md); padding: 14px 20px;
      display: flex; align-items: center; justify-content: space-between;
      font-size: 13px; font-weight: 600; transition: border-color var(--transition);
    }
    .match-card:hover { border-color: var(--accent-blue); }
    .match-card.played { opacity: 0.6; }
    .match-score {
      padding: 4px 12px; background: var(--bg-elevated);
      border-radius: var(--radius-sm); font-size: 12px;
    }

    .injuries-list { display: flex; flex-wrap: wrap; gap: 10px; }
    .injury-chip {
      display: flex; align-items: center; gap: 8px;
      background: var(--bg-card); border: 1px solid var(--border-color);
      border-radius: 8px; padding: 8px 14px; font-size: 13px;
    }
    .injury-name { font-weight: 600; }
    .mt-4 { margin-top: 24px; }
    .mb-2 { margin-bottom: 8px; }
    .mb-4 { margin-bottom: 24px; }
  `],
})
export class DashboardComponent implements OnInit {
  matches = signal<any[]>([]);
  injuries = signal<any[]>([]);
  loadingMatches = signal(true);
  currentSeasonId = signal<number | null>(null);
  syncingPrices = signal(false);
  syncingVotes = signal(false);
  syncMessage = signal('');
  syncIsError = signal(false);

  quickStats = signal([
    { icon: '🛡️',  label: 'Squadre totali',   value: 24 },
    { icon: '⚽',  label: 'Leghe attive',      value: 3 },
    { icon: '🏥',  label: 'Infortuni attivi',  value: null },
    { icon: '📅',  label: 'Giornata corrente', value: null },
  ]);

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.getNextMatches().subscribe({
      next: data => { this.matches.set(data); this.loadingMatches.set(false); },
      error: ()  => this.loadingMatches.set(false),
    });
    this.api.getInjuries().subscribe({
      next: data => {
        this.injuries.set(data);
        this.quickStats.update(s =>
          s.map(x => x.label === 'Infortuni attivi' ? { ...x, value: data.length } : x)
        );
      },
    });
    this.api.getSeasons().subscribe({
      next: seasons => {
        const current = seasons.find(s => s.is_current);
        this.currentSeasonId.set(current ? current.id : null);
      },
    });
  }

  runSyncPrices() {
    const seasonId = this.currentSeasonId();
    if (!seasonId) return;
    this.syncingPrices.set(true);
    this.syncMessage.set('');
    this.api.syncPrices(seasonId).subscribe({
      next: res => {
        this.syncingPrices.set(false);
        if (res.ok) {
          this.setSyncMessage(
            `Quotazioni: ${res.created} nuovi, ${res.updated} aggiornati (giornata ${res.match_day}).`, false
          );
        } else {
          this.setSyncMessage(res.message || 'Sync quotazioni fallito.', true);
        }
      },
      error: err => {
        this.syncingPrices.set(false);
        this.setSyncMessage(err.error?.detail || 'Errore durante il sync quotazioni.', true);
      },
    });
  }

  runSyncVotes() {
    const seasonId = this.currentSeasonId();
    if (!seasonId) return;
    this.syncingVotes.set(true);
    this.syncMessage.set('');
    this.api.syncVotes(seasonId).subscribe({
      next: res => {
        this.syncingVotes.set(false);
        if (res.ok) {
          this.setSyncMessage(`Voti: ${res.saved} salvati (giornata ${res.match_day}).`, false);
        } else {
          this.setSyncMessage(res.message || 'Sync voti fallito.', true);
        }
      },
      error: err => {
        this.syncingVotes.set(false);
        this.setSyncMessage(err.error?.detail || 'Errore durante il sync voti.', true);
      },
    });
  }

  private setSyncMessage(text: string, isError: boolean) {
    this.syncMessage.set(text);
    this.syncIsError.set(isError);
  }
}
