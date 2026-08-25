import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { DropdownModule } from 'primeng/dropdown';
import { InputTextModule } from 'primeng/inputtext';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { ApiService } from '../../core/services/api.service';

const ROLE_ORDER = ['P', 'D', 'C', 'A'];

@Component({
  selector: 'app-admin-market',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, DropdownModule, InputTextModule, ButtonModule, CheckboxModule],
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <a routerLink="/admin" class="back-link">← Admin</a>
        <h1 class="page-title">🔄 Mercato</h1>
        <p class="text-secondary">Scambi tra squadre e riparazione invernale</p>
      </div>

      @if (message()) {
        <div class="card mb-4 status-msg" [class.error]="messageIsError()">{{ message() }}</div>
      }

      <div class="filters-bar card mb-4">
        <p-dropdown
          [options]="seasonOptions()"
          [(ngModel)]="selectedSeasonId"
          placeholder="Stagione"
          (ngModelChange)="onSeasonChange()"
          styleClass="filter-drop"
        />
      </div>

      @if (selectedSeasonId) {
        <!-- Scambi -->
        <div class="section-title">🔄 Scambi</div>
        <div class="card mb-4 trade-panel">
          <div class="team-pick-row">
            <p-dropdown
              [options]="teamOptions()"
              [(ngModel)]="tradeTeamAId"
              placeholder="Squadra A"
              [filter]="true" filterBy="label" [showClear]="true" appendTo="body"
              styleClass="manual-drop"
              (ngModelChange)="onTradeTeamChange('a')"
            />
            <span class="text-muted">↔</span>
            <p-dropdown
              [options]="teamOptions()"
              [(ngModel)]="tradeTeamBId"
              placeholder="Squadra B"
              [filter]="true" filterBy="label" [showClear]="true" appendTo="body"
              styleClass="manual-drop"
              (ngModelChange)="onTradeTeamChange('b')"
            />
          </div>

          @if (tradeTeamA() && tradeTeamB()) {
            <div class="trade-columns">
              <div class="trade-column">
                <div class="trade-column-title">{{ tradeTeamA().name }} cede</div>
                @for (role of ROLE_ORDER; track role) {
                  @if (rosterByRole(tradeRosterA(), role).length) {
                    <div class="role-group-label">{{ role }}</div>
                    @for (p of rosterByRole(tradeRosterA(), role); track p.player_id) {
                      <label class="player-pick">
                        <p-checkbox [(ngModel)]="p._selected" [binary]="true" (ngModelChange)="recomputeTradeValidity()" />
                        {{ p.player_name }} <span class="text-muted">({{ p.purchase_price }})</span>
                      </label>
                    }
                  }
                }
              </div>
              <div class="trade-column">
                <div class="trade-column-title">{{ tradeTeamB().name }} cede</div>
                @for (role of ROLE_ORDER; track role) {
                  @if (rosterByRole(tradeRosterB(), role).length) {
                    <div class="role-group-label">{{ role }}</div>
                    @for (p of rosterByRole(tradeRosterB(), role); track p.player_id) {
                      <label class="player-pick">
                        <p-checkbox [(ngModel)]="p._selected" [binary]="true" (ngModelChange)="recomputeTradeValidity()" />
                        {{ p.player_name }} <span class="text-muted">({{ p.purchase_price }})</span>
                      </label>
                    }
                  }
                }
              </div>
            </div>

            @if (tradeRoleMismatch()) {
              <p class="text-muted trade-warning">{{ tradeRoleMismatch() }}</p>
            }

            <div class="trade-form-row">
              <input pInputText type="date" [(ngModel)]="tradeDate" class="trade-date-input" />
              <input pInputText placeholder="Note (opzionale)" [(ngModel)]="tradeNotes" class="trade-notes-input" />
              <button
                pButton label="Registra scambio" size="small"
                [disabled]="!tradeIsValid()" [loading]="creatingTrade()"
                (click)="submitTrade()"
              ></button>
            </div>
          }

          <div class="trade-history">
            @for (t of trades(); track t.id) {
              <div class="trade-history-row">
                <div class="trade-history-main">
                  <strong>{{ t.team_a_name }}</strong> ↔ <strong>{{ t.team_b_name }}</strong>
                  <span class="text-muted">{{ t.trade_date | date:'dd/MM/yyyy' }}</span>
                </div>
                <div class="trade-history-items">
                  @for (i of t.items; track i.player_id) {
                    <span class="text-muted">
                      {{ i.player_name }} ({{ i.from_team_id === t.team_a_id ? t.team_a_name : t.team_b_name }} →
                      {{ i.to_team_id === t.team_a_id ? t.team_a_name : t.team_b_name }}, {{ i.price_before }}→{{ i.price_after }})
                    </span>
                  }
                </div>
                <button
                  pButton label="Annulla" size="small" class="p-button-outlined delete-btn"
                  [loading]="cancellingTradeId() === t.id"
                  (click)="cancelTrade(t)"
                ></button>
              </div>
            }
            @empty {
              <p class="text-muted" style="padding:14px 16px; margin:0;">Nessuno scambio registrato per questa stagione.</p>
            }
          </div>
        </div>

        <!-- Riparazione invernale -->
        <div class="section-title">❄️ Riparazione invernale</div>
        <div class="card mb-4 winter-panel">
          <p class="text-muted" style="padding:14px 16px 0; font-size:12px; margin:0;">
            Carica un file (CSV/Excel) con la rosa post mercato di tutte le squadre: il sistema calcola
            svincoli e acquisti per differenza rispetto alla rosa attuale. L'asta avviene fuori piattaforma.
          </p>
          <div class="winter-form-row">
            <input type="file" accept=".csv,.xlsx,.xls,.dat,.html,.htm" (change)="onFileSelected($event)" />
            <input pInputText type="date" [(ngModel)]="winterDate" class="trade-date-input" />
            <label class="text-muted" style="display:flex; align-items:center; gap:4px; font-size:12px;">
              <input type="checkbox" [(ngModel)]="winterCreateMissingPlayers" />
              Crea giocatori mancanti (file storici)
            </label>
            <button pButton label="Verifica" size="small" class="p-button-outlined"
              [disabled]="!winterFile" [loading]="winterLoading()" (click)="runWinterMarket(true)"></button>
            <button pButton label="Applica" size="small"
              [disabled]="!winterPreview()" [loading]="winterLoading()" (click)="runWinterMarket(false)"></button>
          </div>

          @if (winterPreview(); as preview) {
            <div class="winter-report">
              @for (r of preview.report; track r.team_id) {
                <div class="winter-team-report">
                  <strong>{{ r.team_name }}</strong>
                  <span class="text-muted">(delta crediti: {{ r.credit_delta }})</span>
                  @for (p of r.released; track p.player_id) {
                    <div class="text-muted">− {{ p.player_name }} (rimborso {{ p.refund }})</div>
                  }
                  @for (p of r.added; track p.player_id) {
                    <div class="text-muted">+ {{ p.player_name }} ({{ p.price }})</div>
                  }
                </div>
              }
              @if (preview.created_players?.length) {
                <p class="text-muted" style="padding:8px 16px;">
                  Giocatori storici creati: {{ preview.created_players.length }}
                  ({{ createdPlayersSummary(preview.created_players) }})
                </p>
              }
              @if (preview.unmatched_teams.length || preview.unmatched_players.length) {
                <p class="trade-warning">
                  Non riconosciuti — squadre: {{ preview.unmatched_teams.join(', ') || 'nessuna' }};
                  giocatori: {{ preview.unmatched_players.join(', ') || 'nessuno' }}
                </p>
              }
              @if (preview.applied) {
                <p class="text-muted" style="padding:8px 16px; font-weight:700;">✅ Applicato.</p>
              }
            </div>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1100px; margin: 0 auto; }
    .page-header { margin-bottom: 24px; }
    .back-link { display: inline-block; margin-bottom: 8px; font-size: 13px; color: var(--text-secondary); text-decoration: none; }
    .back-link:hover { text-decoration: underline; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; }
    .section-title { font-weight: 700; margin-bottom: 10px; }
    .mb-4 { margin-bottom: 24px; }

    .status-msg { padding: 12px 16px; font-size: 13px; }
    .status-msg.error { color: var(--text-negative, #e05260); }

    .filters-bar { display: flex; align-items: center; gap: 12px; padding: 14px 16px; }
    .filter-drop { min-width: 160px; }
    .manual-drop { min-width: 220px; }

    .trade-panel { padding: 0; }
    .team-pick-row { display: flex; align-items: center; gap: 10px; padding: 14px 16px; flex-wrap: wrap; }
    .trade-columns { display: flex; gap: 16px; padding: 0 16px 14px; flex-wrap: wrap; }
    .trade-column { flex: 1; min-width: 240px; }
    .trade-column-title { font-weight: 700; font-size: 13px; margin-bottom: 8px; }
    .role-group-label { font-size: 11px; font-weight: 700; color: var(--text-muted); margin-top: 8px; }
    .player-pick { display: flex; align-items: center; gap: 8px; font-size: 13px; padding: 4px 0; }
    .trade-warning { color: var(--text-negative, #e05260); font-size: 12px; padding: 0 16px 10px; margin: 0; }
    .trade-form-row { display: flex; align-items: center; gap: 10px; padding: 0 16px 16px; flex-wrap: wrap; }
    .trade-date-input { width: 150px; }
    .trade-notes-input { flex: 1; min-width: 180px; }

    .trade-history { border-top: 1px solid var(--border-subtle); }
    .trade-history-row { padding: 10px 16px; border-bottom: 1px solid var(--border-subtle); display: flex; flex-direction: column; gap: 4px; }
    .trade-history-row:last-child { border-bottom: none; }
    .trade-history-main { display: flex; align-items: center; gap: 10px; font-size: 13px; }
    .trade-history-items { display: flex; flex-direction: column; gap: 2px; font-size: 12px; }
    .delete-btn { color: var(--text-negative, #e05260); border-color: rgba(248,81,73,.3); align-self: flex-start; }

    .winter-panel { padding: 0; }
    .winter-form-row { display: flex; align-items: center; gap: 10px; padding: 14px 16px; flex-wrap: wrap; }
    .winter-report { border-top: 1px solid var(--border-subtle); padding: 4px 0; }
    .winter-team-report { padding: 10px 16px; border-bottom: 1px solid var(--border-subtle); font-size: 13px; }
    .winter-team-report:last-child { border-bottom: none; }
  `],
})
export class AdminMarketComponent implements OnInit {
  ROLE_ORDER = ROLE_ORDER;

  seasonOptions = signal<any[]>([]);
  teams = signal<any[]>([]);
  trades = signal<any[]>([]);

  tradeTeamA = signal<any>(null);
  tradeTeamB = signal<any>(null);
  tradeRosterA = signal<any[]>([]);
  tradeRosterB = signal<any[]>([]);
  tradeRoleMismatch = signal<string | null>(null);
  tradeValid = signal(false);

  creatingTrade = signal(false);
  cancellingTradeId = signal<number | null>(null);
  winterLoading = signal(false);
  winterPreview = signal<any>(null);

  message = signal('');
  messageIsError = signal(false);

  selectedSeasonId: number | null = null;
  tradeTeamAId: number | null = null;
  tradeTeamBId: number | null = null;
  tradeDate: string = new Date().toISOString().slice(0, 10);
  tradeNotes = '';
  winterFile: File | null = null;
  winterDate: string = new Date().toISOString().slice(0, 10);
  winterCreateMissingPlayers = false;

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.getSeasons().subscribe({
      next: seasons => {
        this.seasonOptions.set(seasons.map(s => ({ label: s.label, value: s.id })));
        const current = seasons.find(s => s.is_current);
        if (current) {
          this.selectedSeasonId = current.id;
          this.onSeasonChange();
        }
      },
    });
  }

  onSeasonChange() {
    this.tradeTeamAId = null;
    this.tradeTeamBId = null;
    this.tradeTeamA.set(null);
    this.tradeTeamB.set(null);
    this.winterPreview.set(null);
    if (!this.selectedSeasonId) return;
    this.api.getFantaTeams(this.selectedSeasonId).subscribe({ next: d => this.teams.set(d) });
    this.loadTrades();
  }

  loadTrades() {
    if (!this.selectedSeasonId) return;
    this.api.getTrades(this.selectedSeasonId).subscribe({ next: d => this.trades.set(d) });
  }

  teamOptions() {
    return this.teams().map(t => ({ label: t.name, value: t.id }));
  }

  onTradeTeamChange(side: 'a' | 'b') {
    const id = side === 'a' ? this.tradeTeamAId : this.tradeTeamBId;
    if (!id) {
      (side === 'a' ? this.tradeTeamA : this.tradeTeamB).set(null);
      (side === 'a' ? this.tradeRosterA : this.tradeRosterB).set([]);
      return;
    }
    this.api.getFantaTeam(id).subscribe({
      next: team => {
        (side === 'a' ? this.tradeTeamA : this.tradeTeamB).set(team);
        (side === 'a' ? this.tradeRosterA : this.tradeRosterB).set(
          team.roster.map((p: any) => ({ ...p, _selected: false }))
        );
        this.recomputeTradeValidity();
      },
    });
  }

  rosterByRole(roster: any[], role: string) {
    return roster.filter(p => p.role === role);
  }

  recomputeTradeValidity() {
    const rolesA = this.tradeRosterA().filter(p => p._selected).map(p => p.role).sort();
    const rolesB = this.tradeRosterB().filter(p => p._selected).map(p => p.role).sort();
    if (!rolesA.length || !rolesB.length) {
      this.tradeRoleMismatch.set(null);
      this.tradeValid.set(false);
      return;
    }
    const matches = JSON.stringify(rolesA) === JSON.stringify(rolesB);
    this.tradeRoleMismatch.set(matches ? null : `Ruoli non corrispondenti: A cede [${rolesA}], B cede [${rolesB}]`);
    this.tradeValid.set(matches);
  }

  tradeIsValid() {
    return this.tradeValid();
  }

  submitTrade() {
    const teamA = this.tradeTeamA();
    const teamB = this.tradeTeamB();
    if (!teamA || !teamB || !this.selectedSeasonId) return;
    this.creatingTrade.set(true);
    this.api.createTrade({
      season_id: this.selectedSeasonId,
      team_a_id: teamA.id,
      team_b_id: teamB.id,
      trade_date: this.tradeDate,
      notes: this.tradeNotes || undefined,
      player_ids_a: this.tradeRosterA().filter(p => p._selected).map(p => p.player_id),
      player_ids_b: this.tradeRosterB().filter(p => p._selected).map(p => p.player_id),
    }).subscribe({
      next: () => {
        this.creatingTrade.set(false);
        this.setMessage('Scambio registrato.', false);
        this.tradeNotes = '';
        this.onTradeTeamChange('a');
        this.onTradeTeamChange('b');
        this.loadTrades();
      },
      error: err => {
        this.creatingTrade.set(false);
        this.setMessage(err.error?.detail || 'Errore durante la registrazione dello scambio.', true);
      },
    });
  }

  cancelTrade(trade: any) {
    if (!confirm('Annullare questo scambio? Le rose torneranno come prima.')) return;
    this.cancellingTradeId.set(trade.id);
    this.api.cancelTrade(trade.id).subscribe({
      next: () => {
        this.cancellingTradeId.set(null);
        this.setMessage('Scambio annullato.', false);
        this.loadTrades();
        if (this.tradeTeamAId) this.onTradeTeamChange('a');
        if (this.tradeTeamBId) this.onTradeTeamChange('b');
      },
      error: err => {
        this.cancellingTradeId.set(null);
        this.setMessage(err.error?.detail || 'Errore durante l\'annullamento.', true);
      },
    });
  }

  onFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    this.winterFile = input.files?.[0] ?? null;
    this.winterPreview.set(null);
  }

  createdPlayersSummary(createdPlayers: { player_name: string; role: string }[]): string {
    return createdPlayers.map(p => `${p.player_name} (${p.role})`).join(', ');
  }

  runWinterMarket(dryRun: boolean) {
    if (!this.winterFile || !this.selectedSeasonId) return;
    this.winterLoading.set(true);
    this.api.reconcileWinterMarket(this.selectedSeasonId, this.winterFile, dryRun, this.winterDate, this.winterCreateMissingPlayers).subscribe({
      next: res => {
        this.winterLoading.set(false);
        this.winterPreview.set(res);
        this.setMessage(dryRun ? 'Anteprima calcolata: controlla il report prima di applicare.' : 'Riparazione applicata.', false);
      },
      error: err => {
        this.winterLoading.set(false);
        this.setMessage(err.error?.detail || 'Errore durante la riconciliazione.', true);
      },
    });
  }

  private setMessage(text: string, isError: boolean) {
    this.message.set(text);
    this.messageIsError.set(isError);
  }
}
