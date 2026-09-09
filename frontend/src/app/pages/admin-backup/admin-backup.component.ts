import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { InputTextModule } from 'primeng/inputtext';
import { ButtonModule } from 'primeng/button';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-admin-backup',
  standalone: true,
  imports: [CommonModule, FormsModule, InputTextModule, ButtonModule],
  template: `
    <div class="page-container fade-up">
      <div class="page-header">
        <h1 class="page-title">💾 Dump e restore DB</h1>
        <p class="text-secondary">
          Scarica un dump completo del DB (es. da prod) e ripristinalo in un altro ambiente (es. staging)
          per riprodurre un comportamento visto solo lì. Il restore sovrascrive completamente il DB su cui
          gira: operazione irreversibile, protetta da una password dedicata oltre al login admin.
        </p>
      </div>

      <div class="card ops-panel">
        <label class="field-label" for="ops-password">Password dump/restore</label>
        <input
          id="ops-password"
          pInputText
          type="password"
          [(ngModel)]="password"
          placeholder="Password"
          class="password-input"
          autocomplete="off"
        />

        @if (message()) {
          <div class="status-msg" [class.error]="messageIsError()">{{ message() }}</div>
        }

        <div class="actions-row">
          <button
            pButton
            label="Scarica dump"
            size="small"
            [disabled]="!password"
            [loading]="dumping()"
            (click)="downloadDump()"
          ></button>
        </div>

        <div class="restore-row">
          <input #fileInput type="file" accept=".sql" (change)="onFileSelected($event)" />
          <button
            pButton
            label="Ripristina"
            size="small"
            class="p-button-outlined p-button-danger"
            [disabled]="!password || !selectedFile() || restoring()"
            [loading]="restoring()"
            (click)="restore(fileInput)"
          ></button>
        </div>
        <p class="text-muted" style="font-size:12px; margin:0;">
          Il restore va abilitato esplicitamente per ambiente (variabile <code>ALLOW_DB_RESTORE</code>):
          se non lo è, l'operazione viene rifiutata anche con la password corretta.
        </p>
      </div>
    </div>
  `,
  styles: [`
    .page-container { padding: 28px 32px; max-width: 800px; margin: 0 auto; }
    .page-header { margin-bottom: 24px; }
    .page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; }

    .ops-panel { padding: 20px; display: flex; flex-direction: column; gap: 14px; }
    .field-label { font-size: 13px; font-weight: 600; }
    .password-input { width: 260px; }

    .status-msg { padding: 10px 12px; font-size: 13px; border-radius: 8px; background: var(--bg-subtle, rgba(255,255,255,.05)); }
    .status-msg.error { color: var(--text-negative, #e05260); }

    .actions-row, .restore-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  `],
})
export class AdminBackupComponent {
  password = '';
  dumping = signal(false);
  restoring = signal(false);
  selectedFile = signal<File | null>(null);
  message = signal('');
  messageIsError = signal(false);

  constructor(private api: ApiService) {}

  onFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    this.selectedFile.set(input.files?.[0] ?? null);
  }

  downloadDump() {
    if (!this.password) return;
    this.dumping.set(true);
    this.setMessage('', false);
    this.api.dumpDatabase(this.password).subscribe({
      next: response => {
        this.dumping.set(false);
        const blob = response.body;
        if (!blob) return;
        const disposition = response.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename="?([^"]+)"?/);
        const filename = match ? match[1] : 'dump.sql';
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
        this.setMessage('Dump scaricato.', false);
      },
      error: async err => {
        this.dumping.set(false);
        this.setMessage(await this.extractError(err, 'Errore durante il dump.'), true);
      },
    });
  }

  restore(fileInput: HTMLInputElement) {
    const file = this.selectedFile();
    if (!this.password || !file) return;
    const confirmed = confirm(
      'Confermi il ripristino? Questa operazione sovrascrive completamente il DB di questo ambiente ' +
      'con il contenuto del file caricato ed è irreversibile.'
    );
    if (!confirmed) return;

    this.restoring.set(true);
    this.setMessage('', false);
    this.api.restoreDatabase(this.password, file).subscribe({
      next: () => {
        this.restoring.set(false);
        this.selectedFile.set(null);
        fileInput.value = '';
        this.setMessage('Restore completato.', false);
      },
      error: err => {
        this.restoring.set(false);
        this.setMessage(err.error?.detail || 'Errore durante il restore.', true);
      },
    });
  }

  private async extractError(err: any, fallback: string): Promise<string> {
    // La risposta di errore del dump arriva come Blob (responseType: 'blob'), quindi
    // err.error e' un Blob JSON e va letto/parsato invece di leggere err.error.detail.
    if (err.error instanceof Blob) {
      try {
        const text = await err.error.text();
        const parsed = JSON.parse(text);
        return parsed.detail || fallback;
      } catch {
        return fallback;
      }
    }
    return err.error?.detail || fallback;
  }

  private setMessage(text: string, isError: boolean) {
    this.message.set(text);
    this.messageIsError.set(isError);
  }
}
