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

      <p-tabView (activeIndexChange)="onTabChange($event)">
        @for (tab of tabs; track tab.type) {
          <p-tabPanel [header]="tab.label">
            @if (loading()) {
              <p-skeleton height="300px" />
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
                      <strong>Squadra #{{ s.fanta_team_id }}</strong>
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
  `],
})
export class LeagueComponent implements OnInit {
  tabs = LEAGUE_TABS;
  seasons = signal<any[]>([]);
  standings = signal<any[]>([]);
  loading = signal(false);
  selectedSeason: number | null = null;
  activeTab = 0;

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.getSeasons().subscribe(data => {
      this.seasons.set(data);
      const current = data.find(s => s.is_current) ?? data[0];
      if (current) {
        this.selectedSeason = current.id;
        this.loadStandings();
      }
    });
  }

  onSeasonChange() { this.loadStandings(); }
  onTabChange(idx: number) { this.activeTab = idx; this.loadStandings(); }

  loadStandings() {
    if (!this.selectedSeason) return;
    this.loading.set(true);
    const compType = this.tabs[this.activeTab].type;
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
