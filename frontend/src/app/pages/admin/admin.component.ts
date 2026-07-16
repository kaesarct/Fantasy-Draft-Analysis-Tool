import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { InputTextModule } from 'primeng/inputtext';
import { DropdownModule } from 'primeng/dropdown';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [CommonModule, FormsModule, InputTextModule, DropdownModule, ButtonModule, CheckboxModule],
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <h1 class="page-title">⚙️ Amministrazione</h1>
        <p class="text-secondary">Allenatori e associazioni con le fantasquadre</p>
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

      <!-- Allenatori -->
      <div class="section-title">👤 Allenatori</div>
      <div class="card mb-4 coach-panel">
        <div class="coach-form">
          <input pInputText placeholder="Username" [(ngModel)]="newUsername" />
          <input pInputText placeholder="Nome visualizzato" [(ngModel)]="newDisplayName" />
          <input pInputText placeholder="Email (opzionale)" [(ngModel)]="newEmail" />
          <button
            pButton
            label="Crea allenatore"
            icon="pi pi-user-plus"
            [loading]="creating()"
            [disabled]="!newUsername.trim() || !newDisplayName.trim()"
            (click)="createAllenatore()"
          ></button>
        </div>
        <div class="coach-list">
          @for (a of allenatori(); track a.id) {
            <div class="coach-chip" [class.inactive]="!a.is_active">
              <span class="coach-name">{{ a.display_name }}</span>
              <span class="text-muted">{{ '@' + a.username }}</span>
              <button class="chip-btn" (click)="toggleActive(a)" [title]="a.is_active ? 'Disattiva' : 'Riattiva'">
                {{ a.is_active ? '🟢' : '⚪' }}
              </button>
            </div>
          }
          @empty {
            <p class="text-muted">Nessun allenatore: creane uno per iniziare.</p>
          }
        </div>
      </div>

      <!-- Associazioni -->
      <div class="section-title">🔗 Associazioni squadra → allenatore</div>
      <div class="filters-bar card mb-4">
        <p-dropdown
          [options]="seasonOptions()"
          [(ngModel)]="selectedSeasonId"
          placeholder="Stagione"
          (ngModelChange)="loadTeams()"
          styleClass="filter-drop"
        />
        <span class="text-muted" style="font-size:12px">{{ teams().length }} squadre</span>
      </div>

      @if (selectedSeasonId) {
        <div class="team-table card">
          @for (t of teams(); track t.id) {
            <div class="team-row">
              <div class="team-info">
                <span class="team-name">{{ t.name }}</span>
                <div class="coaches">
                  @for (c of t.coaches; track c.id) {
                    <span class="assigned-chip" [class.primary]="c.primary">
                      {{ c.primary ? '⭐' : '' }}{{ c.name }}
                      <button class="chip-btn" title="Rimuovi" (click)="removeCoach(t, c)">×</button>
                    </span>
                  }
                  @empty {
                    <span class="text-muted" style="font-size:12px">nessun allenatore</span>
                  }
                </div>
              </div>
              <div class="assign-controls">
                <p-dropdown
                  [options]="activeAllenatoriOptions()"
                  [(ngModel)]="t._selectedCoach"
                  placeholder="Allenatore"
                  [filter]="true"
                  styleClass="assign-drop"
                  appendTo="body"
                />
                <label class="primary-check">
                  <p-checkbox [(ngModel)]="t._isPrimary" [binary]="true" /> primario
                </label>
                <button
                  pButton
                  label="Assegna"
                  size="small"
                  [disabled]="!t._selectedCoach"
                  (click)="assignCoach(t)"
                ></button>
              </div>
            </div>
          }
          @empty {
            <p class="text-muted" style="padding:20px;">Nessuna squadra per questa stagione.</p>
          }
        </div>
      }

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
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1280px; margin: 0 auto; }
    .page-header { margin-bottom: 24px; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; }
    .section-title { font-weight: 700; margin-bottom: 10px; }

    .status-msg { padding: 12px 16px; font-size: 13px; }
    .status-msg.error { color: var(--text-negative, #e05260); }

    .coach-panel { padding: 16px; }
    .coach-form { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }
    .coach-form input { flex: 1; min-width: 160px; }
    .coach-list { display: flex; flex-wrap: wrap; gap: 8px; }
    .coach-chip {
      display: inline-flex; align-items: center; gap: 6px;
      background: var(--bg-elevated); border: 1px solid var(--border-color);
      border-radius: 999px; padding: 5px 12px; font-size: 13px;
    }
    .coach-chip.inactive { opacity: 0.55; }
    .coach-name { font-weight: 600; }

    .filters-bar { display: flex; align-items: center; gap: 12px; padding: 14px 16px; }
    .filter-drop { min-width: 160px; }

    .sync-panel { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
    .sync-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .matchday-input { width: 170px; }
    .refresh-btn { background: none; border: none; cursor: pointer; padding: 0 0 0 4px; font-size: 12px; }

    .team-table { padding: 0; overflow: visible; }
    .team-row {
      display: flex; align-items: center; justify-content: space-between; gap: 16px;
      padding: 12px 16px; border-bottom: 1px solid var(--border-subtle); flex-wrap: wrap;
    }
    .team-row:last-child { border-bottom: none; }
    .team-info { flex: 1; min-width: 220px; }
    .team-name { font-weight: 700; font-size: 14px; display: block; margin-bottom: 4px; }
    .coaches { display: flex; flex-wrap: wrap; gap: 6px; }
    .assigned-chip {
      display: inline-flex; align-items: center; gap: 4px;
      background: var(--bg-elevated); border: 1px solid var(--border-color);
      border-radius: 999px; padding: 2px 10px; font-size: 12px;
    }
    .assigned-chip.primary { border-color: var(--accent-green); }
    .chip-btn {
      background: none; border: none; cursor: pointer; color: var(--text-muted);
      font-size: 13px; padding: 0 2px; line-height: 1;
    }
    .chip-btn:hover { color: var(--text-negative, #e05260); }

    .assign-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .assign-drop { min-width: 180px; }
    .primary-check { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); }
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
  `],
})
export class AdminComponent implements OnInit {
  allenatori = signal<any[]>([]);
  seasonOptions = signal<any[]>([]);
  currentSeasonId = signal<number | null>(null);
  currentSeasonLabel = signal<string | null>(null);
  detectedMatchDay = signal<number | null>(null);
  teams = signal<any[]>([]);
  creating = signal(false);
  settingCurrent = signal(false);
  syncingPrices = signal(false);
  syncingVotes = signal(false);
  checkingRecovery = signal(false);
  message = signal('');
  messageIsError = signal(false);

  mergeCandidates = signal<any[]>([]);
  loadingMergeCandidates = signal(false);
  mergingKey = signal<string | null>(null);

  newUsername = '';
  newDisplayName = '';
  newEmail = '';
  selectedSeasonId: number | null = null;
  syncSeasonId: number | null = null;
  syncMatchDay: number | null = null;

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.loadAllenatori();
    this.loadSeasons();
    this.loadDetectedMatchday();
    this.loadMergeCandidates();
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

  activeAllenatoriOptions() {
    return this.allenatori()
      .filter(a => a.is_active)
      .map(a => ({ label: a.display_name, value: a.id }));
  }

  loadAllenatori() {
    this.api.getAllenatori().subscribe({ next: d => this.allenatori.set(d) });
  }

  loadTeams() {
    if (!this.selectedSeasonId) return;
    this.api.getFantaTeams(this.selectedSeasonId).subscribe({
      next: teams => this.teams.set(
        teams
          .sort((a, b) => a.name.localeCompare(b.name))
          .map(t => ({ ...t, _selectedCoach: null, _isPrimary: true }))
      ),
      error: () => this.setMessage('Errore nel caricamento delle squadre.', true),
    });
  }

  createAllenatore() {
    this.creating.set(true);
    this.api.createAllenatore({
      username: this.newUsername.trim(),
      display_name: this.newDisplayName.trim(),
      email: this.newEmail.trim() || undefined,
    }).subscribe({
      next: res => {
        this.creating.set(false);
        this.setMessage(`Allenatore "${res.display_name}" creato.`, false);
        this.newUsername = this.newDisplayName = this.newEmail = '';
        this.loadAllenatori();
      },
      error: err => {
        this.creating.set(false);
        this.setMessage(err.error?.detail || 'Errore nella creazione.', true);
      },
    });
  }

  toggleActive(a: any) {
    this.api.updateAllenatore(a.id, { is_active: !a.is_active }).subscribe({
      next: () => this.loadAllenatori(),
      error: err => this.setMessage(err.error?.detail || 'Errore aggiornamento.', true),
    });
  }

  assignCoach(team: any) {
    this.api.assignCoach(team.id, team._selectedCoach, team._isPrimary).subscribe({
      next: () => {
        this.setMessage(`Allenatore assegnato a ${team.name}.`, false);
        this.loadTeams();
      },
      error: err => this.setMessage(err.error?.detail || 'Errore assegnazione.', true),
    });
  }

  removeCoach(team: any, coach: any) {
    this.api.removeCoach(team.id, coach.id).subscribe({
      next: () => {
        this.setMessage(`${coach.name} rimosso da ${team.name}.`, false);
        this.loadTeams();
      },
      error: err => this.setMessage(err.error?.detail || 'Errore rimozione.', true),
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
