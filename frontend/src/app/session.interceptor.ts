import { inject } from '@angular/core';
import { HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';
import { AuthService } from './auth.service';

export const sessionInterceptor: HttpInterceptorFn = (request,next) => {
  const auth = inject(AuthService);
  return next(request).pipe(catchError(error => {
    if (error.status === 401 && !request.url.includes('/api/auth/login')) auth.user.set(null);
    return throwError(() => error);
  }));
};
