import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { EventDefinition } from './events.service';

export interface AlarmConfig {
  enabled: boolean;
  helper_entity?: string;
  notification_message: string;
  speak_message: string;
  default_trigger: number;
  default_seconds: number;
  retention_seconds?: number;
  delay_seconds?: number;
}

export interface AlarmRuleData {
  entity: string;
  trigger: number;
  seconds: number;
  notification: boolean;
  speak: boolean;
}

export interface AlarmRulePayload {
  name: string;
  entity: string;
  event_type: string;
  parameter?: string;
  trigger: number;
  seconds: number;
  notification: boolean;
  speak: boolean;
  holiday?: string;
  is_active?: number;
}

export interface AlarmMemoryEvent {
  entity: string;
  date: string;
}

export interface AlarmTestPayload {
  entity?: string;
  trigger?: number;
  seconds?: number;
  notification?: boolean;
  speak?: boolean;
}

@Injectable({
  providedIn: 'root',
})
export class AlarmService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.backendUrl;

  private getHeaders(): HttpHeaders {
    return new HttpHeaders({
      'Content-Type': 'application/json',
      'X-API-Key': environment.apiKey,
    });
  }

  getAlarmConfig(): Observable<{ status: string; config: AlarmConfig }> {
    return this.http.get<{ status: string; config: AlarmConfig }>(
      `${this.baseUrl}/alarm/config`,
      { headers: this.getHeaders() }
    );
  }

  updateAlarmConfig(
    payload: Partial<AlarmConfig>
  ): Observable<{ status: string; message: string; config: AlarmConfig }> {
    return this.http.put<{ status: string; message: string; config: AlarmConfig }>(
      `${this.baseUrl}/alarm/config`,
      payload,
      { headers: this.getHeaders() }
    );
  }

  getAlarmRules(): Observable<{ status: string; rules: EventDefinition[] }> {
    return this.http.get<{ status: string; rules: EventDefinition[] }>(
      `${this.baseUrl}/alarm/rules`,
      { headers: this.getHeaders() }
    );
  }

  createAlarmRule(
    payload: AlarmRulePayload
  ): Observable<{ message: string; event_definition: EventDefinition }> {
    const dataObj: AlarmRuleData = {
      entity: payload.entity.trim(),
      trigger: Math.max(1, payload.trigger),
      seconds: Math.max(1, payload.seconds),
      notification: payload.notification,
      speak: payload.speak,
    };

    const entity = payload.entity.trim();
    const eventPayload = {
      name: payload.name.trim(),
      type: 'alarm',
      event_type: 'alarm',
      parameter: entity,
      use_case: 'check_alarm',
      data: JSON.stringify(dataObj),
      holiday: payload.holiday || 'all_days',
      notify: 0,
      notification_message: '',
      speak: 0,
      speak_message: '',
      is_active: payload.is_active !== undefined ? payload.is_active : 1,
    };

    return this.http.post<{ message: string; event_definition: EventDefinition }>(
      `${this.baseUrl}/event-definitions`,
      eventPayload,
      { headers: this.getHeaders() }
    );
  }

  updateAlarmRule(
    id: number,
    payload: AlarmRulePayload
  ): Observable<{ message: string; event_definition: EventDefinition }> {
    const dataObj: AlarmRuleData = {
      entity: payload.entity.trim(),
      trigger: Math.max(1, payload.trigger),
      seconds: Math.max(1, payload.seconds),
      notification: payload.notification,
      speak: payload.speak,
    };

    const entity = payload.entity.trim();
    const eventPayload = {
      name: payload.name.trim(),
      type: 'alarm',
      event_type: 'alarm',
      parameter: entity,
      use_case: 'check_alarm',
      data: JSON.stringify(dataObj),
      holiday: payload.holiday || 'all_days',
      notify: 0,
      notification_message: '',
      speak: 0,
      speak_message: '',
      is_active: payload.is_active !== undefined ? payload.is_active : 1,
    };

    return this.http.put<{ message: string; event_definition: EventDefinition }>(
      `${this.baseUrl}/event-definitions/${id}`,
      eventPayload,
      { headers: this.getHeaders() }
    );
  }

  deleteAlarmRule(id: number): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(
      `${this.baseUrl}/event-definitions/${id}`,
      { headers: this.getHeaders() }
    );
  }

  toggleRuleActive(
    rule: EventDefinition
  ): Observable<{ message: string; event_definition: EventDefinition }> {
    const newActive = rule.is_active === 1 ? 0 : 1;
    const payload = {
      name: rule.name,
      type: rule.type || 'alarm',
      event_type: rule.type || 'alarm',
      parameter: rule.parameter || '',
      use_case: rule.use_case,
      data: rule.data || '{}',
      holiday: rule.holiday || 'all_days',
      notify: rule.notify || 0,
      speak: rule.speak || 0,
      is_active: newActive,
    };

    return this.http.put<{ message: string; event_definition: EventDefinition }>(
      `${this.baseUrl}/event-definitions/${rule.id}`,
      payload,
      { headers: this.getHeaders() }
    );
  }

  getAlarmHistory(): Observable<{ status: string; events: AlarmMemoryEvent[] }> {
    return this.http.get<{ status: string; events: AlarmMemoryEvent[] }>(
      `${this.baseUrl}/alarm/events-history`,
      { headers: this.getHeaders() }
    );
  }

  clearAlarmHistory(): Observable<{ status: string; message: string }> {
    return this.http.delete<{ status: string; message: string }>(
      `${this.baseUrl}/alarm/events-history`,
      { headers: this.getHeaders() }
    );
  }

  testAlarm(payload: AlarmTestPayload): Observable<{ status: string; result: any }> {
    return this.http.post<{ status: string; result: any }>(
      `${this.baseUrl}/alarm/test`,
      payload,
      { headers: this.getHeaders() }
    );
  }

  parseRuleData(data: any): AlarmRuleData {
    if (!data) {
      return { entity: '', trigger: 2, seconds: 60, notification: true, speak: false };
    }
    if (typeof data === 'object') {
      return {
        entity: data.entity || '',
        trigger: Number(data.trigger) || 2,
        seconds: Number(data.seconds) || 60,
        notification: data.notification !== false && data.notification !== 0,
        speak: Boolean(data.speak),
      };
    }
    try {
      const parsed = JSON.parse(data);
      return {
        entity: parsed.entity || '',
        trigger: Number(parsed.trigger) || 2,
        seconds: Number(parsed.seconds) || 60,
        notification: parsed.notification !== false && parsed.notification !== 0,
        speak: Boolean(parsed.speak),
      };
    } catch {
      return { entity: '', trigger: 2, seconds: 60, notification: true, speak: false };
    }
  }
}
