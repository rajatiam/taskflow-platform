import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { forkJoin } from 'rxjs';
import { ProjectConfig, RecordItem } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  config() { return this.http.get<ProjectConfig>('/api/config'); }
  workspace(query: string) {
    const options = { params: { q: query } };
    return forkJoin({
      records: this.http.get<RecordItem[]>('/api/records', options),
      summary: this.http.get<Record<string, unknown>>('/api/summary', options)
    });
  }
  create(data: Record<string, unknown>) { return this.http.post<RecordItem>('/api/records', data); }
  action(id: number, action: string) { return this.http.post<RecordItem>(`/api/records/${id}/${action}`, {}); }
  delete(id: number) { return this.http.delete<{deleted: boolean}>(`/api/records/${id}`); }
}
