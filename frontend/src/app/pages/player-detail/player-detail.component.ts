import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
@Component({ selector: 'app-player-detail', standalone: true, imports: [CommonModule],
  template: `<div class="page-container fade-up"><h1 class="page-title">⚽ Dettaglio Giocatore</h1><p class="text-muted">Storico prezzi e statistiche — in sviluppo</p></div>`,
  styles: [`.page-container{padding:28px 32px}.page-title{font-size:24px;font-weight:800;margin-bottom:8px}`]
})
export class PlayerDetailComponent {}
