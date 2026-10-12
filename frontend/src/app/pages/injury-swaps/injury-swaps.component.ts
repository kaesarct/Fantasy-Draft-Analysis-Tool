import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ToastModule } from 'primeng/toast';
import { SkeletonModule } from 'primeng/skeleton';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-injury-swaps',
  standalone: true,
  imports: [CommonModule, FormsModule, ConfirmDialogModule, ToastModule, SkeletonModule, DialogModule, InputTextModule],
  providers: [ConfirmationService, MessageService],
  template: `
    <div class="page-container fade-up">
      <p-toast />
      <p-confirmDialog />

      <div class="page-header">
        <h1 class="page-title">🔁 Infortuni scambiati</h1>
        <p class="text-secondary">
          Chi ha chiesto il cambio e con chi. Sostituto con quotazione attuale ≤ a quella dell'infortunato;
          massimo {{ maxSwaps() }} cambi a stagione per squadra, anche se l'infortunato rientra.
        </p>
      </div>

      @if (warning()) {
        <div class="warning-box mb-4">⚠️ {{ warning() }}</div>
      }

      @if (loading()) {
        @for (i of [1,2,3]; track i) { <p-skeleton height="90px" styleClass="mb-2" /> }
      } @else {
        @for (inj of injuries(); track inj.injury_id) {
          <div class="inj-card" [class.recovered]="!inj.is_active">
            <div class="inj-head">
              <span class="inj-name">{{ inj.player_name }} <span class="text-muted">({{ inj.role }})</span></span>
              <span class="text-muted">
                Quotazione attuale: {{ inj.current_price ?? 'n/d' }}
                @if (!inj.is_active) { &nbsp;·&nbsp; rientrato }
              </span>
            </div>
            @for (t of inj.teams; track t.roster_id) {
              <div class="team-row">
                <div>
                  <strong>{{ t.team_name }}</strong>
                  <span class="text-muted"> · {{ t.league_level }} · cambi {{ t.swaps_used }}/{{ maxSwaps() }}</span>
                </div>
                @if (t.swap) {
                  <div class="swap-done">
                    ➜ {{ t.swap.replacement_player_name }} ({{ t.swap.replacement_role }})
                    @if (auth.isAuthenticated()) {
                      <button class="btn-sm btn-danger" (click)="deleteSwap(t.swap.id)">🗑</button>
                    }
                  </div>
                } @else if (auth.isAuthenticated()) {
                  <button class="btn-sm btn-outline"
                          [disabled]="t.swaps_used >= maxSwaps() || inj.current_price == null"
                          (click)="openDialog(inj, t)">
                    {{ t.swaps_used >= maxSwaps() ? 'Cambi esauriti' : 'Registra cambio' }}
                  </button>
                } @else {
                  <span class="text-muted">Nessun cambio</span>
                }
              </div>
            }
            @empty {
              <p class="text-muted">Nessuna squadra ha questo giocatore in rosa.</p>
            }
          </div>
        }
        @empty {
          <div class="empty-state">Nessun infortunato inserito.</div>
        }
      }

      <p-dialog
        [header]="'Sostituto per ' + (selInjury?.player_name ?? '')"
        [(visible)]="dialogVisible"
        [modal]="true"
        [style]="{ width: 'min(440px, 92vw)' }"
        (onHide)="resetDialog()"
      >
        <p class="text-muted" style="font-size:12px">
          {{ selTeam?.team_name }} — quotazione massima: {{ selInjury?.current_price }}
        </p>
        <input pInputText class="search-input" [(ngModel)]="searchTerm"
               (ngModelChange)="onSearchChange($event)" placeholder="Cerca sostituto..." autocomplete="off" />
        @if (searching()) {
          <p-skeleton height="36px" />
        } @else {
          <div class="search-results">
            @for (p of results(); track p.id) {
              <button class="player-result" [disabled]="saving()" (click)="confirmSwap(p)">
                {{ p.name }} <span class="text-muted">({{ p.role }}) · {{ p.price }}</span>
              </button>
            }
            @if (searchTerm.trim().length >= 2 && results().length === 0) {
              <p class="text-muted">Nessun giocatore idoneo.</p>
            }
          </div>
        }
      </p-dialog>
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1000px; margin: 0 auto; }
    .page-header { margin-bottom: 20px; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; }
    .mb-4 { margin-bottom: 20px; }
    .warning-box { padding: 12px 16px; border-radius: var(--radius-md); border: 1px solid var(--accent-orange); background: var(--bg-card); font-size: 13px; }
    .inj-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 14px 18px; margin-bottom: 12px; }
    .inj-card.recovered { opacity: .7; }
    .inj-head { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
    .inj-name { font-weight: 700; font-size: 14px; }
    .team-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; padding: 8px 0; border-top: 1px solid var(--border-subtle); font-size: 13px; }
    .swap-done { display: flex; align-items: center; gap: 8px; font-weight: 600; }
    .btn-sm { padding: 5px 12px; border-radius: var(--radius-sm); font-size: 12px; font-weight: 600; cursor: pointer; border: 1px solid var(--border-color); }
    .btn-sm:disabled { opacity: .5; cursor: not-allowed; }
    .btn-outline { background: transparent; color: var(--text-primary); }
    .btn-danger { background: rgba(248,81,73,.12); color: var(--accent-red); border-color: rgba(248,81,73,.3); }
    .empty-state { text-align: center; padding: 48px; color: var(--text-muted); }
    .search-input { width: 100%; margin-bottom: 12px; }
    .search-results { display: flex; flex-direction: column; gap: 6px; max-height: 320px; overflow-y: auto; }
    .player-result { text-align: left; padding: 8px 12px; border-radius: var(--radius-sm); border: 1px solid var(--border-color); background: var(--bg-elevated); cursor: pointer; font-size: 13px; font-weight: 600; color: var(--text-primary); }
    .player-result:hover:not(:disabled) { border-color: var(--accent-blue); }
  `],
})
export class InjurySwapsComponent implements OnInit {
  injuries = signal<any[]>([]);
  loading = signal(true);
  warning = signal<string | null>(null);
  maxSwaps = signal(3);
  private seasonId: number | null = null;

  dialogVisible = false;
  selInjury: any = null;
  selTeam: any = null;
  searchTerm = '';
  results = signal<any[]>([]);
  searching = signal(false);
  saving = signal(false);
  private searchTimeout?: ReturnType<typeof setTimeout>;

  constructor(
    private api: ApiService,
    private confirm: ConfirmationService,
    private toast: MessageService,
    public auth: AuthService,
  ) {}

  ngOnInit() {
    this.api.getSeasons().subscribe({
      next: seasons => {
        const current = seasons.find((s: any) => s.is_current) ?? seasons[0];
        this.seasonId = current?.id ?? null;
        this.load();
      },
      error: () => this.loading.set(false),
    });
  }

  load() {
    if (!this.seasonId) { this.loading.set(false); return; }
    this.loading.set(true);
    this.api.getInjurySwaps(this.seasonId).subscribe({
      next: res => {
        this.injuries.set(res.injuries);
        this.maxSwaps.set(res.max_swaps_per_team);
        this.warning.set(res.warning);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  openDialog(inj: any, team: any) {
    this.resetDialog();
    this.selInjury = inj;
    this.selTeam = team;
    this.dialogVisible = true;
  }

  resetDialog() {
    this.searchTerm = '';
    this.results.set([]);
    this.searching.set(false);
    clearTimeout(this.searchTimeout);
  }

  onSearchChange(term: string) {
    clearTimeout(this.searchTimeout);
    if (term.trim().length < 2) { this.results.set([]); this.searching.set(false); return; }
    this.searching.set(true);
    this.searchTimeout = setTimeout(() => {
      this.api.getInjurySwapCandidates(this.selInjury.injury_id, this.selTeam.team_id, term.trim()).subscribe({
        next: r => { this.results.set(r); this.searching.set(false); },
        error: () => this.searching.set(false),
      });
    }, 300);
  }

  confirmSwap(player: any) {
    this.saving.set(true);
    this.api.createInjurySwap({
      injury_id: this.selInjury.injury_id,
      team_id: this.selTeam.team_id,
      replacement_player_id: player.id,
    }).subscribe({
      next: res => {
        this.saving.set(false);
        this.dialogVisible = false;
        this.toast.add({ severity: 'success', summary: 'Cambio registrato', detail: `${this.selTeam.team_name}: ${player.name} (${res.swaps_used}/${this.maxSwaps()})` });
        this.load();
      },
      error: err => {
        this.saving.set(false);
        this.toast.add({ severity: 'warn', summary: 'Attenzione', detail: err.error?.detail ?? 'Errore durante il salvataggio.' });
      },
    });
  }

  deleteSwap(id: number) {
    this.confirm.confirm({
      message: 'Eliminare il cambio? Libera uno dei cambi della squadra: usalo solo per correggere un errore.',
      accept: () => this.api.deleteInjurySwap(id).subscribe(() => this.load()),
    });
  }
}
