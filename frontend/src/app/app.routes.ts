import { Routes } from '@angular/router';
import { DashboardComponent } from './pages/dashboard/dashboard.component';
import { IrrigationComponent } from './pages/irrigation/irrigation.component';
import { BlindsComponent } from './pages/blinds/blinds.component';
import { HeatingComponent } from './pages/heating/heating.component';
import { SchedulesComponent } from './pages/schedules/schedules.component';
import { EventsComponent } from './pages/events/events.component';
import { HolidaysComponent } from './pages/holidays/holidays.component';
import { LogsComponent } from './pages/logs/logs.component';
import { SettingsComponent } from './pages/settings/settings.component';

export const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  { path: 'dashboard', component: DashboardComponent },
  { path: 'irrigation', component: IrrigationComponent },
  { path: 'blinds', component: BlindsComponent },
  { path: 'heating', component: HeatingComponent },
  { path: 'schedules', component: SchedulesComponent },
  { path: 'events', component: EventsComponent },
  { path: 'holidays', component: HolidaysComponent },
  { path: 'logs', component: LogsComponent },
  { path: 'log', redirectTo: 'logs' },
  { path: 'settings', component: SettingsComponent },
  { path: '**', redirectTo: 'dashboard' },
];
