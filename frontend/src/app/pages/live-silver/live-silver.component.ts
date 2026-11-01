import { Component, OnInit, OnDestroy, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-live-silver',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="fade-up">
      <!-- Header -->
      <div class="page-header">
        <div>
          <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
            <h1 class="page-title">⚡ Live SILVER</h1>
            <span class="badge badge-silver">TUTTI CONTRO TUTTI</span>
            @if (data(); as d) {
              <span class="badge" [class.badge-green]="!d.is_calculated" [class.badge-gold]="d.is_calculated">
                {{ d.is_calculated ? '📦 GIORNATA CALCOLATA' : '🔴 LIVE / SIMULAZIONE ATTIVA' }}
              </span>
            }
          </div>
          <p class="page-sub">
            Calcolo live in tempo reale delle formazioni schierate in SILVER (voti, bonus/malus, sostituzioni automatiche, modificatore difesa e fasce gol)
          </p>
        </div>

        <div class="header-actions">
          @if (data(); as d) {
            <div class="day-selector">
              <label for="matchday-select">Giornata Serie A:</label>
              <select
                id="matchday-select"
                class="filter-select"
                [ngModel]="selectedDay()"
                (ngModelChange)="onDayChange($event)"
              >
                @for (day of d.available_days; track day.serie_a_day) {
                  <option [ngValue]="day.serie_a_day">
                    {{ day.serie_a_day }}ª Serie A ({{ day.comp_round }}ª Silver){{ day.is_calculated ? ' ✓' : '' }}
                  </option>
                }
              </select>
            </div>
          }

          <button
            class="btn-action"
            [class.active-auto]="autoRefresh()"
            (click)="toggleAutoRefresh()"
            title="Aggiornamento automatico ogni 60 secondi"
          >
            {{ autoRefresh() ? '⏱️ Auto (60s) ON' : '⏱️ Auto OFF' }}
          </button>

          <button class="btn-action btn-refresh" (click)="refreshNow()" [disabled]="loading()">
            {{ loading() ? '⏳ Aggiornamento...' : '🔄 Aggiorna Live' }}
          </button>
        </div>
      </div>

      @if (data(); as d) {
        <!-- KPI Cards -->
        <div class="kpi-grid">
          <div class="stat-card kpi-card kpi-top">
            <div class="kpi-label">🔥 Miglior Punteggio Live</div>
            @if (topTeam(); as top) {
              <div class="kpi-value text-positive">{{ top.tot_simulated | number:'1.1-2' }}</div>
              <div class="kpi-sub">
                <strong>{{ top.name }}</strong>
                @if (top.league_level) {
                  <span class="badge" [ngClass]="leagueBadgeClass(top.league_level)" style="margin-left:6px">{{ top.league_level }}</span>
                }
              </div>
            } @else {
              <div class="kpi-value">—</div>
            }
          </div>

          <div class="stat-card kpi-card kpi-low">
            <div class="kpi-label">💀 Peggior Punteggio Live</div>
            @if (bottomTeam(); as bot) {
              <div class="kpi-value text-negative">{{ bot.tot_simulated | number:'1.1-2' }}</div>
              <div class="kpi-sub">
                <strong>{{ bot.name }}</strong>
                @if (bot.league_level) {
                  <span class="badge" [ngClass]="leagueBadgeClass(bot.league_level)" style="margin-left:6px">{{ bot.league_level }}</span>
                }
              </div>
            } @else {
              <div class="kpi-value">—</div>
            }
          </div>

          <div class="stat-card kpi-card">
            <div class="kpi-label">📊 Media Giornata SILVER</div>
            <div class="kpi-value">{{ avgScore() | number:'1.2-2' }}</div>
            <div class="kpi-sub">{{ d.standings.length }} squadre partecipanti</div>
          </div>

          <div class="stat-card kpi-card">
            <div class="kpi-label">📡 Stato Serie A ({{ d.serie_a_day }}ª Giornata)</div>
            <div class="kpi-value" style="font-size:18px">
              {{ d.serie_a_status?.finished_count || 0 }}/20 concluse
              @if (d.serie_a_status?.playing_count) {
                <span class="text-positive" style="font-size:14px">({{ d.serie_a_status.playing_count }} live)</span>
              }
            </div>
            <div class="kpi-sub">
              {{ d.serie_a_status?.votes_loaded || 0 }} calciatori a voto • Agg. {{ d.updated_at }}
            </div>
          </div>
        </div>

        <!-- Filtri tabella -->
        <div class="card filter-bar">
          <div class="filter-tabs">
            @for (lg of ['TUTTE', 'GOLD', 'BRONZE', 'CARBON']; track lg) {
              <button
                class="tab-pill"
                [class.active]="leagueFilter() === lg"
                (click)="leagueFilter.set(lg)"
              >
                {{ lg }}
              </button>
            }
          </div>

          <div class="filter-right">
            <input
              type="text"
              class="search-input"
              placeholder="🔍 Cerca squadra o allenatore..."
              [ngModel]="searchQuery()"
              (ngModelChange)="searchQuery.set($event)"
            />
            <button class="btn-link" (click)="toggleAllExpanded()">
              {{ allExpanded() ? '🔼 Chiudi tutte' : '🔽 Espandi tutte' }}
            </button>
          </div>
        </div>

        <!-- Classifica Live SILVER -->
        <div class="card" style="padding:0;overflow:hidden">
          <div class="table-wrap">
            <table class="live-table">
              <thead>
                <tr>
                  <th style="width:52px;text-align:center">#</th>
                  <th>Squadra</th>
                  <th style="text-align:center">Lega</th>
                  <th style="text-align:center">Modulo</th>
                  <th style="text-align:center" title="Giocatori con voto reale su 11">Votati</th>
                  <th style="text-align:right" title="Somma fantavoti dei giocatori in campo">Punti Campo</th>
                  <th style="text-align:center" title="Modificatore Difesa">Mod. Dif</th>
                  <th style="text-align:right">Totale Live</th>
                  <th style="text-align:center">Gol</th>
                  @if (d.is_calculated) {
                    <th style="text-align:right" title="Punteggio ufficiale calcolato su Leghe">Ufficiale</th>
                  }
                  <th style="width:44px"></th>
                </tr>
              </thead>
              <tbody>
                @for (team of filteredTeams(); track team.tid) {
                  <tr
                    class="team-row"
                    [class.row-expanded]="isExpanded(team.tid)"
                    [class.row-top]="team.is_top_score"
                    (click)="toggleTeam(team.tid)"
                  >
                    <td style="text-align:center">
                      <span
                        class="rank-badge"
                        [class.rank-1]="team.position === 1"
                        [class.rank-2]="team.position === 2"
                        [class.rank-3]="team.position === 3"
                      >
                        {{ team.position }}
                      </span>
                    </td>

                    <td>
                      <div class="team-cell">
                        <div class="team-info">
                          <span class="team-name">{{ team.name }}</span>
                          @if (team.coaches?.length) {
                            <span class="team-coaches">{{ team.coaches.join(', ') }}</span>
                          }
                        </div>
                        @if (team.substitutions?.length) {
                          <span class="sub-count-badge" title="Sostituzioni attive">
                            🔄 {{ team.substitutions.length }}
                          </span>
                        }
                      </div>
                    </td>

                    <td style="text-align:center">
                      @if (team.league_level) {
                        <span class="badge" [ngClass]="leagueBadgeClass(team.league_level)">
                          {{ team.league_level }}
                        </span>
                      } @else {
                        <span class="text-muted">—</span>
                      }
                    </td>

                    <td style="text-align:center">
                      @if (team.has_lineup) {
                        <span class="module-pill">{{ team.module }}</span>
                        @if (team.module !== team.orig_module && team.orig_module) {
                          <div class="module-orig" title="Modulo schierato originariamente">
                            da {{ team.orig_module }}
                          </div>
                        }
                      } @else {
                        <span class="badge badge-red">Non schierata</span>
                      }
                    </td>

                    <td style="text-align:center">
                      @if (team.has_lineup) {
                        <span
                          class="voted-pill"
                          [class.voted-complete]="team.voted_count === 11"
                          [class.voted-partial]="team.voted_count > 0 && team.voted_count < 11"
                        >
                          {{ team.voted_count }}/11
                        </span>
                      } @else {
                        <span class="text-muted">—</span>
                      }
                    </td>

                    <td style="text-align:right;font-variant-numeric:tabular-nums">
                      @if (team.has_lineup) {
                        {{ team.tot_field_votes | number:'1.1-2' }}
                      } @else {
                        <span class="text-muted">—</span>
                      }
                    </td>

                    <td style="text-align:center;font-variant-numeric:tabular-nums">
                      @if (team.has_lineup) {
                        <span
                          class="mod-pill"
                          [class.mod-pos]="team.mod_points > 0"
                          [class.mod-neg]="team.mod_points < 0"
                        >
                          {{ team.mod_points > 0 ? '+' : '' }}{{ team.mod_points | number:'1.1-1' }}
                        </span>
                      } @else {
                        <span class="text-muted">—</span>
                      }
                    </td>

                    <td style="text-align:right">
                      @if (team.has_lineup) {
                        <span class="total-score">{{ team.tot_simulated | number:'1.1-2' }}</span>
                      } @else {
                        <span class="text-muted">0.0</span>
                      }
                    </td>

                    <td style="text-align:center">
                      @if (team.has_lineup) {
                        <span class="goals-pill" [class.goals-positive]="team.goals > 0">
                          ⚽ {{ team.goals }}
                        </span>
                      } @else {
                        <span class="text-muted">—</span>
                      }
                    </td>

                    @if (d.is_calculated) {
                      <td style="text-align:right;font-variant-numeric:tabular-nums;color:var(--text-secondary)">
                        {{ team.tot_official !== null && team.tot_official !== undefined ? (team.tot_official | number:'1.1-2') : '—' }}
                      </td>
                    }

                    <td style="text-align:center">
                      <span class="expand-arrow" [class.open]="isExpanded(team.tid)">▾</span>
                    </td>
                  </tr>

                  <!-- Dettaglio Formazione Espanso -->
                  @if (isExpanded(team.tid)) {
                    <tr class="detail-row">
                      <td [attr.colspan]="d.is_calculated ? 11 : 10" style="padding:0">
                        <div class="lineup-detail">
                          @if (!team.has_lineup) {
                            <div class="empty-lineup">
                              ⚠️ {{ team.error || 'Nessuna formazione schierata trovata per questa squadra nella giornata selezionata.' }}
                            </div>
                          } @else {
                            <!-- Box riepilogo Modificatore, Sostituzioni e Gol -->
                            <div class="summary-boxes">
                              <div class="summary-box">
                                <div class="summary-box-title">🛡️ Modificatore Difesa</div>
                                <div class="summary-box-val">{{ team.mod_desc }}</div>
                              </div>
                              <div class="summary-box">
                                <div class="summary-box-title">⚽ Calcolo Gol</div>
                                <div class="summary-box-val">{{ team.goals_desc }}</div>
                              </div>
                              <div class="summary-box">
                                <div class="summary-box-title">
                                  🔄 Sostituzioni ({{ team.substitutions?.length || 0 }}/{{ d.league_rules?.max_substitutions || 5 }})
                                </div>
                                @if (team.substitutions?.length) {
                                  <div class="subs-list">
                                    @for (s of team.substitutions; track s.out_name + s.in_name) {
                                      <div class="sub-item">
                                        🔄 <strong>{{ s.in_name }}</strong> ({{ s.in_role || s.role }})
                                        per <span class="text-secondary">{{ s.out_name }} ({{ s.out_role || s.role }})</span>
                                      </div>
                                    }
                                  </div>
                                } @else {
                                  <div class="summary-box-val text-muted">Nessuna sostituzione effettuata</div>
                                }
                              </div>
                            </div>

                            <div class="lineup-columns">
                              <!-- 11 In Campo -->
                              <div class="lineup-col">
                                <h4 class="col-title">
                                  🏟️ Undici in Campo (Modulo attivo: {{ team.module }})
                                </h4>
                                <table class="players-mini-table">
                                  <thead>
                                    <tr>
                                      <th style="width:40px">R</th>
                                      <th>Giocatore</th>
                                      <th>Club</th>
                                      <th style="text-align:center">Voto</th>
                                      <th>Bonus / Malus</th>
                                      <th style="text-align:right">FantaVoto</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    @for (p of team.field_players; track p.pid + '_' + $index) {
                                      <tr [class.subbed-in-row]="p.is_sub" [class.provisional-row]="p.is_base_vote">
                                        <td>
                                          <span class="role-badge" [ngClass]="'role-' + p.role">{{ p.role }}</span>
                                        </td>
                                        <td>
                                          <div class="player-name-wrap">
                                            <span class="player-name">{{ p.name }}</span>
                                            @if (p.is_sub) {
                                              <span class="tag-sub-in" [title]="'Entrato per ' + (p.replaced_name || '')">
                                                SUB IN
                                              </span>
                                            }
                                            @if (p.is_base_vote) {
                                              <span class="tag-prov" title="Giocatore non ancora a voto: conteggiato 6.0 provvisorio">
                                                ⏳ {{ p.status || '6.0 provv.' }}
                                              </span>
                                            } @else if (p.vote === null) {
                                              <span class="tag-sv">{{ p.status || 'S.V.' }}</span>
                                            }
                                          </div>
                                        </td>
                                        <td class="text-secondary" style="font-size:12px">{{ p.club || '—' }}</td>
                                        <td style="text-align:center;font-variant-numeric:tabular-nums">
                                          {{ p.vote !== null && p.vote !== undefined ? (p.vote | number:'1.1-2') : 'S.V.' }}
                                        </td>
                                        <td>
                                          @if (p.events_formatted) {
                                            <span class="bonus-pills">{{ p.events_formatted }}</span>
                                          } @else {
                                            <span class="text-muted">—</span>
                                          }
                                        </td>
                                        <td style="text-align:right;font-weight:700;font-variant-numeric:tabular-nums">
                                          <span
                                            [class.text-positive]="!p.is_base_vote && p.fanta_vote !== null && p.fanta_vote >= 6.5"
                                            [class.text-negative]="!p.is_base_vote && p.fanta_vote !== null && p.fanta_vote < 6.0"
                                            [class.text-muted]="p.is_base_vote || p.fanta_vote === null"
                                          >
                                            {{ p.fanta_vote !== null && p.fanta_vote !== undefined ? (p.fanta_vote | number:'1.1-2') : 'S.V.' }}
                                          </span>
                                        </td>
                                      </tr>
                                    }
                                  </tbody>
                                </table>
                              </div>

                              <!-- Panchina -->
                              <div class="lineup-col">
                                <h4 class="col-title">🪑 Panchina</h4>
                                <table class="players-mini-table">
                                  <thead>
                                    <tr>
                                      <th style="width:40px">R</th>
                                      <th>Giocatore</th>
                                      <th>Club</th>
                                      <th style="text-align:center">Voto</th>
                                      <th>Bonus / Malus</th>
                                      <th style="text-align:right">FantaVoto</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    @for (b of team.bench_players; track b.pid + '_' + $index) {
                                      <tr [class.entered-bench-row]="b.status === 'SUB IN' || isSubbedIn(team, b.name)">
                                        <td>
                                          <span class="role-badge" [ngClass]="'role-' + b.role">{{ b.role }}</span>
                                        </td>
                                        <td>
                                          <div class="player-name-wrap">
                                            <span class="player-name">{{ b.name }}</span>
                                            @if (b.status === 'SUB IN' || isSubbedIn(team, b.name)) {
                                              <span class="tag-sub-in">ENTRATO</span>
                                            } @else if (b.status === 'in corso' || b.status === 'in attesa') {
                                              <span class="tag-prov">{{ b.status }}</span>
                                            }
                                          </div>
                                        </td>
                                        <td class="text-secondary" style="font-size:12px">{{ b.club || '—' }}</td>
                                        <td style="text-align:center;font-variant-numeric:tabular-nums">
                                          {{ b.vote !== null && b.vote !== undefined ? (b.vote | number:'1.1-2') : 'S.V.' }}
                                        </td>
                                        <td>
                                          @if (b.events_formatted) {
                                            <span class="bonus-pills">{{ b.events_formatted }}</span>
                                          } @else {
                                            <span class="text-muted">—</span>
                                          }
                                        </td>
                                        <td style="text-align:right;font-weight:600;font-variant-numeric:tabular-nums">
                                          {{ b.fanta_vote !== null && b.fanta_vote !== undefined ? (b.fanta_vote | number:'1.1-2') : 'S.V.' }}
                                        </td>
                                      </tr>
                                    }
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          }
                        </div>
                      </td>
                    </tr>
                  }
                }
              </tbody>
            </table>
          </div>
        </div>
      } @else if (loading()) {
        <div class="card loading-state">
          <div class="spinner"></div>
          <div>Recupero formazioni SILVER e calcolo punteggi live in corso...</div>
        </div>
      } @else if (error()) {
        <div class="card error-state">
          <div style="font-size:18px;font-weight:700;margin-bottom:8px">⚠️ Errore nel caricamento Live SILVER</div>
          <div class="text-secondary" style="margin-bottom:14px">{{ error() }}</div>
          <button class="btn-action btn-refresh" (click)="refreshNow()">Riprova</button>
        </div>
      }
    </div>
  `,
  styles: [`
    .page-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }
    .page-title {
      font-size: 26px;
      font-weight: 800;
      letter-spacing: -0.02em;
      margin: 0;
    }
    .page-sub {
      color: var(--text-secondary);
      font-size: 13px;
      margin-top: 4px;
    }
    .header-actions {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .day-selector {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: var(--text-secondary);
    }
    .filter-select {
      background: var(--bg-elevated);
      color: var(--text-primary);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-sm);
      padding: 7px 12px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }
    .btn-action {
      background: var(--bg-elevated);
      color: var(--text-primary);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-sm);
      padding: 7px 14px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all var(--transition);
    }
    .btn-action:hover:not(:disabled) {
      border-color: var(--accent-blue);
      background: var(--bg-card);
    }
    .btn-action.active-auto {
      background: rgba(63, 185, 80, 0.15);
      border-color: var(--accent-green);
      color: var(--accent-green);
    }
    .btn-refresh {
      background: var(--accent-green);
      border-color: var(--accent-green);
      color: #0d1117;
      font-weight: 700;
    }
    .btn-refresh:hover:not(:disabled) {
      opacity: 0.92;
      background: var(--accent-green);
      border-color: var(--accent-green);
    }
    .btn-action:disabled {
      opacity: 0.6;
      cursor: wait;
    }

    /* KPI Grid */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin-bottom: 16px;
    }
    .kpi-card {
      padding: 16px 20px;
    }
    .kpi-label {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 6px;
    }
    .kpi-value {
      font-size: 26px;
      font-weight: 800;
      line-height: 1.2;
      font-variant-numeric: tabular-nums;
    }
    .kpi-sub {
      font-size: 12px;
      color: var(--text-secondary);
      margin-top: 6px;
      display: flex;
      align-items: center;
      flex-wrap: wrap;
    }

    /* Filter Bar */
    .filter-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 12px 16px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }
    .filter-tabs {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .tab-pill {
      background: var(--bg-elevated);
      color: var(--text-secondary);
      border: 1px solid var(--border-color);
      border-radius: 20px;
      padding: 5px 14px;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      transition: all var(--transition);
    }
    .tab-pill.active {
      background: var(--accent-green);
      color: #0d1117;
      border-color: var(--accent-green);
    }
    .filter-right {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
    .search-input {
      background: var(--bg-elevated);
      border: 1px solid var(--border-color);
      color: var(--text-primary);
      border-radius: var(--radius-sm);
      padding: 6px 12px;
      font-size: 13px;
      min-width: 220px;
    }
    .btn-link {
      background: none;
      border: none;
      color: var(--accent-blue);
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
    }
    .btn-link:hover {
      text-decoration: underline;
    }

    /* Table */
    .table-wrap {
      overflow-x: auto;
    }
    .live-table {
      width: 100%;
      border-collapse: collapse;
    }
    .live-table thead th {
      background: var(--bg-elevated);
      color: var(--text-secondary);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 12px 14px;
      border-bottom: 1px solid var(--border-color);
    }
    .team-row {
      border-bottom: 1px solid var(--border-subtle);
      cursor: pointer;
      transition: background var(--transition);
    }
    .team-row:hover {
      background: var(--bg-elevated);
    }
    .team-row.row-expanded {
      background: rgba(88, 166, 255, 0.06);
    }
    .team-row.row-top {
      background: rgba(63, 185, 80, 0.05);
    }
    .team-row td {
      padding: 12px 14px;
      vertical-align: middle;
    }

    .rank-badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 26px;
      height: 26px;
      border-radius: 50%;
      font-size: 12px;
      font-weight: 700;
      background: var(--bg-elevated);
      color: var(--text-secondary);
    }
    .rank-1 {
      background: rgba(255, 215, 0, 0.2);
      color: #ffd700;
      border: 1px solid rgba(255, 215, 0, 0.5);
    }
    .rank-2 {
      background: rgba(192, 192, 192, 0.2);
      color: #e0e0e0;
      border: 1px solid rgba(192, 192, 192, 0.5);
    }
    .rank-3 {
      background: rgba(205, 127, 50, 0.2);
      color: #cd7f32;
      border: 1px solid rgba(205, 127, 50, 0.5);
    }

    .team-cell {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .team-info {
      display: flex;
      flex-direction: column;
    }
    .team-name {
      font-weight: 700;
      color: var(--text-primary);
      font-size: 14px;
    }
    .team-coaches {
      font-size: 11px;
      color: var(--text-secondary);
    }
    .sub-count-badge {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 12px;
      background: rgba(88, 166, 255, 0.14);
      color: var(--accent-blue);
    }
    .module-pill {
      font-family: monospace;
      font-size: 12px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 6px;
      background: var(--bg-elevated);
      border: 1px solid var(--border-color);
    }
    .module-orig {
      font-size: 10px;
      color: var(--accent-orange);
      margin-top: 2px;
    }
    .voted-pill {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 700;
      background: var(--bg-elevated);
      color: var(--text-secondary);
    }
    .voted-complete {
      background: rgba(63, 185, 80, 0.15);
      color: var(--accent-green);
    }
    .voted-partial {
      background: rgba(240, 136, 62, 0.15);
      color: var(--accent-orange);
    }
    .mod-pill {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 700;
      color: var(--text-secondary);
    }
    .mod-pos {
      background: rgba(63, 185, 80, 0.14);
      color: var(--accent-green);
    }
    .mod-neg {
      background: rgba(248, 81, 73, 0.14);
      color: var(--accent-red);
    }
    .total-score {
      font-size: 17px;
      font-weight: 800;
      color: var(--accent-green);
      font-variant-numeric: tabular-nums;
    }
    .goals-pill {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 3px 9px;
      border-radius: 14px;
      font-size: 12px;
      font-weight: 700;
      background: var(--bg-elevated);
      color: var(--text-secondary);
    }
    .goals-positive {
      background: rgba(88, 166, 255, 0.15);
      color: var(--accent-blue);
    }
    .expand-arrow {
      display: inline-block;
      transition: transform 0.2s ease;
      color: var(--text-secondary);
      font-size: 14px;
    }
    .expand-arrow.open {
      transform: rotate(180deg);
      color: var(--accent-blue);
    }

    /* Expanded Detail */
    .detail-row {
      background: var(--bg-surface);
      border-bottom: 2px solid var(--border-color);
    }
    .lineup-detail {
      padding: 18px 20px;
    }
    .empty-lineup {
      padding: 16px;
      color: var(--accent-orange);
      text-align: center;
      font-weight: 600;
    }
    .summary-boxes {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .summary-box {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      padding: 10px 14px;
    }
    .summary-box-title {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      color: var(--text-secondary);
      margin-bottom: 4px;
    }
    .summary-box-val {
      font-size: 13px;
      font-weight: 600;
      color: var(--text-primary);
    }
    .subs-list {
      display: flex;
      flex-direction: column;
      gap: 3px;
      font-size: 12px;
      color: var(--accent-blue);
    }

    .lineup-columns {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
      gap: 16px;
    }
    .lineup-col {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      padding: 14px;
      overflow-x: auto;
    }
    .col-title {
      font-size: 13px;
      font-weight: 700;
      margin-bottom: 10px;
      color: var(--text-primary);
    }
    .players-mini-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .players-mini-table th {
      text-align: left;
      font-size: 10px;
      text-transform: uppercase;
      color: var(--text-muted);
      padding: 6px 8px;
      border-bottom: 1px solid var(--border-color);
    }
    .players-mini-table td {
      padding: 7px 8px;
      border-bottom: 1px solid var(--border-subtle);
    }
    .player-name-wrap {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }
    .player-name {
      font-weight: 600;
    }
    .tag-sub-in {
      font-size: 10px;
      font-weight: 700;
      padding: 1px 6px;
      border-radius: 4px;
      background: rgba(88, 166, 255, 0.18);
      color: var(--accent-blue);
    }
    .tag-prov {
      font-size: 10px;
      font-weight: 600;
      padding: 1px 6px;
      border-radius: 4px;
      background: rgba(240, 136, 62, 0.14);
      color: var(--accent-orange);
    }
    .tag-sv {
      font-size: 10px;
      font-weight: 600;
      padding: 1px 6px;
      border-radius: 4px;
      background: rgba(248, 81, 73, 0.14);
      color: var(--accent-red);
    }
    .subbed-in-row {
      background: rgba(88, 166, 255, 0.04);
    }
    .entered-bench-row {
      opacity: 0.65;
    }
    .bonus-pills {
      font-size: 12px;
    }

    .loading-state, .error-state {
      text-align: center;
      padding: 48px 20px;
      color: var(--text-secondary);
    }
    .spinner {
      width: 32px;
      height: 32px;
      border: 3px solid var(--border-color);
      border-top-color: var(--accent-green);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      margin: 0 auto 14px;
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
  `]
})
export class LiveSilverComponent implements OnInit, OnDestroy {
  private api = inject(ApiService);

  data = signal<any | null>(null);
  loading = signal<boolean>(false);
  error = signal<string | null>(null);

  selectedDay = signal<number | null>(null);
  leagueFilter = signal<string>('TUTTE');
  searchQuery = signal<string>('');
  expandedIds = signal<Set<number>>(new Set());
  autoRefresh = signal<boolean>(false);

  private refreshTimer: any = null;

  filteredTeams = computed(() => {
    const d = this.data();
    if (!d?.standings) return [];
    const lg = this.leagueFilter();
    const q = this.searchQuery().trim().toLowerCase();

    return d.standings.filter((t: any) => {
      if (lg !== 'TUTTE' && (t.league_level || '').toUpperCase() !== lg) {
        return false;
      }
      if (q) {
        const matchName = (t.name || '').toLowerCase().includes(q);
        const matchCoach = (t.coaches || []).join(' ').toLowerCase().includes(q);
        return matchName || matchCoach;
      }
      return true;
    });
  });

  topTeam = computed(() => {
    const teams = (this.data()?.standings || []).filter((t: any) => t.has_lineup);
    if (!teams.length) return null;
    return teams.reduce((best: any, cur: any) =>
      cur.tot_simulated > best.tot_simulated ? cur : best
    , teams[0]);
  });

  bottomTeam = computed(() => {
    const teams = (this.data()?.standings || []).filter((t: any) => t.has_lineup);
    if (!teams.length) return null;
    return teams.reduce((worst: any, cur: any) =>
      cur.tot_simulated < worst.tot_simulated ? cur : worst
    , teams[0]);
  });

  avgScore = computed(() => {
    const teams = (this.data()?.standings || []).filter((t: any) => t.has_lineup);
    if (!teams.length) return 0;
    const sum = teams.reduce((acc: number, t: any) => acc + (t.tot_simulated || 0), 0);
    return sum / teams.length;
  });

  allExpanded = computed(() => {
    const visible = this.filteredTeams();
    if (!visible.length) return false;
    const exp = this.expandedIds();
    return visible.every((t: any) => exp.has(t.tid));
  });

  ngOnInit(): void {
    this.load(false);
  }

  ngOnDestroy(): void {
    this.stopTimer();
  }

  load(forceRefresh = false): void {
    this.loading.set(true);
    this.error.set(null);

    this.api.getSilverLive(this.selectedDay(), forceRefresh).subscribe({
      next: (res) => {
        this.data.set(res);
        if (this.selectedDay() === null && res?.serie_a_day) {
          this.selectedDay.set(res.serie_a_day);
        }
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(err?.error?.detail || err?.message || 'Errore di comunicazione con il server.');
        this.loading.set(false);
      },
    });
  }

  onDayChange(day: number): void {
    this.selectedDay.set(day);
    this.load(false);
  }

  refreshNow(): void {
    this.load(true);
  }

  toggleAutoRefresh(): void {
    const nextState = !this.autoRefresh();
    this.autoRefresh.set(nextState);
    if (nextState) {
      this.startTimer();
    } else {
      this.stopTimer();
    }
  }

  private startTimer(): void {
    this.stopTimer();
    this.refreshTimer = setInterval(() => {
      if (!this.loading()) {
        this.load(true);
      }
    }, 60000);
  }

  private stopTimer(): void {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
  }

  isExpanded(teamId: number): boolean {
    return this.expandedIds().has(teamId);
  }

  toggleTeam(teamId: number): void {
    const next = new Set(this.expandedIds());
    if (next.has(teamId)) {
      next.delete(teamId);
    } else {
      next.add(teamId);
    }
    this.expandedIds.set(next);
  }

  toggleAllExpanded(): void {
    const visible = this.filteredTeams();
    if (this.allExpanded()) {
      this.expandedIds.set(new Set());
    } else {
      this.expandedIds.set(new Set(visible.map((t: any) => t.tid)));
    }
  }

  isSubbedIn(team: any, playerName: string): boolean {
    return (team.substitutions || []).some((s: any) => s.in_name === playerName);
  }

  leagueBadgeClass(leagueName: string | null): string {
    const name = (leagueName || '').toUpperCase();
    if (name === 'GOLD') return 'badge-gold';
    if (name === 'BRONZE') return 'badge-bronze';
    if (name === 'CARBON') return 'badge-carbon';
    return 'badge-silver';
  }
}
