import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { InputTextModule } from 'primeng/inputtext';
import { DropdownModule } from 'primeng/dropdown';
import { ButtonModule } from 'primeng/button';
import { ApiService } from '../../core/services/api.service';

interface ConflictDiffEntry {
  keep: unknown;
  remove: unknown;
}

interface ConflictItem {
  table: string;
  key_values: Record<string, number>;
  diff: Record<string, ConflictDiffEntry>;
  choice: 'keep' | 'remove' | null;
}

interface PendingMerge {
  keepId: number;
  removeId: number;
  keepName: string;
  removeName: string;
  items: ConflictItem[];
  unresolved: { table: string; key_values: Record<string, number>; reason: string }[];
}

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, InputTextModule, DropdownModule, ButtonModule],
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <h1 class="page-title">⚙️ Amministrazione</h1>
        <p class="text-secondary">Sincronizzazione dati e strumenti di manutenzione</p>
        <a routerLink="/admin/squadre" class="section-link">🛡️ Gestione Squadre (allenatori, associazioni, coppe) →</a>
        <a routerLink="/admin/mercato" class="section-link">🔄 Mercato (scambi, riparazione invernale) →</a>
      </div>

      @if (message()) {
        <div class="card mb-4 status-msg" [class.error]="messageIsError()">{{ message() }}</div>
      }

      @if (pendingMerge(); as pm) {
        <div class="card mb-4 conflict-panel">
          <div class="conflict-header">
            <strong>Risolvi i conflitti: "{{ pm.keepName }}" ↔ "{{ pm.removeName }}"</strong>
            <button class="dismiss-btn" (click)="cancelConflictResolution()">Annulla</button>
          </div>
          @for (item of pm.items; track item) {
            <div class="conflict-item">
              <div class="text-muted conflict-meta">{{ item.table }} — {{ item.key_values | json }}</div>
              @for (kv of item.diff | keyvalue; track kv.key) {
                <div class="conflict-row">
                  <span class="conflict-col">{{ kv.key }}</span>
                  <span class="conflict-val">{{ pm.keepName }}: <strong>{{ kv.value.keep }}</strong></span>
                  <span class="conflict-val">{{ pm.removeName }}: <strong>{{ kv.value.remove }}</strong></span>
                </div>
              }
              <div class="conflict-choice">
                <button
                  pButton size="small" [label]="'Tieni ' + pm.keepName"
                  [class.p-button-outlined]="item.choice !== 'keep'"
                  (click)="chooseConflictWinner(item, 'keep')"
                ></button>
                <button
                  pButton size="small" [label]="'Tieni ' + pm.removeName"
                  [class.p-button-outlined]="item.choice !== 'remove'"
                  (click)="chooseConflictWinner(item, 'remove')"
                ></button>
              </div>
            </div>
          }
          @if (pm.unresolved.length) {
            <p class="conflict-unresolved">Non risolvibile automaticamente: {{ pm.unresolved[0].reason }}</p>
          }
          <div class="conflict-footer">
            <button
              pButton size="small" label="Applica e completa merge"
              [disabled]="!allConflictsChosen()"
              [loading]="resolvingConflict()"
              (click)="confirmConflictResolutions()"
            ></button>
          </div>
        </div>
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
        <div class="sync-row">
          <button
            pButton
            label="🏁 Stagione conclusa"
            size="small"
            class="p-button-outlined p-button-danger"
            [disabled]="!conclusionReady() || concludingSeason()"
            [loading]="concludingSeason()"
            (click)="concludeSeason()"
          ></button>
          @if (concludingSeason()) {
            <span class="text-muted" style="font-size:12px">Operazione in corso, può richiedere qualche minuto…</span>
          } @else if (!conclusionReady() && conclusionMissing().length) {
            <span class="text-muted" style="font-size:12px">In attesa della 38ª giornata per: {{ conclusionMissing().join(', ') }}</span>
          } @else if (conclusionReady()) {
            <span class="text-muted" style="font-size:12px">38ª giornata giocata per {{ currentSeasonLabel() }}: puoi chiudere la stagione.</span>
          }
        </div>
        @if (conclusionReport(); as report) {
          <div class="conclusion-report">
            <div>✅ Stagione <strong>{{ report.new_season.label }}</strong> creata e impostata come corrente ({{ report.teams_created }} squadre copiate, {{ report.coaches_carried }} allenatori riportati).</div>
            @for (kv of report.archive_import | keyvalue; track kv.key) {
              <div [class.text-negative]="!$any(kv.value).ok">
                Archivio {{ kv.key }}: {{ $any(kv.value).ok ? ('✅ ' + ($any(kv.value).rows ?? 0) + ' righe') : ('⚠️ ' + $any(kv.value).message) }}
              </div>
            }
          </div>
        }
        <div class="sync-row">
          <span class="text-muted" style="font-size:12px">Importa storico per la stagione selezionata sopra (anche se non corrente):</span>
          <button pButton label="Statistiche" size="small" class="p-button-outlined" [disabled]="!syncSeasonId" [loading]="importingArchive() === 'stats'" (click)="importArchive('stats')"></button>
          <button pButton label="Quotazioni" size="small" class="p-button-outlined" [disabled]="!syncSeasonId" [loading]="importingArchive() === 'prices'" (click)="importArchive('prices')"></button>
          <button pButton label="Voti" size="small" class="p-button-outlined" [disabled]="!syncSeasonId" [loading]="importingArchive() === 'votes'" (click)="importArchive('votes')"></button>
        </div>
      </div>

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
                  @if (p.seasons?.length) {
                    · <span [title]="seasonsSummary(p.seasons)">{{ p.seasons.length }} stagioni: {{ seasonsSummary(p.seasons) }}</span>
                  } @else {
                    · <span class="text-negative">nessuna stagione</span>
                  }
                </span>
                <button
                  pButton
                  size="small"
                  label="Unisci qui"
                  [disabled]="mergeBusy()"
                  [loading]="mergingKey() === pairKey(pair)"
                  (click)="mergeInto(p, pair)"
                ></button>
              </div>
            }
            @if (seasonOverlap(pair); as overlap) {
              <p class="text-muted" [class.text-negative]="overlap.length" style="padding:0 0 4px; font-size:11px;">
                {{ overlap.length ? '⚠️ Stagioni in comune: ' + seasonsSummary(overlap) + ' — probabile persona diversa' : '✅ Nessuna stagione in comune — probabile stesso giocatore rinominato' }}
              </p>
            }
            <button class="dismiss-btn" [disabled]="mergeBusy()" (click)="dismissPair(pair)">
              {{ dismissingKey() === pairKey(pair) ? 'Rifiuto in corso…' : 'Rifiuta — non è la stessa persona' }}
            </button>
          </div>
        }
        @empty {
          @if (!loadingMergeCandidates()) {
            <p class="text-muted" style="padding:20px;">Nessuna coppia sospetta trovata.</p>
          }
        }
      </div>

      <!-- Unioni sospette (nome identico, ruoli incompatibili) -->
      <div class="section-title">🧬 Unioni da verificare (ruoli incompatibili)</div>
      <div class="card mb-4 merge-panel">
        <p class="text-muted" style="padding:14px 16px 0; font-size:12px; margin:0;">
          Giocatori con nome ESATTAMENTE identico (mai passati dal controllo sopra, che confronta solo nomi
          diversi) ma con ruoli che non possono coesistere in una carriera reale — quasi sempre due persone
          diverse unite per coincidenza di cognome durante un import storico.
        </p>
        <div class="merge-toolbar">
          <button
            pButton label="Ricontrolla" size="small" class="p-button-outlined"
            [loading]="loadingRoleConflicts()" (click)="loadRoleConflicts()"
          ></button>
          <span class="text-muted" style="font-size:12px">
            {{ highSeverityConflicts().length }} da controllare ora
            @if (lowSeverityConflicts().length) {
              · {{ lowSeverityConflicts().length }} probabili evoluzioni di ruolo (nascoste)
              <button class="dismiss-btn" style="margin-left:6px" (click)="showLowSeverity.set(!showLowSeverity())">
                {{ showLowSeverity() ? 'nascondi' : 'mostra comunque' }}
              </button>
            }
          </span>
        </div>
        @for (c of (showLowSeverity() ? roleConflicts() : highSeverityConflicts()); track c.player_id) {
          <div class="merge-pair">
            <div class="merge-row">
              <span class="merge-name">{{ c.player_name }}</span>
              @if (!c.fanta_id) {
                <span class="badge badge-red" style="font-size:10px">vuoto</span>
              }
              @if (c.severity === 'bassa') {
                <span class="text-muted" style="font-size:11px">(probabile evoluzione di ruolo)</span>
              }
            </div>
            <div class="role-conflict-entries">
              @for (e of c.entries; track e.source + e.row_id) {
                <span class="role-conflict-entry" [class.is-anchor]="e.source !== 'archive'">
                  <span class="role-badge role-{{ e.role }}">{{ e.role }}</span>
                  {{ e.season_label }} — {{ e.team || '?' }}
                  <span class="text-muted">({{ e.source === 'archive' ? 'archivio storico' : 'excel/live' }})</span>
                </span>
              }
            </div>
            <div class="role-conflict-actions">
              @for (role of distinctRoles(c); track role) {
                <button
                  pButton size="small" class="p-button-outlined"
                  [label]="'Separa ruolo ' + role + ' in un nuovo giocatore'"
                  [disabled]="splittingKey() !== null || confirmingKey() !== null || c.anchor_roles.includes(role)"
                  [loading]="splittingKey() === (c.player_id + '-' + role)"
                  (click)="splitRole(c, role)"
                ></button>
              }
              <button
                pButton size="small" class="p-button-outlined confirm-btn"
                label="✅ È la stessa persona — consolida"
                [disabled]="splittingKey() !== null || confirmingKey() !== null"
                [loading]="confirmingKey() === c.player_id"
                (click)="confirmRoleConflict(c)"
              ></button>
            </div>
          </div>
        }
        @if (!loadingRoleConflicts() && !roleConflicts().length) {
          <p class="text-muted" style="padding:20px;">Nessuna unione sospetta trovata.</p>
        }
      </div>

      <!-- Merge manuale -->
      <div class="section-title">🔍 Unisci manualmente</div>
      <div class="card mb-4 merge-panel">
        <p class="text-muted" style="padding:14px 16px 0; font-size:12px; margin:0;">
          Per i casi che il ricontrollo automatico non trova perché il cambio nome è troppo diverso.
        </p>
        <div class="manual-pick">
          <p-dropdown
            [options]="allPlayersOptions()"
            [(ngModel)]="manualPlayerAId"
            placeholder="Cerca primo giocatore..."
            [filter]="true"
            filterBy="label"
            [showClear]="true"
            appendTo="body"
            styleClass="manual-drop"
          />
          <span class="text-muted">+</span>
          <p-dropdown
            [options]="allPlayersOptions()"
            [(ngModel)]="manualPlayerBId"
            placeholder="Cerca secondo giocatore..."
            [filter]="true"
            filterBy="label"
            [showClear]="true"
            appendTo="body"
            styleClass="manual-drop"
          />
        </div>
        @if (manualPair(); as pair) {
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
                  [disabled]="mergeBusy()"
                  [loading]="mergingKey() === pairKey(pair)"
                  (click)="mergeManualInto(p, pair)"
                ></button>
              </div>
            }
          </div>
        } @else if (manualPlayerAId && manualPlayerBId) {
          <p class="text-muted" style="padding:10px 16px;">Seleziona due giocatori diversi.</p>
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

    .section-link { display: inline-block; margin-top: 6px; font-size: 13px; font-weight: 600; text-decoration: none; }
    .section-link:hover { text-decoration: underline; }

    .filter-drop { min-width: 160px; }

    .sync-panel { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
    .sync-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .matchday-input { width: 170px; }
    .refresh-btn { background: none; border: none; cursor: pointer; padding: 0 0 0 4px; font-size: 12px; }
    .conclusion-report {
      padding: 10px 12px; border-radius: 8px; font-size: 12px;
      background: var(--bg-subtle, rgba(255,255,255,.05)); display: flex; flex-direction: column; gap: 4px;
    }

    .mb-4 { margin-bottom: 24px; }

    .merge-panel { padding: 0; }
    .merge-toolbar { display: flex; align-items: center; gap: 10px; padding: 14px 16px; border-bottom: 1px solid var(--border-subtle); }
    .merge-pair { padding: 10px 16px; border-bottom: 1px solid var(--border-subtle); }
    .merge-pair:last-child { border-bottom: none; }
    .merge-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; flex-wrap: wrap; }
    .merge-row.empty-row { opacity: 0.6; }
    .merge-name { font-weight: 600; font-size: 13px; min-width: 140px; }
    .merge-stats { font-size: 12px; flex: 1; min-width: 200px; }
    .role-conflict-entries { display: flex; flex-wrap: wrap; gap: 6px; padding: 4px 0 8px; }
    .role-conflict-entry {
      font-size: 11px; padding: 3px 8px; border-radius: 6px;
      background: var(--bg-subtle, rgba(255,255,255,.05)); display: inline-flex; align-items: center; gap: 5px;
    }
    .role-conflict-entry.is-anchor { border: 1px solid rgba(76,175,80,.4); }
    .role-conflict-actions { display: flex; gap: 8px; flex-wrap: wrap; padding-bottom: 8px; }
    .confirm-btn { margin-left: auto; }
    .dismiss-btn {
      background: none; border: none; cursor: pointer; color: var(--text-muted);
      font-size: 12px; padding: 4px 0 0; text-decoration: underline;
    }
    .dismiss-btn:hover { color: var(--text-negative, #e05260); }
    .text-negative { color: var(--text-negative, #e05260); }
    .dismiss-btn:disabled { cursor: not-allowed; opacity: 0.5; text-decoration: none; }

    .manual-pick { display: flex; align-items: center; gap: 10px; padding: 14px 16px; flex-wrap: wrap; }
    .manual-drop { min-width: 220px; }

    .conflict-panel { padding: 0; border: 1px solid var(--border-subtle); }
    .conflict-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 12px 16px; border-bottom: 1px solid var(--border-subtle); font-size: 13px;
    }
    .conflict-item { padding: 10px 16px; border-bottom: 1px solid var(--border-subtle); }
    .conflict-item:last-of-type { border-bottom: none; }
    .conflict-meta { font-size: 12px; margin-bottom: 6px; }
    .conflict-row { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; font-size: 12px; padding: 2px 0; }
    .conflict-col { min-width: 140px; font-weight: 600; }
    .conflict-val { flex: 1; }
    .conflict-choice { display: flex; gap: 8px; margin-top: 8px; }
    .conflict-unresolved { padding: 10px 16px; margin: 0; font-size: 12px; color: var(--text-negative, #e05260); }
    .conflict-footer { padding: 12px 16px; }
  `],
})
export class AdminComponent implements OnInit {
  seasonOptions = signal<any[]>([]);
  currentSeasonId = signal<number | null>(null);
  currentSeasonLabel = signal<string | null>(null);
  detectedMatchDay = signal<number | null>(null);
  settingCurrent = signal(false);
  syncingPrices = signal(false);
  syncingVotes = signal(false);
  checkingRecovery = signal(false);
  conclusionReady = signal(false);
  conclusionMissing = signal<string[]>([]);
  concludingSeason = signal(false);
  conclusionReport = signal<any>(null);
  importingArchive = signal<'stats' | 'prices' | 'votes' | null>(null);
  message = signal('');
  messageIsError = signal(false);

  mergeCandidates = signal<any[]>([]);
  loadingMergeCandidates = signal(false);
  mergingKey = signal<string | null>(null);
  dismissingKey = signal<string | null>(null);
  roleConflicts = signal<any[]>([]);
  loadingRoleConflicts = signal(false);
  splittingKey = signal<string | null>(null);
  confirmingKey = signal<number | null>(null);
  showLowSeverity = signal(false);
  allPlayersForMerge = signal<any[]>([]);
  pendingMerge = signal<PendingMerge | null>(null);
  resolvingConflict = signal(false);

  syncSeasonId: number | null = null;
  syncMatchDay: number | null = null;
  manualPlayerAId: number | null = null;
  manualPlayerBId: number | null = null;

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.loadSeasons();
    this.loadDetectedMatchday();
    this.loadMergeCandidates();
    this.loadRoleConflicts();
    this.loadAllPlayersForMerge();
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
        this.loadConclusionStatus();
      },
    });
  }

  loadConclusionStatus() {
    const seasonId = this.currentSeasonId();
    if (!seasonId) {
      this.conclusionReady.set(false);
      this.conclusionMissing.set([]);
      return;
    }
    this.api.getSeasonConclusionStatus(seasonId).subscribe({
      next: res => {
        this.conclusionReady.set(res.ready);
        this.conclusionMissing.set(res.missing);
      },
      error: () => {
        this.conclusionReady.set(false);
        this.conclusionMissing.set([]);
      },
    });
  }

  concludeSeason() {
    const seasonId = this.currentSeasonId();
    if (!seasonId || !this.conclusionReady()) return;
    const confirmed = confirm(
      `Confermi la chiusura della stagione "${this.currentSeasonLabel()}"?\n\n` +
      "Verrà creata la stagione successiva con le stesse squadre (crediti azzerati, rosa vuota) " +
      "collegate a quelle attuali, impostata come corrente, e questa stagione verrà archiviata " +
      "definitivamente nello Storico. Operazione non banale da annullare."
    );
    if (!confirmed) return;

    this.concludingSeason.set(true);
    this.conclusionReport.set(null);
    this.api.concludeSeason(seasonId).subscribe({
      next: res => {
        this.concludingSeason.set(false);
        this.conclusionReport.set(res);
        this.setMessage(`Stagione "${res.new_season.label}" creata e impostata come corrente.`, false);
        this.loadSeasons();
      },
      error: err => {
        this.concludingSeason.set(false);
        this.setMessage(err.error?.detail || 'Errore durante la chiusura della stagione.', true);
      },
    });
  }

  importArchive(dataType: 'stats' | 'prices' | 'votes') {
    if (!this.syncSeasonId) return;
    this.importingArchive.set(dataType);
    this.api.importSeasonHistory(this.syncSeasonId, dataType, true).subscribe({
      next: res => {
        this.importingArchive.set(null);
        this.setMessage(
          res.imported ? `${dataType}: ${res.rows} righe importate.` : (res.message || 'Import completato.'),
          !res.ok,
        );
      },
      error: err => {
        this.importingArchive.set(null);
        this.setMessage(err.error?.detail || `Errore durante l'import ${dataType}.`, true);
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

  loadRoleConflicts() {
    this.loadingRoleConflicts.set(true);
    this.api.getPlayerRoleConflicts().subscribe({
      next: conflicts => {
        this.roleConflicts.set(conflicts);
        this.loadingRoleConflicts.set(false);
      },
      error: err => {
        this.loadingRoleConflicts.set(false);
        this.setMessage(err.error?.detail || 'Errore nel controllo dei ruoli incompatibili.', true);
      },
    });
  }

  highSeverityConflicts() {
    return this.roleConflicts().filter(c => c.severity === 'alta');
  }

  lowSeverityConflicts() {
    return this.roleConflicts().filter(c => c.severity !== 'alta');
  }

  distinctRoles(c: any): string[] {
    return Array.from(new Set(c.entries.map((e: any) => e.role))) as string[];
  }

  splitRole(c: any, role: string) {
    const key = `${c.player_id}-${role}`;
    this.splittingKey.set(key);
    this.api.splitPlayerRole(c.player_id, role).subscribe({
      next: res => {
        this.splittingKey.set(null);
        this.setMessage(`Ruolo "${role}" separato in un nuovo giocatore (${res.moved_rows} stagioni spostate).`, false);
        this.loadRoleConflicts();
      },
      error: err => {
        this.splittingKey.set(null);
        this.setMessage(err.error?.detail || 'Errore durante la separazione.', true);
      },
    });
  }

  confirmRoleConflict(c: any) {
    this.confirmingKey.set(c.player_id);
    this.api.confirmRoleConflict(c.player_id).subscribe({
      next: () => {
        this.confirmingKey.set(null);
        this.roleConflicts.set(this.roleConflicts().filter(x => x.player_id !== c.player_id));
        this.setMessage(`"${c.player_name}" confermato come una sola persona.`, false);
      },
      error: err => {
        this.confirmingKey.set(null);
        this.setMessage(err.error?.detail || 'Errore durante la conferma.', true);
      },
    });
  }

  pairKey(pair: any): string {
    return `${pair.player_a.id}-${pair.player_b.id}`;
  }

  mergeBusy(): boolean {
    return this.mergingKey() !== null || this.dismissingKey() !== null;
  }

  seasonsSummary(seasons: { label: string; team: string | null }[]): string {
    return seasons.map(s => s.team ? `${s.label} (${s.team})` : s.label).join(', ');
  }

  seasonOverlap(pair: any): { label: string; team: string | null }[] | null {
    const a: { season_id: number }[] = pair.player_a.seasons ?? [];
    const b: { season_id: number }[] = pair.player_b.seasons ?? [];
    if (!a.length || !b.length) return null;
    const bIds = new Set(b.map(s => s.season_id));
    return a.filter(s => bIds.has(s.season_id)) as any;
  }

  mergeInto(keep: any, pair: any) {
    const remove = pair.player_a.id === keep.id ? pair.player_b : pair.player_a;
    this.mergingKey.set(this.pairKey(pair));
    this.submitMerge(keep.id, remove.id, keep.name, remove.name, []);
  }

  loadAllPlayersForMerge() {
    this.api.getPlayers().subscribe({ next: players => this.allPlayersForMerge.set(players) });
  }

  allPlayersOptions() {
    return this.allPlayersForMerge().map(p => ({ label: p.name, value: p.id }));
  }

  manualPair(): { player_a: any; player_b: any } | null {
    if (!this.manualPlayerAId || !this.manualPlayerBId || this.manualPlayerAId === this.manualPlayerBId) {
      return null;
    }
    const a = this.allPlayersForMerge().find(p => p.id === this.manualPlayerAId);
    const b = this.allPlayersForMerge().find(p => p.id === this.manualPlayerBId);
    return a && b ? { player_a: a, player_b: b } : null;
  }

  mergeManualInto(keep: any, pair: any) {
    const remove = pair.player_a.id === keep.id ? pair.player_b : pair.player_a;
    this.mergingKey.set(this.pairKey(pair));
    this.submitMerge(keep.id, remove.id, keep.name, remove.name, [], () => {
      this.manualPlayerAId = null;
      this.manualPlayerBId = null;
      this.loadAllPlayersForMerge();
    });
  }

  private submitMerge(
    keepId: number,
    removeId: number,
    keepName: string,
    removeName: string,
    resolutions: { table: string; key_values: Record<string, number>; winner: 'keep' | 'remove' }[],
    onMerged?: () => void,
  ) {
    this.api.mergePlayers(keepId, removeId, resolutions).subscribe({
      next: res => {
        this.mergingKey.set(null);
        this.resolvingConflict.set(false);
        if (res.merged) {
          this.pendingMerge.set(null);
          this.setMessage(`"${removeName}" unito a "${keepName}".`, false);
          onMerged?.();
        } else {
          this.pendingMerge.set({
            keepId, removeId, keepName, removeName,
            items: (res.conflicts ?? []).map((c: any) => ({ ...c, choice: null })),
            unresolved: res.unresolved ?? [],
          });
          this.setMessage(
            `Merge parziale: ${res.conflicts?.length ?? 0} conflitto/i da risolvere prima di completare l'unione di "${removeName}" in "${keepName}".`,
            true,
          );
        }
        this.loadMergeCandidates();
      },
      error: err => {
        this.mergingKey.set(null);
        this.resolvingConflict.set(false);
        this.setMessage(err.error?.detail || 'Errore durante il merge.', true);
      },
    });
  }

  chooseConflictWinner(item: ConflictItem, winner: 'keep' | 'remove') {
    item.choice = winner;
  }

  allConflictsChosen(): boolean {
    const pm = this.pendingMerge();
    return !!pm && pm.items.length > 0 && pm.items.every(i => !!i.choice);
  }

  confirmConflictResolutions() {
    const pm = this.pendingMerge();
    if (!pm || !this.allConflictsChosen()) return;
    this.resolvingConflict.set(true);
    const resolutions = pm.items.map(i => ({ table: i.table, key_values: i.key_values, winner: i.choice! }));
    this.submitMerge(pm.keepId, pm.removeId, pm.keepName, pm.removeName, resolutions);
  }

  cancelConflictResolution() {
    this.pendingMerge.set(null);
  }

  dismissPair(pair: any) {
    this.dismissingKey.set(this.pairKey(pair));
    this.api.dismissPlayerMerge(pair.player_a.id, pair.player_b.id).subscribe({
      next: () => {
        this.dismissingKey.set(null);
        this.mergeCandidates.set(this.mergeCandidates().filter(p => this.pairKey(p) !== this.pairKey(pair)));
        this.setMessage('Coppia rifiutata: non verrà più suggerita.', false);
      },
      error: err => {
        this.dismissingKey.set(null);
        this.setMessage(err.error?.detail || 'Errore nel rifiuto.', true);
      },
    });
  }

  private setMessage(text: string, isError: boolean) {
    this.message.set(text);
    this.messageIsError.set(isError);
  }
}
