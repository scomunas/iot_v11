import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import {
  AlarmConfig,
  AlarmMemoryEvent,
  AlarmRuleData,
  AlarmRulePayload,
  AlarmService,
} from '../../services/alarm.service';
import { EventDefinition } from '../../services/events.service';
import { DeviceItem, HomeAssistantEntity, SettingsService } from '../../services/settings.service';
import { ConfirmModalComponent } from '../../components/confirm-modal/confirm-modal.component';

@Component({
  selector: 'app-alarm',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, ConfirmModalComponent],
  templateUrl: './alarm.component.html',
  styleUrls: ['./alarm.component.scss'],
})
export class AlarmComponent implements OnInit {
  private readonly alarmService = inject(AlarmService);
  private readonly settingsService = inject(SettingsService);

  // Loading and feedback states
  readonly loading = signal<boolean>(false);
  readonly savingConfig = signal<boolean>(false);
  readonly togglingAlarm = signal<boolean>(false);
  readonly testingAlarm = signal<boolean>(false);
  readonly clearingHistory = signal<boolean>(false);
  readonly successMessage = signal<string | null>(null);
  readonly errorMessage = signal<string | null>(null);

  // Alarm system state
  readonly alarmConfig = signal<AlarmConfig | null>(null);
  readonly rules = signal<EventDefinition[]>([]);
  readonly history = signal<AlarmMemoryEvent[]>([]);
  readonly hassEntities = signal<HomeAssistantEntity[]>([]);
  readonly devices = signal<DeviceItem[]>([]);

  // Filtering & Search
  readonly searchQuery = signal<string>('');
  readonly filterSensor = signal<string>('all');

  // General Configuration Form Model
  configEnabled = true;
  configNotificationMessage = '';
  configSpeakMessage = '';
  configDefaultTrigger = 2;
  configDefaultSeconds = 60;

  // Available tag helpers for user interface tag insertion
  readonly availableTags = [
    { tag: '{device_name}', label: 'Device Name', desc: 'Configured device friendly name' },
    { tag: '{device_type}', label: 'Device Type', desc: 'Configured device type (e.g. movement, door, presence)' },
    { tag: '{entity}', label: 'Sensor / Entity', desc: 'Sensor ID or name' },
    { tag: '{trigger}', label: 'Threshold', desc: 'Configured event threshold' },
    { tag: '{seconds}', label: 'Window', desc: 'Evaluation window in seconds' },
    { tag: '{count}', label: 'Event Count', desc: 'Actual events detected' },
    { tag: '{time}', label: 'Time', desc: 'Detection timestamp (HH:MM:SS)' },
  ];

  // Rule Modal State
  readonly isRuleModalOpen = signal<boolean>(false);
  readonly ruleModalMode = signal<'create' | 'edit'>('create');
  readonly editingRuleId = signal<number | null>(null);
  readonly isSavingRule = signal<boolean>(false);

  // Rule Form Model
  formRuleName = '';
  formRuleEntity = '';
  formRuleEventType = '';
  formRuleParameter = '';
  formRuleTrigger = 2;
  formRuleSeconds = 60;
  formRuleNotification = true;
  formRuleSpeak = false;
  formRuleHoliday = 'all_days';
  formRuleIsActive = true;

  // Delete Confirm Modal State
  readonly isDeleteModalOpen = signal<boolean>(false);
  readonly deletingRule = signal<EventDefinition | null>(null);
  readonly isDeleting = signal<boolean>(false);

  // Computeds
  readonly alarmHelperEntity = computed(() => this.alarmConfig()?.helper_entity || '');

  readonly filteredRules = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const sensor = this.filterSensor();

    return this.rules().filter((r) => {
      const data = this.alarmService.parseRuleData(r.data);
      const devName = this.getDeviceName(data.entity).toLowerCase();
      const devType = this.getDeviceType(data.entity).toLowerCase();
      const matchesSearch =
        !q ||
        r.name.toLowerCase().includes(q) ||
        r.type.toLowerCase().includes(q) ||
        devName.includes(q) ||
        devType.includes(q) ||
        (r.parameter && r.parameter.toLowerCase().includes(q)) ||
        data.entity.toLowerCase().includes(q);

      const matchesSensor = sensor === 'all' || data.entity === sensor;

      return matchesSearch && matchesSensor;
    });
  });

  readonly activeRulesCount = computed(() => {
    return this.rules().filter((r) => r.is_active === 1).length;
  });

  readonly availableSensors = computed(() => {
    const sensors = new Set<string>();
    this.rules().forEach((r) => {
      const d = this.alarmService.parseRuleData(r.data);
      if (d.entity) sensors.add(d.entity);
    });
    return Array.from(sensors).sort();
  });

  readonly sensorDevices = computed(() => {
    return this.devices().filter(
      (d) => d.type === 'movement' || d.type === 'presence' || d.type === 'door'
    );
  });

  readonly candidateEntities = computed(() => {
    return this.hassEntities().filter((e) => {
      const d = e.domain;
      return (
        d === 'binary_sensor' ||
        d === 'sensor' ||
        d === 'input_boolean' ||
        d === 'door' ||
        d === 'cover' ||
        d === 'lock'
      );
    });
  });

  ngOnInit(): void {
    this.loadAllData();
  }

  onToggleAlarm(event: Event): void {
    const isChecked = (event.target as HTMLInputElement).checked;
    this.togglingAlarm.set(true);
    this.alarmService.updateAlarmConfig({ enabled: isChecked }).subscribe({
      next: (resp) => {
        this.configEnabled = resp.config.enabled;
        this.alarmConfig.set(resp.config);
        this.togglingAlarm.set(false);
        this.showSuccess(isChecked ? 'Alarm system activated.' : 'Alarm system deactivated.');
      },
      error: (err) => {
        this.togglingAlarm.set(false);
        (event.target as HTMLInputElement).checked = this.configEnabled;
        this.showError('Failed to update alarm state: ' + (err.error?.detail || err.message));
      },
    });
  }

  loadAllData(): void {
    this.loading.set(true);
    this.loadConfig();
    this.loadRules();
    this.loadHistory();
    this.loadEntities();
    this.loadDevices();
  }

  loadConfig(): void {
    this.alarmService.getAlarmConfig().subscribe({
      next: (resp) => {
        const c = resp.config;
        this.alarmConfig.set(c);
        this.configEnabled = c.enabled;
        this.configNotificationMessage = c.notification_message;
        this.configSpeakMessage = c.speak_message;
        this.configDefaultTrigger = c.default_trigger;
        this.configDefaultSeconds = c.default_seconds;
        this.loading.set(false);
      },
      error: (err) => {
        this.showError(`Failed to load alarm configuration: ${err.message}`);
        this.loading.set(false);
      },
    });
  }

  loadRules(): void {
    this.alarmService.getAlarmRules().subscribe({
      next: (resp) => {
        this.rules.set(resp.rules || []);
      },
      error: (err) => {
        this.showError(`Failed to load alarm rules: ${err.message}`);
      },
    });
  }

  loadHistory(): void {
    this.alarmService.getAlarmHistory().subscribe({
      next: (resp) => {
        this.history.set(resp.events || []);
      },
      error: () => {},
    });
  }

  loadEntities(): void {
    this.settingsService.getHomeAssistantEntities().subscribe({
      next: (resp) => {
        this.hassEntities.set(resp.entities || []);
      },
      error: () => {},
    });
  }

  loadDevices(): void {
    this.settingsService.getDevices().subscribe({
      next: (resp) => {
        this.devices.set(resp.devices || []);
      },
      error: () => {},
    });
  }

  // Tag insertion into message inputs
  insertTagIntoNotification(tag: string): void {
    if (!this.configNotificationMessage) {
      this.configNotificationMessage = tag;
    } else {
      this.configNotificationMessage += ` ${tag}`;
    }
  }

  insertTagIntoSpeak(tag: string): void {
    if (!this.configSpeakMessage) {
      this.configSpeakMessage = tag;
    } else {
      this.configSpeakMessage += ` ${tag}`;
    }
  }

  saveGeneralConfig(): void {
    this.savingConfig.set(true);
    this.alarmService
      .updateAlarmConfig({
        enabled: this.configEnabled,
        notification_message: this.configNotificationMessage.trim(),
        speak_message: this.configSpeakMessage.trim(),
        default_trigger: Number(this.configDefaultTrigger),
        default_seconds: Number(this.configDefaultSeconds),
      })
      .subscribe({
        next: (resp) => {
          this.savingConfig.set(false);
          this.alarmConfig.set(resp.config);
          this.showSuccess('Alarm general configuration saved successfully!');
        },
        error: (err) => {
          this.savingConfig.set(false);
          this.showError(`Failed to save alarm configuration: ${err.message}`);
        },
      });
  }

  testAlarmSimulation(): void {
    this.testingAlarm.set(true);
    const candidateEntity = this.rules().length > 0
      ? this.alarmService.parseRuleData(this.rules()[0].data).entity
      : 'binary_sensor.front_door';

    this.alarmService
      .testAlarm({
        entity: candidateEntity,
        trigger: 1,
        seconds: 30,
        notification: true,
        speak: false,
      })
      .subscribe({
        next: (resp) => {
          this.testingAlarm.set(false);
          this.loadHistory();
          const r = resp.result;
          if (r?.alarm_triggered) {
            this.showSuccess(`Alarm simulated: ${r.message}`);
          } else {
            this.showSuccess(`Event recorded: ${r.message}`);
          }
        },
        error: (err) => {
          this.testingAlarm.set(false);
          this.showError(`Failed to run test simulation: ${err.message}`);
        },
      });
  }

  clearHistory(): void {
    this.clearingHistory.set(true);
    this.alarmService.clearAlarmHistory().subscribe({
      next: () => {
        this.clearingHistory.set(false);
        this.history.set([]);
        this.showSuccess('In-memory alarm events history cleared.');
      },
      error: (err) => {
        this.clearingHistory.set(false);
        this.showError(`Failed to clear history: ${err.message}`);
      },
    });
  }

  // Rule Modal Handling
  openCreateRuleModal(): void {
    this.ruleModalMode.set('create');
    this.editingRuleId.set(null);
    this.formRuleName = '';
    this.formRuleEntity = '';
    this.formRuleEventType = '';
    this.formRuleParameter = '';
    this.formRuleTrigger = this.configDefaultTrigger || 2;
    this.formRuleSeconds = this.configDefaultSeconds || 60;
    this.formRuleNotification = true;
    this.formRuleSpeak = false;
    this.formRuleHoliday = 'all_days';
    this.formRuleIsActive = true;
    this.isRuleModalOpen.set(true);
  }

  openEditRuleModal(rule: EventDefinition): void {
    this.ruleModalMode.set('edit');
    this.editingRuleId.set(rule.id);
    const data = this.alarmService.parseRuleData(rule.data);

    this.formRuleName = rule.name;
    this.formRuleEntity = data.entity || rule.type;
    this.formRuleEventType = rule.type;
    this.formRuleParameter = rule.parameter || '';
    this.formRuleTrigger = data.trigger || 2;
    this.formRuleSeconds = data.seconds || 60;
    this.formRuleNotification = data.notification;
    this.formRuleSpeak = data.speak;
    this.formRuleHoliday = rule.holiday || 'all_days';
    this.formRuleIsActive = rule.is_active === 1;
    this.isRuleModalOpen.set(true);
  }

  closeRuleModal(): void {
    this.isRuleModalOpen.set(false);
    this.editingRuleId.set(null);
  }

  getDeviceForEntity(entityId: string): DeviceItem | undefined {
    if (!entityId) return undefined;
    return this.devices().find((d) => d.entity_id === entityId);
  }

  getDeviceName(entityId: string): string {
    if (!entityId) return 'Unknown Sensor';
    const dev = this.getDeviceForEntity(entityId);
    if (dev) return dev.name;
    return this.getEntityFriendlyName(entityId);
  }

  getDeviceType(entityId: string): string {
    if (!entityId) return 'movement';
    const dev = this.getDeviceForEntity(entityId);
    if (dev) return dev.type;
    if (entityId.includes('.')) {
      const prefix = entityId.split('.')[0];
      if (prefix === 'binary_sensor') return 'movement';
      return prefix;
    }
    return 'movement';
  }

  getDeviceTypeIcon(type: string): string {
    switch (type?.toLowerCase()) {
      case 'door': return '🚪';
      case 'movement': return '🚶';
      case 'presence': return '👤';
      case 'temperature': return '🌡️';
      case 'rain': return '🌧️';
      case 'blinds': return '🪟';
      case 'irrigation': return '💧';
      case 'light': return '💡';
      default: return '📍';
    }
  }

  getStandardRuleName(): string {
    if (!this.formRuleEntity) {
      return this.formRuleName || 'Auto - Alarm';
    }
    const dev = this.sensorDevices().find((d) => d.entity_id === this.formRuleEntity);
    const friendly = dev ? dev.name : this.getEntityFriendlyName(this.formRuleEntity);
    return `Auto - Alarm - ${friendly}`;
  }

  getSelectedSensorDisplayName(): string {
    if (!this.formRuleEntity) return 'None Selected';
    const dev = this.sensorDevices().find((d) => d.entity_id === this.formRuleEntity);
    return dev ? dev.name : this.formRuleEntity;
  }

  onEntitySelectChange(): void {
    this.formRuleEventType = 'alarm';
    this.formRuleParameter = this.formRuleEntity;
    this.formRuleName = this.getStandardRuleName();
  }

  saveRule(): void {
    if (!this.formRuleEntity.trim()) {
      this.showError('Please select or enter a sensor entity.');
      return;
    }

    const ruleName = this.formRuleName.trim() || this.getStandardRuleName();

    this.isSavingRule.set(true);
    const entity = this.formRuleEntity.trim();
    const payload: AlarmRulePayload = {
      name: ruleName,
      entity: entity,
      event_type: 'alarm',
      parameter: entity,
      trigger: Number(this.formRuleTrigger),
      seconds: Number(this.formRuleSeconds),
      notification: this.formRuleNotification,
      speak: this.formRuleSpeak,
      holiday: this.formRuleHoliday,
      is_active: 1,
    };

    if (this.ruleModalMode() === 'create') {
      this.alarmService.createAlarmRule(payload).subscribe({
        next: (resp) => {
          this.isSavingRule.set(false);
          this.closeRuleModal();
          this.rules.update((list) => [resp.event_definition, ...list]);
          this.showSuccess(`Alarm rule '${payload.name}' created successfully!`);
        },
        error: (err) => {
          this.isSavingRule.set(false);
          this.showError(`Failed to create rule: ${err.message}`);
        },
      });
    } else {
      const id = this.editingRuleId();
      if (!id) return;
      this.alarmService.updateAlarmRule(id, payload).subscribe({
        next: (resp) => {
          this.isSavingRule.set(false);
          this.closeRuleModal();
          this.rules.update((list) =>
            list.map((r) => (r.id === id ? resp.event_definition : r))
          );
          this.showSuccess(`Alarm rule '${payload.name}' updated successfully!`);
        },
        error: (err) => {
          this.isSavingRule.set(false);
          this.showError(`Failed to update rule: ${err.message}`);
        },
      });
    }
  }

  toggleRule(rule: EventDefinition): void {
    this.alarmService.toggleRuleActive(rule).subscribe({
      next: (resp) => {
        this.rules.update((list) =>
          list.map((r) => (r.id === rule.id ? resp.event_definition : r))
        );
        const st = resp.event_definition.is_active === 1 ? 'activated' : 'deactivated';
        this.showSuccess(`Rule '${rule.name}' ${st}.`);
      },
      error: (err) => {
        this.showError(`Failed to toggle rule: ${err.message}`);
      },
    });
  }

  openDeleteRuleModal(rule: EventDefinition): void {
    this.deletingRule.set(rule);
    this.isDeleteModalOpen.set(true);
  }

  closeDeleteModal(): void {
    this.isDeleteModalOpen.set(false);
    this.deletingRule.set(null);
  }

  confirmDeleteRule(): void {
    const rule = this.deletingRule();
    if (!rule) return;
    this.isDeleting.set(true);
    this.alarmService.deleteAlarmRule(rule.id).subscribe({
      next: () => {
        this.isDeleting.set(false);
        this.closeDeleteModal();
        this.rules.update((list) => list.filter((r) => r.id !== rule.id));
        this.showSuccess(`Alarm rule '${rule.name}' deleted successfully.`);
      },
      error: (err) => {
        this.isDeleting.set(false);
        this.showError(`Failed to delete rule: ${err.message}`);
      },
    });
  }

  parseRuleData(data: any): AlarmRuleData {
    return this.alarmService.parseRuleData(data);
  }

  getEntityFriendlyName(entityId: string): string {
    const ent = this.hassEntities().find((e) => e.entity_id === entityId);
    return ent?.friendly_name || entityId;
  }

  getHolidayLabel(holiday?: string): string {
    switch (holiday) {
      case 'holiday': return '🎉 Holidays Only';
      case 'not_holiday': return '💼 Workdays Only';
      default: return '📅 All Days';
    }
  }

  private showSuccess(msg: string): void {
    this.successMessage.set(msg);
    setTimeout(() => this.successMessage.set(null), 5000);
  }

  private showError(msg: string): void {
    this.errorMessage.set(msg);
    setTimeout(() => this.errorMessage.set(null), 7000);
  }
}
