import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { catchError, of, tap } from 'rxjs';

export interface User { id: number; username: string; role: 'viewer' | 'editor' | 'admin'; }
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  readonly user = signal<User | null>(null);
  readonly canWrite = computed(() => this.user()?.role === 'admin' || this.user()?.role === 'editor');
  readonly isAdmin = computed(() => this.user()?.role === 'admin');
  restore() { return this.http.get<User>('/api/auth/me').pipe(tap(user => this.user.set(user)),catchError(error => { this.user.set(null); if (error.status !== 401) throw error; return of(null); })); }
  login(data: {username: string; password: string}) { return this.http.post<User>('/api/auth/login',data).pipe(tap(user => this.user.set(user))); }
  register(data: {username: string; password: string}) { return this.http.post<User>('/api/auth/register',data).pipe(tap(user => this.user.set(user))); }
  logout() { return this.http.post('/api/auth/logout',{}).pipe(tap(() => this.user.set(null))); }
}
