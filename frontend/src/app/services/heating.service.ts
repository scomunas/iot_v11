import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { DeviceItem } from './settings.service';
import { Schedule } from './schedules.service';

export interface HeatingStatusResponse {
  state: 'on' | 'off';
  deactivated_until?: string | null;
  updated_at?: string;
  active_map_id?: number | null;
  active_map?: HeatingMap | null;
  devices: DeviceItem[];
  temperature_devices?: DeviceItem[];
  pending_resume_schedules?: Schedule[];
}

export interface HeatingMap {
  id: number;
  name: string;
  description?: string;
  rules: Record<string, number | null>;
  is_default: number;
  created_at: string;
  updated_at: string;
}

export interface HeatingMapsResponse {
  maps: HeatingMap[];
  active_map_id: number | null;
  default_map_id: number | null;
}

export interface HeatingMapPayload {
  name: string;
  description?: string;
  rules: Record<string, number | null>;
  is_default?: number;
}

export interface HeatingCalendarSlot {
  id?: number;
  day_of_week: number;
  start_time: string;
  end_time: string;
  map_id: number;
  map_name?: string;
  map_is_default?: number;
  map_description?: string;
}

export interface HeatingCalendarDay {
  id: number;
  name: string;
  short: string;
}

export interface HeatingCalendarResponse {
  calendar: HeatingCalendarSlot[];
  resolved_map: HeatingMap | null;
  current_time: string;
  current_date: string;
  current_day_of_week: number;
  is_today_holiday: boolean;
  days: HeatingCalendarDay[];
}

export interface HeatingCalendarDayUpdatePayload {
  day_of_week: number;
  slots: Array<{
    start_time: string;
    end_time: string;
    map_id: number;
  }>;
  copy_to_days?: number[];
}

export interface HeatingStatePayload {
  action: 'on' | 'off';
  mode?: 'immediate' | 'hours' | 'until';
  hours?: number;
  until?: string;
}

export interface HeatingStateResponse {
  status: string;
  message: string;
  state: {
    id: number;
    state: 'on' | 'off';
    deactivated_until?: string | null;
    updated_at: string;
  };
  schedule?: Schedule;
}

@Injectable({
  providedIn: 'root'
})
export class HeatingService {
  private readonly http = inject(HttpClient);

  private get headers(): HttpHeaders {
    return new HttpHeaders({
      'Content-Type': 'application/json',
      'X-API-Key': environment.apiKey,
    });
  }

  getHeatingState(): Observable<HeatingStatusResponse> {
    return this.http.get<HeatingStatusResponse>(`${environment.backendUrl}/heating/state`, {
      headers: this.headers,
    });
  }

  setHeatingState(payload: HeatingStatePayload): Observable<HeatingStateResponse> {
    return this.http.post<HeatingStateResponse>(`${environment.backendUrl}/heating/state`, payload, {
      headers: this.headers,
    });
  }

  getHeatingMaps(): Observable<HeatingMapsResponse> {
    return this.http.get<HeatingMapsResponse>(`${environment.backendUrl}/heating/maps`, {
      headers: this.headers,
    });
  }

  getHeatingMap(id: number): Observable<{ map: HeatingMap }> {
    return this.http.get<{ map: HeatingMap }>(`${environment.backendUrl}/heating/maps/${id}`, {
      headers: this.headers,
    });
  }

  createHeatingMap(payload: HeatingMapPayload): Observable<{ message: string; map: HeatingMap }> {
    return this.http.post<{ message: string; map: HeatingMap }>(`${environment.backendUrl}/heating/maps`, payload, {
      headers: this.headers,
    });
  }

  updateHeatingMap(id: number, payload: HeatingMapPayload): Observable<{ message: string; map: HeatingMap }> {
    return this.http.put<{ message: string; map: HeatingMap }>(`${environment.backendUrl}/heating/maps/${id}`, payload, {
      headers: this.headers,
    });
  }

  deleteHeatingMap(id: number): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(`${environment.backendUrl}/heating/maps/${id}`, {
      headers: this.headers,
    });
  }

  activateHeatingMap(id: number): Observable<{ message: string; state: any; active_map: HeatingMap }> {
    return this.http.post<{ message: string; state: any; active_map: HeatingMap }>(
      `${environment.backendUrl}/heating/maps/${id}/activate`,
      {},
      { headers: this.headers }
    );
  }

  setDefaultHeatingMap(id: number): Observable<{ message: string; map: HeatingMap }> {
    return this.http.post<{ message: string; map: HeatingMap }>(
      `${environment.backendUrl}/heating/maps/${id}/set-default`,
      {},
      { headers: this.headers }
    );
  }

  getHeatingCalendar(): Observable<HeatingCalendarResponse> {
    return this.http.get<HeatingCalendarResponse>(`${environment.backendUrl}/heating/calendar`, {
      headers: this.headers,
    });
  }

  updateHeatingCalendarDay(payload: HeatingCalendarDayUpdatePayload): Observable<{
    status: string;
    message: string;
    calendar: HeatingCalendarSlot[];
    resolved_map: HeatingMap | null;
  }> {
    return this.http.put<{
      status: string;
      message: string;
      calendar: HeatingCalendarSlot[];
      resolved_map: HeatingMap | null;
    }>(`${environment.backendUrl}/heating/calendar/day`, payload, {
      headers: this.headers,
    });
  }
}
