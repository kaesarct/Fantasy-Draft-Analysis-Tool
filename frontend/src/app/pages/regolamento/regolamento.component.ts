import { Component } from '@angular/core';

@Component({
  selector: 'app-regolamento',
  standalone: true,
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <h1 class="page-title">📜 Regolamento Tamarros 2026</h1>
        <a class="download-link" href="regolamento-tamarros-2026.pdf" download>⬇️ Scarica il PDF</a>
      </div>
      <iframe class="pdf-frame" src="regolamento-tamarros-2026.pdf" title="Regolamento Tamarros 2026"></iframe>
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 1000px; margin: 0 auto; }
    .page-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
    .page-title { font-size: 24px; font-weight: 800; }
    .download-link { font-size: 13px; font-weight: 600; color: var(--accent-blue); }
    .pdf-frame { width: 100%; height: 80vh; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: var(--bg-card); }
  `],
})
export class RegolamentoComponent {}
