import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface Schedule {
  id: number;
  name: string;
  type: 'one-time' | 'recurrent';
  trigger_spec: string;
  use_case: string;
  is_active: number; // 1 or 0
  data?: string; // JSON parameters for task execution
  notify?: number; // 1 to notify, 0 otherwise
  notification_message?: string; // Optional custom notification message override
  speak?: number; // 1 to broadcast speech announcement, 0 otherwise
  speak_message?: string; // Optional custom speech message override
  block?: number; // 1 if blocked/protected from changes or deletion, 0 otherwise
  created_at: string;
}

export interface InMemoryJob {
  job_id: string;
  name: string;
  next_run_time: string | null;
}

export interface SchedulesResponse {
  schedules: Schedule[];
  in_memory_jobs: InMemoryJob[];
}

export interface SchedulePayload {
  name: string;
  type: 'one-time' | 'recurrent';
  trigger_spec: string;
  use_case: string;
  is_active?: number;
  data?: string; // JSON parameters for task execution
  notify?: number;
  notification_message?: string;
  speak?: number;
  speak_message?: string;
  block?: number;
}

@Injectable({
  providedIn: 'root'
})
export class SchedulesService {
  private readonly http = inject(HttpClient);

  private get headers(): HttpHeaders {
    return new HttpHeaders({
      'X-API-Key': environment.apiKey,
      'Content-Type': 'application/json',
    });
  }

  getSchedules(): Observable<SchedulesResponse> {
    return this.http.get<SchedulesResponse>(`${environment.backendUrl}/schedules`, {
      headers: this.headers,
    });
  }

  createSchedule(payload: SchedulePayload): Observable<{ message: string; schedule: Schedule }> {
    return this.http.post<{ message: string; schedule: Schedule }>(
      `${environment.backendUrl}/schedules`,
      payload,
      { headers: this.headers }
    );
  }

  updateSchedule(id: number, payload: SchedulePayload): Observable<{ message: string; schedule: Schedule }> {
    return this.http.put<{ message: string; schedule: Schedule }>(
      `${environment.backendUrl}/schedules/${id}`,
      payload,
      { headers: this.headers }
    );
  }

  deleteSchedule(id: number): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(
      `${environment.backendUrl}/schedules/${id}?permanent=true`,
      { headers: this.headers }
    );
  }

  setBlockStatus(id: number, block: number): Observable<{ message: string; schedule: Schedule }> {
    return this.http.patch<{ message: string; schedule: Schedule }>(
      `${environment.backendUrl}/schedules/${id}/block`,
      { block },
      { headers: this.headers }
    );
  }
}
