import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { catchError, concatMap, from, map, of, reduce } from 'rxjs';
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
  historicalTeamId: number | null;
  newName: string;
  updateName: boolean;
  primaryLegheCoachId: number | null;
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
          <button pButton label="Carica da leghe.fantacalcio.it" icon="pi pi-download" [loading]="loading()" [disabled]="!selectedSeasonId || !legheEnabled()" (click)="load()"></button>
          <button pButton label="🎯 Sync punteggi + classifiche (Goku/Oscar)" class="p-button-outlined" [loading]="syncingScores()" [disabled]="!selectedSeasonId || !legheEnabled()" (click)="syncMatchdayScores()"></button>
          <button pButton label="Sync risultati/calendario" icon="pi pi-chart-bar" class="p-button-outlined" [loading]="syncingResults()" [disabled]="!selectedSeasonId || !legheEnabled()" (click)="syncResults()"></button>
          <button pButton label="Carica Excel (calendari e formazioni)" icon="pi pi-upload" class="p-button-outlined" [loading]="syncingResults()" [disabled]="!selectedSeasonId" (click)="calendarFile.click()"></button>
          <input #calendarFile type="file" accept=".xlsx" multiple hidden (change)="importCalendarFile($event)" />
        </div>
        @if (!legheEnabled()) {
          <div class="card status-msg mb-4" style="margin-top:10px;">
            ℹ️ Le chiamate a leghe.fantacalcio.it sono disattivate (<code>LEGHE_API_ENABLED=false</code>): i pulsanti di sincronizzazione
            sono spenti. Per risultati, classifiche e punteggi usa <strong>Carica Excel (calendari e formazioni)</strong>.
          </div>
        }
        <p class="text-muted" style="font-size:12px; margin-top:6px;">
          <strong>Carica Excel</strong>: alternativa senza login automatico. Scarica da leghe.fantacalcio.it
          i file delle competizioni e caricali qui anche tutti insieme, o solo quelli che hai (Coppa Italia, Ciempions, UEFA, Euro Cup possono mancare): tipo di file e competizione si riconoscono dal titolo di ogni file e, se la competizione non esiste ancora (es. UEFA), viene creata.
          I <strong>Calendari</strong> (Calendario → Esporta Excel) portano partite, gironi e il numero di giornata di Serie A di ogni turno.
          Le <strong>Formazioni</strong> (es. «GOLD · Giornata 4») portano il totale di ogni squadra: servono i Calendari già caricati, per sapere a quale giornata di Serie A corrispondono.
          Dopo ogni caricamento parte il controllo di coerenza di Silver e di Goku/Oscar.
        </p>
        <p class="text-muted" style="font-size:12px; margin-top:6px;">
          <strong>Sync punteggi</strong> (il pulsante lancia di seguito anche la sync risultati, cosi' popola con un click anche le Classifiche): fonte usata da Premio Goku/Oscar, copre tutte le competizioni
          collegate incluso Silver, ma non dice chi ha giocato contro chi. <strong>Sync risultati/calendario</strong>:
          dà anche l'accoppiamento partita e i gol da fasce (non funziona per Silver). Entrambe da fare
          dopo aver collegato le squadre qui sotto.
        </p>
      </div>

      @if (error()) {
        <div class="card status-msg error mb-4">{{ error() }}</div>
      }

      @if (preview()?.competitions_created?.length) {
        <div class="card status-msg mb-4">✅ Competizioni create: {{ preview().competitions_created.join(', ') }}</div>
      }

      @if (report(); as r) {
        <div class="card status-msg mb-4" [class.error]="r.errors.length">
          <div>✅ Squadre collegate: {{ r.teams_linked }} (nuove: {{ r.teams_created }}, rinominate: {{ r.teams_renamed }}) · Allenatori creati: {{ r.allenatori_created }} (email aggiornate: {{ r.allenatori_email_aggiornati }}) · Associazioni squadra-allenatore: {{ r.coaches_assigned }}</div>
          @for (e of r.errors; track e) {
            <div class="text-negative">⚠️ {{ e }}</div>
          }
        </div>
      }

      @if (scoresReport(); as sr) {
        <div class="card status-msg mb-4">
          @for (kv of resultsReportEntries(sr); track kv.type) {
            <div>
              <strong>{{ kv.type }}</strong>:
              @if (kv.data.error) {
                <span class="text-negative">⚠️ {{ kv.data.error }}</span>
              } @else {
                {{ kv.data.scores_synced }} punteggi sincronizzati
                @if (kv.data.teams_unmatched) {
                  <span class="text-negative">— {{ kv.data.teams_unmatched }} squadre non collegate</span>
                }
                @if (kv.data.reason) {
                  <span class="text-muted">({{ kv.data.reason }})</span>
                }
              }
            </div>
          }
          @empty {
            <p class="text-muted">Nessuna competizione con id leghe.fantacalcio.it collegato per questa stagione — collega prima le squadre qui sotto.</p>
          }
        </div>
      }

      @if (resultsReport(); as rr) {
        <div class="card status-msg mb-4">
          @for (kv of resultsReportEntries(rr); track kv.type) {
            <div>
              <strong>{{ kv.type }}</strong>:
              @if (kv.data.error) {
                <span class="text-negative">⚠️ {{ kv.data.error }}</span>
              } @else if (kv.data.scores_imported !== undefined) {
                {{ kv.data.scores_imported }} punteggi importati, {{ kv.data.scores_updated }} aggiornati
                <span class="text-muted">(giornata {{ kv.data.league_day }} = {{ kv.data.serie_a_day }}ª di Serie A)</span>
                @if (kv.data.appena_creata) {
                  <span class="text-muted">(competizione creata ora)</span>
                }
                @if (kv.data.teams_unmatched?.length) {
                  <span class="text-negative">— squadre non riconosciute: {{ kv.data.teams_unmatched.join(', ') }}</span>
                }
              } @else {
                {{ kv.data.matches_imported }} importate, {{ kv.data.matches_updated }} aggiornate
                @if (kv.data.serie_a_days) {
                  <span class="text-muted">({{ kv.data.serie_a_days }} giornate associate alla Serie A)</span>
                }
                @if (kv.data.appena_creata) {
                  <span class="text-muted">(competizione creata ora)</span>
                }
                @if (kv.data.teams_unmatched?.length) {
                  <span class="text-negative">— squadre non riconosciute: {{ kv.data.teams_unmatched.join(', ') }}</span>
                }
              }
              @if (kv.data.teams_unmatched?.length && kv.data.rename_candidates?.length) {
                @for (n of kv.data.teams_unmatched; track n) {
                  <div class="rename-row">
                    <span>Il file chiama «{{ n }}» una squadra che non riconosco. Aggiornare il nome di:</span>
                    <p-dropdown
                      [options]="candidateOptions(kv.data.rename_candidates)"
                      [(ngModel)]="renameChoice[n]"
                      placeholder="Scegli la squadra"
                      [filter]="true"
                      appendTo="body"
                    />
                    <button pButton label="Rinomina" class="p-button-sm" [loading]="renaming()" [disabled]="!renameChoice[n]" (click)="renameTeam(n)"></button>
                  </div>
                }
              }
            </div>
          }
          @empty {
            <p class="text-muted">Nessuna competizione con id leghe.fantacalcio.it collegato per questa stagione — collega prima le squadre qui sotto.</p>
          }
        </div>
      }

      @if (renameNotice()) {
        <div class="card status-msg mb-4">{{ renameNotice() }}</div>
      }

      @if (consistency(); as c) {
        <div class="card status-msg mb-4" [class.error]="c.silver.discrepancies.length">
          <div><strong>Controllo coerenza</strong></div>
          <div>
            <strong>Silver</strong>:
            @if (c.silver.discrepancies.length) {
              <span class="text-negative">⚠️ {{ c.silver.discrepancies.length }} differenze ({{ c.silver.checked }} confronti completi)</span>
            } @else if (c.silver.checked) {
              ✅ coerente con i campionati ({{ c.silver.checked }} confronti squadra/giornata)
            } @else {
              <span class="text-muted">nessun confronto possibile: mancano i punteggi di Silver o dei campionati</span>
            }
          </div>
          @for (d of c.silver.discrepancies.slice(0, 30); track $index) {
            <div class="text-negative">
              ⚠️ {{ d.fanta_team_name }}, giornata {{ d.match_day }}:
              @if (d.kind === 'mismatch') {
                Silver {{ d.silver_value }} contro {{ d.league_type }} {{ d.league_value }}
              } @else if (d.kind === 'missing_silver') {
                manca in Silver (in {{ d.league_type }}: {{ d.league_value }})
              } @else {
                manca in {{ d.league_type }} (in Silver: {{ d.silver_value }})
              }
            </div>
          }
          @if (c.silver.discrepancies.length > 30) {
            <div class="text-muted">…e altre {{ c.silver.discrepancies.length - 30 }}</div>
          }
          @for (g of c.goku; track $index) {
            <div>🏆 <strong>Goku</strong>: {{ g.fanta_team_name }} {{ g.score }} ({{ g.competition_type }}, {{ g.round_label }})</div>
          }
          @for (o of c.oscar; track $index) {
            <div>🥔 <strong>Oscar</strong>: {{ o.fanta_team_name }} {{ o.score }} ({{ o.competition_type }}, {{ o.round_label }})</div>
          }
          @if (!c.goku.length && !c.oscar.length) {
            <div class="text-muted">Goku/Oscar: nessun punteggio disponibile</div>
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
                  @if (!teamOptions().length) {
                    <span class="text-muted" style="font-size:11px">nessuna squadra ancora presente in questa stagione</span>
                  }
                }
              </div>
            }

            @if (decisions[team.leghe_team_id].createNew) {
              <div class="team-link-row">
                <span class="text-muted" style="font-size:12px">Storico (opzionale) — eredita l'identità di una squadra di stagioni passate:</span>
                <p-dropdown
                  [options]="historicalTeamOptions()"
                  [(ngModel)]="decisions[team.leghe_team_id].historicalTeamId"
                  placeholder="Nessuno, squadra nuova"
                  [filter]="true"
                  filterBy="label"
                  [showClear]="true"
                  appendTo="body"
                  styleClass="team-drop"
                />
              </div>
            }

            @if (matchedTeamName(team); as currentName) {
              @if (currentName !== team.leghe_team_name) {
                <div class="rename-row">
                  <span class="text-muted">Nome diverso da leghe.fantacalcio.it: "{{ currentName }}" →</span>
                  <input pInputText [(ngModel)]="decisions[team.leghe_team_id].newName" class="rename-input" />
                  <p-checkbox
                    [binary]="true"
                    [(ngModel)]="decisions[team.leghe_team_id].updateName"
                    inputId="rename-{{ team.leghe_team_id }}"
                  />
                  <label [for]="'rename-' + team.leghe_team_id">aggiorna nome</label>
                </div>
              }
            }

            <div class="coach-list">
              @for (coach of team.coaches; track coach.leghe_coach_id) {
                <div class="coach-row">
                  @if (team.coaches.length > 1) {
                    <input
                      type="radio"
                      [name]="'primary-' + team.leghe_team_id"
                      [value]="coach.leghe_coach_id"
                      [(ngModel)]="decisions[team.leghe_team_id].primaryLegheCoachId"
                      id="primary-{{ team.leghe_team_id }}-{{ coach.leghe_coach_id }}"
                    />
                    <label class="text-muted" [for]="'primary-' + team.leghe_team_id + '-' + coach.leghe_coach_id" title="Allenatore principale">principale</label>
                  }
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
    .rename-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 6px 0 2px; }
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

    .rename-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; font-size: 12px; }
    .rename-input { width: 200px; }

    .coach-list { display: flex; flex-direction: column; gap: 8px; padding-top: 8px; border-top: 1px solid var(--border-subtle); }
    .coach-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; }
    .coach-row label[for^="primary-"] { margin-right: 6px; font-size: 11px; }
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
  syncingResults = signal(false);
  syncingScores = signal(false);
  error = signal('');
  preview = signal<any>(null);
  report = signal<any>(null);
  resultsReport = signal<Record<string, any> | null>(null);
  scoresReport = signal<Record<string, any> | null>(null);
  consistency = signal<any>(null);
  renaming = signal(false);
  renameNotice = signal('');
  legheEnabled = signal(true);
  renameChoice: Record<string, number | null> = {};
  private lastFiles: File[] = [];

  decisions: Record<number, TeamDecisionState> = {};

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.getFeatures().subscribe({
      next: f => this.legheEnabled.set(!!f.leghe_api_enabled),
      error: () => {},
    });
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
            historicalTeamId: team.suggested_lineage_team_id,
            newName: team.leghe_team_name,
            updateName: false,
            primaryLegheCoachId: team.coaches[0]?.leghe_coach_id ?? null,
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

  /** Nome della squadra attualmente abbinata (collegata o scelta nel dropdown),
   * null se si sta creando una nuova squadra o non è ancora stata scelta. */
  matchedTeamName(team: any): string | null {
    const d = this.decisions[team.leghe_team_id];
    if (!d || d.createNew) return null;
    const id = team.already_linked_team_id ?? d.fantaTeamId;
    return id ? this.teamName(id) : null;
  }

  teamOptions() {
    return (this.preview()?.our_teams ?? []).map((t: any) => ({ label: t.name, value: t.id }));
  }

  historicalTeamOptions() {
    return (this.preview()?.historical_teams ?? []).map((t: any) => ({
      label: `${t.name} (${t.season_label})`, value: t.id,
    }));
  }

  allenatoreOptions() {
    return (this.preview()?.our_allenatori ?? []).map((a: any) => ({
      label: a.email ? `${a.display_name} (${a.email})` : a.display_name,
      value: a.id,
    }));
  }

  syncResults() {
    if (!this.selectedSeasonId) return;
    this.syncingResults.set(true);
    this.error.set('');
    this.resultsReport.set(null);
    this.api.syncLegheResults(this.selectedSeasonId).subscribe({
      next: res => {
        this.syncingResults.set(false);
        this.resultsReport.set(res);
      },
      error: err => {
        this.syncingResults.set(false);
        this.error.set(err.error?.detail || 'Errore durante la sync dei risultati.');
      },
    });
  }

  importCalendarFile(event: Event) {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    input.value = '';
    this.renameNotice.set('');
    this.runImport(files);
  }

  private runImport(selected: File[]) {
    if (!selected.length || !this.selectedSeasonId) return;
    const seasonId = this.selectedSeasonId;
    // Le Formazioni hanno bisogno della giornata di Serie A portata dai Calendari: vanno caricate dopo
    const isLineup = (f: File) => f.name.toLowerCase().includes('formazioni');
    const files = [...selected].sort((a, b) => Number(isLineup(a)) - Number(isLineup(b)));
    this.lastFiles = files;
    this.syncingResults.set(true);
    this.error.set('');
    this.resultsReport.set(null);
    this.consistency.set(null);
    this.renameChoice = {};
    from(files).pipe(
      concatMap(file => this.api.importLegheCalendarFile(seasonId, file).pipe(
        catchError(err => of({ [file.name]: { error: err.error?.detail || "Errore durante l'import del file." } })),
      )),
      reduce((all, res) => ({ ...all, ...res }), {} as Record<string, any>),
      map(all => all),
    ).subscribe({
      next: all => {
        this.syncingResults.set(false);
        this.resultsReport.set(all);
        for (const data of Object.values(all)) {
          // Un solo nome sconosciuto e una sola squadra senza corrispondenza: abbinamento ovvio, preselezionato
          // (la rinomina resta comunque da confermare con il pulsante).
          if (data.teams_unmatched?.length === 1 && data.rename_candidates?.length === 1) {
            this.renameChoice[data.teams_unmatched[0]] = data.rename_candidates[0].id;
          }
        }
        this.api.getConsistencyCheck(seasonId).subscribe({
          next: c => this.consistency.set(c),
          error: err => this.error.set(err.error?.detail || 'Errore durante il controllo di coerenza.'),
        });
      },
      error: () => {
        this.syncingResults.set(false);
        this.error.set("Errore durante l'import dei file.");
      },
    });
  }

  resultsReportEntries(report: Record<string, any>): { type: string; data: any }[] {
    return Object.entries(report).map(([type, data]) => ({ type, data }));
  }

  candidateOptions(candidates: { id: number; name: string }[]) {
    return candidates.map(c => ({ label: c.name, value: c.id }));
  }

  renameTeam(newName: string) {
    const teamId = this.renameChoice[newName];
    if (!teamId || !this.selectedSeasonId) return;
    this.renaming.set(true);
    this.error.set('');
    this.api.renameLegheTeam(this.selectedSeasonId, teamId, newName).subscribe({
      next: res => {
        this.renaming.set(false);
        this.renameNotice.set(`✅ «${res.old_name}» rinominata in «${res.new_name}» (solo stagione corrente). Reimporto i file.`);
        this.runImport(this.lastFiles);
      },
      error: err => {
        this.renaming.set(false);
        this.error.set(err.error?.detail || 'Errore durante la rinomina della squadra.');
      },
    });
  }

  syncMatchdayScores() {
    if (!this.selectedSeasonId) return;
    this.syncingScores.set(true);
    this.error.set('');
    this.scoresReport.set(null);
    this.api.syncLegheMatchdayScores(this.selectedSeasonId).subscribe({
      next: res => {
        this.syncingScores.set(false);
        this.scoresReport.set(res);
        this.syncResults();
      },
      error: err => {
        this.syncingScores.set(false);
        this.error.set(err.error?.detail || 'Errore durante la sync dei punteggi.');
      },
    });
  }

  apply() {
    const p = this.preview();
    if (!p || !this.selectedSeasonId) return;

    const teams = p.participants.map((team: any) => {
      const d = this.decisions[team.leghe_team_id];
      const fantaTeamId = team.already_linked_team_id ?? (d.createNew ? null : d.fantaTeamId);
      const coaches = team.coaches.map((c: any) => {
        const cd = d.coaches[c.leghe_coach_id];
        const isPrimary = d.primaryLegheCoachId === c.leghe_coach_id;
        if (cd.createNew) {
          return {
            leghe_coach_id: c.leghe_coach_id,
            create: { username: cd.username, display_name: cd.displayName, email: cd.email || null },
            is_primary: isPrimary,
          };
        }
        return {
          leghe_coach_id: c.leghe_coach_id,
          allenatore_id: cd.allenatoreId,
          leghe_email: c.email || null,
          is_primary: isPrimary,
        };
      });
      return {
        leghe_team_id: team.leghe_team_id,
        leghe_team_name: team.leghe_team_name,
        league_level: team.league_level,
        fanta_team_id: fantaTeamId,
        create_new: !team.already_linked_team_id && d.createNew,
        lineage_source_team_id: d.createNew ? d.historicalTeamId : null,
        new_name: d.newName,
        update_name: d.updateName,
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
