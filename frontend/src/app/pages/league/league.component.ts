import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TabViewModule } from 'primeng/tabview';
import { TableModule } from 'primeng/table';
import { DropdownModule } from 'primeng/dropdown';
import { SkeletonModule } from 'primeng/skeleton';
import { ApiService } from '../../core/services/api.service';

const LEAGUE_TABS = [
  { label: '🥇 Gold',   type: 'GOLD'   },
  { label: '🥉 Bronze', type: 'BRONZE' },
  { label: '⚫ Carbon',  type: 'CARBON' },
  { label: '🥈 Silver', type: 'SILVER' },
  { label: '🏆 Ciempions', type: 'CIEMPIONS' },
  { label: '🌍 UEFA',   type: 'UEFA'   },
];

const CUP_TYPES = new Set(['CIEMPIONS', 'UEFA', 'COPPA_ITALIA', 'EURO_CUP']);

const PHASE_LABELS: Record<string, string> = {
  ROUND_OF_16: 'Ottavi di finale',
  QUARTER_FINAL: 'Quarti di finale',
  SEMI_FINAL: 'Semifinali',
  FINAL: 'Finale',
};

@Component({
  selector: 'app-league',
  standalone: true,
  imports: [CommonModule, FormsModule, TabViewModule, TableModule, DropdownModule, SkeletonModule],
  template: `
    <div class="page-container fade-up">
      <div class="page-header row">
        <div>
          <h1 class="page-title">🏆 Classifica</h1>
          <p class="text-secondary">Tutte le competizioni della stagione</p>
        </div>
        <p-dropdown
          [options]="seasons()"
          [(ngModel)]="selectedSeason"
          optionLabel="label"
          optionValue="id"
          placeholder="Stagione"
          (ngModelChange)="onSeasonChange()"
          styleClass="season-drop"
        />
      </div>

      @if (seasonDisclaimer()) {
        <div class="season-disclaimer">⚠️ {{ seasonDisclaimer() }}</div>
      }

      <p-tabView [(activeIndex)]="activeTab" (activeIndexChange)="onTabChange($event)">
        @for (tab of tabs(); track tab.type) {
          <p-tabPanel [header]="tab.label">
            @if (loading()) {
              <p-skeleton height="300px" />
            } @else if (isCupType(tab.type)) {
              @if (!bracket() || (!bracket().groups.length && !bracket().knockout.length)) {
                <p class="empty-msg">Nessun dato disponibile. Avvia un sync per caricare i dati.</p>
              } @else {
                @if (bracket().groups.length) {
                  <div class="groups-grid">
                    @for (g of bracket().groups; track g.name) {
                      <div class="group-card">
                        <div class="group-title">{{ g.name }}</div>
                        <table class="group-table">
                          <thead>
                            <tr>
                              <th>Squadra</th>
                              <th>G</th><th>V</th><th>N</th><th>P</th>
                              <th>GF</th><th>GS</th><th>Pt</th>
                            </tr>
                          </thead>
                          <tbody>
                            @for (s of g.standings; track s.fanta_team_id) {
                              <tr>
                                <td class="team-name">{{ s.name }}</td>
                                <td>{{ s.played }}</td>
                                <td class="text-positive">{{ s.wins }}</td>
                                <td>{{ s.draws }}</td>
                                <td class="text-negative">{{ s.losses }}</td>
                                <td>{{ s.goals_for }}</td>
                                <td>{{ s.goals_against }}</td>
                                <td class="pts-col">{{ s.pts }}</td>
                              </tr>
                            }
                          </tbody>
                        </table>
                      </div>
                    }
                  </div>
                }
                @if (bracket().knockout.length) {
                  <div class="knockout-section">
                    @for (round of bracket().knockout; track round.phase) {
                      <div class="round-block">
                        <div class="round-title">{{ phaseLabel(round.phase) }}</div>
                        <div class="ties-grid">
                          @for (tie of round.ties; track tie.team_a_id) {
                            <div class="tie-card">
                              <div class="tie-row" [class.winner]="tie.winner_id === tie.team_a_id">
                                <span class="tie-team">{{ tie.team_a_name }}</span>
                                <span class="tie-score">{{ tie.aggregate_a }}</span>
                              </div>
                              <div class="tie-row" [class.winner]="tie.winner_id === tie.team_b_id">
                                <span class="tie-team">{{ tie.team_b_name }}</span>
                                <span class="tie-score">{{ tie.aggregate_b }}</span>
                              </div>
                              @if (tie.legs.length > 1) {
                                <div class="tie-legs">
                                  @for (leg of tie.legs; track leg.match_day) {
                                    <span>{{ leg.goals_home }}-{{ leg.goals_away }}</span>
                                  }
                                </div>
                              }
                            </div>
                          }
                        </div>
                      </div>
                    }
                  </div>
                }
              }
            } @else {
              <p-table [value]="standings()" styleClass="standing-table" [rowHover]="true">
                <ng-template pTemplate="header">
                  <tr>
                    <th style="width:40px">#</th>
                    <th>Squadra</th>
                    <th style="text-align:center">G</th>
                    <th style="text-align:center">V</th>
                    <th style="text-align:center">P</th>
                    <th style="text-align:center">S</th>
                    <th style="text-align:center">GF</th>
                    <th style="text-align:center">GS</th>
                    <th style="text-align:center;font-weight:800;color:var(--accent-green)">Pts</th>
                    @if (tab.type === 'SILVER') {
                      <th style="text-align:center">Acc.</th>
                    }
                  </tr>
                </ng-template>
                <ng-template pTemplate="body" let-s let-i="rowIndex">
                  <tr>
                    <td>
                      <span [class]="positionClass(i)">{{ i + 1 }}</span>
                    </td>
                    <td>
                      <strong>{{ s.fanta_team_name ?? ('Squadra #' + s.fanta_team_id) }}</strong>
                    </td>
                    <td style="text-align:center">{{ s.played ?? (s.wins + s.draws + s.losses) }}</td>
                    <td style="text-align:center;color:var(--accent-green)">{{ s.wins }}</td>
                    <td style="text-align:center">{{ s.draws }}</td>
                    <td style="text-align:center;color:var(--accent-red)">{{ s.losses }}</td>
                    <td style="text-align:center">{{ s.goals_for | number:'1.0-0' }}</td>
                    <td style="text-align:center">{{ s.goals_against | number:'1.0-0' }}</td>
                    <td style="text-align:center;font-weight:800;font-size:15px">{{ s.pts }}</td>
                    @if (tab.type === 'SILVER') {
                      <td style="text-align:center">{{ s.total_score | number:'1.0-1' }}</td>
                    }
                  </tr>
                </ng-template>
                <ng-template pTemplate="emptymessage">
                  <tr><td colspan="9" style="text-align:center;padding:32px;color:var(--text-muted)">
                    Nessun dato disponibile. Avvia un sync per caricare i dati.
                  </td></tr>
                </ng-template>
              </p-table>
            }
          </p-tabPanel>
        }
      </p-tabView>
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1280px; margin: 0 auto; }
    .page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 24px; flex-wrap: wrap; gap: 16px; }
    .page-title  { font-size: 24px; font-weight: 800; margin-bottom: 4px; }
    .season-drop { min-width: 140px; }

    .season-disclaimer {
      background: rgba(240, 136, 62, .12); border: 1px solid var(--accent-orange);
      color: var(--accent-orange); border-radius: 8px; padding: 10px 14px;
      font-size: 13px; font-weight: 600; margin-bottom: 16px;
    }

    :host ::ng-deep .p-tabview-panels { padding: 0; margin-top: 16px; }
    :host ::ng-deep .standing-table .p-datatable-thead th {
      background: var(--bg-elevated);
      color: var(--text-muted);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      border-bottom: 1px solid var(--border-color);
      padding: 10px 14px;
    }
    :host ::ng-deep .standing-table .p-datatable-tbody td {
      padding: 12px 14px;
      border-bottom: 1px solid var(--border-subtle);
    }

    .pos-1 { color: var(--gold-league); font-weight: 800; }
    .pos-2 { color: var(--silver-league); font-weight: 700; }
    .pos-3 { color: var(--bronze-league); font-weight: 700; }
    .pos-other { color: var(--text-muted); }

    .empty-msg { text-align: center; padding: 32px; color: var(--text-muted); }

    .groups-grid {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px; margin-bottom: 28px;
    }
    .group-card { background: var(--bg-elevated); border: 1px solid var(--border-color); border-radius: 10px; overflow: hidden; }
    .group-title { font-weight: 700; font-size: 13px; padding: 10px 14px; border-bottom: 1px solid var(--border-color); }
    .group-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .group-table th {
      color: var(--text-muted); font-weight: 700; text-transform: uppercase; font-size: 10px;
      text-align: center; padding: 6px 8px;
    }
    .group-table th:first-child { text-align: left; }
    .group-table td { text-align: center; padding: 6px 8px; border-top: 1px solid var(--border-subtle); }
    .group-table .team-name { text-align: left; font-weight: 600; }
    .group-table .pts-col { font-weight: 800; }

    .round-block { margin-bottom: 24px; }
    .round-title { font-weight: 700; font-size: 14px; margin-bottom: 10px; }
    .ties-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
    .tie-card { background: var(--bg-elevated); border: 1px solid var(--border-color); border-radius: 10px; padding: 10px 14px; }
    .tie-row { display: flex; align-items: center; justify-content: space-between; padding: 4px 0; font-size: 13px; }
    .tie-row.winner { font-weight: 800; color: var(--accent-green); }
    .tie-score { font-weight: 800; }
    .tie-legs { display: flex; gap: 8px; margin-top: 6px; font-size: 11px; color: var(--text-muted); }
  `],
})
export class LeagueComponent implements OnInit {
  tabs = signal(LEAGUE_TABS);
  seasons = signal<any[]>([]);
  standings = signal<any[]>([]);
  bracket = signal<any>(null);
  loading = signal(false);
  selectedSeason: number | null = null;
  activeTab = 0;
  seasonDisclaimer = signal<string | null>(null);
  private competitions: any[] = [];

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.getSeasons().subscribe(data => {
      this.seasons.set(data);
      const current = data.find(s => s.is_current) ?? data[0];
      if (current) {
        this.selectedSeason = current.id;
        this.onSeasonChange();
      }
    });
  }

  onSeasonChange() {
    if (!this.selectedSeason) return;
    this.activeTab = 0;
    const season = this.seasons().find(s => s.id === this.selectedSeason);
    this.seasonDisclaimer.set(season?.disclaimer ?? null);
    this.api.getSeasonCompetitions(this.selectedSeason).subscribe({
      next: comps => {
        this.competitions = comps;
        const types = new Set(comps.map(c => c.type));
        this.tabs.set(LEAGUE_TABS.filter(t => types.has(t.type)));
        this.loadStandings();
      },
      error: () => {
        this.competitions = [];
        this.tabs.set(LEAGUE_TABS);
        this.loadStandings();
      },
    });
  }

  onTabChange(idx: number) { this.activeTab = idx; this.loadStandings(); }

  isCupType(type: string): boolean {
    return CUP_TYPES.has(type);
  }

  phaseLabel(phase: string): string {
    return PHASE_LABELS[phase] ?? phase;
  }

  loadStandings() {
    const tabs = this.tabs();
    if (!this.selectedSeason || !tabs.length) { this.standings.set([]); this.bracket.set(null); return; }
    const compType = tabs[this.activeTab].type;

    if (this.isCupType(compType)) {
      this.standings.set([]);
      const comp = this.competitions.find(c => c.type === compType);
      if (!comp) { this.bracket.set(null); return; }
      this.loading.set(true);
      this.api.getCompetitionBracket(comp.id).subscribe({
        next: data => { this.bracket.set(data); this.loading.set(false); },
        error: () => { this.bracket.set(null); this.loading.set(false); },
      });
      return;
    }

    this.bracket.set(null);
    this.loading.set(true);
    this.api.getSeasonStandings(this.selectedSeason, compType).subscribe({
      next: data => { this.standings.set(data); this.loading.set(false); },
      error: ()  => this.loading.set(false),
    });
  }

  positionClass(i: number): string {
    if (i === 0) return 'pos-1';
    if (i === 1) return 'pos-2';
    if (i === 2) return 'pos-3';
    return 'pos-other';
  }
}
