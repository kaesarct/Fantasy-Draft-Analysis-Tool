import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { DropdownModule } from 'primeng/dropdown';
import { InputTextModule } from 'primeng/inputtext';
import { CheckboxModule } from 'primeng/checkbox';
import { SkeletonModule } from 'primeng/skeleton';
import { ApiService } from '../../core/services/api.service';

interface CoachDecisionState {
  allenatoreId: number | null;
  createNew: boolean;
  username: string;
  displayName: string;
  email: string;
}

interface TeamDecisionState {
  fantaTeamId: number | null;
  createNew: boolean;
  coaches: Record<number, CoachDecisionState>;
}

function slugUsername(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

@Component({
  selector: 'app-admin-leghe-sync',
  standalone: true,
  imports: [CommonModule, FormsModule, ButtonModule, DropdownModule, InputTextModule, CheckboxModule, SkeletonModule],
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <h1 class="page-title">🔗 Sync squadre/allenatori leghe.fantacalcio.it</h1>
        <p class="text-secondary">
          Da fare una volta l'anno, a inizio stagione, quando su leghe.fantacalcio.it hai già creato tutte
          le competizioni e sei sicuro dei partecipanti definitivi. Collega ogni squadra/allenatore a un
          record già esistente, oppure creane uno nuovo.
        </p>
        <div class="toolbar">
          <p-dropdown
            [options]="seasonOptions()"
            [(ngModel)]="selectedSeasonId"
            placeholder="Stagione"
            styleClass="filter-drop"
          />
          <button pButton label="Carica da leghe.fantacalcio.it" icon="pi pi-download" [loading]="loading()" [disabled]="!selectedSeasonId" (click)="load()"></button>
        </div>
      </div>

      @if (error()) {
        <div class="card status-msg error mb-4">{{ error() }}</div>
      }

      @if (report(); as r) {
        <div class="card status-msg mb-4" [class.error]="r.errors.length">
          <div>✅ Squadre collegate: {{ r.teams_linked }} (di cui nuove: {{ r.teams_created }}) · Allenatori creati: {{ r.allenatori_created }} · Associazioni squadra-allenatore: {{ r.coaches_assigned }}</div>
          @for (e of r.errors; track e) {
            <div class="text-negative">⚠️ {{ e }}</div>
          }
        </div>
      }

      @if (preview(); as p) {
        @for (team of p.participants; track team.leghe_team_id) {
          <div class="card team-card mb-4">
            <div class="team-header">
              <div>
                <strong>{{ team.leghe_team_name }}</strong>
                @if (team.league_level) {
                  <span class="badge badge-green">{{ team.league_level }}</span>
                }
              </div>
              @if (team.already_linked_team_id) {
                <span class="text-muted">già collegata</span>
              }
            </div>

            @if (team.already_linked_team_id) {
              <div class="text-muted linked-info">
                Collegata a: {{ teamName(team.already_linked_team_id) }}
              </div>
            } @else {
              <div class="team-link-row">
                <p-checkbox
                  [binary]="true"
                  [(ngModel)]="decisions[team.leghe_team_id].createNew"
                  inputId="new-team-{{ team.leghe_team_id }}"
                />
                <label [for]="'new-team-' + team.leghe_team_id">Crea nuova squadra</label>
                @if (!decisions[team.leghe_team_id].createNew) {
                  <p-dropdown
                    [options]="teamOptions()"
                    [(ngModel)]="decisions[team.leghe_team_id].fantaTeamId"
                    placeholder="Collega a squadra esistente..."
                    [filter]="true"
                    filterBy="label"
                    [showClear]="true"
                    appendTo="body"
                    styleClass="team-drop"
                  />
                }
              </div>
            }

            <div class="coach-list">
              @for (coach of team.coaches; track coach.leghe_coach_id) {
                <div class="coach-row">
                  <span class="coach-name">{{ coach.name }}</span>
                  <span class="text-muted coach-email">{{ coach.email || 'nessuna email' }}</span>
                  <p-checkbox
                    [binary]="true"
                    [(ngModel)]="decisions[team.leghe_team_id].coaches[coach.leghe_coach_id].createNew"
                    inputId="new-coach-{{ team.leghe_team_id }}-{{ coach.leghe_coach_id }}"
                  />
                  <label [for]="'new-coach-' + team.leghe_team_id + '-' + coach.leghe_coach_id">Crea nuovo</label>
                  @if (!decisions[team.leghe_team_id].coaches[coach.leghe_coach_id].createNew) {
                    <p-dropdown
                      [options]="allenatoreOptions()"
                      [(ngModel)]="decisions[team.leghe_team_id].coaches[coach.leghe_coach_id].allenatoreId"
                      placeholder="Collega ad allenatore..."
                      [filter]="true"
                      filterBy="label"
                      [showClear]="true"
                      appendTo="body"
                      styleClass="coach-drop"
                    />
                  } @else {
                    <input pInputText placeholder="username" [(ngModel)]="decisions[team.leghe_team_id].coaches[coach.leghe_coach_id].username" class="coach-input" />
                    <input pInputText placeholder="nome visualizzato" [(ngModel)]="decisions[team.leghe_team_id].coaches[coach.leghe_coach_id].displayName" class="coach-input" />
                    <input pInputText placeholder="email" [(ngModel)]="decisions[team.leghe_team_id].coaches[coach.leghe_coach_id].email" class="coach-input" />
                  }
                </div>
              }
            </div>
          </div>
        }

        <button pButton label="Conferma e applica" icon="pi pi-check" [loading]="applying()" (click)="apply()"></button>
      } @else if (loading()) {
        <p-skeleton height="120px" styleClass="mb-2" />
        <p-skeleton height="120px" styleClass="mb-2" />
        <p-skeleton height="120px" />
      }
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1100px; margin: 0 auto; }
    .page-header { margin-bottom: 24px; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; }
    .page-header .text-secondary { margin-bottom: 12px; }
    .toolbar { display: flex; align-items: center; gap: 10px; }
    .filter-drop { min-width: 160px; }
    .mb-2 { margin-bottom: 8px; }
    .mb-4 { margin-bottom: 24px; }

    .status-msg { padding: 12px 16px; font-size: 13px; }
    .status-msg.error { color: var(--text-negative, #e05260); }
    .text-negative { color: var(--text-negative, #e05260); }

    .team-card { padding: 16px 20px; }
    .team-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
    .team-header .badge { margin-left: 8px; }
    .linked-info { font-size: 13px; margin-bottom: 6px; }
    .team-link-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
    .team-drop { min-width: 220px; }

    .coach-list { display: flex; flex-direction: column; gap: 8px; padding-top: 8px; border-top: 1px solid var(--border-subtle); }
    .coach-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; }
    .coach-name { font-weight: 600; min-width: 120px; }
    .coach-email { min-width: 160px; }
    .coach-drop { min-width: 200px; }
    .coach-input { width: 150px; }
  `],
})
export class AdminLegheSyncComponent implements OnInit {
  seasonOptions = signal<any[]>([]);
  selectedSeasonId: number | null = null;

  loading = signal(false);
  applying = signal(false);
  error = signal('');
  preview = signal<any>(null);
  report = signal<any>(null);

  decisions: Record<number, TeamDecisionState> = {};

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.getSeasons().subscribe({
      next: seasons => {
        this.seasonOptions.set(seasons.map((s: any) => ({ label: s.label, value: s.id })));
        const current = seasons.find((s: any) => s.is_current);
        this.selectedSeasonId = current ? current.id : (seasons[0]?.id ?? null);
      },
    });
  }

  load() {
    if (!this.selectedSeasonId) return;
    this.loading.set(true);
    this.error.set('');
    this.report.set(null);
    this.api.getLeghePreview(this.selectedSeasonId).subscribe({
      next: res => {
        this.preview.set(res);
        this.decisions = {};
        for (const team of res.participants) {
          const coaches: Record<number, CoachDecisionState> = {};
          for (const c of team.coaches) {
            coaches[c.leghe_coach_id] = {
              allenatoreId: c.suggested_allenatore_id,
              createNew: !c.suggested_allenatore_id,
              username: slugUsername(c.name),
              displayName: c.name,
              email: c.email,
            };
          }
          this.decisions[team.leghe_team_id] = {
            fantaTeamId: team.suggested_fanta_team_id,
            createNew: !team.suggested_fanta_team_id && !team.already_linked_team_id,
            coaches,
          };
        }
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Errore nel caricamento da leghe.fantacalcio.it.');
        this.loading.set(false);
      },
    });
  }

  teamName(id: number): string {
    return this.preview()?.our_teams?.find((t: any) => t.id === id)?.name ?? `#${id}`;
  }

  teamOptions() {
    return (this.preview()?.our_teams ?? []).map((t: any) => ({ label: t.name, value: t.id }));
  }

  allenatoreOptions() {
    return (this.preview()?.our_allenatori ?? []).map((a: any) => ({
      label: a.email ? `${a.display_name} (${a.email})` : a.display_name,
      value: a.id,
    }));
  }

  apply() {
    const p = this.preview();
    if (!p || !this.selectedSeasonId) return;

    const teams = p.participants.map((team: any) => {
      const d = this.decisions[team.leghe_team_id];
      const fantaTeamId = team.already_linked_team_id ?? (d.createNew ? null : d.fantaTeamId);
      const coaches = team.coaches.map((c: any) => {
        const cd = d.coaches[c.leghe_coach_id];
        if (cd.createNew) {
          return {
            leghe_coach_id: c.leghe_coach_id,
            create: { username: cd.username, display_name: cd.displayName, email: cd.email || null },
          };
        }
        return { leghe_coach_id: c.leghe_coach_id, allenatore_id: cd.allenatoreId };
      });
      return {
        leghe_team_id: team.leghe_team_id,
        leghe_team_name: team.leghe_team_name,
        league_level: team.league_level,
        fanta_team_id: fantaTeamId,
        create_new: !team.already_linked_team_id && d.createNew,
        coaches,
      };
    });

    this.applying.set(true);
    this.report.set(null);
    this.api.applyLegheSync({ season_id: this.selectedSeasonId, teams }).subscribe({
      next: res => {
        this.applying.set(false);
        this.report.set(res);
        this.load();
      },
      error: err => {
        this.applying.set(false);
        this.error.set(err.error?.detail || "Errore durante l'applicazione.");
      },
    });
  }
}
