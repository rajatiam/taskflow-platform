import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient, withInterceptors, withXsrfConfiguration } from '@angular/common/http';
import { provideZonelessChangeDetection } from '@angular/core';
import { AppComponent } from './app/app.component';
import { sessionInterceptor } from './app/session.interceptor';
import { CSRF_COOKIE } from './project-info';

bootstrapApplication(AppComponent, {providers:[provideHttpClient(withXsrfConfiguration({cookieName:CSRF_COOKIE,headerName:'X-CSRF-Token'}),withInterceptors([sessionInterceptor])),provideZonelessChangeDetection()]}).catch(console.error);
