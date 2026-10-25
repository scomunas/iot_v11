import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface Holiday {
  id: number;
  date: string;
  name?: string;
  created_at: string;
}

export interface HolidaysResponse {
  holidays: Holiday[];
}

export interface CreateHolidayPayload {
  date: string;
  name?: string;
}

export interface CreateHolidayResponse {
  message: string;
  holiday: Holiday;
}

export interface DeleteHolidayResponse {
  message: string;
  id: number;
}

@Injectable({
  providedIn: 'root'
})
export class HolidaysService {
  private readonly http = inject(HttpClient);

  private get headers(): HttpHeaders {
    return new HttpHeaders({
      'X-API-Key': environment.apiKey,
      'Content-Type': 'application/json',
    });
  }

  getHolidays(): Observable<HolidaysResponse> {
    return this.http.get<HolidaysResponse>(`${environment.backendUrl}/holidays`, {
      headers: this.headers,
    });
  }

  createHoliday(payload: CreateHolidayPayload): Observable<CreateHolidayResponse> {
    return this.http.post<CreateHolidayResponse>(`${environment.backendUrl}/holidays`, payload, {
      headers: this.headers,
    });
  }

  deleteHoliday(id: number): Observable<DeleteHolidayResponse> {
    return this.http.delete<DeleteHolidayResponse>(`${environment.backendUrl}/holidays/${id}`, {
      headers: this.headers,
    });
  }

  syncYearHolidays(payload?: { year?: number; county?: string }): Observable<{ status: string; message: string; holidays: Holiday[] }> {
    return this.http.post<{ status: string; message: string; holidays: Holiday[] }>(
      `${environment.backendUrl}/holidays/sync`,
      payload || {},
      {
        headers: this.headers,
      }
    );
  }
}
