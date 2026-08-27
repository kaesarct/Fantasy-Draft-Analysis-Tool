import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-teams',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <div>
          <h1 class="page-title">👤 Allenatori</h1>
          <p class="text-secondary">Ogni allenatore raccoglie le sue squadre stagione per stagione</p>
        </div>
      </div>

      <div class="allenatori-grid">
        @for (a of allenatori(); track a.id) {
          <a [routerLink]="['/allenatori', a.id]" class="allenatore-card">
            <div class="avatar">{{ a.display_name[0] }}</div>
            <div class="al-info">
              <div class="al-name">{{ a.display_name }}</div>
              <div class="al-username text-muted">{{ '@' + a.username }}</div>
            </div>
            <span class="badge" [class]="a.is_active ? 'badge-green' : 'badge-carbon'">
              {{ a.is_active ? 'Attivo' : 'Inattivo' }}
            </span>
          </a>
        }
        @empty {
          <p class="text-muted">Nessun allenatore registrato.</p>
        }
      </div>
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1280px; margin: 0 auto; }
    .page-header { margin-bottom: 24px; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; }
    .allenatori-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
    .allenatore-card {
      background: var(--bg-card); border: 1px solid var(--border-color);
      border-radius: var(--radius-md); padding: 16px 20px;
      display: flex; align-items: center; gap: 14px;
      text-decoration: none; color: var(--text-primary);
      transition: border-color var(--transition), transform var(--transition);
    }
    .allenatore-card:hover { border-color: var(--accent-blue); transform: translateY(-2px); }
    .avatar {
      width: 44px; height: 44px; border-radius: 50%;
      background: linear-gradient(135deg, var(--accent-green), var(--accent-blue));
      display: flex; align-items: center; justify-content: center;
      font-size: 18px; font-weight: 800; color: #fff; flex-shrink: 0;
    }
    .al-info { flex: 1; }
    .al-name { font-weight: 700; font-size: 14px; }
    .al-username { font-size: 12px; }
  `],
})
export class TeamsComponent implements OnInit {
  allenatori = signal<any[]>([]);

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.getAllenatori().subscribe({ next: d => this.allenatori.set(d) });
  }
}
