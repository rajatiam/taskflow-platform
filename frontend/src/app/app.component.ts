import { AuthService } from './auth.service';
import { AuthPanelComponent } from './auth-panel.component';
import { AuditPanelComponent, MembersPanelComponent, ArchivePanelComponent } from './admin-panels.component';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, debounceTime, distinctUntilChanged, of, switchMap, catchError, timer } from 'rxjs';
import { ApiService } from './api.service';
import { Field, ProjectConfig, RecordItem, Value } from './models';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, AuthPanelComponent, AuditPanelComponent, MembersPanelComponent, ArchivePanelComponent],
  templateUrl: './app.component.html'
})
export class AppComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly auth = inject(AuthService);
  private workspaceStarted = false;
  logout() { this.auth.logout().subscribe({error:error=>this.fail(error)}); }
  private readonly destroy = inject(DestroyRef);
  private readonly searchEvents = new Subject<string>();
  readonly config = signal<ProjectConfig | null>(null);
  readonly rows = signal<RecordItem[]>([]);
  readonly stats = signal<Record<string, unknown>>({});
  readonly error = signal('');
  readonly notice = signal('');
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly tab = signal<'workspace' | 'analytics' | 'architecture' | 'audit' | 'members' | 'archives'>('workspace');
  readonly pendingDelete = signal<number | null>(null);
  readonly selected = signal<RecordItem | null>(null);
  readonly query = signal('');
  readonly offset=signal(0); readonly total=signal(0);
  page(direction:number){this.offset.update(value=>Math.max(0,value+direction*50));this.refresh();}
  export(format:string){this.api.export(this.query(),format).subscribe({next:blob=>{const url=URL.createObjectURL(blob);const anchor=document.createElement('a');anchor.href=url;anchor.download=document.title.replaceAll(' ','-')+'.'+format;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);},error:error=>this.fail(error)});}
  readonly fields = signal<Field[]>([]);
  readonly metrics = computed(() => Object.entries(this.stats()).filter(([,v]) => typeof v === 'number').map(([label,value]) => ({label: label.replaceAll('_',' '),value:Number(value)})));
  readonly columns = ['todo','doing','done'];
  form = new FormGroup<Record<string, FormControl<Value>>>({});

  ngOnInit() {
    this.auth.restore().subscribe({next:user => { if(user) this.initializeWorkspace(); },error:error=>this.fail(error)});
  }

  initializeWorkspace() {
    if (this.workspaceStarted) { this.refresh(); return; }
    this.workspaceStarted = true;
    this.api.config().pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: config => {
        this.config.set(config); document.title = config.name;
        const controls: Record<string, FormControl<Value>> = {};
        this.fields.set(Object.entries(config.example).map(([key,value]) => {
          const options = this.options(config.kind,key,value);
          controls[key] = new FormControl<Value>(typeof value === 'boolean' ? String(value) : value, { validators: [Validators.required, ...(typeof value === 'number' ? [Validators.min(0)] : [])] });
          return { key, label:key.replaceAll('_',' '), options, type:options.length ? 'select' : typeof value === 'number' ? 'number' : ['start','end'].includes(key) ? 'datetime-local' : ['payload','message'].includes(key) ? 'textarea' : 'text', step:Number.isInteger(value) ? '1' : 'any' } as Field;
        }));
        this.form = new FormGroup(controls);
        this.refresh();
        if (config.kind === 'jobs') timer(2000,2000).pipe(takeUntilDestroyed(this.destroy)).subscribe(() => { if (!this.saving()) this.refresh(false); });
      }, error: error => this.fail(error)
    });
    this.searchEvents.pipe(debounceTime(250), distinctUntilChanged(), switchMap(query => this.api.workspace(query).pipe(catchError(error => { this.fail(error); return of(null); }))), takeUntilDestroyed(this.destroy)).subscribe(data => { if (data) { this.rows.set(data.records); this.total.set(data.total); this.stats.set(data.summary); } });
  }

  private options(kind: string, key: string, value: Value): string[] {
    if (typeof value === 'boolean') return ['true','false'];
    const choices: Record<string, Record<string,string[]>> = {
      taskboard: {status:['todo','doing','done']}, support: {status:['open','investigating','resolved'],priority:['low','medium','high']},
      jobs: {operation:['uppercase','word_count','sort_lines']}, logs:{level:['DEBUG','INFO','WARN','ERROR']}, releases:{environment:['dev']}
    };
    return choices[kind]?.[key] ?? [];
  }
  refresh(showLoading = true) {
    if (showLoading) this.loading.set(true);
    this.api.workspace(this.query(),this.offset()).pipe(takeUntilDestroyed(this.destroy)).subscribe({ next: data => { this.rows.set(data.records); this.total.set(data.total); this.stats.set(data.summary); this.loading.set(false); }, error: error => this.fail(error) });
  }
  search(value: string) { this.offset.set(0); this.query.set(value); this.searchEvents.next(value); }
  create() {
    if (this.form.invalid || this.saving()) { this.form.markAllAsTouched(); return; }
    const data = this.form.getRawValue();
    for (const [key,example] of Object.entries(this.config()!.example)) {
      if (typeof example === 'boolean') data[key] = data[key] === true || data[key] === 'true';
      if (typeof example === 'number') data[key] = Number(data[key]);
    }
    this.saving.set(true); this.error.set('');
    this.api.create(data).pipe(takeUntilDestroyed(this.destroy)).subscribe({ next: () => { this.saving.set(false); this.notice.set('Record created successfully.'); this.offset.set(0); this.refresh(); }, error: error => this.fail(error) });
  }
  action(row: RecordItem, name: string) {
    this.saving.set(true); this.error.set('');
    this.api.action(row.id,name).pipe(takeUntilDestroyed(this.destroy)).subscribe({ next: () => { this.saving.set(false); this.notice.set(`${name} completed.`); this.refresh(); }, error: error => this.fail(error) });
  }
  remove(id: number) {
    this.saving.set(true); this.error.set('');
    this.api.delete(id).pipe(takeUntilDestroyed(this.destroy)).subscribe({ next: () => { this.saving.set(false); this.pendingDelete.set(null); this.notice.set('Record deleted.'); this.refresh(); }, error: error => this.fail(error) });
  }
  private fail(error: HttpErrorResponse) { this.error.set(error.status === 409 ? 'This record changed in another session. Refresh the workspace and retry.' : error.error?.error ?? error.message ?? 'Request failed'); this.loading.set(false); this.saving.set(false); }
  text(row: RecordItem, key: string) { return String(row[key] ?? '—'); }
  number(row: RecordItem, key: string) { return Number(row[key] ?? 0); }
  truth(row: RecordItem, key: string) { return row[key] === true; }
  column(status: string) { return this.rows().filter(row => row['status'] === status); }
  actions(row: RecordItem): string[] {
    if(!this.auth.canWrite()) return [];
    return this.domainActions(row).filter(action => action !== 'approve' || this.auth.isAdmin());
  }
  private domainActions(row: RecordItem): string[] {
    switch (this.config()?.kind) {
      case 'taskboard': return row['status'] === 'done' ? [] : ['advance'];
      case 'support': return row['status'] === 'resolved' ? [] : ['advance'];
      case 'inventory': return ['restock','consume'];
      case 'jobs': return row['status'] === 'failed' ? ['retry'] : [];
      case 'uptime': return ['check'];
      case 'releases': return row['environment'] === 'dev' ? ['promote'] : row['environment'] === 'staging' ? row['approved'] ? ['promote'] : ['approve'] : [];
      default: return [];
    }
  }
  policyViolations(row: RecordItem) { return [this.truth(row,'public') ? 'Public access' : '', !this.truth(row,'encrypted') ? 'Encryption disabled' : '', !this.truth(row,'backup') ? 'Backups disabled' : ''].filter(Boolean); }
  label(row: RecordItem) { return this.text(row,this.config()!.fields[0]); }
}
