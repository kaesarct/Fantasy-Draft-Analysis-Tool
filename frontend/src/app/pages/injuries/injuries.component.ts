import { Component, OnInit, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ToastModule } from 'primeng/toast';
import { TagModule } from 'primeng/tag';
import { SkeletonModule } from 'primeng/skeleton';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-injuries',
  standalone: true,
  imports: [
    CommonModule, FormsModule, ButtonModule, ConfirmDialogModule, ToastModule,
    TagModule, SkeletonModule, DialogModule, InputTextModule,
  ],
  providers: [ConfirmationService, MessageService],
  template: `
    <div class="page-container fade-up">
      <p-toast />
      <p-confirmDialog />

      <div class="page-header">
        <div>
          <h1 class="page-title">🏥 Gestione Infortuni</h1>
          <p class="text-secondary">Giocatori infortunati, recuperi e sostituzioni temporanee</p>
        </div>
      </div>

      @if (auth.isAuthenticated()) {
        <div class="actions-bar mb-4">
          <button pButton label="➕ Inserisci infortunato" (click)="openAddModal()"></button>
          <button
            pButton
            label="🔄 Verifica recupero"
            class="p-button-outlined"
            [loading]="checkingRecovery()"
            [disabled]="!currentSeasonId()"
            (click)="checkRecovery()"
          ></button>
        </div>
      }

      <!-- Legend -->
      <div class="legend card mb-4">
        <span class="badge badge-red">≥8 sett.</span>
        <span class="text-muted" style="font-size:12px">Sost. temporanea disponibile (art. regolamento)</span>
        &nbsp;·&nbsp;
        <span class="badge badge-green">Recuperato</span>
        <span class="text-muted" style="font-size:12px">Rientrato in convocazione</span>
      </div>

      <div class="section-title">📋 Infortunati inseriti</div>
      @if (loading()) {
        @for (i of [1,2,3,4]; track i) { <p-skeleton height="72px" styleClass="mb-2" /> }
      } @else {
        <div class="injury-list mb-4">
          @for (inj of injuries(); track inj.id) {
            <div class="injury-card" [class.recovered]="!inj.is_active">
              <div class="inj-left">
                <div class="inj-name">{{ inj.player_name ?? 'Giocatore #' + inj.player_id }}</div>
                <div class="inj-meta text-muted">
                  Inserito: {{ inj.created_at | date:'dd/MM/yyyy' }}
                  @if (inj.expected_weeks) { &nbsp;·&nbsp; {{ inj.expected_weeks }} settimane }
                  @if (inj.expected_return) { &nbsp;·&nbsp; Rientro stimato: {{ inj.expected_return }} }
                </div>
              </div>
              <div class="inj-right">
                @if (inj.qualifies_for_temp_sub && inj.is_active) {
                  <span class="badge badge-red">≥8 sett. — Sost. disponibile</span>
                }
                @if (!inj.is_active) {
                  <span class="badge badge-green">✓ Recuperato {{ inj.confirmed_return }}</span>
                }
                @if (auth.isAuthenticated()) {
                  @if (inj.is_active) {
                    <button class="btn-sm btn-outline" (click)="markRecovered(inj)">Segna rientro</button>
                  }
                  <button class="btn-sm btn-danger" (click)="deleteInjury(inj.id)">🗑</button>
                }
              </div>
            </div>
          }
          @empty {
            <div class="empty-state">
              <p>✅ Nessun giocatore infortunato.</p>
            </div>
          }
        </div>

        <div class="section-title">✅ Rientrati</div>
        <div class="returned-list">
          @for (r of returnedList(); track r.id) {
            <div class="returned-row">
              <span class="inj-name">{{ r.player_name ?? 'Giocatore #' + r.player_id }}</span>
              <span class="text-muted">Rientrato il {{ r.confirmed_return | date:'dd/MM/yyyy' }}</span>
            </div>
          }
          @empty {
            <p class="text-muted">Nessun rientro registrato.</p>
          }
        </div>
      }

      <div class="section-title">🩺 Infortunati Serie A (ufficiale fantacalcio.it)</div>
      @if (auth.isAuthenticated()) {
        <div class="actions-bar mb-3">
          <button pButton label="🔄 Sincronizza" size="small" [loading]="syncingSerieA()" (click)="syncSerieA()"></button>
          <button
            pButton
            [label]="showSerieAArchive ? 'Nascondi rientrati' : 'Mostra rientrati'"
            size="small"
            class="p-button-outlined"
            (click)="toggleSerieAArchive()"
          ></button>
        </div>
      }

      @if (loadingSerieA()) {
        <p-skeleton height="60px" styleClass="mb-2" />
      } @else {
        <div class="seriea-groups mb-4">
          @for (group of serieAGrouped(); track group.team_name) {
            <div class="seriea-team-group">
              <div class="seriea-team-name">{{ group.team_name }}</div>
              @for (p of group.players; track p.id) {
                <div class="seriea-player-row">
                  <div class="seriea-player-main">
                    <span class="inj-name">
                      {{ p.player_name }}
                      @if (p.player_id) { <span class="badge badge-green" style="margin-left:6px;">collegato</span> }
                    </span>
                    <span class="text-muted" style="font-size:12px">dal {{ p.first_seen_at | date:'dd/MM/yyyy' }}</span>
                  </div>
                  <p class="seriea-desc text-muted">{{ p.description }}</p>
                  @if (p.descriptions.length > 1) {
                    <button class="seriea-history-toggle" (click)="toggleSerieAExpanded(p.id)">
                      {{ expandedSerieA().has(p.id) ? 'Nascondi storico' : 'Mostra storico (' + p.descriptions.length + ')' }}
                    </button>
                  }
                  @if (expandedSerieA().has(p.id)) {
                    <div class="seriea-history">
                      @for (h of p.descriptions; track h.recorded_at) {
                        <div class="seriea-history-row">
                          <span class="text-muted" style="font-size:11px">{{ h.recorded_at | date:'dd/MM/yyyy HH:mm' }}</span>
                          <span style="font-size:12px">{{ h.description }}</span>
                        </div>
                      }
                    </div>
                  }
                </div>
              }
            </div>
          }
          @empty {
            <p class="text-muted">Nessun infortunato Serie A sincronizzato. Premi "Sincronizza".</p>
          }
        </div>

        @if (auth.isAuthenticated() && showSerieAArchive) {
          <div class="section-title">Rientrati (Serie A)</div>
          <div class="returned-list">
            @for (a of serieAArchive(); track a.id) {
              <div class="returned-row">
                <span class="inj-name">{{ a.player_name }} <span class="text-muted">({{ a.team_name }})</span></span>
                <span class="text-muted">{{ a.started_at | date:'dd/MM/yyyy' }} → {{ a.ended_at | date:'dd/MM/yyyy' }}</span>
              </div>
            }
            @empty {
              <p class="text-muted">Nessun rientro registrato.</p>
            }
          </div>
        }
      }

      <p-dialog
        header="Inserisci infortunato"
        [(visible)]="addModalVisible"
        [modal]="true"
        [style]="{ width: '420px' }"
        (onHide)="resetAddModal()"
      >
        <input
          pInputText
          class="search-input"
          [(ngModel)]="searchTerm"
          (ngModelChange)="onSearchChange($event)"
          placeholder="Cerca giocatore per nome..."
          autocomplete="off"
        />
        @if (searching()) {
          <p-skeleton height="36px" styleClass="mb-2" />
        } @else {
          <div class="search-results">
            @for (p of searchResults(); track p.id) {
              <button class="player-result" [disabled]="adding()" (click)="selectPlayer(p)">
                {{ p.name }} <span class="text-muted">({{ p.role }})</span>
              </button>
            }
            @if (searchTerm.trim().length >= 2 && searchResults().length === 0) {
              <p class="text-muted">Nessun giocatore trovato.</p>
            }
          </div>
        }
      </p-dialog>
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1280px; margin: 0 auto; }
    .page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; }

    .actions-bar { display: flex; gap: 12px; flex-wrap: wrap; }

    .legend { padding: 12px 16px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .mb-2 { margin-bottom: 8px; }
    .mb-4 { margin-bottom: 24px; }

    .section-title { font-weight: 700; margin-bottom: 10px; }

    .injury-list { display: flex; flex-direction: column; gap: 10px; }
    .injury-card {
      background: var(--bg-card); border: 1px solid var(--border-color);
      border-radius: var(--radius-md); padding: 16px 20px;
      display: flex; align-items: center; justify-content: space-between; gap: 16px;
      transition: border-color var(--transition);
    }
    .injury-card:hover { border-color: var(--accent-orange); }
    .injury-card.recovered { opacity: 0.6; border-color: rgba(63,185,80,.3); }
    .inj-name { font-weight: 700; font-size: 14px; margin-bottom: 4px; }
    .inj-meta { font-size: 12px; }
    .inj-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

    .btn-sm { padding: 5px 12px; border-radius: var(--radius-sm); font-size: 12px; font-weight: 600; cursor: pointer; border: 1px solid var(--border-color); transition: all var(--transition); }
    .btn-outline { background: transparent; color: var(--text-primary); }
    .btn-outline:hover { border-color: var(--accent-blue); }
    .btn-danger { background: rgba(248,81,73,.12); color: var(--accent-red); border-color: rgba(248,81,73,.3); }
    .btn-danger:hover { background: rgba(248,81,73,.25); }

    .empty-state { text-align: center; padding: 48px; color: var(--accent-green); font-size: 16px; font-weight: 600; }

    .returned-list { display: flex; flex-direction: column; gap: 8px; }
    .returned-row {
      background: var(--bg-card); border: 1px solid var(--border-color);
      border-radius: var(--radius-md); padding: 10px 16px;
      display: flex; align-items: center; justify-content: space-between; gap: 16px;
      font-size: 13px;
    }

    .search-input { width: 100%; margin-bottom: 12px; }
    .search-results { display: flex; flex-direction: column; gap: 6px; max-height: 320px; overflow-y: auto; }
    .player-result {
      text-align: left; padding: 8px 12px; border-radius: var(--radius-sm);
      border: 1px solid var(--border-color); background: var(--bg-elevated);
      cursor: pointer; font-size: 13px; font-weight: 600; color: var(--text-primary);
      transition: all var(--transition);
    }
    .player-result:hover:not(:disabled) { border-color: var(--accent-blue); }
    .player-result:disabled { opacity: 0.6; cursor: not-allowed; }

    .mb-3 { margin-bottom: 16px; }

    .seriea-groups { display: flex; flex-direction: column; gap: 14px; }
    .seriea-team-group {
      background: var(--bg-card); border: 1px solid var(--border-color);
      border-radius: var(--radius-md); padding: 14px 18px;
    }
    .seriea-team-name { font-weight: 800; font-size: 13px; margin-bottom: 10px; letter-spacing: .02em; }
    .seriea-player-row { padding: 8px 0; border-top: 1px solid var(--border-subtle); }
    .seriea-player-row:first-of-type { border-top: none; padding-top: 0; }
    .seriea-player-main { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 4px; flex-wrap: wrap; }
    .seriea-desc { font-size: 13px; margin: 0 0 6px; line-height: 1.4; }
    .seriea-history-toggle {
      background: none; border: none; cursor: pointer; padding: 0;
      font-size: 12px; font-weight: 600; color: var(--accent-blue);
    }
    .seriea-history { margin-top: 8px; padding: 8px 12px; background: var(--bg-elevated); border-radius: var(--radius-sm); display: flex; flex-direction: column; gap: 6px; }
    .seriea-history-row { display: flex; gap: 10px; align-items: baseline; }
  `],
})
export class InjuriesComponent implements OnInit {
  injuries = signal<any[]>([]);
  loading = signal(true);
  currentSeasonId = signal<number | null>(null);

  checkingRecovery = signal(false);

  addModalVisible = false;
  searchTerm = '';
  searchResults = signal<any[]>([]);
  searching = signal(false);
  adding = signal(false);
  private searchTimeout?: ReturnType<typeof setTimeout>;

  returnedList = computed(() =>
    this.injuries()
      .filter(i => !i.is_active)
      .sort((a, b) => (b.confirmed_return ?? '').localeCompare(a.confirmed_return ?? ''))
  );

  serieAInjuries = signal<any[]>([]);
  serieAArchive = signal<any[]>([]);
  loadingSerieA = signal(true);
  syncingSerieA = signal(false);
  showSerieAArchive = false;
  expandedSerieA = signal<Set<number>>(new Set());

  serieAGrouped = computed(() => {
    const groups = new Map<string, any[]>();
    for (const p of this.serieAInjuries()) {
      if (!groups.has(p.team_name)) groups.set(p.team_name, []);
      groups.get(p.team_name)!.push(p);
    }
    return Array.from(groups.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([team_name, players]) => ({ team_name, players }));
  });

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
        this.currentSeasonId.set(current?.id ?? null);
        this.loadInjuries();
      },
      error: () => this.loadInjuries(),
    });
    this.loadSerieAInjuries();
  }

  loadSerieAInjuries() {
    this.loadingSerieA.set(true);
    this.api.getSerieAInjuries().subscribe({
      next: data => { this.serieAInjuries.set(data); this.loadingSerieA.set(false); },
      error: () => this.loadingSerieA.set(false),
    });
  }

  loadSerieAArchive() {
    this.api.getSerieAInjuryArchive().subscribe({ next: data => this.serieAArchive.set(data) });
  }

  toggleSerieAArchive() {
    this.showSerieAArchive = !this.showSerieAArchive;
    if (this.showSerieAArchive && this.serieAArchive().length === 0) {
      this.loadSerieAArchive();
    }
  }

  toggleSerieAExpanded(id: number) {
    const set = new Set(this.expandedSerieA());
    if (set.has(id)) set.delete(id); else set.add(id);
    this.expandedSerieA.set(set);
  }

  syncSerieA() {
    this.syncingSerieA.set(true);
    this.api.syncSerieAInjuries().subscribe({
      next: res => {
        this.syncingSerieA.set(false);
        if (res.ok) {
          this.toast.add({
            severity: 'success',
            summary: 'Sincronizzazione completata',
            detail: `${res.created} nuovi, ${res.updated} aggiornati, ${res.archived} rientrati.`,
          });
          this.loadSerieAInjuries();
          if (this.showSerieAArchive) this.loadSerieAArchive();
        } else {
          this.toast.add({ severity: 'warn', summary: 'Attenzione', detail: res.message || 'Sync fallito.' });
        }
      },
      error: err => {
        this.syncingSerieA.set(false);
        const detail = err.error?.detail ?? 'Errore durante la sincronizzazione.';
        this.toast.add({ severity: 'error', summary: 'Errore', detail });
      },
    });
  }

  loadInjuries() {
    this.loading.set(true);
    this.api.getInjuries(this.currentSeasonId() ?? undefined, false).subscribe({
      next: data => { this.injuries.set(data); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  markRecovered(inj: any) {
    const today = new Date().toISOString().split('T')[0];
    this.api.recoverPlayer(inj.id, today).subscribe({
      next: () => {
        this.toast.add({ severity: 'success', summary: 'Rientro registrato', detail: inj.player_name });
        this.loadInjuries();
      },
    });
  }

  deleteInjury(id: number) {
    this.confirm.confirm({
      message: 'Eliminare questo infortunio?',
      accept: () => {
        this.api.deleteInjury(id).subscribe(() => this.loadInjuries());
      },
    });
  }

  openAddModal() {
    this.resetAddModal();
    this.addModalVisible = true;
  }

  resetAddModal() {
    this.searchTerm = '';
    this.searchResults.set([]);
    this.searching.set(false);
    clearTimeout(this.searchTimeout);
  }

  onSearchChange(term: string) {
    clearTimeout(this.searchTimeout);
    const trimmed = term.trim();
    if (trimmed.length < 2) {
      this.searchResults.set([]);
      this.searching.set(false);
      return;
    }
    const seasonId = this.currentSeasonId();
    this.searching.set(true);
    this.searchTimeout = setTimeout(() => {
      this.api.getPlayers(trimmed, undefined, undefined, seasonId ?? undefined).subscribe({
        next: players => { this.searchResults.set(players); this.searching.set(false); },
        error: () => this.searching.set(false),
      });
    }, 300);
  }

  selectPlayer(player: any) {
    const seasonId = this.currentSeasonId();
    if (!seasonId) return;
    this.adding.set(true);
    this.api.createInjury({ player_id: player.id, season_id: seasonId }).subscribe({
      next: () => {
        this.adding.set(false);
        this.toast.add({
          severity: 'success',
          summary: 'Infortunio registrato',
          detail: `Giocatore ${player.name} inserito come infortunato.`,
        });
        this.addModalVisible = false;
        this.resetAddModal();
        this.loadInjuries();
      },
      error: err => {
        this.adding.set(false);
        const detail = err.error?.detail ?? "Errore durante l'inserimento.";
        this.toast.add({ severity: 'warn', summary: 'Attenzione', detail });
      },
    });
  }

  checkRecovery() {
    const seasonId = this.currentSeasonId();
    if (!seasonId) return;
    this.checkingRecovery.set(true);
    this.api.checkInjuryRecovery(seasonId).subscribe({
      next: res => {
        this.checkingRecovery.set(false);
        if (res.returned?.length) {
          const names = res.returned.map((p: any) => p.player_name).join(', ');
          this.toast.add({
            severity: 'success',
            summary: `Rientri alla giornata ${res.match_day}`,
            detail: `Sono tornati dall'infortunio: ${names}`,
            life: 8000,
          });
        } else {
          this.toast.add({
            severity: 'info',
            summary: `Giornata ${res.match_day}`,
            detail: "Nessun giocatore è tornato dall'infortunio.",
          });
        }
        this.loadInjuries();
      },
      error: err => {
        this.checkingRecovery.set(false);
        const detail = err.error?.detail ?? 'Errore durante la verifica dei recuperi.';
        this.toast.add({ severity: 'error', summary: 'Errore', detail });
      },
    });
  }
}
