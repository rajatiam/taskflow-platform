import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { User } from './auth.service';

interface AuditEvent { id:number; actor:string; operation:string; record_id:number|null; request_id:string; created_at:string; metadata:Record<string,unknown>; }
@Component({selector:'app-audit-panel',standalone:true,imports:[CommonModule],template:`
<section class="panel"><div class="panel-heading"><h2>Audit history</h2><button (click)="load()">Refresh</button></div>
<p class="muted">Mutations and their audit events commit atomically. Passwords and session tokens are never included.</p>
@if (error()) { <p role="alert" class="validation">{{error()}}</p> }
@for (event of events(); track event.id) { <article class="record"><div class="record-title"><h3>{{event.operation}}</h3><span class="record-id">{{event.created_at | date:'medium'}}</span></div><p>{{event.actor}} · Record {{event.record_id ?? '—'}}</p><pre class="output">{{event.metadata | json}}</pre><small class="muted">Request {{event.request_id}}</small></article> }
<div class="actions"><button (click)="previous()" [disabled]="offset()===0">Previous page</button><button (click)="next()" [disabled]="offset()+events().length>=total()">Next page</button></div></section>`})
export class AuditPanelComponent implements OnInit {
  private readonly http=inject(HttpClient);
  readonly events=signal<AuditEvent[]>([]); readonly total=signal(0); readonly offset=signal(0); readonly error=signal('');
  ngOnInit(){this.load();}
  load(){ this.http.get<{items:AuditEvent[];total:number}>('/api/audit',{params:{limit:20,offset:this.offset()}}).subscribe({next:data=>{this.events.set(data.items);this.total.set(data.total);this.error.set('');},error:error=>this.error.set(error.error?.error??'Could not load audit history')}); }
  previous(){this.offset.update(value=>Math.max(0,value-20));this.load();} next(){this.offset.update(value=>value+20);this.load();}
}

@Component({selector:'app-members-panel',standalone:true,imports:[FormsModule],template:`
<section class="panel"><div class="panel-heading"><h2>Workspace access</h2><button (click)="load()">Refresh</button></div><p class="muted">Viewers can read; editors can work; administrators approve and manage access. The last administrator cannot be demoted.</p>
@if (error()) { <p role="alert" class="validation">{{error()}}</p> }
@for (user of users(); track user.id) { <article class="record"><h3>{{user.username}}</h3><label [for]="'role-'+user.id">Role</label><select [id]="'role-'+user.id" [ngModel]="user.role" (ngModelChange)="change(user.id,$event)"><option value="viewer">viewer</option><option value="editor">editor</option><option value="admin">admin</option></select></article> }</section>`})
export class MembersPanelComponent implements OnInit {
  private readonly http=inject(HttpClient); readonly users=signal<User[]>([]); readonly error=signal('');
  ngOnInit(){this.load();}
  load(){this.http.get<User[]>('/api/admin/users').subscribe({next:users=>this.users.set(users),error:error=>this.error.set(error.error?.error??'Could not load members')});}
  change(id:number,role:string){this.http.patch<User>(`/api/admin/users/${id}/role`,{role}).subscribe({next:()=>{this.error.set('');this.load();},error:error=>{this.error.set(error.error?.error??'Role change failed');this.load();}});}
}
