import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ConfirmModalComponent } from '../../components/confirm-modal/confirm-modal.component';
import { AlarmConfig, AlarmService } from '../../services/alarm.service';
import {
  DeviceItem,
  DevicePayload,
  DeviceType,
  HomeAssistantEntity,
  NotificationChannel,
  SettingsService,
  SpeakerSystemConfig,
  SystemFunction,
  TestExecutionResult,
  UseCase,
} from '../../services/settings.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [CommonModule, FormsModule, DatePipe, ConfirmModalComponent],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.scss'
})
export class SettingsComponent implements OnInit {
  private readonly settingsService = inject(SettingsService);
  private readonly alarmService = inject(AlarmService);

  // Use Cases State
  readonly useCases = signal<UseCase[]>([]);
  readonly availableFunctions = signal<SystemFunction[]>([]);
  readonly loading = signal<boolean>(false);
  readonly testingId = signal<number | null>(null);
  readonly errorMessage = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);
  readonly testResult = signal<TestExecutionResult | null>(null);

  // Use Case Modal State
  readonly isModalOpen = signal<boolean>(false);
  readonly modalMode = signal<'create' | 'edit'>('create');
  readonly selectedUseCaseId = signal<number | null>(null);

  // Use Case Form Fields
  formName = '';
  formFunctionName = 'create_datetime_file';
  formDescription = '';
  formSection = '';

  // Devices & Home Assistant State
  readonly devices = signal<DeviceItem[]>([]);
  readonly hassEntities = signal<HomeAssistantEntity[]>([]);
  readonly hassConnected = signal<boolean>(false);
  readonly hassUrl = signal<string>('');
  readonly hassError = signal<string | null>(null);
  readonly loadingDevices = signal<boolean>(false);

  // Device Modal State
  readonly isDeviceModalOpen = signal<boolean>(false);
  readonly deviceModalMode = signal<'create' | 'edit'>('create');
  readonly selectedDeviceId = signal<number | null>(null);

  // Device Form Fields
  formDeviceName = '';
  formDeviceType: DeviceType = 'light';
  formDeviceEntityId = '';
  readonly entityFilter = signal<string>('');

  readonly deviceTypes: { id: DeviceType; label: string; icon: string }[] = [
    { id: 'light', label: 'Light', icon: '💡' },
    { id: 'irrigation', label: 'Irrigation', icon: '💧' },
    { id: 'blinds', label: 'Blinds', icon: '🪟' },
    { id: 'rain', label: 'Rain', icon: '🌧️' },
    { id: 'temperature', label: 'Temperature', icon: '🌡️' },
    { id: 'movement', label: 'Movement', icon: '🚶' },
    { id: 'presence', label: 'Presence', icon: '📍' },
    { id: 'door', label: 'Door', icon: '🚪' },
  ];

  // System & Heating Settings State
  readonly heatingIntervalMinutes = signal<number>(5);
  readonly heatingHelperEntity = signal<string>('');
  readonly heatingHeaters = signal<string[]>([]);
  newHeaterEntityId = '';
  readonly isSavingSettings = signal<boolean>(false);
  readonly presetIntervals = [5, 10, 15, 30, 60];

  // Notification Channels State
  readonly notificationChannels = signal<NotificationChannel[]>([]);
  readonly loadingChannels = signal<boolean>(false);
  readonly savingChannel = signal<string | null>(null);
  readonly testingChannel = signal<string | null>(null);

  // Telegram Channel Form Model
  telegramEnabled: boolean = true;
  telegramChatId: string = '';
  telegramBotToken: string = '';

  // Speaker System (Chime TTS) State
  readonly speakerConfig = signal<SpeakerSystemConfig | null>(null);
  readonly loadingSpeakers = signal<boolean>(false);
  readonly savingSpeakers = signal<boolean>(false);
  readonly broadcastingSpeaker = signal<boolean>(false);

  // Speaker Form Model
  speakerEnabled: boolean = true;
  selectedSpeakers: string[] = ['media_player.todos_los_altavoces'];
  speakerChimePath: string = 'bells';
  speakerTtsPlatform: string = 'tts.google_translate_say';
  speakerVolumeLevel: number = 0.8;
  speakerDefaultMessage: string = 'Se ha detectado su presencia de forma indebida y se está comunicando a la policía.';
  newSpeakerEntityId: string = '';

  // Chime Presets
  readonly chimePresets = ['bells', 'chord', 'ding_dong', 'marimba', 'soft'];
  readonly ttsPresets = ['tts.google_translate_say', 'tts.piper', 'tts.cloud'];
  readonly Math = Math;

  readonly availableMediaPlayerEntities = computed(() => {
    return this.hassEntities().filter(
      (e) => e.domain === 'media_player' || e.entity_id.startsWith('media_player.')
    );
  });

  readonly filteredEntities = computed(() => {
    const query = this.entityFilter().toLowerCase().trim();
    const list = this.hassEntities();
    if (!query) return list;
    return list.filter(
      (e) =>
        e.friendly_name.toLowerCase().includes(query) ||
        e.entity_id.toLowerCase().includes(query) ||
        e.domain.toLowerCase().includes(query)
    );
  });

  // Alarm System State
  readonly loadingAlarmConfig = signal<boolean>(false);
  readonly savingAlarmConfig = signal<boolean>(false);
  readonly alarmConfig = signal<AlarmConfig | null>(null);

  alarmEnabled = true;
  alarmHelperEntity = '';
  alarmNotificationMessage = '';
  alarmSpeakMessage = '';
  alarmDefaultTrigger = 2;
  alarmDefaultSeconds = 60;
  alarmRetentionSeconds = 300;
  alarmDelaySeconds = 30;

  readonly alarmAvailableTags = [
    { tag: '{device_name}', label: 'Device Name', desc: 'Configured device friendly name' },
    { tag: '{device_type}', label: 'Device Type', desc: 'Configured device type (e.g. movement, door, presence)' },
    { tag: '{entity}', label: 'Sensor / Entity', desc: 'Sensor ID or name' },
    { tag: '{trigger}', label: 'Threshold', desc: 'Configured event threshold' },
    { tag: '{seconds}', label: 'Window', desc: 'Evaluation window in seconds' },
    { tag: '{count}', label: 'Event Count', desc: 'Actual events detected' },
    { tag: '{time}', label: 'Time', desc: 'Detection timestamp (HH:MM:SS)' },
  ];

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading.set(true);
    this.errorMessage.set(null);

    // 1. Load Use Cases & Functions
    this.settingsService.getUseCases().subscribe({
      next: (resp) => {
        this.useCases.set(resp.use_cases);
        this.availableFunctions.set(resp.available_functions);
        if (resp.available_functions.length > 0 && !this.formFunctionName) {
          this.formFunctionName = resp.available_functions[0].id;
        }
        this.loading.set(false);
      },
      error: (err) => {
        this.errorMessage.set(err.message || 'Failed to load settings from backend');
        this.loading.set(false);
      }
    });

    // 2. Load Devices
    this.loadDevices();

    // 3. Load Home Assistant Entities
    this.loadHassEntities();

    // 4. Load System & Heating Settings
    this.loadSettings();

    // 5. Load Notification Channels
    this.loadNotificationChannels();

    // 6. Load Speaker System Config
    this.loadSpeakerConfig();
    this.loadAlarmConfig();
  }

  loadNotificationChannels(): void {
    this.loadingChannels.set(true);
    this.settingsService.getNotificationChannels().subscribe({
      next: (resp) => {
        const channels = resp.channels || [];
        this.notificationChannels.set(channels);
        const tg = channels.find((c) => c.id === 'telegram');
        if (tg) {
          this.telegramEnabled = tg.enabled;
          this.telegramChatId = tg.config?.['chat_id'] || '';
          this.telegramBotToken = tg.config?.['bot_token'] || '';
        }
        this.loadingChannels.set(false);
      },
      error: () => {
        this.loadingChannels.set(false);
      }
    });
  }

  saveTelegramChannel(): void {
    this.savingChannel.set('telegram');
    this.settingsService
      .updateNotificationChannel('telegram', {
        enabled: true,
        config: {
          chat_id: this.telegramChatId.trim(),
          bot_token: this.telegramBotToken.trim(),
        },
      })
      .subscribe({
        next: () => {
          this.savingChannel.set(null);
          this.showSuccess('Telegram notification channel updated successfully!');
          this.loadNotificationChannels();
        },
        error: (err) => {
          this.savingChannel.set(null);
          this.showError(`Failed to update Telegram channel: ${err.error?.detail || err.message}`);
        },
      });
  }

  testTelegramChannel(): void {
    this.testingChannel.set('telegram');
    this.settingsService.testNotificationChannel('telegram').subscribe({
      next: () => {
        this.testingChannel.set(null);
        this.showSuccess('Test alert dispatched to Telegram successfully!');
      },
      error: (err) => {
        this.testingChannel.set(null);
        this.showError(`Failed to send test alert: ${err.error?.detail || err.message}`);
      },
    });
  }

  getTelegramChannel(): NotificationChannel | undefined {
    return this.notificationChannels().find((c) => c.id === 'telegram');
  }

  loadSpeakerConfig(): void {
    this.loadingSpeakers.set(true);
    this.settingsService.getSpeakerConfig().subscribe({
      next: (cfg) => {
        this.speakerConfig.set(cfg);
        this.speakerEnabled = cfg.enabled ?? true;
        this.selectedSpeakers = Array.isArray(cfg.speakers) ? [...cfg.speakers] : [];
        this.speakerChimePath = cfg.chime_path || 'bells';
        this.speakerTtsPlatform = cfg.tts_platform || 'tts.google_translate_say';
        this.speakerVolumeLevel = cfg.volume_level !== undefined ? cfg.volume_level : 0.8;
        this.speakerDefaultMessage = cfg.default_message || '';
        this.loadingSpeakers.set(false);
      },
      error: () => {
        this.loadingSpeakers.set(false);
      }
    });
  }

  addSpeaker(entityId: string): void {
    const clean = entityId.trim();
    if (!clean) return;
    if (!this.selectedSpeakers.includes(clean)) {
      this.selectedSpeakers.push(clean);
    }
    this.newSpeakerEntityId = '';
  }

  removeSpeaker(speaker: string): void {
    this.selectedSpeakers = this.selectedSpeakers.filter((s) => s !== speaker);
  }

  setChimePreset(preset: string): void {
    this.speakerChimePath = preset;
  }

  saveSpeakerConfig(): void {
    this.savingSpeakers.set(true);
    this.settingsService
      .updateSpeakerConfig({
        enabled: true,
        speakers: this.selectedSpeakers,
        chime_path: this.speakerChimePath.trim(),
        tts_platform: this.speakerTtsPlatform.trim(),
        volume_level: Number(this.speakerVolumeLevel),
        default_message: this.speakerDefaultMessage.trim(),
      })
      .subscribe({
        next: (resp) => {
          this.savingSpeakers.set(false);
          this.speakerConfig.set(resp.config);
          this.showSuccess('Speaker system settings saved successfully!');
        },
        error: (err) => {
          this.savingSpeakers.set(false);
          this.showError(`Failed to save speaker system settings: ${err.error?.detail || err.message}`);
        },
      });
  }

  testSpeakerBroadcast(): void {
    this.broadcastingSpeaker.set(true);
    this.settingsService
      .broadcastSpeaker({
        message: this.speakerDefaultMessage.trim() || undefined,
        speakers: this.selectedSpeakers.length > 0 ? this.selectedSpeakers : undefined,
        chime_path: this.speakerChimePath.trim() || undefined,
        tts_platform: this.speakerTtsPlatform.trim() || undefined,
        volume_level: Number(this.speakerVolumeLevel),
        force: true,
      })
      .subscribe({
        next: (resp) => {
          this.broadcastingSpeaker.set(false);
          if (resp.result?.success) {
            this.showSuccess('Broadcast audio sent to speakers successfully!');
          } else if (resp.result?.skipped) {
            this.showSuccess(`Broadcast skipped: ${resp.result.reason}`);
          } else {
            this.showSuccess('Broadcast command dispatched to Home Assistant.');
          }
        },
        error: (err) => {
          this.broadcastingSpeaker.set(false);
          this.showError(`Failed to broadcast to speakers: ${err.error?.detail || err.message}`);
        },
      });
  }

  loadSettings(): void {
    this.settingsService.getSystemSettings().subscribe({
      next: (resp) => {
        if (resp && resp.settings) {
          if (resp.settings['heating_interval_minutes']) {
            this.heatingIntervalMinutes.set(Number(resp.settings['heating_interval_minutes']));
          }
          if (resp.settings['heating_helper_entity'] !== undefined) {
            this.heatingHelperEntity.set(String(resp.settings['heating_helper_entity'] || ''));
          }
          if (resp.settings['heating_heater_entities'] !== undefined) {
            const raw = resp.settings['heating_heater_entities'];
            try {
              if (Array.isArray(raw)) {
                this.heatingHeaters.set(raw.map(e => String(e).trim()).filter(e => e.length > 0));
              } else if (typeof raw === 'string') {
                const trimmed = raw.trim();
                if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
                  try {
                    const parsed = JSON.parse(trimmed);
                    this.heatingHeaters.set(Array.isArray(parsed) ? parsed.map(e => String(e).trim()).filter(e => e.length > 0) : []);
                  } catch {
                    const parsed = trimmed.slice(1, -1).split(',')
                      .map(s => s.trim().replace(/^['"]|['"]$/g, ''))
                      .filter(s => s.length > 0);
                    this.heatingHeaters.set(parsed);
                  }
                } else if (trimmed) {
                  this.heatingHeaters.set([trimmed]);
                } else {
                  this.heatingHeaters.set([]);
                }
              } else {
                this.heatingHeaters.set([]);
              }
            } catch {
              this.heatingHeaters.set([]);
            }
          }
        }
      },
      error: (err) => {
        console.error('Failed to load system settings:', err);
      }
    });
  }

  addHeater(entityId: string): void {
    const clean = entityId.trim();
    if (!clean) return;
    const current = this.heatingHeaters();
    if (!current.includes(clean)) {
      this.heatingHeaters.set([...current, clean]);
    }
    this.newHeaterEntityId = '';
  }

  removeHeater(entityId: string): void {
    this.heatingHeaters.set(this.heatingHeaters().filter((h) => h !== entityId));
  }

  adjustInterval(delta: number): void {
    const current = Number(this.heatingIntervalMinutes()) || 5;
    const next = Math.max(1, Math.min(720, current + delta));
    this.heatingIntervalMinutes.set(next);
  }

  selectPresetInterval(mins: number): void {
    this.heatingIntervalMinutes.set(mins);
  }

  saveHeatingSettings(): void {
    const mins = Number(this.heatingIntervalMinutes());
    if (isNaN(mins) || mins < 1) {
      alert('Please enter a valid interval of at least 1 minute.');
      return;
    }
    this.isSavingSettings.set(true);
    this.settingsService.updateSystemSettings({
      heating_interval_minutes: mins,
      heating_helper_entity: this.heatingHelperEntity().trim(),
      heating_heater_entities: this.heatingHeaters(),
    }).subscribe({
      next: () => {
        this.isSavingSettings.set(false);
        this.showSuccess('Heating settings saved successfully.');
      },
      error: (err) => {
        this.isSavingSettings.set(false);
        alert(`Error saving heating settings: ${err.error?.detail || err.message}`);
      }
    });
  }

  loadDevices(): void {
    this.loadingDevices.set(true);
    this.settingsService.getDevices().subscribe({
      next: (resp) => {
        this.devices.set(resp.devices || []);
        this.loadingDevices.set(false);
      },
      error: (err) => {
        console.error('Failed to load devices:', err);
        this.loadingDevices.set(false);
      }
    });
  }

  loadHassEntities(): void {
    this.settingsService.getHomeAssistantEntities().subscribe({
      next: (resp) => {
        this.hassEntities.set(resp.entities || []);
        this.hassConnected.set(resp.connected);
        this.hassUrl.set(resp.hass_url);
        this.hassError.set(resp.error || null);
      },
      error: (err) => {
        console.error('Failed to load Home Assistant entities:', err);
        this.hassConnected.set(false);
        this.hassError.set(err.message || 'Could not fetch Home Assistant entities');
      }
    });
  }

  // ==========================================
  // Use Cases Actions
  // ==========================================

  openCreateModal(): void {
    this.modalMode.set('create');
    this.selectedUseCaseId.set(null);
    this.formName = '';
    this.formFunctionName = this.availableFunctions()[0]?.id || 'create_datetime_file';
    this.formDescription = '';
    this.formSection = '';
    this.isModalOpen.set(true);
  }

  openEditModal(uc: UseCase): void {
    this.modalMode.set('edit');
    this.selectedUseCaseId.set(uc.id);
    this.formName = uc.name;
    this.formFunctionName = uc.function_name;
    this.formDescription = uc.description || '';
    this.formSection = uc.section || '';
    this.isModalOpen.set(true);
  }

  closeModal(): void {
    this.isModalOpen.set(false);
  }

  saveUseCase(): void {
    const trimmedName = this.formName.trim();
    if (!trimmedName) {
      alert('Please provide a use case name.');
      return;
    }
    if (!this.formFunctionName) {
      alert('Please select an executable function.');
      return;
    }

    const payload = {
      name: trimmedName,
      function_name: this.formFunctionName,
      description: this.formDescription.trim(),
      section: this.formSection ? this.formSection.trim() : null,
    };

    if (this.modalMode() === 'create') {
      this.settingsService.createUseCase(payload).subscribe({
        next: () => {
          this.showSuccess(`Use case '${trimmedName}' created successfully.`);
          this.closeModal();
          this.loadData();
        },
        error: (err) => {
          alert(`Error creating use case: ${err.error?.detail || err.message}`);
        }
      });
    } else {
      const id = this.selectedUseCaseId();
      if (!id) return;

      this.settingsService.updateUseCase(id, payload).subscribe({
        next: () => {
          this.showSuccess(`Use case #${id} updated successfully.`);
          this.closeModal();
          this.loadData();
        },
        error: (err) => {
          alert(`Error updating use case: ${err.error?.detail || err.message}`);
        }
      });
    }
  }

  deleteUseCase(uc: UseCase): void {
    this.openConfirmModal(
      'Delete Use Case',
      `Are you sure you want to delete use case "${uc.name}" (ID #${uc.id})?`,
      () => {
        this.isConfirming.set(true);
        this.settingsService.deleteUseCase(uc.id).subscribe({
          next: () => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            this.showSuccess(`Use case #${uc.id} deleted.`);
            this.loadData();
          },
          error: (err) => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            alert(`Failed to delete use case: ${err.error?.detail || err.message}`);
          }
        });
      }
    );
  }

  // Test Modal State
  readonly isTestModalOpen = signal<boolean>(false);
  readonly testingUseCase = signal<UseCase | null>(null);
  readonly testParamsJson = signal<string>('{}');
  readonly testModalError = signal<string | null>(null);

  openTestModal(uc: UseCase): void {
    this.testingUseCase.set(uc);
    this.testModalError.set(null);

    // Provide helpful prefilled template according to function_name
    let defaultJson = '{}';
    if (uc.function_name === 'start_irrigation') {
      defaultJson = JSON.stringify({ entity_id: 'switch.garden_irrigation_zone1', seconds: 5 }, null, 2);
    } else if (uc.function_name === 'move_blind') {
      defaultJson = JSON.stringify({ entity: 'cover.living_room_blind', position: 50, not_before: '' }, null, 2);
    } else if (uc.function_name === 'add_holiday') {
      defaultJson = JSON.stringify({ when: 'today', name: 'Manual Test Holiday' }, null, 2);
    } else if (uc.function_name === 'get_year_holidays') {
      defaultJson = JSON.stringify({ county: 'ES-CT' }, null, 2);
    } else if (uc.function_name === 'send_telegram_alert') {
      defaultJson = JSON.stringify({ message: '🚨 Alert: Automation triggered!', chat_id: '' }, null, 2);
    } else if (uc.function_name === 'start_heating') {
      defaultJson = JSON.stringify({ action: 'on' }, null, 2);
    } else if (uc.function_name === 'control_heating') {
      defaultJson = '{}';
    } else if (uc.function_name === 'set_heating_map') {
      defaultJson = JSON.stringify({ map_name: 'Comfort' }, null, 2);
    } else if (uc.function_name === 'create_datetime_file' || uc.function_name === 'do_nothing') {
      defaultJson = '{}';
    }

    this.testParamsJson.set(defaultJson);
    this.isTestModalOpen.set(true);
  }

  closeTestModal(): void {
    this.isTestModalOpen.set(false);
    this.testingUseCase.set(null);
    this.testModalError.set(null);
  }

  formatTestJson(): void {
    try {
      const parsed = JSON.parse(this.testParamsJson().trim() || '{}');
      this.testParamsJson.set(JSON.stringify(parsed, null, 2));
      this.testModalError.set(null);
    } catch {
      this.testModalError.set('Invalid JSON in Parameters field.');
    }
  }

  setTestParamPreset(params: Record<string, any>): void {
    this.testParamsJson.set(JSON.stringify(params, null, 2));
    this.testModalError.set(null);
  }

  executeTest(): void {
    const uc = this.testingUseCase();
    if (!uc) return;

    let parsedData: any = {};
    const raw = this.testParamsJson().trim();
    if (raw) {
      try {
        parsedData = JSON.parse(raw);
      } catch {
        this.testModalError.set('Invalid JSON format. Please correct it before running.');
        return;
      }
    }

    this.testingId.set(uc.id);
    this.testResult.set(null);
    this.testModalError.set(null);

    this.settingsService.testUseCase(uc.id, parsedData).subscribe({
      next: (res) => {
        this.testResult.set(res);
        this.testingId.set(null);
        this.closeTestModal();
        const details = res.result || res.result_file || res.message;
        this.showSuccess(`Test run completed! ${details}`);
      },
      error: (err) => {
        this.testingId.set(null);
        this.testModalError.set(err.error?.detail || err.message);
      }
    });
  }

  runTest(uc: UseCase): void {
    this.openTestModal(uc);
  }

  clearTestResult(): void {
    this.testResult.set(null);
  }

  getFunctionLabel(fnId: string): string {
    const found = this.availableFunctions().find((f) => f.id === fnId);
    return found ? found.name : fnId;
  }

  getSectionLabel(section?: string | null): string {
    if (!section) return '';
    switch (section) {
      case 'irrigation': return '💧 Irrigation';
      case 'blinds': return '🪟 Blinds';
      case 'rain': return '🌧️ Rain';
      case 'heating':
      case 'heating_control': return '🔥 Heating';
      case 'alarm': return '🚨 Alarm';
      case 'general': return '⚙️ General';
      default: return section;
    }
  }

  getSelectedFunctionDescription(): string {
    const fn = this.availableFunctions().find((f) => f.id === this.formFunctionName);
    return fn ? fn.description : '';
  }

  // ==========================================
  // Devices Actions
  // ==========================================

  openCreateDeviceModal(): void {
    this.deviceModalMode.set('create');
    this.selectedDeviceId.set(null);
    this.formDeviceName = '';
    this.formDeviceType = 'light';
    this.entityFilter.set('');

    // Preselect first entity if available
    const entities = this.hassEntities();
    this.formDeviceEntityId = entities.length > 0 ? entities[0].entity_id : '';
    this.isDeviceModalOpen.set(true);
  }

  openEditDeviceModal(device: DeviceItem): void {
    this.deviceModalMode.set('edit');
    this.selectedDeviceId.set(device.id);
    this.formDeviceName = device.name;
    this.formDeviceType = device.type;
    this.formDeviceEntityId = device.entity_id;
    this.entityFilter.set('');
    this.isDeviceModalOpen.set(true);
  }

  closeDeviceModal(): void {
    this.isDeviceModalOpen.set(false);
  }

  saveDevice(): void {
    const trimmedName = this.formDeviceName.trim();
    if (!trimmedName) {
      alert('Please provide a device name.');
      return;
    }
    if (!this.formDeviceEntityId.trim()) {
      alert('Please select or specify a Home Assistant entity.');
      return;
    }

    const payload: DevicePayload = {
      name: trimmedName,
      type: this.formDeviceType,
      entity_id: this.formDeviceEntityId.trim(),
    };

    if (this.deviceModalMode() === 'create') {
      this.settingsService.createDevice(payload).subscribe({
        next: () => {
          this.showSuccess(`Device '${trimmedName}' configured successfully.`);
          this.closeDeviceModal();
          this.loadDevices();
        },
        error: (err) => {
          alert(`Error creating device: ${err.error?.detail || err.message}`);
        }
      });
    } else {
      const id = this.selectedDeviceId();
      if (!id) return;

      this.settingsService.updateDevice(id, payload).subscribe({
        next: () => {
          this.showSuccess(`Device #${id} updated successfully.`);
          this.closeDeviceModal();
          this.loadDevices();
        },
        error: (err) => {
          alert(`Error updating device: ${err.error?.detail || err.message}`);
        }
      });
    }
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

  deleteDevice(device: DeviceItem): void {
    this.openConfirmModal(
      'Delete Device',
      `Are you sure you want to delete configured device "${device.name}" (ID #${device.id})?`,
      () => {
        this.isConfirming.set(true);
        this.settingsService.deleteDevice(device.id).subscribe({
          next: () => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            this.showSuccess(`Device #${device.id} deleted.`);
            this.loadDevices();
          },
          error: (err) => {
            this.isConfirming.set(false);
            this.closeConfirmModal();
            alert(`Failed to delete device: ${err.error?.detail || err.message}`);
          }
        });
      }
    );
  }

  getDeviceTypeInfo(type: DeviceType) {
    return this.deviceTypes.find((d) => d.id === type) || { id: type, label: type, icon: '⚙️' };
  }

  getEntityFriendlyName(entityId: string): string {
    const found = this.hassEntities().find((e) => e.entity_id === entityId);
    return found ? found.friendly_name : entityId;
  }

  isEntityInHassList(entityId: string): boolean {
    if (!entityId) return false;
    return this.hassEntities().some((e) => e.entity_id === entityId);
  }

  private showSuccess(msg: string): void {
    this.successMessage.set(msg);
    setTimeout(() => this.successMessage.set(null), 5000);
  }

  private showError(msg: string): void {
    this.errorMessage.set(msg);
    setTimeout(() => this.errorMessage.set(null), 7000);
  }

loadAlarmConfig(): void {
    this.loadingAlarmConfig.set(true);
    this.alarmService.getAlarmConfig().subscribe({
      next: (resp) => {
        if (resp && resp.config) {
          this.alarmConfig.set(resp.config);
          this.alarmEnabled = resp.config.enabled;
          this.alarmHelperEntity = resp.config.helper_entity || '';
          this.alarmNotificationMessage = resp.config.notification_message || '';
          this.alarmSpeakMessage = resp.config.speak_message || '';
          this.alarmDefaultTrigger = resp.config.default_trigger || 2;
          this.alarmDefaultSeconds = resp.config.default_seconds || 60;
          this.alarmRetentionSeconds = resp.config.retention_seconds || 300;
          this.alarmDelaySeconds = resp.config.delay_seconds ?? 30;
        }
        this.loadingAlarmConfig.set(false);
      },
      error: (err) => {
        this.showError('Failed to load alarm configuration: ' + (err.error?.detail || err.message));
        this.loadingAlarmConfig.set(false);
      },
    });
  }

  saveAlarmConfig(): void {
    this.savingAlarmConfig.set(true);
    const payload = {
      enabled: this.alarmEnabled,
      helper_entity: this.alarmHelperEntity,
      notification_message: this.alarmNotificationMessage,
      speak_message: this.alarmSpeakMessage,
      default_trigger: Number(this.alarmDefaultTrigger) || 2,
      default_seconds: Number(this.alarmDefaultSeconds) || 60,
      retention_seconds: Number(this.alarmRetentionSeconds) || 300,
      delay_seconds: Number(this.alarmDelaySeconds) >= 0 ? Number(this.alarmDelaySeconds) : 30,
    };

    this.alarmService.updateAlarmConfig(payload).subscribe({
      next: (resp) => {
        this.alarmConfig.set(resp.config);
        this.savingAlarmConfig.set(false);
        this.showSuccess('Alarm configuration saved successfully.');
      },
      error: (err) => {
        this.savingAlarmConfig.set(false);
        this.showError('Failed to save alarm configuration: ' + (err.error?.detail || err.message));
      },
    });
  }

  insertTagIntoAlarmNotification(tag: string): void {
    this.alarmNotificationMessage = this.alarmNotificationMessage
      ? this.alarmNotificationMessage + ' ' + tag
      : tag;
  }

  insertTagIntoAlarmSpeak(tag: string): void {
    this.alarmSpeakMessage = this.alarmSpeakMessage
      ? this.alarmSpeakMessage + ' ' + tag
      : tag;
  }

  adjustAlarmTrigger(delta: number): void {
    const current = Number(this.alarmDefaultTrigger) || 2;
    this.alarmDefaultTrigger = Math.max(1, Math.min(99, current + delta));
  }

  adjustAlarmSeconds(delta: number): void {
    const current = Number(this.alarmDefaultSeconds) || 60;
    this.alarmDefaultSeconds = Math.max(5, Math.min(3600, current + delta));
  }

  adjustAlarmRetention(delta: number): void {
    const current = Number(this.alarmRetentionSeconds) || 300;
    this.alarmRetentionSeconds = Math.max(10, Math.min(86400, current + delta));
  }

  adjustAlarmDelay(delta: number): void {
    const current = Number(this.alarmDelaySeconds) || 0;
    this.alarmDelaySeconds = Math.max(0, Math.min(3600, current + delta));
  }
}
