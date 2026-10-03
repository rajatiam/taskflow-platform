import { Component, inject, output, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { AuthService } from './auth.service';
import { PROJECT_NAME } from '../project-info';

@Component({
  selector: 'app-auth-panel', standalone: true, imports: [ReactiveFormsModule],
  template: `
  <main class="auth-shell"><section class="auth-card">
    <p class="eyebrow">PYTHON + ANGULAR ENGINEERING PORTFOLIO</p><h1>{{ projectName }}</h1>
    <p class="muted">{{ signup() ? 'Create a local workspace account.' : 'Sign in to your workspace.' }}</p>
    <form [formGroup]="form" (ngSubmit)="submit()">
      <label for="auth-username">Username</label><input id="auth-username" autocomplete="username" formControlName="username">
      <label for="auth-password">Password</label><input id="auth-password" type="password" [autocomplete]="signup() ? 'new-password' : 'current-password'" formControlName="password">
      <small class="muted">Use a password of at least 12 characters.</small>
      @if (error()) { <p role="alert" class="validation">{{ error() }}</p> }
      <button class="primary" type="submit" [disabled]="busy() || form.invalid">{{ busy() ? 'Please wait…' : signup() ? 'Create workspace account' : 'Sign in' }}</button>
    </form>
    <button class="auth-toggle" (click)="signup.set(!signup()); error.set('')">{{ signup() ? 'Already registered? Sign in' : 'New here? Create account' }}</button>
    <p class="form-note">Sessions use HttpOnly cookies. Self-registration is available in local development; administrators are created using the CLI.</p>
  </section></main>`
})
export class AuthPanelComponent {
  private readonly auth = inject(AuthService);
  readonly authenticated = output<void>();
  readonly projectName = PROJECT_NAME;
  readonly signup = signal(false);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly form = new FormGroup({
    username:new FormControl('',{nonNullable:true,validators:[Validators.required,Validators.pattern(/^[a-zA-Z0-9_.-]{3,40}$/)]}),
    password:new FormControl('',{nonNullable:true,validators:[Validators.required,Validators.minLength(12),Validators.maxLength(128)]})
  });
  submit() {
    if (this.form.invalid || this.busy()) return;
    this.busy.set(true); this.error.set('');
    const request = this.signup() ? this.auth.register(this.form.getRawValue()) : this.auth.login(this.form.getRawValue());
    request.subscribe({next:() => { this.busy.set(false); this.form.controls.password.reset(); this.authenticated.emit(); },error:error => { this.busy.set(false); this.error.set(error.error?.error ?? 'Could not sign in. Start the Python backend and retry.'); }});
  }
}
