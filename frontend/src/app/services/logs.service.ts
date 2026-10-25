import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface LogEntry {
  id: number;
  timestamp: string;
  level: string;
  logger: string;
  message: string;
}

export interface PaginatedLogsResponse {
  logs: LogEntry[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

@Injectable({
  providedIn: 'root'
})
export class LogsService {
  private readonly http = inject(HttpClient);

  private get headers(): HttpHeaders {
    return new HttpHeaders({
      'X-API-Key': environment.apiKey,
    });
  }

  getLogs(
    page: number = 1,
    pageSize: number = 25,
    level?: string,
    search?: string
  ): Observable<PaginatedLogsResponse> {
    let params = new HttpParams()
      .set('page', page.toString())
      .set('page_size', pageSize.toString());

    if (level && level.toUpperCase() !== 'ALL') {
      params = params.set('level', level.toUpperCase());
    }
    if (search && search.trim()) {
      params = params.set('search', search.trim());
    }

    return this.http.get<PaginatedLogsResponse>(`${environment.backendUrl}/logs`, {
      headers: this.headers,
      params,
    });
  }

  clearLogs(): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(`${environment.backendUrl}/logs`, {
      headers: this.headers,
    });
  }
}
