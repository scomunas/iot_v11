import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ConfirmModalComponent } from '../../components/confirm-modal/confirm-modal.component';
import { EventDefinition, EventDefinitionPayload, EventsService } from '../../services/events.service';
import { SettingsService, UseCase } from '../../services/settings.service';

@Component({
  selector: 'app-events',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, ConfirmModalComponent],
  templateUrl: './events.component.html',
  styleUrl: './events.component.scss'
})
export class EventsComponent implements OnInit {
  private readonly eventsService = inject(EventsService);
  private readonly settingsService = inject(SettingsService);

  readonly eventDefinitions = signal<EventDefinition[]>([]);
  readonly configuredUseCases = signal<UseCase[]>([]);
  readonly loading = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);

  // Search & Filter
  readonly searchQuery = signal<string>('');
  readonly filterType = signal<string>('all');

  // Modal State
  readonly isModalOpen = signal<boolean>(false);
  readonly modalMode = signal<'create' | 'edit'>('create');
  readonly selectedId = signal<number | null>(null);

  // Form Fields
  formName: string = '';
  formType: string = 'sunrise';
  formParameter: string = '';
  formUseCase: string = '';
  formData: string = '{}';
  formHoliday: string = 'all_days';
  formNotify: number = 0;
  formNotificationMessage: string = '';
  formIsActive: number = 1;

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

  setEventType(type: string, param: string = ''): void {
    this.formType = type;
    this.formParameter = param;
  }

  // Test firing state
  readonly firingEventId = signal<number | null>(null);

  readonly filteredDefinitions = computed(() => {
    const query = this.searchQuery().toLowerCase().trim();
    const typeFilter = this.filterType().toLowerCase().trim();

    return this.eventDefinitions().filter((def) => {
      const matchesSearch =
        !query ||
        def.name.toLowerCase().includes(query) ||
        def.type.toLowerCase().includes(query) ||
        def.parameter.toLowerCase().includes(query) ||
        def.use_case.toLowerCase().includes(query);

      const matchesType = typeFilter === 'all' || def.type.toLowerCase() === typeFilter;

      return matchesSearch && matchesType;
    });
  });

  readonly availableTypes = computed(() => {
    const set = new Set<string>();
    this.eventDefinitions().forEach((d) => {
      if (d.type) set.add(d.type.trim().toLowerCase());
    });
    return Array.from(set).sort();
  });

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading.set(true);
    this.errorMessage.set(null);

    // 1. Load Event Definitions
    this.eventsService.getEventDefinitions().subscribe({
      next: (resp) => {
        this.eventDefinitions.set(resp.event_definitions || []);
        this.loading.set(false);
      },
      error: (err) => {
        this.errorMessage.set(err.message || 'Failed to load event definitions');
        this.loading.set(false);
      }
    });

    // 2. Load Configured Use Cases from Settings
    this.settingsService.getUseCases().subscribe({
      next: (resp) => {
        this.configuredUseCases.set(resp.use_cases || []);
      },
      error: (err) => {
        console.error('Failed to load use cases for events:', err);
      }
    });
  }

  openCreateModal(): void {
    this.modalMode.set('create');
    this.selectedId.set(null);

    this.formName = '';
    this.formType = 'sunrise';
    this.formParameter = '';
    this.formUseCase = this.configuredUseCases()[0]?.name || '';
    this.formData = '{}';
    this.formHoliday = 'all_days';
    this.formNotify = 0;
    this.formNotificationMessage = '';
    this.formIsActive = 1;
    this.onUseCaseChange();

    this.isModalOpen.set(true);
  }

  openEditModal(def: EventDefinition): void {
    this.modalMode.set('edit');
    this.selectedId.set(def.id);

    this.formName = def.name;
    this.formType = def.type;
    this.formParameter = def.parameter || '';
    this.formUseCase = def.use_case;
    this.formHoliday = def.holiday || 'all_days';
    this.formNotify = def.notify || 0;
    this.formNotificationMessage = def.notification_message || '';
    this.formIsActive = def.is_active;

    if (def.data) {
      try {
        const parsed = JSON.parse(def.data);
        this.formData = JSON.stringify(parsed, null, 2);
      } catch {
        this.formData = def.data;
      }
    } else {
      this.formData = '{}';
    }

    this.isModalOpen.set(true);
  }

  closeModal(): void {
    this.isModalOpen.set(false);
  }

  onUseCaseChange(): void {
    const selectedUc = this.configuredUseCases().find((u) => u.name === this.formUseCase);
    if (selectedUc) {
      if (!this.formData || this.formData.trim() === '{}' || this.formData.trim() === '') {
        if (selectedUc.function_name === 'start_irrigation') {
          this.formData = JSON.stringify({ entity_id: 'switch.garden_irrigation_zone1', seconds: 300 }, null, 2);
        } else if (selectedUc.function_name === 'move_blind') {
          this.formData = JSON.stringify({ entity: 'cover.living_room_blind', position: 50, not_before: '19:30' }, null, 2);
        }
      }
    }
  }

  formatJsonData(): void {
    try {
      const parsed = JSON.parse(this.formData.trim() || '{}');
      this.formData = JSON.stringify(parsed, null, 2);
    } catch {
      alert('Invalid JSON in Parameters field. Please correct formatting.');
    }
  }

  saveEventDefinition(): void {
    if (!this.formName.trim()) {
      alert('Please provide a name for this event definition.');
      return;
    }
    if (!this.formType.trim()) {
      alert('Please specify an event type (e.g. sunrise, sunset).');
      return;
    }
    if (!this.formUseCase.trim()) {
      alert('Please select a use case.');
      return;
    }

    // Validate JSON in formData
    let cleanedData = '{}';
    if (this.formData.trim()) {
      try {
        const parsed = JSON.parse(this.formData.trim());
        cleanedData = JSON.stringify(parsed);
      } catch {
        alert('Invalid JSON in Parameters field.');
        return;
      }
    }

    const payload: EventDefinitionPayload = {
      name: this.formName.trim(),
      type: this.formType.trim(),
      parameter: this.formParameter.trim(),
      use_case: this.formUseCase.trim(),
      data: cleanedData,
      holiday: this.formHoliday || 'all_days',
      notify: this.formNotify,
      notification_message: this.formNotify === 1 ? this.formNotificationMessage.trim() : '',
      is_active: this.formIsActive,
    };

    if (this.modalMode() === 'create') {
      this.eventsService.createEventDefinition(payload).subscribe({
        next: (resp) => {
          this.eventDefinitions.update((list) => [resp.event_definition, ...list]);
          this.closeModal();
          this.showSuccess(`Event definition '${payload.name}' created successfully.`);
        },
        error: (err) => {
          alert(`Failed to create event definition: ${err.error?.detail || err.message}`);
        }
      });
    } else {
      const id = this.selectedId()!;
      this.eventsService.updateEventDefinition(id, payload).subscribe({
        next: (resp) => {
          this.eventDefinitions.update((list) =>
            list.map((item) => (item.id === id ? resp.event_definition : item))
          );
          this.closeModal();
          this.showSuccess(`Event definition #${id} updated successfully.`);
        },
        error: (err) => {
          alert(`Failed to update event definition: ${err.error?.detail || err.message}`);
        }
      });
    }
  }

  toggleActive(def: EventDefinition): void {
    const updatedStatus = def.is_active === 1 ? 0 : 1;
    const payload: EventDefinitionPayload = {
      name: def.name,
      type: def.type,
      parameter: def.parameter,
      use_case: def.use_case,
      data: def.data,
      holiday: def.holiday || 'all_days',
      notify: def.notify || 0,
      notification_message: def.notification_message || '',
      is_active: updatedStatus,
    };

    this.eventsService.updateEventDefinition(def.id, payload).subscribe({
      next: (resp) => {
        this.eventDefinitions.update((list) =>
          list.map((item) => (item.id === def.id ? resp.event_definition : item))
        );
        this.showSuccess(
          `Event definition #${def.id} is now ${updatedStatus === 1 ? 'Active' : 'Paused'}.`
        );
      },
      error: (err) => {
        alert(`Failed to toggle active status: ${err.error?.detail || err.message}`);
      }
    });
  }

  // Delete Modal State
  readonly isDeleteModalOpen = signal<boolean>(false);
  readonly eventToDelete = signal<EventDefinition | null>(null);
  readonly isDeleting = signal<boolean>(false);

  deleteEventDefinition(def: EventDefinition): void {
    this.eventToDelete.set(def);
    this.isDeleteModalOpen.set(true);
  }

  cancelDelete(): void {
    this.isDeleteModalOpen.set(false);
    this.eventToDelete.set(null);
  }

  confirmDelete(): void {
    const def = this.eventToDelete();
    if (!def) return;
    this.isDeleting.set(true);
    this.eventsService.deleteEventDefinition(def.id).subscribe({
      next: () => {
        this.eventDefinitions.update((list) => list.filter((item) => item.id !== def.id));
        this.isDeleting.set(false);
        this.isDeleteModalOpen.set(false);
        this.eventToDelete.set(null);
        this.showSuccess(`Event definition #${def.id} deleted successfully.`);
      },
      error: (err) => {
        this.isDeleting.set(false);
        this.isDeleteModalOpen.set(false);
        alert(`Failed to delete event definition: ${err.error?.detail || err.message}`);
      }
    });
  }

  testTrigger(def: EventDefinition): void {
    this.firingEventId.set(def.id);
    this.eventsService.simulateEvent({ type: def.type, parameter: def.parameter }).subscribe({
      next: (resp) => {
        this.firingEventId.set(null);
        const count = resp.triggered_definitions?.length || 0;
        this.showSuccess(`Simulated event '${def.type}'! Triggered ${count} active definition(s).`);
      },
      error: (err) => {
        this.firingEventId.set(null);
        alert(`Failed to simulate event: ${err.error?.detail || err.message}`);
      }
    });
  }

  isUseCaseConfigured(useCaseName: string): boolean {
    return this.configuredUseCases().some((uc) => uc.name === useCaseName);
  }

  private showSuccess(msg: string): void {
    this.successMessage.set(msg);
    setTimeout(() => this.successMessage.set(null), 4000);
  }
}
