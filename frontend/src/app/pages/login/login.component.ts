import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { InputTextModule } from 'primeng/inputtext';
import { ButtonModule } from 'primeng/button';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, InputTextModule, ButtonModule],
  template: `
    <div class="login-page">
      <form class="login-card card" (ngSubmit)="submit()">
        <h1 class="login-title">🔒 Accesso admin</h1>

        <label class="field-label" for="username">Username</label>
        <input pInputText id="username" name="username" [(ngModel)]="username" autocomplete="username" />

        <label class="field-label" for="password">Password</label>
        <input pInputText type="password" id="password" name="password" [(ngModel)]="password" autocomplete="current-password" />

        @if (error()) {
          <div class="login-error">{{ error() }}</div>
        }

        <button pButton type="submit" label="Accedi" [loading]="loading()" [disabled]="!username || !password"></button>
      </form>
    </div>
  `,
  styles: [`
    .login-page {
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100%;
      padding: 24px;
    }
    .login-card {
      width: 100%;
      max-width: 340px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 28px;
    }
    .login-title {
      font-size: 18px;
      margin: 0 0 8px;
      text-align: center;
    }
    .field-label {
      font-size: 12px;
      color: var(--text-muted);
    }
    .login-error {
      color: var(--text-negative, #e05260);
      font-size: 13px;
    }
  `],
})
export class LoginComponent {
  username = '';
  password = '';
  loading = signal(false);
  error = signal('');

  constructor(private auth: AuthService, private router: Router) {}

  async submit() {
    this.loading.set(true);
    this.error.set('');
    try {
      await this.auth.login(this.username, this.password);
      this.router.navigateByUrl('/admin');
    } catch {
      this.error.set('Credenziali non valide.');
    } finally {
      this.loading.set(false);
    }
  }
}
