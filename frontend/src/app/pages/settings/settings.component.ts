import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ConfirmModalComponent } from '../../components/confirm-modal/confirm-modal.component';
import {
  DeviceItem,
  DevicePayload,
  DeviceType,
  HomeAssistantEntity,
  SettingsService,
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
    { id: 'heating', label: 'Heating', icon: '🔥' },
    { id: 'temperature', label: 'Temperature', icon: '🌡️' },
    { id: 'movement', label: 'Movement', icon: '🚶' },
    { id: 'presence', label: 'Presence', icon: '📍' },
  ];

  // System & Heating Settings State
  readonly heatingIntervalMinutes = signal<number>(5);
  readonly isSavingSettings = signal<boolean>(false);
  readonly presetIntervals = [5, 10, 15, 30, 60];

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
  }

  loadSettings(): void {
    this.settingsService.getSystemSettings().subscribe({
      next: (resp) => {
        if (resp && resp.settings && resp.settings['heating_interval_minutes']) {
          this.heatingIntervalMinutes.set(Number(resp.settings['heating_interval_minutes']));
        }
      },
      error: (err) => {
        console.error('Failed to load system settings:', err);
      }
    });
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
    this.settingsService.updateSystemSettings({ heating_interval_minutes: mins }).subscribe({
      next: () => {
        this.isSavingSettings.set(false);
        this.showSuccess(`Heating check interval updated to ${mins} minutes.`);
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
    } else if (uc.function_name === 'create_datetime_file') {
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
      case 'heating_control': return '🔥 Heating Control';
      case 'heating_recurrent': return '🔥 Heating Recurrent';
      case 'notification': return '🔔 Notification';
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

  private showSuccess(msg: string): void {
    this.successMessage.set(msg);
    setTimeout(() => this.successMessage.set(null), 5000);
  }
}
