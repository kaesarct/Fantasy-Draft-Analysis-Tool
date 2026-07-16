import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { InputTextModule } from 'primeng/inputtext';
import { DropdownModule } from 'primeng/dropdown';
import { ButtonModule } from 'primeng/button';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, InputTextModule, DropdownModule, ButtonModule],
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <h1 class="page-title">⚙️ Amministrazione</h1>
        <p class="text-secondary">Sincronizzazione dati e strumenti di manutenzione</p>
        <a routerLink="/admin/squadre" class="section-link">🛡️ Gestione Squadre (allenatori, associazioni, coppe) →</a>
      </div>

      @if (message()) {
        <div class="card mb-4 status-msg" [class.error]="messageIsError()">{{ message() }}</div>
      }

      <!-- Stagione e sincronizzazione -->
      <div class="section-title">🗓️ Stagione e sincronizzazione</div>
      <div class="card mb-4 sync-panel">
        <div class="sync-row">
          <p-dropdown
            [options]="seasonOptions()"
            [(ngModel)]="syncSeasonId"
            placeholder="Stagione"
            styleClass="filter-drop"
          />
          @if (syncSeasonId && syncSeasonId === currentSeasonId()) {
            <span class="badge badge-green">✓ è la stagione corrente</span>
          } @else {
            <span class="text-muted" style="font-size:12px">
              Corrente: {{ currentSeasonLabel() ?? 'nessuna' }}
            </span>
            <button
              pButton
              label="Imposta come corrente"
              size="small"
              class="p-button-outlined"
              [disabled]="!syncSeasonId"
              [loading]="settingCurrent()"
              (click)="setCurrentSeason()"
            ></button>
          }
        </div>
        <div class="sync-row">
          <input
            pInputText
            type="number"
            placeholder="Giornata (vuoto = auto)"
            [(ngModel)]="syncMatchDay"
            class="matchday-input"
          />
          <span class="text-muted" style="font-size:12px">
            Rilevata automaticamente da fantacalcio.it: <strong>{{ detectedMatchDay() ?? '…' }}</strong>
            <button class="refresh-btn" title="Aggiorna" (click)="loadDetectedMatchday()">🔄</button>
          </span>
        </div>
        <div class="sync-row">
          <button pButton label="Sync quotazioni" size="small" [disabled]="!syncSeasonId" [loading]="syncingPrices()" (click)="runSyncPrices()"></button>
          <button pButton label="Sync voti" size="small" [disabled]="!syncSeasonId" [loading]="syncingVotes()" (click)="runSyncVotes()"></button>
          <button pButton label="Verifica recupero" size="small" [disabled]="!syncSeasonId" [loading]="checkingRecovery()" (click)="runCheckRecovery()"></button>
        </div>
        <p class="text-muted" style="font-size:12px; margin: 0;">
          Il campo "Giornata" è vuoto per default: se lo lasci vuoto viene usata la giornata rilevata automaticamente (mostrata sopra).
          A inizio stagione può risultare 0 (nessuna giornata ancora giocata): se una sincronizzazione fallisce, inseriscila qui a mano.
        </p>
      </div>

      <!-- Merge giocatori duplicati -->
      <div class="section-title">🧩 Giocatori simili da verificare</div>
      <div class="card mb-4 merge-panel">
        <div class="merge-toolbar">
          <button
            pButton
            label="Ricontrolla"
            size="small"
            class="p-button-outlined"
            [loading]="loadingMergeCandidates()"
            (click)="loadMergeCandidates()"
          ></button>
          <span class="text-muted" style="font-size:12px">{{ mergeCandidates().length }} coppie trovate</span>
        </div>
        @for (pair of mergeCandidates(); track pairKey(pair)) {
          <div class="merge-pair">
            @for (p of [pair.player_a, pair.player_b]; track p.id) {
              <div class="merge-row" [class.empty-row]="!p.fanta_id">
                <span class="merge-name">{{ p.name }}</span>
                @if (p.roles?.length) {
                  <span class="role-badge role-{{ p.roles[0] }}">{{ p.roles.join('/') }}</span>
                }
                @if (!p.fanta_id) {
                  <span class="badge badge-red" style="font-size:10px">vuoto</span>
                }
                <span class="text-muted merge-stats">
                  {{ p.price_min ?? '—' }}–{{ p.price_max ?? '—' }} ·
                  FVM {{ p.fvm_min ?? '—' }}–{{ p.fvm_max ?? '—' }} ·
                  Diff {{ p.diff_min ?? '—' }}/{{ p.diff_max ?? '—' }}
                </span>
                <button
                  pButton
                  size="small"
                  label="Unisci qui"
                  [loading]="mergingKey() === pairKey(pair)"
                  (click)="mergeInto(p, pair)"
                ></button>
              </div>
            }
            <button class="dismiss-btn" (click)="dismissPair(pair)">Rifiuta — non è la stessa persona</button>
          </div>
        }
        @empty {
          @if (!loadingMergeCandidates()) {
            <p class="text-muted" style="padding:20px;">Nessuna coppia sospetta trovata.</p>
          }
        }
      </div>

      <!-- Merge manuale -->
      <div class="section-title">🔍 Unisci manualmente</div>
      <div class="card mb-4 merge-panel">
        <p class="text-muted" style="padding:14px 16px 0; font-size:12px; margin:0;">
          Per i casi che il ricontrollo automatico non trova perché il cambio nome è troppo diverso.
        </p>
        <div class="manual-pick">
          <p-dropdown
            [options]="allPlayersOptions()"
            [(ngModel)]="manualPlayerAId"
            placeholder="Cerca primo giocatore..."
            [filter]="true"
            filterBy="label"
            [showClear]="true"
            appendTo="body"
            styleClass="manual-drop"
          />
          <span class="text-muted">+</span>
          <p-dropdown
            [options]="allPlayersOptions()"
            [(ngModel)]="manualPlayerBId"
            placeholder="Cerca secondo giocatore..."
            [filter]="true"
            filterBy="label"
            [showClear]="true"
            appendTo="body"
            styleClass="manual-drop"
          />
        </div>
        @if (manualPair(); as pair) {
          <div class="merge-pair">
            @for (p of [pair.player_a, pair.player_b]; track p.id) {
              <div class="merge-row" [class.empty-row]="!p.fanta_id">
                <span class="merge-name">{{ p.name }}</span>
                @if (p.roles?.length) {
                  <span class="role-badge role-{{ p.roles[0] }}">{{ p.roles.join('/') }}</span>
                }
                @if (!p.fanta_id) {
                  <span class="badge badge-red" style="font-size:10px">vuoto</span>
                }
                <span class="text-muted merge-stats">
                  {{ p.price_min ?? '—' }}–{{ p.price_max ?? '—' }} ·
                  FVM {{ p.fvm_min ?? '—' }}–{{ p.fvm_max ?? '—' }} ·
                  Diff {{ p.diff_min ?? '—' }}/{{ p.diff_max ?? '—' }}
                </span>
                <button
                  pButton
                  size="small"
                  label="Unisci qui"
                  [loading]="mergingKey() === pairKey(pair)"
                  (click)="mergeManualInto(p, pair)"
                ></button>
              </div>
            }
          </div>
        } @else if (manualPlayerAId && manualPlayerBId) {
          <p class="text-muted" style="padding:10px 16px;">Seleziona due giocatori diversi.</p>
        }
      </div>
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1280px; margin: 0 auto; }
    .page-header { margin-bottom: 24px; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; }
    .section-title { font-weight: 700; margin-bottom: 10px; }

    .status-msg { padding: 12px 16px; font-size: 13px; }
    .status-msg.error { color: var(--text-negative, #e05260); }

    .section-link { display: inline-block; margin-top: 6px; font-size: 13px; font-weight: 600; text-decoration: none; }
    .section-link:hover { text-decoration: underline; }

    .filter-drop { min-width: 160px; }

    .sync-panel { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
    .sync-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .matchday-input { width: 170px; }
    .refresh-btn { background: none; border: none; cursor: pointer; padding: 0 0 0 4px; font-size: 12px; }

    .mb-4 { margin-bottom: 24px; }

    .merge-panel { padding: 0; }
    .merge-toolbar { display: flex; align-items: center; gap: 10px; padding: 14px 16px; border-bottom: 1px solid var(--border-subtle); }
    .merge-pair { padding: 10px 16px; border-bottom: 1px solid var(--border-subtle); }
    .merge-pair:last-child { border-bottom: none; }
    .merge-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; flex-wrap: wrap; }
    .merge-row.empty-row { opacity: 0.6; }
    .merge-name { font-weight: 600; font-size: 13px; min-width: 140px; }
    .merge-stats { font-size: 12px; flex: 1; min-width: 200px; }
    .dismiss-btn {
      background: none; border: none; cursor: pointer; color: var(--text-muted);
      font-size: 12px; padding: 4px 0 0; text-decoration: underline;
    }
    .dismiss-btn:hover { color: var(--text-negative, #e05260); }

    .manual-pick { display: flex; align-items: center; gap: 10px; padding: 14px 16px; flex-wrap: wrap; }
    .manual-drop { min-width: 220px; }
  `],
})
export class AdminComponent implements OnInit {
  seasonOptions = signal<any[]>([]);
  currentSeasonId = signal<number | null>(null);
  currentSeasonLabel = signal<string | null>(null);
  detectedMatchDay = signal<number | null>(null);
  settingCurrent = signal(false);
  syncingPrices = signal(false);
  syncingVotes = signal(false);
  checkingRecovery = signal(false);
  message = signal('');
  messageIsError = signal(false);

  mergeCandidates = signal<any[]>([]);
  loadingMergeCandidates = signal(false);
  mergingKey = signal<string | null>(null);
  allPlayersForMerge = signal<any[]>([]);

  syncSeasonId: number | null = null;
  syncMatchDay: number | null = null;
  manualPlayerAId: number | null = null;
  manualPlayerBId: number | null = null;

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.loadSeasons();
    this.loadDetectedMatchday();
    this.loadMergeCandidates();
    this.loadAllPlayersForMerge();
  }

  loadSeasons() {
    this.api.getSeasons().subscribe({
      next: seasons => {
        this.seasonOptions.set(seasons.map(s => ({ label: s.label, value: s.id })));
        const current = seasons.find(s => s.is_current);
        this.currentSeasonId.set(current ? current.id : null);
        this.currentSeasonLabel.set(current ? current.label : null);
        if (!this.syncSeasonId && current) {
          this.syncSeasonId = current.id;
        }
      },
    });
  }

  loadDetectedMatchday() {
    this.api.getLastMatchday().subscribe({
      next: res => this.detectedMatchDay.set(res.match_day),
      error: () => this.detectedMatchDay.set(null),
    });
  }

  setCurrentSeason() {
    if (!this.syncSeasonId) return;
    this.settingCurrent.set(true);
    this.api.setCurrentSeason(this.syncSeasonId).subscribe({
      next: res => {
        this.settingCurrent.set(false);
        this.setMessage(`Stagione corrente impostata su "${res.label}".`, false);
        this.loadSeasons();
      },
      error: err => {
        this.settingCurrent.set(false);
        this.setMessage(err.error?.detail || 'Errore impostazione stagione corrente.', true);
      },
    });
  }

  runSyncPrices() {
    if (!this.syncSeasonId) return;
    this.syncingPrices.set(true);
    this.api.syncPrices(this.syncSeasonId).subscribe({
      next: res => {
        this.syncingPrices.set(false);
        if (res.ok) {
          this.setMessage(`Quotazioni: ${res.created} nuovi, ${res.updated} aggiornati (giornata ${res.match_day}).`, false);
        } else {
          this.setMessage(res.message || 'Sync quotazioni fallito.', true);
        }
      },
      error: err => {
        this.syncingPrices.set(false);
        this.setMessage(err.error?.detail || 'Errore durante il sync quotazioni.', true);
      },
    });
  }

  runSyncVotes() {
    if (!this.syncSeasonId) return;
    this.syncingVotes.set(true);
    this.api.syncVotes(this.syncSeasonId, this.syncMatchDay ?? undefined).subscribe({
      next: res => {
        this.syncingVotes.set(false);
        if (res.ok) {
          this.setMessage(`Voti: ${res.saved} salvati (giornata ${res.match_day}).`, false);
        } else {
          this.setMessage(res.message || 'Sync voti fallito.', true);
        }
      },
      error: err => {
        this.syncingVotes.set(false);
        this.setMessage(err.error?.detail || 'Errore durante il sync voti.', true);
      },
    });
  }

  runCheckRecovery() {
    if (!this.syncSeasonId) return;
    this.checkingRecovery.set(true);
    this.api.checkInjuryRecovery(this.syncSeasonId, this.syncMatchDay ?? undefined).subscribe({
      next: res => {
        this.checkingRecovery.set(false);
        const names = res.returned?.map((p: any) => p.player_name).join(', ');
        this.setMessage(
          res.returned?.length
            ? `Giornata ${res.match_day} — rientrati: ${names}.`
            : `Giornata ${res.match_day} — nessun rientro.`,
          false,
        );
      },
      error: err => {
        this.checkingRecovery.set(false);
        this.setMessage(err.error?.detail || 'Errore durante la verifica dei recuperi.', true);
      },
    });
  }

  loadMergeCandidates() {
    this.loadingMergeCandidates.set(true);
    this.api.getPlayerMergeCandidates().subscribe({
      next: pairs => {
        this.mergeCandidates.set(pairs);
        this.loadingMergeCandidates.set(false);
      },
      error: err => {
        this.loadingMergeCandidates.set(false);
        this.setMessage(err.error?.detail || 'Errore nel ricontrollo dei duplicati.', true);
      },
    });
  }

  pairKey(pair: any): string {
    return `${pair.player_a.id}-${pair.player_b.id}`;
  }

  mergeInto(keep: any, pair: any) {
    const remove = pair.player_a.id === keep.id ? pair.player_b : pair.player_a;
    this.mergingKey.set(this.pairKey(pair));
    this.api.mergePlayers(keep.id, remove.id).subscribe({
      next: res => {
        this.mergingKey.set(null);
        if (res.merged) {
          this.setMessage(`"${remove.name}" unito a "${keep.name}".`, false);
        } else {
          this.setMessage(
            `Merge parziale: alcuni dati non ricollegati per conflitto (${JSON.stringify(res.conflicts)}). Non ho eliminato "${remove.name}".`,
            true,
          );
        }
        this.loadMergeCandidates();
      },
      error: err => {
        this.mergingKey.set(null);
        this.setMessage(err.error?.detail || 'Errore durante il merge.', true);
      },
    });
  }

  loadAllPlayersForMerge() {
    this.api.getPlayers().subscribe({ next: players => this.allPlayersForMerge.set(players) });
  }

  allPlayersOptions() {
    return this.allPlayersForMerge().map(p => ({ label: p.name, value: p.id }));
  }

  manualPair(): { player_a: any; player_b: any } | null {
    if (!this.manualPlayerAId || !this.manualPlayerBId || this.manualPlayerAId === this.manualPlayerBId) {
      return null;
    }
    const a = this.allPlayersForMerge().find(p => p.id === this.manualPlayerAId);
    const b = this.allPlayersForMerge().find(p => p.id === this.manualPlayerBId);
    return a && b ? { player_a: a, player_b: b } : null;
  }

  mergeManualInto(keep: any, pair: any) {
    const remove = pair.player_a.id === keep.id ? pair.player_b : pair.player_a;
    this.mergingKey.set(this.pairKey(pair));
    this.api.mergePlayers(keep.id, remove.id).subscribe({
      next: res => {
        this.mergingKey.set(null);
        if (res.merged) {
          this.setMessage(`"${remove.name}" unito a "${keep.name}".`, false);
          this.manualPlayerAId = null;
          this.manualPlayerBId = null;
          this.loadAllPlayersForMerge();
        } else {
          this.setMessage(
            `Merge parziale: alcuni dati non ricollegati per conflitto (${JSON.stringify(res.conflicts)}). Non ho eliminato "${remove.name}".`,
            true,
          );
        }
        this.loadMergeCandidates();
      },
      error: err => {
        this.mergingKey.set(null);
        this.setMessage(err.error?.detail || 'Errore durante il merge.', true);
      },
    });
  }

  dismissPair(pair: any) {
    this.api.dismissPlayerMerge(pair.player_a.id, pair.player_b.id).subscribe({
      next: () => {
        this.mergeCandidates.set(this.mergeCandidates().filter(p => this.pairKey(p) !== this.pairKey(pair)));
        this.setMessage('Coppia rifiutata: non verrà più suggerita.', false);
      },
      error: err => this.setMessage(err.error?.detail || 'Errore nel rifiuto.', true),
    });
  }

  private setMessage(text: string, isError: boolean) {
    this.message.set(text);
    this.messageIsError.set(isError);
  }
}
