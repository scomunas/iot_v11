import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface SystemFunction {
  id: string;
  name: string;
  description: string;
}

export interface UseCase {
  id: number;
  name: string;
  function_name: string;
  description?: string;
  section?: string | null;
  created_at: string;
}

export interface UseCasesResponse {
  use_cases: UseCase[];
  available_functions: SystemFunction[];
  available_sections?: string[];
}

export interface UseCasePayload {
  name: string;
  function_name: string;
  description?: string;
  section?: string | null;
}

export interface TestExecutionResult {
  message: string;
  result_file?: string;
  result?: any;
}

export interface TelegramStatus {
  configured: boolean;
  bot_token_configured: boolean;
  chat_id_configured: boolean;
  bot_token_masked?: string | null;
  chat_id_masked?: string | null;
  default_chat_id?: string | null;
  message: string;
}

export interface TelegramSendResponse {
  success: boolean;
  simulated?: boolean;
  chat_id?: string;
  message_id?: number;
  message?: string;
  error?: string;
  text?: string;
}

export type DeviceType = 'light' | 'irrigation' | 'temperature' | 'movement' | 'presence' | 'blinds' | 'rain' | 'heating';

export interface DeviceItem {
  id: number;
  name: string;
  type: DeviceType;
  entity_id: string;
  created_at: string;
  current_temperature?: number | string | null;
}

export interface DevicePayload {
  name: string;
  type: DeviceType;
  entity_id: string;
}

export interface DevicesResponse {
  devices: DeviceItem[];
}

export interface HomeAssistantEntity {
  entity_id: string;
  friendly_name: string;
  domain: string;
  state: string;
}

export interface HomeAssistantEntitiesResponse {
  connected: boolean;
  hass_url: string;
  entities: HomeAssistantEntity[];
  error?: string | null;
}

@Injectable({
  providedIn: 'root'
})
export class SettingsService {
  private readonly http = inject(HttpClient);

  private get headers(): HttpHeaders {
    return new HttpHeaders({
      'X-API-Key': environment.apiKey,
      'Content-Type': 'application/json',
    });
  }

  getUseCases(): Observable<UseCasesResponse> {
    return this.http.get<UseCasesResponse>(`${environment.backendUrl}/use-cases`, {
      headers: this.headers,
    });
  }

  createUseCase(payload: UseCasePayload): Observable<{ message: string; use_case: UseCase }> {
    return this.http.post<{ message: string; use_case: UseCase }>(
      `${environment.backendUrl}/use-cases`,
      payload,
      { headers: this.headers }
    );
  }

  updateUseCase(id: number, payload: UseCasePayload): Observable<{ message: string; use_case: UseCase }> {
    return this.http.put<{ message: string; use_case: UseCase }>(
      `${environment.backendUrl}/use-cases/${id}`,
      payload,
      { headers: this.headers }
    );
  }

  deleteUseCase(id: number): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(
      `${environment.backendUrl}/use-cases/${id}`,
      { headers: this.headers }
    );
  }

  testUseCase(id: number, data?: any): Observable<TestExecutionResult> {
    const body = data !== undefined ? { data } : {};
    return this.http.post<TestExecutionResult>(
      `${environment.backendUrl}/use-cases/${id}/test`,
      body,
      { headers: this.headers }
    );
  }

  // ==========================================
  // Devices & Home Assistant
  // ==========================================

  getDevices(): Observable<DevicesResponse> {
    return this.http.get<DevicesResponse>(`${environment.backendUrl}/devices`, {
      headers: this.headers,
    });
  }

  createDevice(payload: DevicePayload): Observable<{ message: string; device: DeviceItem }> {
    return this.http.post<{ message: string; device: DeviceItem }>(
      `${environment.backendUrl}/devices`,
      payload,
      { headers: this.headers }
    );
  }

  updateDevice(id: number, payload: DevicePayload): Observable<{ message: string; device: DeviceItem }> {
    return this.http.put<{ message: string; device: DeviceItem }>(
      `${environment.backendUrl}/devices/${id}`,
      payload,
      { headers: this.headers }
    );
  }

  deleteDevice(id: number): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(
      `${environment.backendUrl}/devices/${id}`,
      { headers: this.headers }
    );
  }

  getHomeAssistantEntities(): Observable<HomeAssistantEntitiesResponse> {
    return this.http.get<HomeAssistantEntitiesResponse>(
      `${environment.backendUrl}/homeassistant/entities`,
      { headers: this.headers }
    );
  }

  getTelegramStatus(): Observable<TelegramStatus> {
    return this.http.get<TelegramStatus>(
      `${environment.backendUrl}/telegram/status`,
      { headers: this.headers }
    );
  }

  sendTelegramAlert(message: string, chatId?: string): Observable<TelegramSendResponse> {
    const payload: any = { message };
    if (chatId) payload.chat_id = chatId;
    return this.http.post<TelegramSendResponse>(
      `${environment.backendUrl}/telegram/send`,
      payload,
      { headers: this.headers }
    );
  }

  getSystemSettings(): Observable<{ settings: Record<string, any> }> {
    return this.http.get<{ settings: Record<string, any> }>(
      `${environment.backendUrl}/settings`,
      { headers: this.headers }
    );
  }

  updateSystemSettings(payload: Record<string, any>): Observable<{ message: string; settings: Record<string, any> }> {
    return this.http.put<{ message: string; settings: Record<string, any> }>(
      `${environment.backendUrl}/settings`,
      payload,
      { headers: this.headers }
    );
  }
}
