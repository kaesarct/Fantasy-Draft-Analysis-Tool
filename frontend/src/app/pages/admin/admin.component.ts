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
        </div>
        <div class="sync-row">
          <input
            pInputText
            type="number"
            placeholder="Giornata (vuoto = auto)"
            [(ngModel)]="syncMatchDay"
            class="matchday-input"
          />
          <button pButton label="Sync quotazioni" size="small" [disabled]="!syncSeasonId" [loading]="syncingPrices()" (click)="runSyncPrices()"></button>
          <button pButton label="Sync voti" size="small" [disabled]="!syncSeasonId" [loading]="syncingVotes()" (click)="runSyncVotes()"></button>
          <button pButton label="Verifica recupero" size="small" [disabled]="!syncSeasonId" [loading]="checkingRecovery()" (click)="runCheckRecovery()"></button>
        </div>
        <p class="text-muted" style="font-size:12px; margin: 0;">
          La giornata viene stimata automaticamente da fantacalcio.it e a inizio stagione può risultare 0 (nessuna giornata giocata):
          se una sincronizzazione fallisce, indicala qui manualmente.
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
  `],
})
export class AdminComponent implements OnInit {
  allenatori = signal<any[]>([]);
  seasonOptions = signal<any[]>([]);
  currentSeasonLabel = signal<string | null>(null);
  teams = signal<any[]>([]);
  creating = signal(false);
  settingCurrent = signal(false);
  syncingPrices = signal(false);
  syncingVotes = signal(false);
  checkingRecovery = signal(false);
  message = signal('');
  messageIsError = signal(false);

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
  }

  loadSeasons() {
    this.api.getSeasons().subscribe({
      next: seasons => {
        this.seasonOptions.set(seasons.map(s => ({ label: s.label, value: s.id })));
        const current = seasons.find(s => s.is_current);
        this.currentSeasonLabel.set(current ? current.label : null);
      },
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

  private setMessage(text: string, isError: boolean) {
    this.message.set(text);
    this.messageIsError.set(isError);
  }
}
