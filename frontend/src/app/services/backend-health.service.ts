import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { environment } from '../../environments/environment';

export interface HealthResponse {
  status: string;
  timestamp: string;
  environment?: string;
  database?: string;
  scheduler?: string;
  homeassistant?: string;
}

export type HealthStatus = 'checking' | 'online' | 'offline';

@Injectable({
  providedIn: 'root'
})
export class BackendHealthService {
  private readonly http = inject(HttpClient);

  readonly status = signal<HealthStatus>('checking');
  readonly healthData = signal<HealthResponse | null>(null);
  readonly lastChecked = signal<Date | null>(null);
  readonly errorMessage = signal<string | null>(null);

  readonly schedulerStatus = computed<HealthStatus>(() => {
    if (this.status() === 'checking') return 'checking';
    if (this.healthData()?.scheduler === 'running') return 'online';
    return 'offline';
  });

  readonly databaseStatus = computed<HealthStatus>(() => {
    if (this.status() === 'checking') return 'checking';
    if (this.healthData()?.database === 'connected') return 'online';
    return 'offline';
  });

  readonly homeAssistantStatus = computed<HealthStatus>(() => {
    if (this.status() === 'checking') return 'checking';
    if (this.healthData()?.homeassistant === 'connected') return 'online';
    return 'offline';
  });

  constructor() {
    this.checkHealth();
    // Periodically refresh health check every 20 seconds
    setInterval(() => this.checkHealth(), 20000);
  }

  checkHealth(): void {
    this.status.set('checking');
    this.errorMessage.set(null);

    const headers = new HttpHeaders({
      'X-API-Key': environment.apiKey,
    });

    this.http.get<HealthResponse>(`${environment.backendUrl}/health`, { headers }).subscribe({
      next: (response) => {
        this.healthData.set(response);
        this.status.set(response.status === 'healthy' ? 'online' : 'offline');
        this.lastChecked.set(new Date());
        this.errorMessage.set(null);
      },
      error: (err) => {
        this.status.set('offline');
        this.healthData.set(null);
        this.lastChecked.set(new Date());
        this.errorMessage.set(err.status ? `HTTP ${err.status}` : 'Connection refused');
      }
    });
  }
}
