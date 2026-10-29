import { Component, HostListener, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ConfirmModalComponent } from '../../components/confirm-modal/confirm-modal.component';
import {
  HeatingCalendarDay,
  HeatingCalendarResponse,
  HeatingCalendarSlot,
  HeatingMap,
  HeatingMapsResponse,
  HeatingService,
  HeatingStatusResponse,
} from '../../services/heating.service';
import { DeviceItem, HomeAssistantEntity, SettingsService, UseCase } from '../../services/settings.service';
import { Schedule, SchedulesService } from '../../services/schedules.service';
import { EventDefinition, EventsService } from '../../services/events.service';

@Component({
  selector: 'app-heating',
  standalone: true,
  imports: [CommonModule, FormsModule, DatePipe, RouterLink, ConfirmModalComponent],
  templateUrl: './heating.component.html',
  styleUrl: './heating.component.scss'
})
export class HeatingComponent implements OnInit, OnDestroy {
  private readonly heatingService = inject(HeatingService);
  private readonly schedulesService = inject(SchedulesService);
  private readonly settingsService = inject(SettingsService);
  private readonly eventsService = inject(EventsService);

  // Active Main Tab: 'maps' (Heating Maps) or 'schedules' (Schedules & Events)
  readonly activeTab = signal<'maps' | 'schedules'>('maps');

  // Temperature Sensors Auto-Refresh Signals & Timer
  readonly autoRefreshEnabled = signal<boolean>(false);
  readonly isRefreshingTemps = signal<boolean>(false);
  private autoRefreshTimer: any = null;

  // Core System State Signals
  readonly heatingState = signal<'on' | 'off'>('on');
  readonly helperEntity = signal<string>('');
  readonly helperState = signal<'on' | 'off'>('off');
  readonly heatingIntervalMinutes = signal<number>(5);
  readonly deactivatedUntil = signal<string | null>(null);
  readonly updatedAt = signal<string | null>(null);
  readonly heatingDevices = signal<DeviceItem[]>([]);
  readonly temperatureDevices = signal<DeviceItem[]>([]);
  readonly pendingResumeSchedules = signal<Schedule[]>([]);

  // Heating Settings Modal State
  readonly isSettingsModalOpen = signal<boolean>(false);
  readonly isSavingHeatingSettings = signal<boolean>(false);
  readonly hassEntities = signal<HomeAssistantEntity[]>([]);
  formHelperEntity = '';
  formIntervalMinutes = 5;
  formHeaterEntities: string[] = [];
  newModalHeaterId = '';

  // Heating Maps Signals
  readonly heatingMaps = signal<HeatingMap[]>([]);
  readonly activeMapId = signal<number | null>(null);
  readonly defaultMapId = signal<number | null>(null);
  readonly activeMap = signal<HeatingMap | null>(null);

  // Weekly Heating Calendar Signals
  readonly calendarSlots = signal<HeatingCalendarSlot[]>([]);
  readonly calendarResolvedMap = signal<HeatingMap | null>(null);
  readonly calendarDays = signal<HeatingCalendarDay[]>([
    { id: 0, name: 'Monday', short: 'Mon' },
    { id: 1, name: 'Tuesday', short: 'Tue' },
    { id: 2, name: 'Wednesday', short: 'Wed' },
    { id: 3, name: 'Thursday', short: 'Thu' },
    { id: 4, name: 'Friday', short: 'Fri' },
    { id: 5, name: 'Saturday', short: 'Sat' },
    { id: 6, name: 'Sunday', short: 'Sun' },
    { id: 7, name: 'Holidays', short: 'Hol' },
  ]);
  readonly calendarCurrentTime = signal<string>('00:00');
  readonly calendarCurrentDate = signal<string>('');
  readonly calendarCurrentDayOfWeek = signal<number>(0);
  readonly calendarIsTodayHoliday = signal<boolean>(false);
  readonly loadingCalendar = signal<boolean>(false);

  // Day Editing Modal Signals
  readonly isDayModalOpen = signal<boolean>(false);
  readonly editingDay = signal<HeatingCalendarDay | null>(null);
  editingDaySlots: Array<{ start_time: string; end_time: string; map_id: number }> = [];
  editingDayCopyTargets: Record<number, boolean> = {};
  readonly isSavingDayCalendar = signal<boolean>(false);

  // Schedules & Events Signals
  readonly allSchedules = signal<Schedule[]>([]);
  readonly inMemoryJobMap = signal<Map<string, string | null>>(new Map());
  readonly allEventDefinitions = signal<EventDefinition[]>([]);
  readonly configuredUseCases = signal<UseCase[]>([]);

  loadHeatingSettings(): void {
    this.heatingService.getHeatingSettings().subscribe({
      next: (res) => {
        this.helperEntity.set(res.heating_helper_entity || '');
        this.heatingIntervalMinutes.set(res.heating_interval_minutes || 5);
        this.formHeaterEntities = res.heating_heater_entities ? [...res.heating_heater_entities] : [];
      },
      error: (err) => console.error('Failed to load heating settings:', err),
    });
  }

  addModalHeater(entityId: string): void {
    const clean = entityId.trim();
    if (!clean) return;
    if (!this.formHeaterEntities.includes(clean)) {
      this.formHeaterEntities.push(clean);
    }
    this.newModalHeaterId = '';
  }

  removeModalHeater(entityId: string): void {
    this.formHeaterEntities = this.formHeaterEntities.filter((h) => h !== entityId);
  }

  isEntityInHassList(entityId: string): boolean {
    if (!entityId) return false;
    return this.hassEntities().some((e) => e.entity_id === entityId);
  }

  openHeatingSettingsModal(): void {
    this.formHelperEntity = this.helperEntity();
    this.formIntervalMinutes = this.heatingIntervalMinutes();
    this.newModalHeaterId = '';
    this.isSettingsModalOpen.set(true);
    if (this.hassEntities().length === 0) {
      this.settingsService.getHomeAssistantEntities().subscribe({
        next: (res) => this.hassEntities.set(res.entities || []),
        error: (err) => console.error('Failed to load HA entities:', err),
      });
    }
  }

  closeHeatingSettingsModal(): void {
    this.isSettingsModalOpen.set(false);
  }

  saveHeatingGlobalSettings(): void {
    const mins = Number(this.formIntervalMinutes) || 5;
    const entity = (this.formHelperEntity || '').trim();
    this.isSavingHeatingSettings.set(true);
    this.heatingService.updateHeatingSettings({
      heating_helper_entity: entity,
      heating_interval_minutes: mins,
      heating_heater_entities: this.formHeaterEntities,
    }).subscribe({
      next: (res) => {
        this.isSavingHeatingSettings.set(false);
        this.helperEntity.set(res.settings.heating_helper_entity);
        this.heatingIntervalMinutes.set(res.settings.heating_interval_minutes);
        this.isSettingsModalOpen.set(false);
        this.successMessage.set('Heating settings updated successfully.');
        setTimeout(() => this.successMessage.set(null), 3500);
        this.loadState();
      },
      error: (err) => {
        this.isSavingHeatingSettings.set(false);
        this.errorMessage.set(`Failed to update heating settings: ${err.error?.detail || err.message}`);
        setTimeout(() => this.errorMessage.set(null), 4000);
      }
    });
  }

  // State Signals
  readonly loading = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);

  // Filtered Lists for Heating Section
  readonly heatingSchedules = computed(() => {
    return this.allSchedules().filter(
      (s) =>
        s.name.startsWith('Auto - Heating Map') ||
        s.use_case === 'set_heating_map' ||
        (s.name.startsWith('Auto - Heating') && !s.name.includes('Activate ('))
    );
  });

  readonly heatingEvents = computed(() => {
    return this.allEventDefinitions().filter(
      (e) =>
        e.name.startsWith('Auto - Heating Map') ||
        e.use_case === 'set_heating_map' ||
        e.name.toLowerCase().includes('heating map')
    );
  });

  // Deactivate Until Modal Signals
  readonly isDeactivateModalOpen = signal<boolean>(false);
  readonly deactivateMode = signal<'hours' | 'until'>('hours');
  readonly deactivateHours = signal<number>(2);
  readonly deactivateUntilInput = signal<string>('');
  readonly isSubmitting = signal<boolean>(false);
  readonly presetHours = [1, 2, 4, 8, 12, 24];

  // Heating Map Form & Modal Signals
  readonly isMapModalOpen = signal<boolean>(false);
  readonly mapModalMode = signal<'create' | 'edit'>('create');
  readonly selectedMapId = signal<number | null>(null);
  formMapName = '';
  formMapDescription = '';
  formMapIsDefault = 0;
  formDeviceRules: Record<number, { enabled: boolean; min_temperature: number | null }> = {};

  // Schedule Modal Signals
  readonly isScheduleModalOpen = signal<boolean>(false);
  readonly scheduleModalMode = signal<'create' | 'edit'>('create');
  readonly selectedScheduleId = signal<number | null>(null);
  formScheduleName = '';
  formScheduleType: 'one-time' | 'recurrent' = 'recurrent';
  formScheduleTrigger = '0 7 * * *';
  formScheduleTargetMapId: number | null = null;
  formScheduleNotify = 0;
  formScheduleNotificationMessage = '';

  // Event Modal Signals
  readonly isEventModalOpen = signal<boolean>(false);
  readonly eventModalMode = signal<'create' | 'edit'>('create');
  readonly selectedEventId = signal<number | null>(null);
  formEventName = '';
  formEventType = 'presence';
  formEventParameter = 'home';
  formEventTargetMapId: number | null = null;
  formEventHoliday = 'all_days';
  formEventNotify = 0;
  formEventNotificationMessage = '';

  // Action Confirmation Modal
  readonly isConfirmModalOpen = signal<boolean>(false);
  readonly confirmModalTitle = signal<string>('Confirm Action');
  readonly confirmModalMessage = signal<string>('');
  readonly isConfirming = signal<boolean>(false);
  private pendingConfirmAction: (() => void) | null = null;

  // Reactivation preview string
  readonly resumePreviewText = computed(() => {
    if (this.deactivateMode() === 'hours') {
      const h = this.deactivateHours();
      if (!h || h <= 0) return 'Invalid duration';
      const target = new Date(Date.now() + h * 3600 * 1000);
      return `Heating will automatically reactivate on ${target.toLocaleString([], {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })} (in ${h} hour${h === 1 ? '' : 's'})`;
    } else {
      const val = this.deactivateUntilInput();
      if (!val) return 'Please choose a target date & time';
      const target = new Date(val);
      if (isNaN(target.getTime())) return 'Invalid date & time';
      const diffMs = target.getTime() - Date.now();
      const diffHours = (diffMs / (3600 * 1000)).toFixed(1);
      return `Heating will automatically reactivate on ${target.toLocaleString([], {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })} (${diffHours}h from now)`;
    }
  });

  ngOnInit(): void {
    this.loadAllData();
  }

  ngOnDestroy(): void {
    this.stopAutoRefresh();
  }

  toggleAutoRefresh(event: Event): void {
    const input = event.target as HTMLInputElement;
    const enabled = input.checked;
    this.autoRefreshEnabled.set(enabled);
    if (enabled) {
      this.startAutoRefresh();
    } else {
      this.stopAutoRefresh();
    }
  }

  refreshTemperatures(): void {
    this.isRefreshingTemps.set(true);
    this.heatingService.getHeatingState().subscribe({
      next: (res: HeatingStatusResponse) => {
        this.heatingState.set(res.state);
        if (res.helper_entity !== undefined) {
          this.helperEntity.set(res.helper_entity || '');
        }
        if (res.helper_state !== undefined) {
          this.helperState.set((res.helper_state as 'on' | 'off') || res.state || 'off');
        }
        this.deactivatedUntil.set(res.deactivated_until ?? null);
        this.updatedAt.set(res.updated_at ?? null);
        this.activeMapId.set(res.active_map_id ?? null);
        this.activeMap.set(res.active_map ?? null);
        this.heatingDevices.set([]);
        this.temperatureDevices.set(res.temperature_devices || []);
        this.pendingResumeSchedules.set(res.pending_resume_schedules || []);
        this.isRefreshingTemps.set(false);
      },
      error: (err) => {
        console.error('Failed to auto-refresh temperatures:', err);
        this.isRefreshingTemps.set(false);
      }
    });
  }

  private startAutoRefresh(): void {
    this.stopAutoRefresh();
    this.refreshTemperatures();
    this.autoRefreshTimer = setInterval(() => {
      this.refreshTemperatures();
    }, 15000);
  }

  private stopAutoRefresh(): void {
    if (this.autoRefreshTimer) {
      clearInterval(this.autoRefreshTimer);
      this.autoRefreshTimer = null;
    }
  }

  loadAllData(): void {
    this.loading.set(true);
    this.loadHeatingSettings();
    this.loadState();
    this.loadMaps();
    this.loadCalendar();
    this.loadSchedulesAndEvents();
  }

  loadState(): void {
    this.heatingService.getHeatingState().subscribe({
      next: (res: HeatingStatusResponse) => {
        this.heatingState.set(res.state);
        if (res.helper_entity !== undefined) {
          this.helperEntity.set(res.helper_entity || '');
        }
        if (res.helper_state !== undefined) {
          this.helperState.set((res.helper_state as 'on' | 'off') || res.state || 'off');
        }
        this.deactivatedUntil.set(res.deactivated_until ?? null);
        this.updatedAt.set(res.updated_at ?? null);
        this.activeMapId.set(res.active_map_id ?? null);
        this.activeMap.set(res.active_map ?? null);
        this.heatingDevices.set([]);
        this.temperatureDevices.set(res.temperature_devices || []);
        this.pendingResumeSchedules.set(res.pending_resume_schedules || []);
        this.loading.set(false);
      },
      error: (err) => {
        this.errorMessage.set(`Failed to load heating status: ${err.error?.detail || err.message}`);
        this.loading.set(false);
      }
    });
  }

  loadMaps(): void {
    this.heatingService.getHeatingMaps().subscribe({
      next: (res: HeatingMapsResponse) => {
        this.heatingMaps.set(res.maps || []);
        this.activeMapId.set(res.active_map_id);
        this.defaultMapId.set(res.default_map_id);
      },
      error: (err) => {
        console.error('Failed to load heating maps', err);
      }
    });
  }

  loadCalendar(): void {
    this.loadingCalendar.set(true);
    this.heatingService.getHeatingCalendar().subscribe({
      next: (resp) => {
        this.calendarSlots.set(resp.calendar || []);
        this.calendarResolvedMap.set(resp.resolved_map || null);
        this.calendarCurrentTime.set(resp.current_time || '00:00');
        this.calendarCurrentDate.set(resp.current_date || '');
        this.calendarCurrentDayOfWeek.set(resp.current_day_of_week ?? 0);
        this.calendarIsTodayHoliday.set(Boolean(resp.is_today_holiday));
        if (resp.days && resp.days.length > 0) {
          this.calendarDays.set(resp.days);
        }
        this.loadingCalendar.set(false);
      },
      error: (err) => {
        console.error('Failed to load heating calendar', err);
        this.loadingCalendar.set(false);
      }
    });
  }

  getDaySlots(dayId: number): HeatingCalendarSlot[] {
    return this.calendarSlots()
      .filter((s) => s.day_of_week === dayId)
      .sort((a, b) => a.start_time.localeCompare(b.start_time));
  }

  getSlotWidth(slot: { start_time: string; end_time: string }): number {
    const parseM = (t: string) => {
      const parts = (t || '00:00').split(':').map(Number);
      return (parts[0] || 0) * 60 + (parts[1] || 0);
    };
    const startM = parseM(slot.start_time);
    let endM = slot.end_time === '24:00' ? 1440 : parseM(slot.end_time);
    if (endM <= startM) endM = 1440;
    const duration = Math.max(1, endM - startM);
    return (duration / 1440) * 100;
  }

  getCurrentTimePercentage(): number {
    const timeStr = this.calendarCurrentTime() || '00:00';
    const parts = timeStr.split(':').map(Number);
    const mins = (parts[0] || 0) * 60 + (parts[1] || 0);
    return Math.min(100, Math.max(0, (mins / 1440) * 100));
  }

  getMapName(mapId: number): string {
    const m = this.heatingMaps().find((map) => map.id === mapId);
    return m ? m.name : `Map #${mapId}`;
  }

  getMapColor(mapId?: number | null): string {
    if (mapId === null || mapId === undefined) {
      return '#f97316';
    }
    const colors = [
      '#f97316', // orange (Comfort)
      '#38bdf8', // sky (Eco)
      '#a855f7', // purple (Away)
      '#10b981', // emerald
      '#ec4899', // pink
      '#eab308', // amber
    ];
    return colors[Math.abs(mapId) % colors.length];
  }

  openEditDayModal(day: HeatingCalendarDay): void {
    this.editingDay.set(day);
    const existing = this.getDaySlots(day.id);
    const defMapId = this.defaultMapId() || (this.heatingMaps().length > 0 ? this.heatingMaps()[0].id : 1);

    if (existing.length > 0) {
      this.editingDaySlots = existing.map((s) => ({
        start_time: s.start_time,
        end_time: s.end_time,
        map_id: s.map_id,
      }));
    } else {
      this.editingDaySlots = [{ start_time: '00:00', end_time: '24:00', map_id: defMapId }];
    }

    this.editingDayCopyTargets = {};
    for (const d of this.calendarDays()) {
      this.editingDayCopyTargets[d.id] = false;
    }
    this.isDayModalOpen.set(true);
  }

  closeDayModal(): void {
    this.isDayModalOpen.set(false);
    this.editingDay.set(null);
  }

  addSlotToDay(): void {
    const defMapId = this.defaultMapId() || (this.heatingMaps().length > 0 ? this.heatingMaps()[0].id : 1);
    let newStart = '18:00';
    if (this.editingDaySlots.length > 0) {
      const last = this.editingDaySlots[this.editingDaySlots.length - 1];
      newStart = last.end_time !== '24:00' ? last.end_time : '12:00';
    }
    this.editingDaySlots.push({ start_time: newStart, end_time: '24:00', map_id: defMapId });
  }

  removeSlotFromDay(index: number): void {
    if (this.editingDaySlots.length <= 1) return;
    this.editingDaySlots.splice(index, 1);
  }

  applyDayPreset(preset: 'all_day' | 'day_night' | 'work_schedule'): void {
    const maps = this.heatingMaps();
    const defId = this.defaultMapId() || (maps.length > 0 ? maps[0].id : 1);
    const ecoMap = maps.find((m) => m.name.toLowerCase().includes('eco')) || maps.find((m) => m.id !== defId) || maps[0];
    const ecoId = ecoMap ? ecoMap.id : defId;

    if (preset === 'all_day') {
      this.editingDaySlots = [{ start_time: '00:00', end_time: '24:00', map_id: defId }];
    } else if (preset === 'day_night') {
      this.editingDaySlots = [
        { start_time: '00:00', end_time: '07:00', map_id: ecoId },
        { start_time: '07:00', end_time: '23:00', map_id: defId },
        { start_time: '23:00', end_time: '24:00', map_id: ecoId },
      ];
    } else if (preset === 'work_schedule') {
      this.editingDaySlots = [
        { start_time: '00:00', end_time: '07:00', map_id: ecoId },
        { start_time: '07:00', end_time: '09:00', map_id: defId },
        { start_time: '09:00', end_time: '18:00', map_id: ecoId },
        { start_time: '18:00', end_time: '23:00', map_id: defId },
        { start_time: '23:00', end_time: '24:00', map_id: ecoId },
      ];
    }
  }

  setCopyPreset(type: 'weekdays' | 'weekend' | 'all' | 'none'): void {
    const curDay = this.editingDay()?.id;
    for (const d of this.calendarDays()) {
      if (d.id === curDay) {
        this.editingDayCopyTargets[d.id] = false;
        continue;
      }
      if (type === 'weekdays') {
        this.editingDayCopyTargets[d.id] = d.id >= 0 && d.id <= 4;
      } else if (type === 'weekend') {
        this.editingDayCopyTargets[d.id] = d.id === 5 || d.id === 6;
      } else if (type === 'all') {
        this.editingDayCopyTargets[d.id] = true;
      } else {
        this.editingDayCopyTargets[d.id] = false;
      }
    }
  }

  saveDaySchedule(): void {
    const day = this.editingDay();
    if (!day) return;

    if (this.editingDaySlots.length === 0) {
      alert('At least one time slot is required.');
      return;
    }

    // Sort slots by start_time
    this.editingDaySlots.sort((a, b) => a.start_time.localeCompare(b.start_time));

    const copyDays: number[] = [];
    for (const [dStr, checked] of Object.entries(this.editingDayCopyTargets)) {
      if (checked && Number(dStr) !== day.id) {
        copyDays.push(Number(dStr));
      }
    }

    this.isSavingDayCalendar.set(true);
    this.heatingService.updateHeatingCalendarDay({
      day_of_week: day.id,
      slots: this.editingDaySlots,
      copy_to_days: copyDays.length > 0 ? copyDays : undefined,
    }).subscribe({
      next: (resp) => {
        this.calendarSlots.set(resp.calendar);
        this.calendarResolvedMap.set(resp.resolved_map);
        this.isSavingDayCalendar.set(false);
        this.closeDayModal();
        let msg = `Schedule for ${day.name} saved successfully.`;
        if (copyDays.length > 0) {
          msg += ` Replicated to ${copyDays.length} other day(s).`;
        }
        this.showSuccess(msg);
      },
      error: (err) => {
        this.isSavingDayCalendar.set(false);
        alert(`Failed to save day schedule: ${err.error?.detail || err.message}`);
      }
    });
  }

  loadSchedulesAndEvents(): void {
    this.schedulesService.getSchedules().subscribe({
      next: (res) => {
        this.allSchedules.set(res.schedules || []);
        const jobMap = new Map<string, string | null>();
        (res.in_memory_jobs || []).forEach((job) => {
          jobMap.set(job.job_id, job.next_run_time || null);
        });
        this.inMemoryJobMap.set(jobMap);
      },
      error: (err) => console.error('Failed to load schedules', err)
    });

    this.eventsService.getEventDefinitions().subscribe({
      next: (res) => {
        this.allEventDefinitions.set(res.event_definitions || []);
      },
      error: (err) => console.error('Failed to load event definitions', err)
    });

    this.settingsService.getUseCases().subscribe({
      next: (res) => {
        this.configuredUseCases.set(res.use_cases || []);
      },
      error: (err) => console.error('Failed to load use cases', err)
    });
  }

  // Master Switch Controls
  onToggleCheck(event: Event): void {
    const isChecked = (event.target as HTMLInputElement).checked;
    if (isChecked) {
      this.activateHeating();
    } else {
      this.deactivateImmediate();
    }
  }

  activateHeating(): void {
    this.loading.set(true);
    this.heatingService.setHeatingState({ action: 'on' }).subscribe({
      next: (res) => {
        this.heatingState.set('on');
        this.deactivatedUntil.set(null);
        this.showSuccess(res.message || 'Heating system activated.');
        this.loadState();
      },
      error: (err) => {
        this.loading.set(false);
        alert(`Failed to activate heating: ${err.error?.detail || err.message}`);
      }
    });
  }

  deactivateImmediate(): void {
    this.loading.set(true);
    this.heatingService.setHeatingState({ action: 'off', mode: 'immediate' }).subscribe({
      next: (res) => {
        this.heatingState.set('off');
        this.deactivatedUntil.set(null);
        this.showSuccess(res.message || 'Heating system deactivated. Devices switched off.');
        this.loadState();
      },
      error: (err) => {
        this.loading.set(false);
        alert(`Failed to deactivate heating: ${err.error?.detail || err.message}`);
      }
    });
  }

  cancelDeferredStart(): void {
    this.loading.set(true);
    this.heatingService.setHeatingState({ action: 'off' }).subscribe({
      next: (res) => {
        this.loading.set(false);
        this.deactivatedUntil.set(null);
        this.heatingState.set('off');
        this.closeDeactivateModal();
        this.showSuccess('Deferred reactivation cancelled. Heating remains deactivated.');
        this.loadState();
      },
      error: (err) => {
        this.loading.set(false);
        alert(`Failed to cancel deferred reactivation: ${err.error?.detail || err.message}`);
      }
    });
  }

  // Deactivate Until Modal
  openDeactivateModal(): void {
    this.deactivateMode.set('hours');
    this.deactivateHours.set(2);
    const defaultTarget = new Date(Date.now() + 2 * 3600 * 1000);
    const pad = (n: number) => n.toString().padStart(2, '0');
    const localIso = `${defaultTarget.getFullYear()}-${pad(defaultTarget.getMonth() + 1)}-${pad(defaultTarget.getDate())}T${pad(defaultTarget.getHours())}:${pad(defaultTarget.getMinutes())}`;
    this.deactivateUntilInput.set(localIso);
    this.isDeactivateModalOpen.set(true);
  }

  closeDeactivateModal(): void {
    this.isDeactivateModalOpen.set(false);
    this.isSubmitting.set(false);
  }

  selectPresetHours(hours: number): void {
    this.deactivateMode.set('hours');
    this.deactivateHours.set(hours);
  }

  submitDeactivateUntil(): void {
    if (this.deactivateMode() === 'hours') {
      const h = this.deactivateHours();
      if (!h || h <= 0) {
        alert('Please enter a valid number of hours.');
        return;
      }
      this.isSubmitting.set(true);
      this.heatingService.setHeatingState({
        action: 'off',
        mode: 'hours',
        hours: h,
      }).subscribe({
        next: (res) => {
          this.closeDeactivateModal();
          this.showSuccess(res.message || `Heating deactivated for ${h} hours.`);
          this.loadState();
        },
        error: (err) => {
          this.isSubmitting.set(false);
          alert(`Failed to deactivate heating: ${err.error?.detail || err.message}`);
        }
      });
    } else {
      const untilVal = this.deactivateUntilInput();
      if (!untilVal) {
        alert('Please select a target date and time.');
        return;
      }
      const target = new Date(untilVal);
      if (isNaN(target.getTime()) || target.getTime() <= Date.now()) {
        alert('Target date and time must be in the future.');
        return;
      }
      this.isSubmitting.set(true);
      this.heatingService.setHeatingState({
        action: 'off',
        mode: 'until',
        until: untilVal,
      }).subscribe({
        next: (res) => {
          this.closeDeactivateModal();
          this.showSuccess(res.message || `Heating deactivated until ${untilVal}.`);
          this.loadState();
        },
        error: (err) => {
          this.isSubmitting.set(false);
          alert(`Failed to deactivate heating: ${err.error?.detail || err.message}`);
        }
      });
    }
  }

  // ==========================================
  // Heating Maps Actions
  // ==========================================

  getDeviceRule(map: HeatingMap | null | undefined, deviceId: number): number | null {
    if (!map || !map.rules) return null;
    const val = map.rules[deviceId] ?? map.rules[String(deviceId)];
    if (val !== undefined && val !== null && !isNaN(Number(val))) {
      return Number(val);
    }
    return null;
  }

  formatTemp(val: number | string | null | undefined, fallback = '--'): string {
    if (val === null || val === undefined || val === '') return fallback;
    const num = Number(val);
    if (isNaN(num)) return String(val);
    return num.toFixed(1);
  }

  openCreateMapModal(): void {
    this.mapModalMode.set('create');
    this.selectedMapId.set(null);
    this.formMapName = '';
    this.formMapDescription = '';
    this.formMapIsDefault = this.heatingMaps().length === 0 ? 1 : 0;
    this.initDeviceRulesForm({});
    this.isMapModalOpen.set(true);
  }

  openEditMapModal(map: HeatingMap): void {
    this.mapModalMode.set('edit');
    this.selectedMapId.set(map.id);
    this.formMapName = map.name;
    this.formMapDescription = map.description || '';
    this.formMapIsDefault = map.is_default || 0;
    this.initDeviceRulesForm(map.rules || {});
    this.isMapModalOpen.set(true);
  }

  private initDeviceRulesForm(rules: Record<string, any>): void {
    this.formDeviceRules = {};
    for (const dev of this.temperatureDevices()) {
      const existingVal = rules[dev.id] ?? rules[String(dev.id)];
      if (existingVal !== undefined && existingVal !== null && !isNaN(Number(existingVal))) {
        this.formDeviceRules[dev.id] = {
          enabled: true,
          min_temperature: Number(existingVal),
        };
      } else {
        this.formDeviceRules[dev.id] = {
          enabled: false,
          min_temperature: 21.0,
        };
      }
    }
  }

  closeMapModal(): void {
    this.isMapModalOpen.set(false);
    this.selectedMapId.set(null);
  }

  saveHeatingMap(): void {
    if (!this.formMapName.trim()) {
      alert('Please enter a heating map name.');
      return;
    }

    const compiledRules: Record<string, number | null> = {};
    for (const dev of this.temperatureDevices()) {
      const rule = this.formDeviceRules[dev.id];
      if (rule && rule.enabled && rule.min_temperature !== null && !isNaN(rule.min_temperature)) {
        compiledRules[String(dev.id)] = Number(rule.min_temperature);
      }
    }

    const payload = {
      name: this.formMapName.trim(),
      description: this.formMapDescription.trim(),
      rules: compiledRules,
      is_default: this.formMapIsDefault,
    };

    if (this.mapModalMode() === 'create') {
      this.heatingService.createHeatingMap(payload).subscribe({
        next: (res) => {
          this.closeMapModal();
          this.showSuccess(res.message || `Heating map '${payload.name}' created.`);
          this.loadMaps();
          this.loadState();
        },
        error: (err) => {
          alert(`Failed to create heating map: ${err.error?.detail || err.message}`);
        }
      });
    } else {
      const id = this.selectedMapId();
      if (!id) return;
      this.heatingService.updateHeatingMap(id, payload).subscribe({
        next: (res) => {
          this.closeMapModal();
          this.showSuccess(res.message || `Heating map '${payload.name}' updated.`);
          this.loadMaps();
          this.loadState();
        },
        error: (err) => {
          alert(`Failed to update heating map: ${err.error?.detail || err.message}`);
        }
      });
    }
  }

  activateMap(map: HeatingMap): void {
    this.heatingService.activateHeatingMap(map.id).subscribe({
      next: (res) => {
        this.showSuccess(res.message || `Active heating map set to '${map.name}'.`);
        this.activeMapId.set(map.id);
        this.activeMap.set(map);
        this.loadState();
      },
      error: (err) => {
        alert(`Failed to activate map: ${err.error?.detail || err.message}`);
      }
    });
  }

  setDefaultMap(map: HeatingMap): void {
    this.heatingService.setDefaultHeatingMap(map.id).subscribe({
      next: (res) => {
        this.showSuccess(res.message || `'${map.name}' is now the default heating map.`);
        this.defaultMapId.set(map.id);
        this.loadMaps();
      },
      error: (err) => {
        alert(`Failed to set default map: ${err.error?.detail || err.message}`);
      }
    });
  }

  deleteMap(map: HeatingMap): void {
    if (this.heatingMaps().length <= 1) {
      alert('Cannot delete the only configured heating map in the system.');
      return;
    }
    this.openConfirmModal(
      'Delete Heating Map',
      `Are you sure you want to delete heating map '${map.name}' (ID #${map.id})? If this map was active or default, another map will take its place.`,
      () => {
        this.isConfirming.set(true);
        this.heatingService.deleteHeatingMap(map.id).subscribe({
          next: () => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            this.showSuccess(`Heating map '${map.name}' deleted.`);
            this.loadMaps();
            this.loadState();
          },
          error: (err) => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            alert(`Failed to delete heating map: ${err.error?.detail || err.message}`);
          }
        });
      }
    );
  }

  // ==========================================
  // Schedules Actions
  // ==========================================

  getScheduleNextRun(schedId: number): string | null {
    return this.inMemoryJobMap().get(`schedule_${schedId}`) || null;
  }

  openCreateScheduleModal(): void {
    this.scheduleModalMode.set('create');
    this.selectedScheduleId.set(null);
    const targetMap = this.heatingMaps()[0];
    this.formScheduleName = targetMap ? `Auto - Heating Map - ${targetMap.name}` : 'Auto - Heating Map';
    this.formScheduleType = 'recurrent';
    this.formScheduleTrigger = '0 7 * * *';
    this.formScheduleTargetMapId = targetMap ? targetMap.id : null;
    this.formScheduleNotify = 0;
    this.formScheduleNotificationMessage = '';
    this.isScheduleModalOpen.set(true);
  }

  openEditScheduleModal(schedule: Schedule): void {
    if (schedule.block === 1) {
      alert(`Schedule #${schedule.id} is locked and protected against changes. Please unlock it from the Schedules section.`);
      return;
    }
    this.scheduleModalMode.set('edit');
    this.selectedScheduleId.set(schedule.id);
    this.formScheduleName = schedule.name;
    this.formScheduleType = schedule.type;
    this.formScheduleTrigger = schedule.trigger_spec;
    this.formScheduleNotify = schedule.notify ?? 0;
    this.formScheduleNotificationMessage = schedule.notification_message || '';

    try {
      const parsed = JSON.parse(schedule.data || '{}');
      this.formScheduleTargetMapId = parsed.map_id || null;
    } catch {
      this.formScheduleTargetMapId = null;
    }
    if (!this.formScheduleTargetMapId && this.heatingMaps().length > 0) {
      this.formScheduleTargetMapId = this.heatingMaps()[0].id;
    }

    this.isScheduleModalOpen.set(true);
  }

  onScheduleTargetMapChange(): void {
    if (this.scheduleModalMode() === 'create') {
      const selectedMap = this.heatingMaps().find((m) => m.id === Number(this.formScheduleTargetMapId));
      if (selectedMap) {
        this.formScheduleName = `Auto - Heating Map - ${selectedMap.name}`;
      }
    }
  }

  closeScheduleModal(): void {
    this.isScheduleModalOpen.set(false);
    this.selectedScheduleId.set(null);
  }

  saveSchedule(): void {
    if (!this.formScheduleName.trim()) {
      alert('Please enter a schedule name.');
      return;
    }
    if (!this.formScheduleTrigger.trim()) {
      alert('Please provide a trigger specification (cron expression or datetime).');
      return;
    }

    const selectedMap = this.heatingMaps().find((m) => m.id === Number(this.formScheduleTargetMapId));
    const dataPayload = {
      map_id: selectedMap ? selectedMap.id : null,
      map_name: selectedMap ? selectedMap.name : '',
    };

    const payload = {
      name: this.formScheduleName.trim(),
      type: this.formScheduleType,
      trigger_spec: this.formScheduleTrigger.trim(),
      use_case: 'set_heating_map',
      is_active: 1,
      data: JSON.stringify(dataPayload),
      notify: this.formScheduleNotify,
      notification_message: this.formScheduleNotificationMessage.trim(),
    };

    if (this.scheduleModalMode() === 'create') {
      this.schedulesService.createSchedule(payload).subscribe({
        next: (res) => {
          this.closeScheduleModal();
          this.showSuccess(`Heating schedule #${res.schedule.id} created.`);
          this.loadSchedulesAndEvents();
        },
        error: (err) => alert(`Failed to create schedule: ${err.error?.detail || err.message}`)
      });
    } else {
      const id = this.selectedScheduleId();
      if (!id) return;
      this.schedulesService.updateSchedule(id, payload).subscribe({
        next: () => {
          this.closeScheduleModal();
          this.showSuccess(`Heating schedule #${id} updated.`);
          this.loadSchedulesAndEvents();
        },
        error: (err) => alert(`Failed to update schedule: ${err.error?.detail || err.message}`)
      });
    }
  }

  toggleScheduleActive(schedule: Schedule): void {
    if (schedule.block === 1) {
      alert(`Schedule #${schedule.id} is locked and protected against changes.`);
      return;
    }
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
        this.loadSchedulesAndEvents();
      },
      error: (err) => alert(`Failed to update status: ${err.error?.detail || err.message}`)
    });
  }

  deleteSchedule(schedule: Schedule): void {
    if (schedule.block === 1) {
      alert(`Schedule #${schedule.id} is locked and protected against deletion.`);
      return;
    }
    this.openConfirmModal(
      'Delete Heating Schedule',
      `Are you sure you want to delete heating schedule #${schedule.id} (${schedule.name})?`,
      () => {
        this.isConfirming.set(true);
        this.schedulesService.deleteSchedule(schedule.id).subscribe({
          next: () => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            this.showSuccess(`Heating schedule #${schedule.id} deleted.`);
            this.loadSchedulesAndEvents();
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
  // Events Actions
  // ==========================================

  openCreateEventModal(): void {
    this.eventModalMode.set('create');
    this.selectedEventId.set(null);
    const targetMap = this.heatingMaps()[0];
    this.formEventName = targetMap ? `Auto - Heating Map - ${targetMap.name} on Presence` : 'Auto - Heating Map';
    this.formEventType = 'presence';
    this.formEventParameter = 'home';
    this.formEventTargetMapId = targetMap ? targetMap.id : null;
    this.formEventHoliday = 'all_days';
    this.formEventNotify = 0;
    this.formEventNotificationMessage = '';
    this.isEventModalOpen.set(true);
  }

  openEditEventModal(eventDef: EventDefinition): void {
    this.eventModalMode.set('edit');
    this.selectedEventId.set(eventDef.id);
    this.formEventName = eventDef.name;
    this.formEventType = eventDef.type;
    this.formEventParameter = eventDef.parameter || '';
    this.formEventHoliday = eventDef.holiday || 'all_days';
    this.formEventNotify = eventDef.notify ?? 0;
    this.formEventNotificationMessage = eventDef.notification_message || '';

    try {
      const parsed = JSON.parse(eventDef.data || '{}');
      this.formEventTargetMapId = parsed.map_id || null;
    } catch {
      this.formEventTargetMapId = null;
    }
    if (!this.formEventTargetMapId && this.heatingMaps().length > 0) {
      this.formEventTargetMapId = this.heatingMaps()[0].id;
    }

    this.isEventModalOpen.set(true);
  }

  onEventTargetMapChange(): void {
    if (this.eventModalMode() === 'create') {
      const selectedMap = this.heatingMaps().find((m) => m.id === Number(this.formEventTargetMapId));
      if (selectedMap) {
        this.formEventName = `Auto - Heating Map - ${selectedMap.name} on ${this.formEventType}`;
      }
    }
  }

  closeEventModal(): void {
    this.isEventModalOpen.set(false);
    this.selectedEventId.set(null);
  }

  saveEventDefinition(): void {
    if (!this.formEventName.trim()) {
      alert('Please enter an event definition name.');
      return;
    }
    if (!this.formEventType.trim()) {
      alert('Please provide an event type (e.g. presence, sunrise, sunset).');
      return;
    }

    const selectedMap = this.heatingMaps().find((m) => m.id === Number(this.formEventTargetMapId));
    const dataPayload = {
      map_id: selectedMap ? selectedMap.id : null,
      map_name: selectedMap ? selectedMap.name : '',
    };

    const payload = {
      name: this.formEventName.trim(),
      type: this.formEventType.trim(),
      parameter: this.formEventParameter.trim(),
      use_case: 'set_heating_map',
      holiday: this.formEventHoliday,
      is_active: 1,
      data: JSON.stringify(dataPayload),
      notify: this.formEventNotify,
      notification_message: this.formEventNotificationMessage.trim(),
    };

    if (this.eventModalMode() === 'create') {
      this.eventsService.createEventDefinition(payload).subscribe({
        next: (res) => {
          this.closeEventModal();
          this.showSuccess(`Heating event definition #${res.event_definition.id} created.`);
          this.loadSchedulesAndEvents();
        },
        error: (err) => alert(`Failed to create event definition: ${err.error?.detail || err.message}`)
      });
    } else {
      const id = this.selectedEventId();
      if (!id) return;
      this.eventsService.updateEventDefinition(id, payload).subscribe({
        next: () => {
          this.closeEventModal();
          this.showSuccess(`Heating event definition #${id} updated.`);
          this.loadSchedulesAndEvents();
        },
        error: (err) => alert(`Failed to update event definition: ${err.error?.detail || err.message}`)
      });
    }
  }

  toggleEventActive(eventDef: EventDefinition): void {
    const newActive = eventDef.is_active === 1 ? 0 : 1;
    this.eventsService.updateEventDefinition(eventDef.id, {
      name: eventDef.name,
      type: eventDef.type,
      parameter: eventDef.parameter || '',
      use_case: eventDef.use_case,
      holiday: eventDef.holiday,
      is_active: newActive,
      data: eventDef.data || '{}',
      notify: eventDef.notify ?? 0,
      notification_message: eventDef.notification_message || '',
    }).subscribe({
      next: () => {
        this.showSuccess(`Event #${eventDef.id} ${newActive ? 'activated' : 'paused'}.`);
        this.loadSchedulesAndEvents();
      },
      error: (err) => alert(`Failed to update event status: ${err.error?.detail || err.message}`)
    });
  }

  deleteEventDefinition(eventDef: EventDefinition): void {
    this.openConfirmModal(
      'Delete Heating Event',
      `Are you sure you want to delete heating event definition #${eventDef.id} (${eventDef.name})?`,
      () => {
        this.isConfirming.set(true);
        this.eventsService.deleteEventDefinition(eventDef.id).subscribe({
          next: () => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            this.showSuccess(`Heating event definition #${eventDef.id} deleted.`);
            this.loadSchedulesAndEvents();
          },
          error: (err) => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            alert(`Failed to delete event definition: ${err.error?.detail || err.message}`);
          }
        });
      }
    );
  }

  // Cancel a scheduled resume one-time schedule
  cancelSchedule(schedule: Schedule): void {
    this.openConfirmModal(
      'Cancel Reactivation Schedule',
      `Are you sure you want to cancel the scheduled reactivation #${schedule.id} (${schedule.name})? Heating will remain deactivated until manually turned back on.`,
      () => {
        this.isConfirming.set(true);
        this.schedulesService.deleteSchedule(schedule.id).subscribe({
          next: () => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            this.showSuccess(`Scheduled reactivation #${schedule.id} cancelled.`);
            this.loadState();
          },
          error: (err) => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            alert(`Failed to cancel schedule: ${err.error?.detail || err.message}`);
          }
        });
      }
    );
  }

  // Confirmation Modal
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

  private showSuccess(msg: string): void {
    this.successMessage.set(msg);
    setTimeout(() => {
      this.successMessage.set(null);
    }, 4500);
  }

  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      if (this.isConfirmModalOpen()) {
        this.closeConfirmModal();
      } else if (this.isDeactivateModalOpen()) {
        this.closeDeactivateModal();
      } else if (this.isMapModalOpen()) {
        this.closeMapModal();
      } else if (this.isScheduleModalOpen()) {
        this.closeScheduleModal();
      } else if (this.isEventModalOpen()) {
        this.closeEventModal();
      }
    } else if (event.key === 'Enter') {
      if (this.isDeactivateModalOpen() && !this.isSubmitting()) {
        event.preventDefault();
        this.submitDeactivateUntil();
      } else if (this.isMapModalOpen()) {
        event.preventDefault();
        this.saveHeatingMap();
      } else if (this.isScheduleModalOpen()) {
        event.preventDefault();
        this.saveSchedule();
      } else if (this.isEventModalOpen()) {
        event.preventDefault();
        this.saveEventDefinition();
      }
    }
  }
}
