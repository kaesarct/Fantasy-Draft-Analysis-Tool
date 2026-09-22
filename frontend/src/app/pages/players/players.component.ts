import { Component, OnInit, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { InputTextModule } from 'primeng/inputtext';
import { DropdownModule } from 'primeng/dropdown';
import { DataViewModule } from 'primeng/dataview';
import { TagModule } from 'primeng/tag';
import { SkeletonModule } from 'primeng/skeleton';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-players',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, InputTextModule, DropdownModule, DataViewModule, TagModule, SkeletonModule],
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <h1 class="page-title">⚽ Giocatori</h1>
        <p class="text-secondary">Tutti i calciatori con quotazioni e variazioni</p>
      </div>

      <!-- Filters -->
      <div class="filters-bar card mb-4">
        <input
          pInputText
          class="filter-input"
          placeholder="🔍 Cerca giocatore..."
          [(ngModel)]="search"
          (ngModelChange)="applyFilters()"
        />
        <p-dropdown
          [options]="roleOptions"
          [(ngModel)]="selectedRole"
          placeholder="Ruolo"
          (ngModelChange)="applyFilters()"
          [showClear]="true"
          styleClass="filter-drop"
        />
        <p-dropdown
          [options]="seasonOptions()"
          [(ngModel)]="selectedSeasonId"
          (ngModelChange)="onSeasonChange()"
          styleClass="filter-drop"
        />
        <span class="results-count text-muted">{{ filtered().length }} risultati</span>
      </div>

      <!-- Table -->
      @if (loading()) {
        <div class="player-list">
          @for (i of [1,2,3,4,5,6,7,8]; track i) {
            <p-skeleton height="52px" styleClass="mb-2" />
          }
        </div>
      } @else {
        <div class="player-table card">
          <div class="table-scroll">
            <div class="table-header">
              <span style="width:40px">#</span>
              <span style="flex:1" class="sortable" (click)="sortBy('name')">Giocatore{{ sortArrow('name') }}</span>
              <span style="width:80px;text-align:center" class="sortable" (click)="sortBy('role')">Ruolo{{ sortArrow('role') }}</span>
              <span style="width:100px;text-align:right" class="sortable" (click)="sortBy('price')">Quotazione{{ sortArrow('price') }}</span>
              <span style="width:80px;text-align:right" class="sortable" (click)="sortBy('fvm')">FVM{{ sortArrow('fvm') }}</span>
              <span style="width:70px;text-align:right" class="sortable" (click)="sortBy('diff')">Diff.{{ sortArrow('diff') }}</span>
            </div>
            @for (p of filtered(); track p.id; let i = $index) {
              <a [routerLink]="['/players', p.id]" class="player-row">
                <span class="row-num text-muted">{{ i + 1 }}</span>
                <span class="player-name">{{ p.name }}</span>
                <span style="width:80px;text-align:center" class="role-badges">
                  @for (r of p.roles; track r) {
                    <span class="role-badge role-{{ r }}">{{ r }}</span>
                  }
                </span>
                @if (selectedSeasonId) {
                  <span style="width:100px;text-align:right;font-weight:700">{{ p.price ?? '—' }}</span>
                  <span style="width:80px;text-align:right;color:var(--accent-blue)">{{ p.fvm ?? '—' }}</span>
                  <span style="width:70px;text-align:right"
                        [class.text-positive]="(p.price_diff ?? 0) > 0"
                        [class.text-negative]="(p.price_diff ?? 0) < 0">
                    {{ (p.price_diff ?? 0) > 0 ? '+' : '' }}{{ p.price_diff ?? '0' }}
                  </span>
                } @else {
                  <span style="width:100px;text-align:right;font-weight:700">
                    {{ p.price_min ?? '—' }}–{{ p.price_max ?? '—' }}
                  </span>
                  <span style="width:80px;text-align:right;color:var(--accent-blue)">
                    {{ p.fvm_min ?? '—' }}–{{ p.fvm_max ?? '—' }}
                  </span>
                  <span style="width:70px;text-align:right">
                    <span [class.text-negative]="(p.diff_min ?? 0) < 0">{{ p.diff_min ?? '—' }}</span>/<span [class.text-positive]="(p.diff_max ?? 0) > 0">{{ p.diff_max ?? '—' }}</span>
                  </span>
                }
              </a>
            }
            @empty {
              <p class="text-muted" style="padding:20px;">Nessun giocatore trovato.</p>
            }
          </div>
        </div>
      }
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1280px; margin: 0 auto; }
    .page-header { margin-bottom: 24px; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; }

    .filters-bar {
      display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
      padding: 14px 16px;
    }
    .filter-input { flex: 1; min-width: 200px; }
    .filter-drop { min-width: 140px; }
    .results-count { margin-left: auto; font-size: 12px; }

    .player-table { padding: 0; overflow: hidden; }
    .table-scroll { overflow-x: auto; }
    .table-header {
      display: flex; align-items: center; gap: 8px;
      padding: 10px 16px; font-size: 11px; font-weight: 700;
      color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em;
      border-bottom: 1px solid var(--border-color);
      min-width: 480px;
    }
    .table-header .sortable { cursor: pointer; user-select: none; white-space: nowrap; }
    .table-header .sortable:hover { color: var(--text-primary); }
    .player-row {
      display: flex; align-items: center; gap: 8px;
      padding: 12px 16px; border-bottom: 1px solid var(--border-subtle);
      text-decoration: none; color: var(--text-primary);
      transition: background var(--transition);
      min-width: 480px;
    }
    .player-row:hover { background: var(--bg-elevated); }
    .row-num { width: 40px; font-size: 12px; }
    .role-badges { display: flex; align-items: center; justify-content: center; gap: 4px; flex-wrap: wrap; }
    .player-name { flex: 1; font-weight: 600; font-size: 13px; }
    .mb-2 { margin-bottom: 8px; }
    .mb-4 { margin-bottom: 24px; }
  `],
})
export class PlayersComponent implements OnInit {
  allPlayers = signal<any[]>([]);
  filtered = signal<any[]>([]);
  loading = signal(true);
  search = '';
  selectedRole: string | null = null;

  seasons = signal<any[]>([]);
  selectedSeasonId: number | null = null;

  sortField: 'name' | 'role' | 'price' | 'fvm' | 'diff' | null = null;
  sortAsc = true;

  roleOptions = [
    { label: 'Portiere', value: 'P' },
    { label: 'Difensore', value: 'D' },
    { label: 'Centrocampista', value: 'C' },
    { label: 'Attaccante', value: 'A' },
  ];

  seasonOptions = computed(() => [
    { label: 'Tutte le stagioni', value: null },
    ...this.seasons().map(s => ({ label: s.label, value: s.id })),
  ]);

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.getSeasons().subscribe(seasons => this.seasons.set(seasons));
    this.loadPlayers();
  }

  onSeasonChange() {
    this.loadPlayers();
  }

  private loadPlayers() {
    this.loading.set(true);
    this.api.getPlayers(undefined, undefined, undefined, this.selectedSeasonId ?? undefined).subscribe({
      next: data => {
        this.allPlayers.set(data);
        this.applyFilters();
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  applyFilters() {
    let result = this.allPlayers();
    if (this.search) {
      result = result.filter(p => p.name.toLowerCase().includes(this.search.toLowerCase()));
    }
    if (this.selectedRole) {
      result = result.filter(p => p.roles.includes(this.selectedRole));
    }
    this.filtered.set(this.applySort(result));
  }

  sortBy(field: 'name' | 'role' | 'price' | 'fvm' | 'diff') {
    if (this.sortField === field) {
      this.sortAsc = !this.sortAsc;
    } else {
      this.sortField = field;
      // Testo in ordine alfabetico crescente di default, numeri dal piu' alto
      // al piu' basso (piu' utile per prezzo/FVM: si cercano i top per valore).
      this.sortAsc = field === 'name' || field === 'role';
    }
    this.filtered.set(this.applySort(this.filtered()));
  }

  sortArrow(field: string): string {
    if (this.sortField !== field) return '';
    return this.sortAsc ? ' ▲' : ' ▼';
  }

  private applySort(list: any[]): any[] {
    const field = this.sortField;
    if (!field) return list;
    const dir = this.sortAsc ? 1 : -1;
    const byMatchingSeason = !!this.selectedSeasonId;
    const valueOf = (p: any): number | string => {
      switch (field) {
        case 'name': return p.name?.toLowerCase() ?? '';
        case 'role': return p.roles?.[0] ?? '';
        case 'price': return byMatchingSeason ? (p.price ?? -Infinity) : (p.price_max ?? -Infinity);
        case 'fvm': return byMatchingSeason ? (p.fvm ?? -Infinity) : (p.fvm_max ?? -Infinity);
        case 'diff': return byMatchingSeason ? (p.price_diff ?? -Infinity) : (p.diff_max ?? -Infinity);
        default: return '';
      }
    };
    return [...list].sort((a, b) => {
      const va = valueOf(a), vb = valueOf(b);
      if (va < vb) return -1 * dir;
      if (va > vb) return 1 * dir;
      return 0;
    });
  }
}
