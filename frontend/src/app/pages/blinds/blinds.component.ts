import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ConfirmModalComponent } from '../../components/confirm-modal/confirm-modal.component';
import { Schedule, SchedulesService, SchedulePayload } from '../../services/schedules.service';
import {
  DeviceItem,
  HomeAssistantEntity,
  SettingsService,
  UseCase,
} from '../../services/settings.service';
import {
  EventDefinition,
  EventDefinitionPayload,
  EventsService,
} from '../../services/events.service';

export const BLINDS_SCHEDULE_NAME = 'Auto - Blinds';

@Component({
  selector: 'app-blinds',
  standalone: true,
  imports: [CommonModule, FormsModule, DatePipe, RouterLink, ConfirmModalComponent],
  templateUrl: './blinds.component.html',
  styleUrl: './blinds.component.scss'
})
export class BlindsComponent implements OnInit {
  private readonly schedulesService = inject(SchedulesService);
  private readonly settingsService = inject(SettingsService);
  private readonly eventsService = inject(EventsService);

  // Core Data Signals
  readonly allSchedules = signal<Schedule[]>([]);
  readonly inMemoryJobMap = signal<Map<string, string | null>>(new Map());
  readonly devices = signal<DeviceItem[]>([]);
  readonly allEventDefinitions = signal<EventDefinition[]>([]);
  readonly configuredUseCases = signal<UseCase[]>([]);
  readonly hassEntities = signal<HomeAssistantEntity[]>([]);

  // State Signals
  readonly loading = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);
  readonly operatingDeviceIds = signal<Set<number>>(new Set());
  readonly localDevicePositions = signal<Map<number, number>>(new Map());

  // Active Device selection (null = show all cards, DeviceItem = show 2 tables view)
  readonly activeDevice = signal<DeviceItem | null>(null);

  // Filtered lists
  readonly blindDevices = computed(() => {
    return this.devices().filter((d) => d.type === 'blinds');
  });

  readonly blindsSchedules = computed(() => {
    return this.allSchedules().filter((s) => s.name.startsWith(BLINDS_SCHEDULE_NAME));
  });

  readonly blindsUseCase = computed(() => {
    const list = this.configuredUseCases();
    return (
      list.find((u) => u.section === 'blinds') ||
      list.find((u) => u.function_name === 'move_blind') ||
      list.find((u) => u.name.toLowerCase().includes('blind')) ||
      list.find((u) => u.name.toLowerCase().includes('persiana')) ||
      list[0]
    );
  });

  // Schedules and Events for the active device
  readonly activeDeviceSchedules = computed(() => {
    const dev = this.activeDevice();
    if (!dev) return [];
    return this.getSchedulesForDevice(dev);
  });

  readonly activeDeviceEvents = computed(() => {
    const dev = this.activeDevice();
    if (!dev) return [];
    return this.getEventsForDevice(dev);
  });

  // ==========================================
  // Schedule Modal State
  // ==========================================
  readonly isScheduleModalOpen = signal<boolean>(false);
  readonly scheduleModalMode = signal<'create' | 'edit'>('create');
  readonly selectedScheduleId = signal<number | null>(null);

  // Backward compatibility aliases
  readonly isModalOpen = computed(() => this.isScheduleModalOpen());
  readonly modalMode = computed(() => this.scheduleModalMode());

  readonly fixedScheduleName = BLINDS_SCHEDULE_NAME;
  readonly fixedScheduleType = 'recurrent';

  // Schedule form fields
  formFrequencyMode: 'preset' | 'custom' = 'preset';
  formFrequencyPreset: string = 'daily';
  formStartTime: string = '08:00';
  formCustomCron: string = '0 8 * * *';
  formPosition: number = 100; // 0 to 100
  formNotBefore: string = '';
  formScheduleIsActive: number = 1;
  formScheduleNotify: number = 0;
  formScheduleNotificationMessage: string = '';

  // Additional fields for compatibility
  formUseCase: string = '';
  formEntityId: string = '';
  formIsActive: number = 1;

  readonly positionPresets = [
    { label: '0% (Closed)', position: 0 },
    { label: '25%', position: 25 },
    { label: '50% (Half)', position: 50 },
    { label: '75%', position: 75 },
    { label: '100% (Open)', position: 100 },
  ];

  // ==========================================
  // Event Modal State
  // ==========================================
  readonly isEventModalOpen = signal<boolean>(false);
  readonly eventModalMode = signal<'create' | 'edit'>('create');
  readonly selectedEventId = signal<number | null>(null);

  formEventType: string = 'sunrise';
  formEventParameter: string = '';
  formEventPosition: number = 100;
  formEventNotBefore: string = '';
  formEventHoliday: string = 'all_days';
  formEventIsActive: number = 1;
  formEventNotify: number = 0;
  formEventNotificationMessage: string = '';

  getHolidayLabel(holiday?: string): string {
    switch (holiday) {
      case 'holiday':
        return 'Holidays & Weekends';
      case 'not_holiday':
        return 'Workdays Only';
      default:
        return 'All Days';
    }
  }

  // ==========================================
  // Device Modal State
  // ==========================================
  readonly isDeviceModalOpen = signal<boolean>(false);
  readonly deviceModalMode = signal<'create' | 'edit'>('create');
  readonly selectedDeviceId = signal<number | null>(null);

  formDeviceName: string = '';
  formDeviceEntityId: string = '';
  deviceEntitySearch: string = '';

  readonly filteredHassEntities = computed(() => {
    const q = this.deviceEntitySearch.toLowerCase().trim();
    const list = this.hassEntities();
    if (!q) {
      return list.filter((e) => e.domain === 'cover').concat(list.filter((e) => e.domain !== 'cover'));
    }
    return list.filter(
      (e) =>
        e.friendly_name.toLowerCase().includes(q) ||
        e.entity_id.toLowerCase().includes(q)
    );
  });

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading.set(true);
    this.errorMessage.set(null);

    // 1. Load schedules
    this.schedulesService.getSchedules().subscribe({
      next: (resp) => {
        this.allSchedules.set(resp.schedules);
        const jobMap = new Map<string, string | null>();
        resp.in_memory_jobs.forEach((j) => {
          jobMap.set(j.job_id, j.next_run_time);
        });
        this.inMemoryJobMap.set(jobMap);
        this.loading.set(false);
      },
      error: (err) => {
        this.errorMessage.set(err.message || 'Failed to load schedules from backend');
        this.loading.set(false);
      }
    });

    // 2. Load configured devices
    this.settingsService.getDevices().subscribe({
      next: (resp) => {
        this.devices.set(resp.devices || []);
        const current = this.activeDevice();
        if (current) {
          const updated = resp.devices.find((d) => d.id === current.id);
          this.activeDevice.set(updated || null);
        }
      },
      error: (err) => {
        console.error('Failed to load devices:', err);
      }
    });

    // 3. Load configured use cases
    this.settingsService.getUseCases().subscribe({
      next: (resp) => {
        this.configuredUseCases.set(resp.use_cases || []);
      },
      error: (err) => {
        console.error('Failed to load use cases:', err);
      }
    });

    // 4. Load event definitions
    this.eventsService.getEventDefinitions().subscribe({
      next: (resp) => {
        this.allEventDefinitions.set(resp.event_definitions || []);
      },
      error: (err) => {
        console.error('Failed to load event definitions:', err);
      }
    });

    // 5. Load Home Assistant entities
    this.settingsService.getHomeAssistantEntities().subscribe({
      next: (resp) => {
        this.hassEntities.set(resp.entities || []);
      },
      error: (err) => {
        console.error('Failed to load HA entities:', err);
      }
    });
  }

  // ==========================================
  // Device Selection & Navigation
  // ==========================================
  openDeviceDetail(device: DeviceItem): void {
    this.activeDevice.set(device);
  }

  closeDeviceDetail(): void {
    this.activeDevice.set(null);
  }

  // ==========================================
  // Manual Blind Position Controls (Slider)
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

  onSliderInput(device: DeviceItem, event: Event): void {
    if (!device) return;
    const inputEl = event.target as HTMLInputElement;
    const val = Math.min(100, Math.max(0, parseInt(inputEl.value, 10) || 0));
    this.localDevicePositions.update((map) => new Map(map).set(device.id, val));
  }

  onSliderChange(device: DeviceItem, event: Event): void {
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
          const updated = new Set(s);
          updated.delete(device.id);
          return updated;
        });
        this.successMessage.set(resp.message || `Blind '${device.name}' set to ${finalPos}%`);
        setTimeout(() => {
          if (this.successMessage()?.includes(device.name)) {
            this.successMessage.set(null);
          }
        }, 4000);
      },
      error: (err) => {
        this.localDevicePositions.update((map) => {
          const next = new Map(map);
          next.delete(device.id);
          return next;
        });
        this.operatingDeviceIds.update((s) => {
          const updated = new Set(s);
          updated.delete(device.id);
          return updated;
        });
        this.errorMessage.set(err.error?.detail || err.message || `Failed to move blind`);
        this.settingsService.getHomeAssistantEntities().subscribe({
          next: (r) => this.hassEntities.set(r.entities || []),
          error: () => {},
        });
        setTimeout(() => this.errorMessage.set(null), 5000);
      },
    });
  }

  getSchedulesForDevice(device: DeviceItem): Schedule[] {
    return this.blindsSchedules().filter((s) => {
      const data = this.parseData(s.data);
      return data.entity_id === device.entity_id || data.entity === device.entity_id;
    });
  }

  getEventsForDevice(device: DeviceItem): EventDefinition[] {
    return this.allEventDefinitions().filter((ed) => {
      const data = this.parseData(ed.data);
      return data.entity_id === device.entity_id || data.entity === device.entity_id;
    });
  }

  // ==========================================
  // Schedule Actions
  // ==========================================
  openCreateModal(targetDevice?: DeviceItem): void {
    this.scheduleModalMode.set('create');
    this.selectedScheduleId.set(null);

    const dev = targetDevice || this.activeDevice() || this.blindDevices()[0] || this.devices()[0];
    if (dev && !this.activeDevice()) {
      this.activeDevice.set(dev);
    }

    this.formEntityId = dev ? dev.entity_id : '';
    const bUc = this.blindsUseCase();
    this.formUseCase = bUc ? bUc.name : 'move_blind';

    this.formFrequencyMode = 'preset';
    this.formFrequencyPreset = 'daily';
    this.formStartTime = '08:00';
    this.formCustomCron = '0 8 * * *';
    this.formPosition = 100;
    this.formNotBefore = '';
    this.formScheduleIsActive = 1;
    this.formScheduleNotify = 0;
    this.formScheduleNotificationMessage = '';
    this.formIsActive = 1;

    this.isScheduleModalOpen.set(true);
  }

  openEditModal(schedule: Schedule): void {
    this.scheduleModalMode.set('edit');
    this.selectedScheduleId.set(schedule.id);

    this.formUseCase = schedule.use_case;
    this.formScheduleIsActive = schedule.is_active;
    this.formScheduleNotify = schedule.notify ?? 0;
    this.formScheduleNotificationMessage = schedule.notification_message || '';
    this.formIsActive = schedule.is_active;

    const params = this.parseData(schedule.data);
    this.formEntityId = params.entity || params.entity_id || '';
    this.formPosition = params.position !== undefined ? Number(params.position) : 100;
    this.formNotBefore = params.not_before || '';

    this.detectFrequency(schedule.trigger_spec);

    const matchingDevice = this.blindDevices().find((d) => d.entity_id === this.formEntityId);
    if (matchingDevice && !this.activeDevice()) {
      this.activeDevice.set(matchingDevice);
    }

    this.isScheduleModalOpen.set(true);
  }

  closeScheduleModal(): void {
    this.isScheduleModalOpen.set(false);
  }

  closeModal(): void {
    this.closeScheduleModal();
  }

  setPosition(pos: number): void {
    this.formPosition = pos;
  }

  setEventPosition(pos: number): void {
    this.formEventPosition = pos;
  }

  onFrequencyChange(): void {
    const [h, m] = this.formStartTime.split(':').map((v) => parseInt(v, 10) || 0);
    if (this.formFrequencyPreset === 'daily') {
      this.formCustomCron = `${m} ${h} * * *`;
    } else if (this.formFrequencyPreset === 'twice_daily') {
      const eveningHour = (h + 12) % 24;
      this.formCustomCron = `${m} ${h},${eveningHour} * * *`;
    } else if (this.formFrequencyPreset === 'every_2_days') {
      this.formCustomCron = `${m} ${h} */2 * *`;
    } else if (this.formFrequencyPreset === 'every_3_days') {
      this.formCustomCron = `${m} ${h} */3 * *`;
    }
  }

  private detectFrequency(cron: string): void {
    const parts = cron.trim().split(/\s+/);
    if (parts.length === 5) {
      const [m, h, dom, mon, dow] = parts;
      const pad = (n: string) => n.padStart(2, '0');
      if (dom === '*' && mon === '*' && dow === '*') {
        if (!h.includes(',')) {
          this.formFrequencyMode = 'preset';
          this.formFrequencyPreset = 'daily';
          this.formStartTime = `${pad(h)}:${pad(m)}`;
          return;
        } else if (h.split(',').length === 2) {
          this.formFrequencyMode = 'preset';
          this.formFrequencyPreset = 'twice_daily';
          this.formStartTime = `${pad(h.split(',')[0])}:${pad(m)}`;
          return;
        }
      } else if (dom === '*/2' && mon === '*' && dow === '*') {
        this.formFrequencyMode = 'preset';
        this.formFrequencyPreset = 'every_2_days';
        this.formStartTime = `${pad(h)}:${pad(m)}`;
        return;
      } else if (dom === '*/3' && mon === '*' && dow === '*') {
        this.formFrequencyMode = 'preset';
        this.formFrequencyPreset = 'every_3_days';
        this.formStartTime = `${pad(h)}:${pad(m)}`;
        return;
      }
    }

    this.formFrequencyMode = 'custom';
    this.formCustomCron = cron;
  }

  computeFinalCron(): string {
    if (this.formFrequencyMode === 'preset') {
      const [h, m] = this.formStartTime.split(':').map((v) => parseInt(v, 10) || 0);
      if (this.formFrequencyPreset === 'daily') {
        return `${m} ${h} * * *`;
      } else if (this.formFrequencyPreset === 'twice_daily') {
        const eveningHour = (h + 12) % 24;
        return `${m} ${h},${eveningHour} * * *`;
      } else if (this.formFrequencyPreset === 'every_2_days') {
        return `${m} ${h} */2 * *`;
      } else if (this.formFrequencyPreset === 'every_3_days') {
        return `${m} ${h} */3 * *`;
      }
    }
    return this.formCustomCron.trim();
  }

  saveSchedule(): void {
    const dev = this.activeDevice();
    const entityId = dev ? dev.entity_id : this.formEntityId;

    if (!entityId) {
      alert('Please select or configure a blind device.');
      return;
    }

    const bUc = this.blindsUseCase();
    const useCaseName = this.formUseCase || (bUc ? bUc.name : 'move_blind');

    const cron = this.computeFinalCron();
    if (!cron) {
      alert('Please specify a valid cron frequency.');
      return;
    }

    const dataObj: any = {
      entity: entityId,
      entity_id: entityId,
      position: Math.min(100, Math.max(0, Math.round(this.formPosition))),
    };
    if (this.formNotBefore.trim()) {
      dataObj.not_before = this.formNotBefore.trim();
    }

    const deviceName = dev
      ? dev.name
      : (this.devices().find((d) => d.entity_id === entityId)?.name || entityId);
    const scheduleName = `Auto - Blinds - ${deviceName}`;

    const payload: SchedulePayload = {
      name: scheduleName,
      type: 'recurrent',
      trigger_spec: cron,
      use_case: useCaseName,
      is_active: this.formScheduleIsActive,
      data: JSON.stringify(dataObj),
      notify: this.formScheduleNotify,
      notification_message: this.formScheduleNotify === 1 ? this.formScheduleNotificationMessage.trim() : '',
    };

    if (this.scheduleModalMode() === 'create') {
      this.schedulesService.createSchedule(payload).subscribe({
        next: () => {
          this.showSuccess('Blinds schedule created successfully!');
          this.closeScheduleModal();
          this.loadData();
        },
        error: (err) => {
          alert(`Error creating blinds schedule: ${err.error?.detail || err.message}`);
        }
      });
    } else {
      const id = this.selectedScheduleId();
      if (!id) return;
      this.schedulesService.updateSchedule(id, payload).subscribe({
        next: () => {
          this.showSuccess(`Blinds schedule #${id} updated successfully!`);
          this.closeScheduleModal();
          this.loadData();
        },
        error: (err) => {
          alert(`Error updating blinds schedule: ${err.error?.detail || err.message}`);
        }
      });
    }
  }

  toggleScheduleActive(schedule: Schedule): void {
    const newActive = schedule.is_active === 1 ? 0 : 1;
    this.schedulesService.updateSchedule(schedule.id, {
      name: schedule.name,
      type: schedule.type,
      trigger_spec: schedule.trigger_spec,
      use_case: schedule.use_case,
      is_active: newActive,
      data: schedule.data || '{}',
      notify: schedule.notify ?? 0,
      notification_message: schedule.notification_message || '',
    }).subscribe({
      next: () => {
        this.showSuccess(`Schedule #${schedule.id} ${newActive ? 'activated' : 'paused'}.`);
        this.loadData();
      },
      error: (err) => {
        alert(`Failed to update status: ${err.error?.detail || err.message}`);
      }
    });
  }

  // Confirmation Modal State
  readonly isConfirmModalOpen = signal<boolean>(false);
  readonly confirmModalTitle = signal<string>('Confirm Action');
  readonly confirmModalMessage = signal<string>('');
  readonly isConfirming = signal<boolean>(false);
  private pendingConfirmAction: (() => void) | null = null;

  openConfirmModal(title: string, message: string, action: () => void): void {
    this.confirmModalTitle.set(title);
    this.confirmModalMessage.set(message);
    this.pendingConfirmAction = action;
    this.isConfirmModalOpen.set(true);
  }

  closeConfirmModal(): void {
    this.isConfirmModalOpen.set(false);
    this.pendingConfirmAction = null;
    this.isConfirming.set(false);
  }

  handleConfirmModal(): void {
    if (this.pendingConfirmAction) {
      this.pendingConfirmAction();
    }
  }

  deleteSchedule(schedule: Schedule): void {
    this.openConfirmModal(
      'Delete Blinds Schedule',
      `Are you sure you want to delete blinds schedule #${schedule.id}?`,
      () => {
        this.isConfirming.set(true);
        this.schedulesService.deleteSchedule(schedule.id).subscribe({
          next: () => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            this.showSuccess(`Blinds schedule #${schedule.id} deleted.`);
            this.loadData();
          },
          error: (err) => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            alert(`Failed to delete schedule: ${err.error?.detail || err.message}`);
          }
        });
      }
    );
  }

  // ==========================================
  // Event Actions
  // ==========================================
  openCreateEventModal(targetDevice?: DeviceItem): void {
    this.eventModalMode.set('create');
    this.selectedEventId.set(null);

    const dev = targetDevice || this.activeDevice() || this.blindDevices()[0];
    if (dev && !this.activeDevice()) {
      this.activeDevice.set(dev);
    }

    this.formEventType = 'sunset';
    this.formEventParameter = '';
    this.formEventPosition = 0; // default close at sunset
    this.formEventNotBefore = '';
    this.formEventHoliday = 'all_days';
    this.formEventIsActive = 1;
    this.formEventNotify = 0;
    this.formEventNotificationMessage = '';

    this.isEventModalOpen.set(true);
  }

  selectEventPreset(type: string, param: string = '', pos?: number): void {
    this.formEventType = type;
    this.formEventParameter = param;
    if (pos !== undefined) {
      this.formEventPosition = pos;
    }
  }

  openEditEventModal(eventDef: EventDefinition): void {
    this.eventModalMode.set('edit');
    this.selectedEventId.set(eventDef.id);

    this.formEventType = eventDef.type;
    this.formEventParameter = eventDef.parameter || '';
    this.formEventHoliday = eventDef.holiday || 'all_days';
    this.formEventIsActive = eventDef.is_active;
    this.formEventNotify = eventDef.notify ?? 0;
    this.formEventNotificationMessage = eventDef.notification_message || '';

    const params = this.parseData(eventDef.data);
    this.formEventPosition = params.position !== undefined ? Number(params.position) : 100;
    this.formEventNotBefore = params.not_before || '';

    this.isEventModalOpen.set(true);
  }

  closeEventModal(): void {
    this.isEventModalOpen.set(false);
  }

  saveEvent(): void {
    const dev = this.activeDevice();
    if (!dev) {
      alert('Please select an active blind device.');
      return;
    }

    if (!this.formEventType.trim()) {
      alert('Please specify an event type (e.g. sunrise, sunset).');
      return;
    }

    const bUc = this.blindsUseCase();
    const useCaseName = bUc ? bUc.name : 'move_blind';

    const eventName = `Auto - Blinds - ${dev.name}`;
    const dataObj: any = {
      entity: dev.entity_id,
      entity_id: dev.entity_id,
      position: Math.min(100, Math.max(0, Math.round(this.formEventPosition))),
    };
    if (this.formEventNotBefore.trim()) {
      dataObj.not_before = this.formEventNotBefore.trim();
    }

    const payload: EventDefinitionPayload = {
      name: eventName,
      type: this.formEventType.trim().toLowerCase(),
      parameter: this.formEventParameter.trim(),
      use_case: useCaseName,
      data: JSON.stringify(dataObj),
      holiday: this.formEventHoliday || 'all_days',
      is_active: this.formEventIsActive,
      notify: this.formEventNotify,
      notification_message: this.formEventNotify === 1 ? this.formEventNotificationMessage.trim() : '',
    };

    if (this.eventModalMode() === 'create') {
      this.eventsService.createEventDefinition(payload).subscribe({
        next: () => {
          this.showSuccess('Blinds event trigger created successfully!');
          this.closeEventModal();
          this.loadData();
        },
        error: (err) => {
          alert(`Error creating event: ${err.error?.detail || err.message}`);
        }
      });
    } else {
      const id = this.selectedEventId();
      if (!id) return;
      this.eventsService.updateEventDefinition(id, payload).subscribe({
        next: () => {
          this.showSuccess(`Blinds event #${id} updated successfully!`);
          this.closeEventModal();
          this.loadData();
        },
        error: (err) => {
          alert(`Error updating event: ${err.error?.detail || err.message}`);
        }
      });
    }
  }

  toggleEventActive(eventDef: EventDefinition): void {
    const newActive = eventDef.is_active === 1 ? 0 : 1;
    this.eventsService.updateEventDefinition(eventDef.id, {
      name: eventDef.name,
      type: eventDef.type,
      parameter: eventDef.parameter,
      use_case: eventDef.use_case,
      data: eventDef.data,
      holiday: eventDef.holiday || 'all_days',
      is_active: newActive,
      notify: eventDef.notify ?? 0,
      notification_message: eventDef.notification_message || '',
    }).subscribe({
      next: () => {
        this.showSuccess(`Event #${eventDef.id} ${newActive ? 'activated' : 'paused'}.`);
        this.loadData();
      },
      error: (err) => {
        alert(`Failed to update event status: ${err.error?.detail || err.message}`);
      }
    });
  }

  deleteEvent(eventDef: EventDefinition): void {
    this.openConfirmModal(
      'Delete Blinds Event',
      `Are you sure you want to delete event trigger #${eventDef.id} (${eventDef.type})?`,
      () => {
        this.isConfirming.set(true);
        this.eventsService.deleteEventDefinition(eventDef.id).subscribe({
          next: () => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            this.showSuccess(`Event trigger #${eventDef.id} deleted.`);
            this.loadData();
          },
          error: (err) => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            alert(`Failed to delete event: ${err.error?.detail || err.message}`);
          }
        });
      }
    );
  }

  // ==========================================
  // Device Actions (Add / Edit / Delete Device)
  // ==========================================
  openCreateDeviceModal(): void {
    this.deviceModalMode.set('create');
    this.selectedDeviceId.set(null);
    this.formDeviceName = '';
    this.formDeviceEntityId = '';
    this.deviceEntitySearch = '';
    this.isDeviceModalOpen.set(true);
  }

  openEditDeviceModal(device: DeviceItem): void {
    this.deviceModalMode.set('edit');
    this.selectedDeviceId.set(device.id);
    this.formDeviceName = device.name;
    this.formDeviceEntityId = device.entity_id;
    this.deviceEntitySearch = '';
    this.isDeviceModalOpen.set(true);
  }

  closeDeviceModal(): void {
    this.isDeviceModalOpen.set(false);
  }

  saveDevice(): void {
    const name = this.formDeviceName.trim();
    const entityId = this.formDeviceEntityId.trim();

    if (!name) {
      alert('Please enter a friendly blind device name.');
      return;
    }
    if (!entityId) {
      alert('Please select or specify a Home Assistant entity.');
      return;
    }

    if (this.deviceModalMode() === 'create') {
      this.settingsService.createDevice({
        name,
        type: 'blinds',
        entity_id: entityId,
      }).subscribe({
        next: (resp) => {
          this.showSuccess(`Blind device '${name}' configured.`);
          this.closeDeviceModal();
          this.loadData();
          if (resp && resp.device) {
            this.activeDevice.set(resp.device);
          }
        },
        error: (err) => {
          alert(`Error saving blind device: ${err.error?.detail || err.message}`);
        }
      });
    } else {
      const id = this.selectedDeviceId();
      if (!id) return;
      this.settingsService.updateDevice(id, {
        name,
        type: 'blinds',
        entity_id: entityId,
      }).subscribe({
        next: (resp) => {
          this.showSuccess(`Blind device #${id} updated.`);
          this.closeDeviceModal();
          this.loadData();
          if (resp && resp.device) {
            this.activeDevice.set(resp.device);
          }
        },
        error: (err) => {
          alert(`Error updating blind device: ${err.error?.detail || err.message}`);
        }
      });
    }
  }

  deleteDevice(device: DeviceItem): void {
    this.openConfirmModal(
      'Delete Blind Device',
      `Are you sure you want to delete blind device '${device.name}'?`,
      () => {
        this.isConfirming.set(true);
        this.settingsService.deleteDevice(device.id).subscribe({
          next: () => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            this.showSuccess(`Blind device '${device.name}' deleted.`);
            if (this.activeDevice()?.id === device.id) {
              this.activeDevice.set(null);
            }
            this.loadData();
          },
          error: (err) => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            alert(`Failed to delete blind device: ${err.error?.detail || err.message}`);
          }
        });
      }
    );
  }

  // ==========================================
  // Display Helpers
  // ==========================================
  parseData(dataStr?: string): { entity?: string; entity_id?: string; position?: number; not_before?: string } {
    if (!dataStr) return {};
    try {
      return JSON.parse(dataStr);
    } catch {
      return {};
    }
  }

  getPosition(item: { data?: string }): number {
    const params = this.parseData(item.data);
    return params.position !== undefined ? Number(params.position) : 100;
  }

  getPositionLabel(pos: number): string {
    if (pos === 0) return '0% (Closed)';
    if (pos === 100) return '100% (Fully Open)';
    return `${pos}%`;
  }

  getPositionDisplay(item: { data?: string }): string {
    const pos = this.getPosition(item);
    return this.getPositionLabel(pos);
  }

  getNotBefore(item: { data?: string }): string | null {
    const params = this.parseData(item.data);
    return params.not_before || null;
  }

  getDeviceFriendlyName(entityId: string): string {
    const device = this.devices().find((d) => d.entity_id === entityId);
    if (device) {
      return `${device.name} (${device.entity_id})`;
    }
    return entityId || 'Unknown Device';
  }

  getReadableFrequency(cron: string): string {
    const parts = cron.trim().split(/\s+/);
    if (parts.length === 5) {
      const [m, h, dom, mon, dow] = parts;
      const pad = (n: string) => n.padStart(2, '0');
      if (dom === '*' && mon === '*' && dow === '*') {
        if (!h.includes(',')) {
          return `Daily at ${pad(h)}:${pad(m)}`;
        } else {
          return `Twice daily at ${h.split(',').map(pad).join(' & ')}:${pad(m)}`;
        }
      } else if (dom === '*/2') {
        return `Every 2 days at ${pad(h)}:${pad(m)}`;
      } else if (dom === '*/3') {
        return `Every 3 days at ${pad(h)}:${pad(m)}`;
      }
    }
    return cron;
  }

  getNextRunTime(scheduleId: number): string | null {
    return this.inMemoryJobMap().get(`schedule_${scheduleId}`) || null;
  }

  private showSuccess(msg: string): void {
    this.successMessage.set(msg);
    setTimeout(() => this.successMessage.set(null), 4000);
  }
}
