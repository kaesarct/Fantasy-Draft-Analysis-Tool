import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { InputTextModule } from 'primeng/inputtext';
import { DropdownModule } from 'primeng/dropdown';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { DragDropModule } from 'primeng/dragdrop';
import { ApiService } from '../../core/services/api.service';

// Gold/Bronze/Carbon hanno l'iscrizione automatica tramite FantaTeam.league_id:
// tutte le altre competizioni (Silver, coppe...) vanno iscritte a mano qui.
const MAIN_LEAGUE_TYPES = ['GOLD', 'BRONZE', 'CARBON'];

@Component({
  selector: 'app-admin-teams',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, InputTextModule, DropdownModule, ButtonModule, CheckboxModule, DragDropModule],
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <a routerLink="/admin" class="back-link">← Admin</a>
        <h1 class="page-title">🛡️ Gestione Squadre</h1>
        <p class="text-secondary">Allenatori, associazioni, anagrafica squadre e iscrizione alle coppe</p>
      </div>

      @if (message()) {
        <div class="card mb-4 status-msg" [class.error]="messageIsError()">{{ message() }}</div>
      }

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

      <!-- Selettore stagione condiviso dalle sezioni sotto -->
      <div class="filters-bar card mb-4">
        <p-dropdown
          [options]="seasonOptions()"
          [(ngModel)]="selectedSeasonId"
          placeholder="Stagione"
          (ngModelChange)="onSeasonChange()"
          styleClass="filter-drop"
        />
        <span class="text-muted" style="font-size:12px">{{ teams().length }} squadre</span>
      </div>

      @if (selectedSeasonId) {
        <!-- Associazioni -->
        <div class="section-title">🔗 Associazioni squadra → allenatore ({{ teams().length }})</div>
        <div class="team-table card mb-4">
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

        <!-- Gestione squadre -->
        <div class="section-title">🛡️ Gestione squadre ({{ teams().length }})</div>
        <div class="team-table card mb-4">
          @for (t of teams(); track t.id) {
            <div class="team-row">
              <div class="team-info team-mgmt-info">
                <input pInputText class="team-name-input" [(ngModel)]="t._editName" />
                <p-dropdown
                  [options]="leagueOptions()"
                  [(ngModel)]="t._editLeagueId"
                  styleClass="filter-drop"
                  appendTo="body"
                />
              </div>
              <div class="assign-controls">
                <button
                  pButton
                  label="Salva"
                  size="small"
                  class="p-button-outlined"
                  [loading]="savingTeamId() === t.id"
                  [disabled]="t._editName === t.name && t._editLeagueId === t.league_id"
                  (click)="saveTeam(t)"
                ></button>
                <button
                  pButton
                  label="Elimina"
                  size="small"
                  class="p-button-outlined delete-btn"
                  [loading]="deletingTeamId() === t.id"
                  (click)="deleteTeam(t)"
                ></button>
              </div>
            </div>
          }
          @empty {
            <p class="text-muted" style="padding:20px;">Nessuna squadra per questa stagione.</p>
          }
        </div>
        <div class="card mb-4 new-team-form">
          <input pInputText placeholder="Nome nuova squadra" [(ngModel)]="newTeamName" />
          <p-dropdown
            [options]="leagueOptions()"
            [(ngModel)]="newTeamLeagueId"
            placeholder="Lega"
            styleClass="filter-drop"
          />
          <button
            pButton
            label="+ Aggiungi squadra"
            size="small"
            [loading]="creatingTeam()"
            [disabled]="!newTeamName.trim() || !newTeamLeagueId"
            (click)="createTeam()"
          ></button>
        </div>

        <!-- Unisci squadre duplicate -->
        <div class="section-title">🔀 Unisci squadre duplicate</div>
        <div class="card mb-4 merge-panel">
          <p class="text-muted" style="padding:14px 16px 0; font-size:12px; margin:0;">
            Per squadre create due volte per errore di import (stesso club, nome leggermente diverso).
          </p>
          <div class="manual-pick">
            <p-dropdown
              [options]="teamOptions()"
              [(ngModel)]="mergeTeamAId"
              placeholder="Cerca prima squadra..."
              [filter]="true"
              filterBy="label"
              [showClear]="true"
              appendTo="body"
              styleClass="manual-drop"
            />
            <span class="text-muted">+</span>
            <p-dropdown
              [options]="teamOptions()"
              [(ngModel)]="mergeTeamBId"
              placeholder="Cerca seconda squadra..."
              [filter]="true"
              filterBy="label"
              [showClear]="true"
              appendTo="body"
              styleClass="manual-drop"
            />
          </div>
          @if (mergeTeamPair(); as pair) {
            <div class="merge-pair">
              @for (t of [pair.a, pair.b]; track t.id) {
                <div class="merge-row">
                  <span class="merge-name">{{ t.name }}</span>
                  <button
                    pButton
                    size="small"
                    label="Unisci qui"
                    [loading]="mergingTeams()"
                    (click)="mergeTeamsInto(t, pair)"
                  ></button>
                </div>
              }
            </div>
          } @else if (mergeTeamAId && mergeTeamBId) {
            <p class="text-muted" style="padding:10px 16px;">Seleziona due squadre diverse.</p>
          }
        </div>

        <!-- Iscrizioni altre competizioni -->
        <div class="section-title">🏆 Iscrizioni altre competizioni ({{ otherCompetitionOptions().length }})</div>
        <div class="card mb-4 cup-panel">
          <div class="filters-bar">
            <p-dropdown
              [options]="otherCompetitionOptions()"
              [(ngModel)]="selectedCompetitionId"
              placeholder="Competizione"
              (ngModelChange)="loadParticipants()"
              styleClass="filter-drop"
            />
          </div>
          @if (selectedCompetitionId) {
            <div class="cup-body">
              <p class="text-muted" style="font-size:12px; margin: 0 0 4px;">
                Trascina una squadra tra le due colonne per iscriverla o rimuoverla.
              </p>
              <div class="cup-columns">
                <div
                  class="cup-column"
                  pDroppable="team"
                  [class.drag-over]="dragOverColumn() === 'available'"
                  (onDragEnter)="dragOverColumn.set('available')"
                  (onDragLeave)="dragOverColumn.set(null)"
                  (onDrop)="dropOn('available')"
                >
                  <div class="cup-column-title">Disponibili ({{ available().length }})</div>
                  <div class="cup-list">
                    @for (t of available(); track t.id) {
                      <span class="assigned-chip draggable-chip" pDraggable="team" (onDragStart)="startDrag(t, 'available')">
                        {{ t.name }}
                      </span>
                    }
                    @empty {
                      <span class="text-muted" style="font-size:12px">nessuna squadra disponibile</span>
                    }
                  </div>
                </div>
                <div
                  class="cup-column"
                  pDroppable="team"
                  [class.drag-over]="dragOverColumn() === 'participants'"
                  (onDragEnter)="dragOverColumn.set('participants')"
                  (onDragLeave)="dragOverColumn.set(null)"
                  (onDrop)="dropOn('participants')"
                >
                  <div class="cup-column-title">Iscritte ({{ participants().length }})</div>
                  <div class="cup-list">
                    @for (p of participants(); track p.id) {
                      <span class="assigned-chip draggable-chip" pDraggable="team" (onDragStart)="startDrag(p, 'participants')">
                        {{ p.name }}
                        <button class="chip-btn" title="Rimuovi" (click)="removeParticipant(p)">×</button>
                      </span>
                    }
                    @empty {
                      <span class="text-muted" style="font-size:12px">nessuna squadra iscritta</span>
                    }
                  </div>
                </div>
              </div>
            </div>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1280px; margin: 0 auto; }
    .page-header { margin-bottom: 24px; }
    .back-link { display: inline-block; margin-bottom: 8px; font-size: 13px; color: var(--text-secondary); text-decoration: none; }
    .back-link:hover { text-decoration: underline; }
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

    .team-table { padding: 0; overflow: visible; }
    .team-row {
      display: flex; align-items: center; justify-content: space-between; gap: 16px;
      padding: 12px 16px; border-bottom: 1px solid var(--border-subtle); flex-wrap: wrap;
    }
    .team-row:last-child { border-bottom: none; }
    .team-info { flex: 1; min-width: 220px; }
    .team-name { font-weight: 700; font-size: 14px; display: block; margin-bottom: 4px; }
    .team-mgmt-info { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .team-name-input { min-width: 200px; }
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

    .new-team-form { padding: 14px 16px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .delete-btn { color: var(--text-negative, #e05260); border-color: rgba(248,81,73,.3); }

    .merge-panel { padding: 0; }
    .merge-pair { padding: 10px 16px; border-bottom: 1px solid var(--border-subtle); }
    .merge-pair:last-child { border-bottom: none; }
    .merge-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; flex-wrap: wrap; }
    .merge-name { font-weight: 600; font-size: 13px; min-width: 140px; }

    .manual-pick { display: flex; align-items: center; gap: 10px; padding: 14px 16px; flex-wrap: wrap; }
    .manual-drop { min-width: 220px; }

    .cup-panel { padding: 0; }
    .cup-body { padding: 14px 16px; display: flex; flex-direction: column; gap: 12px; }
    .cup-list { display: flex; flex-wrap: wrap; gap: 8px; align-content: flex-start; }
    .cup-columns { display: flex; gap: 16px; flex-wrap: wrap; }
    .cup-column {
      flex: 1; min-width: 240px; min-height: 100px;
      border: 1px dashed var(--border-color); border-radius: 8px; padding: 10px;
      transition: background-color .15s, border-color .15s;
    }
    .cup-column.drag-over { background: var(--bg-elevated); border-color: var(--accent-green); }
    .cup-column-title { font-size: 12px; font-weight: 700; color: var(--text-secondary); margin-bottom: 8px; }
    .draggable-chip { cursor: grab; }
    .draggable-chip:active { cursor: grabbing; }
  `],
})
export class AdminTeamsComponent implements OnInit {
  allenatori = signal<any[]>([]);
  seasonOptions = signal<any[]>([]);
  teams = signal<any[]>([]);
  leagues = signal<any[]>([]);
  competitions = signal<any[]>([]);
  participants = signal<any[]>([]);
  available = signal<any[]>([]);

  creating = signal(false);
  savingTeamId = signal<number | null>(null);
  deletingTeamId = signal<number | null>(null);
  creatingTeam = signal(false);
  mergingTeams = signal(false);
  message = signal('');
  messageIsError = signal(false);

  newUsername = '';
  newDisplayName = '';
  newEmail = '';
  selectedSeasonId: number | null = null;
  newTeamName = '';
  newTeamLeagueId: number | null = null;
  mergeTeamAId: number | null = null;
  mergeTeamBId: number | null = null;
  selectedCompetitionId: number | null = null;
  dragOverColumn = signal<'available' | 'participants' | null>(null);
  private draggedTeam: any | null = null;
  private draggedFrom: 'available' | 'participants' | null = null;

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.loadAllenatori();
    this.loadSeasons();
  }

  loadSeasons() {
    this.api.getSeasons().subscribe({
      next: seasons => this.seasonOptions.set(seasons.map(s => ({ label: s.label, value: s.id }))),
    });
  }

  onSeasonChange() {
    this.selectedCompetitionId = null;
    this.participants.set([]);
    this.available.set([]);
    this.loadTeams();
    this.loadLeagues();
    this.loadCompetitions();
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
          .map(t => ({
            ...t,
            _selectedCoach: null,
            _isPrimary: true,
            _editName: t.name,
            _editLeagueId: t.league_id,
          }))
      ),
      error: () => this.setMessage('Errore nel caricamento delle squadre.', true),
    });
  }

  loadLeagues() {
    if (!this.selectedSeasonId) return;
    this.api.getSeasonLeagues(this.selectedSeasonId).subscribe({ next: d => this.leagues.set(d) });
  }

  leagueOptions() {
    return this.leagues().map(l => ({ label: l.level, value: l.id }));
  }

  loadCompetitions() {
    if (!this.selectedSeasonId) return;
    this.api.getSeasonCompetitions(this.selectedSeasonId).subscribe({ next: d => this.competitions.set(d) });
  }

  otherCompetitionOptions() {
    return this.competitions()
      .filter(c => !MAIN_LEAGUE_TYPES.includes(c.type))
      .map(c => ({ label: c.name, value: c.id }));
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

  saveTeam(t: any) {
    this.savingTeamId.set(t.id);
    this.api.updateFantaTeam(t.id, { name: t._editName, league_id: t._editLeagueId }).subscribe({
      next: () => {
        this.savingTeamId.set(null);
        this.setMessage(`Squadra "${t._editName}" aggiornata.`, false);
        this.loadTeams();
      },
      error: err => {
        this.savingTeamId.set(null);
        this.setMessage(err.error?.detail || 'Errore aggiornamento squadra.', true);
      },
    });
  }

  deleteTeam(t: any) {
    if (!confirm(`Eliminare definitivamente "${t.name}"? L'operazione fallisce se ha già dati collegati.`)) return;
    this.deletingTeamId.set(t.id);
    this.api.deleteFantaTeam(t.id).subscribe({
      next: () => {
        this.deletingTeamId.set(null);
        this.setMessage(`Squadra "${t.name}" eliminata.`, false);
        this.loadTeams();
      },
      error: err => {
        this.deletingTeamId.set(null);
        const detail = err.error?.detail;
        this.setMessage(
          typeof detail === 'object' ? detail.message : (detail || 'Errore eliminazione squadra.'),
          true,
        );
      },
    });
  }

  createTeam() {
    if (!this.selectedSeasonId || !this.newTeamLeagueId) return;
    this.creatingTeam.set(true);
    this.api.createFantaTeam({
      name: this.newTeamName.trim(),
      season_id: this.selectedSeasonId,
      league_id: this.newTeamLeagueId,
    }).subscribe({
      next: res => {
        this.creatingTeam.set(false);
        this.setMessage(`Squadra "${res.name}" creata.`, false);
        this.newTeamName = '';
        this.newTeamLeagueId = null;
        this.loadTeams();
      },
      error: err => {
        this.creatingTeam.set(false);
        this.setMessage(err.error?.detail || 'Errore creazione squadra.', true);
      },
    });
  }

  teamOptions() {
    return this.teams().map(t => ({ label: t.name, value: t.id }));
  }

  mergeTeamPair(): { a: any; b: any } | null {
    if (!this.mergeTeamAId || !this.mergeTeamBId || this.mergeTeamAId === this.mergeTeamBId) return null;
    const a = this.teams().find(t => t.id === this.mergeTeamAId);
    const b = this.teams().find(t => t.id === this.mergeTeamBId);
    return a && b ? { a, b } : null;
  }

  mergeTeamsInto(keep: any, pair: { a: any; b: any }) {
    const remove = pair.a.id === keep.id ? pair.b : pair.a;
    this.mergingTeams.set(true);
    this.api.mergeTeams(keep.id, remove.id).subscribe({
      next: res => {
        this.mergingTeams.set(false);
        if (res.merged) {
          this.setMessage(`"${remove.name}" unita a "${keep.name}".`, false);
          this.mergeTeamAId = null;
          this.mergeTeamBId = null;
          this.loadTeams();
        } else {
          this.setMessage(
            `Merge parziale: alcuni dati non ricollegati per conflitto (${JSON.stringify(res.conflicts)}). Non ho eliminato "${remove.name}".`,
            true,
          );
        }
      },
      error: err => {
        this.mergingTeams.set(false);
        this.setMessage(err.error?.detail || 'Errore durante il merge.', true);
      },
    });
  }

  loadParticipants() {
    if (!this.selectedCompetitionId) return;
    this.api.getCompetitionParticipants(this.selectedCompetitionId).subscribe({
      next: res => {
        this.participants.set(res.participants);
        this.available.set(res.available);
      },
      error: err => this.setMessage(err.error?.detail || 'Errore nel caricamento iscritti.', true),
    });
  }

  startDrag(team: any, from: 'available' | 'participants') {
    this.draggedTeam = team;
    this.draggedFrom = from;
  }

  dropOn(target: 'available' | 'participants') {
    this.dragOverColumn.set(null);
    const team = this.draggedTeam;
    const from = this.draggedFrom;
    this.draggedTeam = null;
    this.draggedFrom = null;
    if (!team || !from || from === target || !this.selectedCompetitionId) return;

    if (target === 'participants') {
      this.addCompetitionParticipant(team);
    } else {
      this.removeParticipant(team);
    }
  }

  private addCompetitionParticipant(team: any) {
    if (!this.selectedCompetitionId) return;
    this.api.addCompetitionParticipant(this.selectedCompetitionId, team.id).subscribe({
      next: () => this.loadParticipants(),
      error: err => this.setMessage(err.error?.detail || 'Errore aggiunta squadra.', true),
    });
  }

  removeParticipant(p: any) {
    if (!this.selectedCompetitionId) return;
    this.api.removeCompetitionParticipant(this.selectedCompetitionId, p.id).subscribe({
      next: () => this.loadParticipants(),
      error: err => this.setMessage(err.error?.detail || 'Errore rimozione squadra.', true),
    });
  }

  private setMessage(text: string, isError: boolean) {
    this.message.set(text);
    this.messageIsError.set(isError);
  }
}
