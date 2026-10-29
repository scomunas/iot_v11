import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Schedule, SchedulesService } from '../../services/schedules.service';
import { SettingsService, UseCase } from '../../services/settings.service';
import { ConfirmModalComponent } from '../../components/confirm-modal/confirm-modal.component';

@Component({
  selector: 'app-schedules',
  standalone: true,
  imports: [CommonModule, FormsModule, DatePipe, RouterLink, ConfirmModalComponent],
  templateUrl: './schedules.component.html',
  styleUrl: './schedules.component.scss'
})
export class SchedulesComponent implements OnInit {
  private readonly schedulesService = inject(SchedulesService);
  private readonly settingsService = inject(SettingsService);

  readonly schedules = signal<Schedule[]>([]);
  readonly inMemoryJobMap = signal<Map<string, string | null>>(new Map());
  readonly configuredUseCases = signal<UseCase[]>([]);
  readonly loading = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);

  // Search, filter, and sort
  readonly searchQuery = signal<string>('');
  readonly filterType = signal<'all' | 'one-time' | 'recurrent'>('all');
  readonly sortBy = signal<'name' | 'next_run' | null>(null);
  readonly sortDirection = signal<'asc' | 'desc'>('asc');

  // Modal State
  readonly isModalOpen = signal<boolean>(false);
  readonly modalMode = signal<'create' | 'edit'>('create');
  readonly selectedScheduleId = signal<number | null>(null);

  // Delete Confirm Modal State
  readonly isDeleteModalOpen = signal<boolean>(false);
  readonly scheduleToDelete = signal<Schedule | null>(null);
  readonly isDeleting = signal<boolean>(false);

  // Form Model
  formName = '';
  formType: 'one-time' | 'recurrent' = 'recurrent';
  formTriggerSpec = '*/5 * * * *';
  formUseCase = '';
  formIsActive = 1;
  formData = '{}';
  formNotify = 0;
  formNotificationMessage = '';
  formSpeak = 0;
  formSpeakMessage = '';
  formBlock = 0;

  // Helpers for triggers
  cronPreset = '*/5 * * * *';
  oneTimeDatetime = '';

  readonly filteredSchedules = computed(() => {
    const query = this.searchQuery().toLowerCase().trim();
    const typeFilter = this.filterType();
    const sortCol = this.sortBy();
    const sortDir = this.sortDirection();
    const jobMap = this.inMemoryJobMap();

    const list = this.schedules().filter((s) => {
      const matchesSearch =
        !query ||
        s.name.toLowerCase().includes(query) ||
        s.use_case.toLowerCase().includes(query) ||
        s.trigger_spec.toLowerCase().includes(query);

      const matchesType = typeFilter === 'all' || s.type === typeFilter;

      return matchesSearch && matchesType;
    });

    if (!sortCol) {
      return list;
    }

    return [...list].sort((a, b) => {
      const modifier = sortDir === 'asc' ? 1 : -1;

      if (sortCol === 'name') {
        return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }) * modifier;
      }

      if (sortCol === 'next_run') {
        const nextRunA = jobMap.get(`schedule_${a.id}`);
        const nextRunB = jobMap.get(`schedule_${b.id}`);

        if (!nextRunA && !nextRunB) return 0;
        if (!nextRunA) return 1; // Put unqueued items at end
        if (!nextRunB) return -1;

        const timeA = new Date(nextRunA).getTime();
        const timeB = new Date(nextRunB).getTime();

        return (timeA - timeB) * modifier;
      }

      return 0;
    });
  });

  toggleSort(column: 'name' | 'next_run'): void {
    if (this.sortBy() === column) {
      this.sortDirection.update((dir) => (dir === 'asc' ? 'desc' : 'asc'));
    } else {
      this.sortBy.set(column);
      this.sortDirection.set('asc');
    }
  }

  ngOnInit(): void {
    this.loadSchedules();
    this.loadUseCases();
  }

  loadUseCases(): void {
    this.settingsService.getUseCases().subscribe({
      next: (resp) => {
        this.configuredUseCases.set(resp.use_cases || []);
      },
      error: () => {
        // Silently maintain fallback use cases
      }
    });
  }

  loadSchedules(): void {
    this.loading.set(true);
    this.errorMessage.set(null);

    this.schedulesService.getSchedules().subscribe({
      next: (resp) => {
        this.schedules.set(resp.schedules);
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
  }

  openCreateModal(): void {
    this.modalMode.set('create');
    this.selectedScheduleId.set(null);
    this.formName = '';
    this.formType = 'recurrent';
    this.cronPreset = '*/5 * * * *';
    this.formTriggerSpec = '*/5 * * * *';
    
    const available = this.configuredUseCases();
    this.formUseCase = available.length > 0 ? available[0].name : '';
    this.formIsActive = 1;
    this.formData = '{}';
    this.formNotify = 0;
    this.formNotificationMessage = '';
    this.formSpeak = 0;
    this.formSpeakMessage = '';
    this.formBlock = 0;
    this.onUseCaseChange();

    // Set default one-time datetime 1 hour from now formatted for datetime-local
    const inOneHour = new Date(Date.now() + 3600000);
    this.oneTimeDatetime = this.formatDateForInput(inOneHour);

    this.isModalOpen.set(true);
  }

  openEditModal(schedule: Schedule): void {
    this.modalMode.set('edit');
    this.selectedScheduleId.set(schedule.id);
    this.formName = schedule.name;
    this.formType = schedule.type;
    this.formTriggerSpec = schedule.trigger_spec;
    this.formIsActive = schedule.is_active;
    this.formUseCase = schedule.use_case;
    this.formNotify = schedule.notify || 0;
    this.formNotificationMessage = schedule.notification_message || '';
    this.formSpeak = schedule.speak || 0;
    this.formSpeakMessage = schedule.speak_message || '';
    this.formBlock = schedule.block || 0;

    if (schedule.data) {
      try {
        const parsed = JSON.parse(schedule.data);
        this.formData = JSON.stringify(parsed, null, 2);
      } catch {
        this.formData = schedule.data;
      }
    } else {
      this.formData = '{}';
    }

    if (schedule.type === 'recurrent') {
      this.cronPreset = schedule.trigger_spec;
    } else {
      try {
        const d = new Date(schedule.trigger_spec);
        this.oneTimeDatetime = this.formatDateForInput(d);
      } catch {
        this.oneTimeDatetime = '';
      }
    }

    this.isModalOpen.set(true);
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
      const parsed = JSON.parse(this.formData);
      this.formData = JSON.stringify(parsed, null, 2);
    } catch {
      alert('Invalid JSON: please check formatting before prettifying.');
    }
  }

  isUseCaseConfigured(name: string): boolean {
    return this.configuredUseCases().some((u) => u.name === name);
  }

  closeModal(): void {
    this.isModalOpen.set(false);
  }

  onTypeChange(): void {
    if (this.formType === 'one-time') {
      if (!this.oneTimeDatetime) {
        const inOneHour = new Date(Date.now() + 3600000);
        this.oneTimeDatetime = this.formatDateForInput(inOneHour);
      }
      this.onDatetimeChange();
    } else {
      this.formTriggerSpec = this.cronPreset;
    }
  }

  onCronPresetChange(): void {
    if (this.cronPreset !== 'custom') {
      this.formTriggerSpec = this.cronPreset;
    }
  }

  onDatetimeChange(): void {
    if (this.oneTimeDatetime) {
      const dateObj = new Date(this.oneTimeDatetime);
      if (!isNaN(dateObj.getTime())) {
        const pad = (n: number) => n.toString().padStart(2, '0');
        const offsetMinutes = -dateObj.getTimezoneOffset();
        const sign = offsetMinutes >= 0 ? '+' : '-';
        const hours = pad(Math.floor(Math.abs(offsetMinutes) / 60));
        const mins = pad(Math.abs(offsetMinutes) % 60);
        const offsetStr = `${sign}${hours}:${mins}`;

        this.formTriggerSpec = `${this.oneTimeDatetime}:00${offsetStr}`;
      } else {
        this.formTriggerSpec = this.oneTimeDatetime;
      }
    }
  }

  saveSchedule(): void {
    if (!this.formName.trim()) {
      alert('Please provide a schedule name.');
      return;
    }
    if (!this.formTriggerSpec.trim()) {
      alert('Please specify the trigger datetime or cron expression.');
      return;
    }
    if (!this.formUseCase) {
      alert('Please select a use case.');
      return;
    }
    if (!this.isUseCaseConfigured(this.formUseCase)) {
      alert(`The use case "${this.formUseCase}" is not configured in Settings. Schedules are restricted to use cases configured in Settings.`);
      return;
    }

    let cleanData = this.formData.trim() || '{}';
    try {
      JSON.parse(cleanData);
    } catch {
      alert('Parameters (Data) must be valid JSON format (e.g. {"entity_id": "switch.garden_irrigation_zone1", "seconds": 300}).');
      return;
    }

    const payload = {
      name: this.formName.trim(),
      type: this.formType,
      trigger_spec: this.formTriggerSpec.trim(),
      use_case: this.formUseCase,
      is_active: this.formIsActive,
      data: cleanData,
      notify: this.formNotify,
      notification_message: this.formNotify === 1 ? this.formNotificationMessage.trim() : '',
      speak: this.formSpeak,
      speak_message: this.formSpeak === 1 ? this.formSpeakMessage.trim() : '',
      block: this.formBlock,
    };

    if (this.modalMode() === 'create') {
      this.schedulesService.createSchedule(payload).subscribe({
        next: () => {
          this.showSuccess('Schedule created successfully!');
          this.closeModal();
          this.loadSchedules();
        },
        error: (err) => {
          alert(`Error creating schedule: ${err.error?.detail || err.message}`);
        }
      });
    } else {
      const id = this.selectedScheduleId();
      if (!id) return;
      this.schedulesService.updateSchedule(id, payload).subscribe({
        next: () => {
          this.showSuccess(`Schedule #${id} updated successfully!`);
          this.closeModal();
          this.loadSchedules();
        },
        error: (err) => {
          alert(`Error updating schedule: ${err.error?.detail || err.message}`);
        }
      });
    }
  }

  toggleScheduleActive(schedule: Schedule): void {
    if (schedule.block === 1) {
      alert(`Schedule #${schedule.id} is locked/blocked and protected against changes. Unblock it first.`);
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
      notify: schedule.notify || 0,
      notification_message: schedule.notification_message || '',
      block: schedule.block || 0,
    }).subscribe({
      next: () => {
        this.showSuccess(`Schedule #${schedule.id} ${newActive ? 'activated' : 'paused'}.`);
        this.loadSchedules();
      },
      error: (err) => {
        alert(`Failed to update schedule status: ${err.error?.detail || err.message}`);
      }
    });
  }

  toggleBlock(schedule: Schedule): void {
    const newBlock = schedule.block === 1 ? 0 : 1;
    this.schedulesService.setBlockStatus(schedule.id, newBlock).subscribe({
      next: () => {
        this.showSuccess(`Schedule #${schedule.id} ${newBlock ? 'locked' : 'unlocked'}.`);
        this.loadSchedules();
      },
      error: (err) => {
        alert(`Failed to update lock status: ${err.error?.detail || err.message}`);
      }
    });
  }

  deleteSchedule(schedule: Schedule): void {
    if (schedule.block === 1) {
      alert(`Schedule #${schedule.id} is locked/blocked and protected against deletion. Unblock it first.`);
      return;
    }
    this.scheduleToDelete.set(schedule);
    this.isDeleteModalOpen.set(true);
  }

  cancelDeleteSchedule(): void {
    this.isDeleteModalOpen.set(false);
    this.scheduleToDelete.set(null);
  }

  confirmDeleteSchedule(): void {
    const s = this.scheduleToDelete();
    if (!s) return;
    this.isDeleting.set(true);
    this.schedulesService.deleteSchedule(s.id).subscribe({
      next: () => {
        this.isDeleting.set(false);
        this.isDeleteModalOpen.set(false);
        this.scheduleToDelete.set(null);
        this.showSuccess(`Schedule #${s.id} deleted.`);
        this.loadSchedules();
      },
      error: (err) => {
        this.isDeleting.set(false);
        this.errorMessage.set(`Failed to delete schedule: ${err.error?.detail || err.message}`);
      }
    });
  }

  getNextRunTime(scheduleId: number): string | null {
    return this.inMemoryJobMap().get(`schedule_${scheduleId}`) || null;
  }

  private showSuccess(msg: string): void {
    this.successMessage.set(msg);
    setTimeout(() => this.successMessage.set(null), 4000);
  }

  private formatDateForInput(d: Date): string {
    const pad = (n: number) => n.toString().padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
}
