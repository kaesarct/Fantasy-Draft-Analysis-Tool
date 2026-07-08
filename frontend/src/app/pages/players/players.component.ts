import { Component, OnInit, signal } from '@angular/core';
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
          <div class="table-header">
            <span style="width:40px">#</span>
            <span style="flex:1">Giocatore</span>
            <span style="width:80px;text-align:center">Ruolo</span>
            <span style="width:100px;text-align:right">Quotazione</span>
            <span style="width:80px;text-align:right">FVM</span>
            <span style="width:70px;text-align:right">Diff.</span>
          </div>
          @for (p of filtered(); track p.id; let i = $index) {
            <a [routerLink]="['/players', p.id]" class="player-row">
              <span class="row-num text-muted">{{ i + 1 }}</span>
              <span class="player-name">{{ p.name }}</span>
              <span style="width:80px;text-align:center">
                <span class="role-badge role-{{ p.role }}">{{ p.role }}</span>
              </span>
              <span style="width:100px;text-align:right;font-weight:700">{{ p.price ?? '—' }}</span>
              <span style="width:80px;text-align:right;color:var(--accent-blue)">{{ p.fvm ?? '—' }}</span>
              <span style="width:70px;text-align:right"
                    [class.text-positive]="(p.price_diff ?? 0) > 0"
                    [class.text-negative]="(p.price_diff ?? 0) < 0">
                {{ (p.price_diff ?? 0) > 0 ? '+' : '' }}{{ p.price_diff ?? '0' }}
              </span>
            </a>
          }
          @empty {
            <p class="text-muted" style="padding:20px;">Nessun giocatore trovato.</p>
          }
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
    .table-header {
      display: flex; align-items: center; gap: 8px;
      padding: 10px 16px; font-size: 11px; font-weight: 700;
      color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em;
      border-bottom: 1px solid var(--border-color);
    }
    .player-row {
      display: flex; align-items: center; gap: 8px;
      padding: 12px 16px; border-bottom: 1px solid var(--border-subtle);
      text-decoration: none; color: var(--text-primary);
      transition: background var(--transition);
    }
    .player-row:hover { background: var(--bg-elevated); }
    .row-num { width: 40px; font-size: 12px; }
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

  roleOptions = [
    { label: 'Portiere', value: 'P' },
    { label: 'Difensore', value: 'D' },
    { label: 'Centrocampista', value: 'C' },
    { label: 'Attaccante', value: 'A' },
  ];

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.getPlayers().subscribe({
      next: data => {
        this.allPlayers.set(data);
        this.filtered.set(data);
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
      result = result.filter(p => p.role === this.selectedRole);
    }
    this.filtered.set(result);
  }
}
