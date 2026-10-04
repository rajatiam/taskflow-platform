import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { forkJoin, retry, map, tap, throwError, timer } from 'rxjs';
import { ProjectConfig, RecordItem } from './models';

@Injectable({providedIn:'root'})
export class ApiService {
  private readonly http=inject(HttpClient);
  private readonly versions=new Map<number,number>();
  config() { return this.http.get<ProjectConfig>('/api/config'); }
  workspace(query: string, offset = 0) {
    const options={params:{q:query}};
    return forkJoin({page:this.http.get<{items:RecordItem[];total:number}>('/api/v1/records',{params:{q:query,limit:50,offset}}),summary:this.http.get<Record<string,unknown>>('/api/summary',options)}).pipe(map(data=>({records:data.page.items,total:data.page.total,summary:data.summary})),tap(data => { for (const row of data.records) this.versions.set(row.id,row.version); }));
  }
  export(query:string,format:string){return this.http.get('/api/exports/records',{params:{q:query,format},responseType:'blob'});}
  create(data: Record<string,unknown>) {
    // The same key survives transient retries: the backend stores one result.
    const key=crypto.randomUUID();
    return this.http.post<RecordItem>('/api/records',data,{headers:{'Idempotency-Key':key}}).pipe(
      retry({count:2,delay:(error: HttpErrorResponse,attempt:number) => error.status === 0 || error.status === 503 ? timer(attempt*250) : throwError(() => error)}),
      tap(row => this.versions.set(row.id,row.version))
    );
  }
  action(id:number,action:string) {
    return this.http.post<RecordItem>(`/api/records/${id}/${action}`,{},{headers:{'If-Match':String(this.versions.get(id))}}).pipe(tap(row => this.versions.set(row.id,row.version)));
  }
  delete(id:number) { return this.http.delete<{deleted:boolean}>(`/api/records/${id}`,{headers:{'If-Match':String(this.versions.get(id))}}); }
}
