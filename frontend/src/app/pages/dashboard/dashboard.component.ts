import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { HeatingMap, HeatingService } from '../../services/heating.service';
import {
  DeviceItem,
  HomeAssistantEntity,
  SettingsService,
} from '../../services/settings.service';
import { Schedule, SchedulesService } from '../../services/schedules.service';
import { EventDefinition, EventsService } from '../../services/events.service';

export const BLINDS_SCHEDULE_NAME = 'Auto - Blinds';
export const IRRIGATION_SCHEDULE_NAME = 'Auto - Irrigation';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss'
})
export class DashboardComponent implements OnInit {
  private readonly heatingService = inject(HeatingService);
  private readonly settingsService = inject(SettingsService);
  private readonly schedulesService = inject(SchedulesService);
  private readonly eventsService = inject(EventsService);

  // General State
  readonly loading = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);

  // Heating Section State
  readonly heatingState = signal<'on' | 'off'>('off');
  readonly activeMapName = signal<string>('None');
  readonly activeMap = signal<HeatingMap | null>(null);
  readonly heatingMapsCount = signal<number>(0);
  readonly calendarSlotsCount = signal<number>(0);
  readonly temperatureDevices = signal<DeviceItem[]>([]);

  // Devices & HA State
  readonly devices = signal<DeviceItem[]>([]);
  readonly hassEntities = signal<HomeAssistantEntity[]>([]);
  readonly operatingDeviceIds = signal<Set<number>>(new Set());
  readonly localDevicePositions = signal<Map<number, number>>(new Map());

  // Schedules & Events State
  readonly schedules = signal<Schedule[]>([]);
  readonly eventDefinitions = signal<EventDefinition[]>([]);

  // Filtered computed signals
  readonly blindDevices = computed(() => {
    return this.devices().filter((d) => d.type === 'blinds');
  });

  readonly irrigationDevices = computed(() => {
    return this.devices().filter((d) => d.type === 'irrigation');
  });

  readonly blindsSchedulesCount = computed(() => {
    return this.schedules().filter(
      (s) => s.name.startsWith(BLINDS_SCHEDULE_NAME) || s.use_case === 'blinds' || s.use_case === 'move_blind'
    ).length;
  });

  readonly blindsEventsCount = computed(() => {
    return this.eventDefinitions().filter(
      (e) => e.use_case === 'blinds' || e.use_case === 'move_blind' || e.name.toLowerCase().includes('blind') || e.name.toLowerCase().includes('persiana')
    ).length;
  });

  readonly irrigationSchedulesCount = computed(() => {
    return this.schedules().filter(
      (s) => s.name.startsWith(IRRIGATION_SCHEDULE_NAME) || s.use_case === 'irrigation' || s.use_case === 'start_irrigation'
    ).length;
  });

  readonly irrigationEventsCount = computed(() => {
    return this.eventDefinitions().filter(
      (e) => e.use_case === 'irrigation' || e.use_case === 'start_irrigation' || e.name.toLowerCase().includes('irrigat')
    ).length;
  });

  ngOnInit(): void {
    this.loadAllDashboardData();
  }

  loadAllDashboardData(): void {
    this.loading.set(true);
    this.errorMessage.set(null);

    // 1. Load Heating Status
    this.heatingService.getHeatingState().subscribe({
      next: (resp) => {
        this.heatingState.set(resp.state || 'off');
        this.temperatureDevices.set(resp.temperature_devices || []);
        if (resp.active_map) {
          this.activeMap.set(resp.active_map);
          this.activeMapName.set(resp.active_map.name);
        }
      },
      error: (err) => {
        console.error('Failed to load heating status:', err);
      }
    });

    // 2. Load Heating Maps
    this.heatingService.getHeatingMaps().subscribe({
      next: (resp) => {
        this.heatingMapsCount.set(resp.maps?.length || 0);
        const active = resp.maps?.find((m) => m.id === resp.active_map_id);
        if (active) {
          if (!this.activeMap()) {
            this.activeMap.set(active);
          }
          if (this.activeMapName() === 'None') {
            this.activeMapName.set(active.name);
          }
        }
      },
      error: (err) => {
        console.error('Failed to load heating maps:', err);
      }
    });

    // 3. Load Heating Calendar
    this.heatingService.getHeatingCalendar().subscribe({
      next: (resp) => {
        this.calendarSlotsCount.set(resp.calendar?.length || 0);
      },
      error: (err) => {
        console.error('Failed to load heating calendar:', err);
      }
    });

    // 4. Load Configured Devices
    this.settingsService.getDevices().subscribe({
      next: (resp) => {
        this.devices.set(resp.devices || []);
        this.loading.set(false);
      },
      error: (err) => {
        console.error('Failed to load devices:', err);
        this.loading.set(false);
      }
    });

    // 5. Load Home Assistant Entities
    this.settingsService.getHomeAssistantEntities().subscribe({
      next: (resp) => {
        this.hassEntities.set(resp.entities || []);
      },
      error: (err) => {
        console.error('Failed to load HA entities:', err);
      }
    });

    // 6. Load Schedules
    this.schedulesService.getSchedules().subscribe({
      next: (resp) => {
        this.schedules.set(resp.schedules || []);
      },
      error: (err) => {
        console.error('Failed to load schedules:', err);
      }
    });

    // 7. Load Event Definitions
    this.eventsService.getEventDefinitions().subscribe({
      next: (resp) => {
        this.eventDefinitions.set(resp.event_definitions || []);
      },
      error: (err) => {
        console.error('Failed to load events:', err);
      }
    });
  }

  // ==========================================
  // Heating Card Actions & Helpers
  // ==========================================
  toggleHeatingMaster(event: Event): void {
    const inputEl = event.target as HTMLInputElement;
    const targetAction: 'on' | 'off' = inputEl.checked ? 'on' : 'off';

    this.heatingService.setHeatingState({ action: targetAction }).subscribe({
      next: (resp) => {
        this.heatingState.set(resp.state?.state || targetAction);
        this.successMessage.set(`Heating system ${targetAction === 'on' ? 'activated' : 'deactivated'}`);
        setTimeout(() => this.successMessage.set(null), 3500);
      },
      error: (err) => {
        this.errorMessage.set(err.error?.detail || err.message || 'Failed to toggle heating state');
        this.heatingService.getHeatingState().subscribe({
          next: (r) => this.heatingState.set(r.state || 'off'),
          error: () => {}
        });
        setTimeout(() => this.errorMessage.set(null), 5000);
      }
    });
  }

  formatTemp(temp?: number | string | null): string {
    if (temp === null || temp === undefined || temp === '') return '—';
    const num = typeof temp === 'number' ? temp : parseFloat(String(temp));
    return isNaN(num) ? String(temp) : num.toFixed(1);
  }

  getTargetTemp(deviceId: number): number | null {
    const map = this.activeMap();
    if (!map || !map.rules) return null;
    const val = map.rules[deviceId] ?? map.rules[String(deviceId)];
    if (val !== undefined && val !== null && !isNaN(Number(val))) {
      return Number(val);
    }
    return null;
  }

  // ==========================================
  // Blinds Card Actions & Helpers
  // ==========================================
  isDeviceOperating(deviceId: number): boolean {
    return this.operatingDeviceIds().has(deviceId);
  }

  getDevicePosition(device: DeviceItem): number {
    if (!device) return 100;
    if (this.localDevicePositions().has(device.id)) {
      return this.localDevicePositions().get(device.id)!;
    }
    const match = this.hassEntities().find((e) => e.entity_id === device.entity_id);
    if (match) {
      if (match.current_position !== undefined && match.current_position !== null) {
        return Number(match.current_position);
      }
      if (match.state?.toLowerCase() === 'closed') return 0;
      if (match.state?.toLowerCase() === 'open') return 100;
    }
    return 100;
  }

  getPositionLabel(pos: number): string {
    if (pos === 0) return '0% (Closed)';
    if (pos === 100) return '100% (Open)';
    return `${pos}%`;
  }

  onBlindSliderInput(device: DeviceItem, event: Event): void {
    if (!device) return;
    const inputEl = event.target as HTMLInputElement;
    const val = Math.min(100, Math.max(0, parseInt(inputEl.value, 10) || 0));
    this.localDevicePositions.update((map) => new Map(map).set(device.id, val));
  }

  onBlindSliderChange(device: DeviceItem, event: Event): void {
    if (!device) return;
    const inputEl = event.target as HTMLInputElement;
    const targetPos = Math.min(100, Math.max(0, parseInt(inputEl.value, 10) || 0));

    this.operatingDeviceIds.update((s) => new Set(s).add(device.id));

    this.settingsService.triggerDeviceAction(device.id, 'set_position', targetPos).subscribe({
      next: (resp) => {
        const finalPos = resp.position !== undefined ? resp.position : targetPos;
        this.hassEntities.update((entities) =>
          entities.map((e) =>
            e.entity_id === device.entity_id
              ? {
                  ...e,
                  state: finalPos === 0 ? 'closed' : 'open',
                  current_position: finalPos,
                }
              : e
          )
        );
        this.localDevicePositions.update((map) => {
          const next = new Map(map);
          next.delete(device.id);
          return next;
        });
        this.operatingDeviceIds.update((s) => {
          const next = new Set(s);
          next.delete(device.id);
          return next;
        });
        this.successMessage.set(`Blind '${device.name}' set to ${finalPos}%`);
        setTimeout(() => this.successMessage.set(null), 3500);
      },
      error: (err) => {
        this.localDevicePositions.update((map) => {
          const next = new Map(map);
          next.delete(device.id);
          return next;
        });
        this.operatingDeviceIds.update((s) => {
          const next = new Set(s);
          next.delete(device.id);
          return next;
        });
        this.errorMessage.set(err.error?.detail || err.message || 'Failed to adjust blind position');
        setTimeout(() => this.errorMessage.set(null), 5000);
      }
    });
  }

  // ==========================================
  // Irrigation Card Actions & Helpers
  // ==========================================
  isDeviceOn(device: DeviceItem): boolean {
    if (!device || !device.entity_id) return false;
    const match = this.hassEntities().find((e) => e.entity_id === device.entity_id);
    return match?.state?.toLowerCase() === 'on';
  }

  toggleIrrigationDevice(device: DeviceItem, event: Event): void {
    if (!device) return;
    const inputEl = event.target as HTMLInputElement;
    const targetAction: 'on' | 'off' = inputEl.checked ? 'on' : 'off';

    this.operatingDeviceIds.update((s) => new Set(s).add(device.id));

    this.settingsService.triggerDeviceAction(device.id, targetAction).subscribe({
      next: (resp) => {
        this.hassEntities.update((entities) =>
          entities.map((e) =>
            e.entity_id === device.entity_id ? { ...e, state: resp.state || targetAction } : e
          )
        );
        this.operatingDeviceIds.update((s) => {
          const next = new Set(s);
          next.delete(device.id);
          return next;
        });
        this.successMessage.set(`Irrigation '${device.name}' turned ${targetAction.toUpperCase()}`);
        setTimeout(() => this.successMessage.set(null), 3500);
      },
      error: (err) => {
        this.operatingDeviceIds.update((s) => {
          const next = new Set(s);
          next.delete(device.id);
          return next;
        });
        this.errorMessage.set(err.error?.detail || err.message || 'Failed to toggle irrigation device');
        setTimeout(() => this.errorMessage.set(null), 5000);
      }
    });
  }
}
