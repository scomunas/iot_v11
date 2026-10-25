import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface EventDefinition {
  id: number;
  name: string;
  type: string;
  parameter: string;
  use_case: string;
  data: string;
  holiday?: 'all_days' | 'holiday' | 'not_holiday' | string;
  notify?: number;
  notification_message?: string;
  is_active: number;
  created_at: string;
}

export interface EventDefinitionsResponse {
  event_definitions: EventDefinition[];
}

export interface EventDefinitionPayload {
  name: string;
  type: string;
  parameter?: string;
  use_case: string;
  data?: string;
  holiday?: 'all_days' | 'holiday' | 'not_holiday' | string;
  notify?: number;
  notification_message?: string;
  is_active?: number;
}

export interface TriggerEventPayload {
  type: string;
  parameter?: string;
}

export interface TriggerEventResponse {
  status: string;
  message: string;
  event: any;
  triggered_definitions?: any[];
}

@Injectable({
  providedIn: 'root'
})
export class EventsService {
  private readonly http = inject(HttpClient);

  private get headers(): HttpHeaders {
    return new HttpHeaders({
      'X-API-Key': environment.apiKey,
      'Content-Type': 'application/json',
    });
  }

  getEventDefinitions(): Observable<EventDefinitionsResponse> {
    return this.http.get<EventDefinitionsResponse>(`${environment.backendUrl}/event-definitions`, {
      headers: this.headers,
    });
  }

  createEventDefinition(payload: EventDefinitionPayload): Observable<{ message: string; event_definition: EventDefinition }> {
    return this.http.post<{ message: string; event_definition: EventDefinition }>(
      `${environment.backendUrl}/event-definitions`,
      payload,
      { headers: this.headers }
    );
  }

  updateEventDefinition(id: number, payload: EventDefinitionPayload): Observable<{ message: string; event_definition: EventDefinition }> {
    return this.http.put<{ message: string; event_definition: EventDefinition }>(
      `${environment.backendUrl}/event-definitions/${id}`,
      payload,
      { headers: this.headers }
    );
  }

  deleteEventDefinition(id: number): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(
      `${environment.backendUrl}/event-definitions/${id}`,
      { headers: this.headers }
    );
  }

  simulateEvent(payload: TriggerEventPayload): Observable<TriggerEventResponse> {
    return this.http.post<TriggerEventResponse>(
      `${environment.backendUrl}/events`,
      payload,
      { headers: this.headers }
    );
  }
}
