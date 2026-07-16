import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class AuthService {
  // null = stato non ancora verificato (all'avvio dell'app)
  isAuthenticated = signal<boolean | null>(null);
  username = signal<string | null>(null);

  constructor(private api: ApiService) {}

  async checkAuth(): Promise<void> {
    try {
      const res = await firstValueFrom(this.api.me());
      this.isAuthenticated.set(!!res.authenticated);
      this.username.set(res.username ?? null);
    } catch {
      this.isAuthenticated.set(false);
      this.username.set(null);
    }
  }

  async login(username: string, password: string): Promise<void> {
    const res = await firstValueFrom(this.api.login(username, password));
    this.isAuthenticated.set(true);
    this.username.set(res.username);
  }

  async logout(): Promise<void> {
    await firstValueFrom(this.api.logout());
    this.isAuthenticated.set(false);
    this.username.set(null);
  }
}
