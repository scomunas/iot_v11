import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Holiday, HolidaysService } from '../../services/holidays.service';
import { ConfirmModalComponent } from '../../components/confirm-modal/confirm-modal.component';

@Component({
  selector: 'app-holidays',
  standalone: true,
  imports: [CommonModule, FormsModule, ConfirmModalComponent],
  templateUrl: './holidays.component.html',
  styleUrl: './holidays.component.scss',
})
export class HolidaysComponent implements OnInit {
  private readonly holidaysService = inject(HolidaysService);

  holidays = signal<Holiday[]>([]);
  loading = signal<boolean>(false);
  saving = signal<boolean>(false);
  deleting = signal<boolean>(false);
  syncing = signal<boolean>(false);

  searchQuery = signal<string>('');
  selectedYear = signal<string>('all');

  isAddModalOpen = signal<boolean>(false);
  isDeleteModalOpen = signal<boolean>(false);
  isSyncModalOpen = signal<boolean>(false);
  holidayToDelete = signal<Holiday | null>(null);

  syncCounty = signal<string>('ES-CT');
  syncYear = signal<number>(new Date().getFullYear());

  readonly spanishCounties = [
    { code: 'ES-CT', name: 'Catalunya / Catalonia (ES-CT)' },
    { code: 'ES-MD', name: 'Comunidad de Madrid (ES-MD)' },
    { code: 'ES-AN', name: 'Andalucía (ES-AN)' },
    { code: 'ES-AR', name: 'Aragón (ES-AR)' },
    { code: 'ES-AS', name: 'Asturias (ES-AS)' },
    { code: 'ES-CB', name: 'Cantabria (ES-CB)' },
    { code: 'ES-CL', name: 'Castilla y León (ES-CL)' },
    { code: 'ES-CM', name: 'Castilla-La Mancha (ES-CM)' },
    { code: 'ES-CN', name: 'Canarias (ES-CN)' },
    { code: 'ES-EX', name: 'Extremadura (ES-EX)' },
    { code: 'ES-GA', name: 'Galicia (ES-GA)' },
    { code: 'ES-IB', name: 'Illes Balears (ES-IB)' },
    { code: 'ES-MC', name: 'Murcia (ES-MC)' },
    { code: 'ES-NC', name: 'Navarra (ES-NC)' },
    { code: 'ES-PV', name: 'País Vasco (ES-PV)' },
    { code: 'ES-RI', name: 'La Rioja (ES-RI)' },
    { code: 'ES-VC', name: 'Comunitat Valenciana (ES-VC)' },
    { code: 'ES-CE', name: 'Ceuta (ES-CE)' },
    { code: 'ES-ML', name: 'Melilla (ES-ML)' },
    { code: 'ALL', name: 'All Counties (National & All Regional)' },
  ];

  newDate = signal<string>('');
  newName = signal<string>('');
  formError = signal<string | null>(null);

  successMessage = signal<string | null>(null);
  errorMessage = signal<string | null>(null);

  // Available distinct years for tab filtering
  availableYears = computed(() => {
    const years = new Set<string>();
    const currentYear = new Date().getFullYear().toString();
    years.add(currentYear);
    for (const h of this.holidays()) {
      if (h.date && h.date.length >= 4) {
        years.add(h.date.substring(0, 4));
      }
    }
    return Array.from(years).sort();
  });

  // Filtered and sorted holidays
  filteredHolidays = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const yr = this.selectedYear();

    return this.holidays()
      .filter((h) => {
        const matchesYear = yr === 'all' || (h.date && h.date.startsWith(yr));
        const matchesQuery =
          !q ||
          h.date.toLowerCase().includes(q) ||
          (h.name && h.name.toLowerCase().includes(q)) ||
          this.getDayName(h.date).toLowerCase().includes(q);
        return matchesYear && matchesQuery;
      })
      .sort((a, b) => a.date.localeCompare(b.date));
  });

  // Stats
  upcomingCount = computed(() => {
    const today = this.getTodayIso();
    return this.holidays().filter((h) => h.date >= today).length;
  });

  ngOnInit(): void {
    this.loadHolidays();
  }

  loadHolidays(): void {
    this.loading.set(true);
    this.clearAlerts();
    this.holidaysService.getHolidays().subscribe({
      next: (res) => {
        this.holidays.set(res.holidays || []);
        this.loading.set(false);
      },
      error: (err) => {
        this.errorMessage.set(err?.error?.detail || 'Failed to load holidays');
        this.loading.set(false);
      },
    });
  }

  openSyncModal(): void {
    this.syncCounty.set('ES-CT');
    this.syncYear.set(new Date().getFullYear());
    this.isSyncModalOpen.set(true);
  }

  confirmSync(): void {
    this.isSyncModalOpen.set(false);
    this.syncYearHolidays();
  }

  syncYearHolidays(county?: string, year?: number): void {
    const selectedCounty = county !== undefined ? county : this.syncCounty();
    const selectedYear = year !== undefined ? year : this.syncYear();

    this.syncing.set(true);
    this.clearAlerts();
    this.holidaysService.syncYearHolidays({ county: selectedCounty, year: selectedYear }).subscribe({
      next: (res) => {
        this.holidays.set(res.holidays || []);
        this.setSuccess(res.message || 'Public holidays synced successfully.');
        this.syncing.set(false);
      },
      error: (err) => {
        this.errorMessage.set(err?.error?.detail || err?.message || 'Failed to sync year holidays');
        this.syncing.set(false);
      },
    });
  }

  openAddModal(): void {
    this.newDate.set(this.getTodayIso());
    this.newName.set('');
    this.formError.set(null);
    this.isAddModalOpen.set(true);
  }

  setQuickDate(offsetDays: number): void {
    const d = new Date();
    d.setDate(d.getDate() + offsetDays);
    const dateStr = this.formatDateIso(d);
    this.newDate.set(dateStr);
    if (!this.newName().trim()) {
      this.newName.set(offsetDays === 0 ? 'Holiday (Today)' : offsetDays === 1 ? 'Holiday (Tomorrow)' : '');
    }
  }

  saveHoliday(): void {
    const dateStr = this.newDate().trim();
    if (!dateStr) {
      this.formError.set('Date is required.');
      return;
    }

    if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
      this.formError.set('Invalid date format. Use YYYY-MM-DD.');
      return;
    }

    this.saving.set(true);
    this.formError.set(null);

    this.holidaysService
      .createHoliday({
        date: dateStr,
        name: this.newName().trim() || undefined,
      })
      .subscribe({
        next: (res) => {
          this.saving.set(false);
          this.isAddModalOpen.set(false);
          this.setSuccess(`Holiday for ${dateStr} added successfully.`);
          this.loadHolidays();
        },
        error: (err) => {
          this.saving.set(false);
          this.formError.set(err?.error?.detail || 'Error creating holiday.');
        },
      });
  }

  openDeleteModal(h: Holiday): void {
    this.holidayToDelete.set(h);
    this.isDeleteModalOpen.set(true);
  }

  confirmDelete(): void {
    const h = this.holidayToDelete();
    if (!h) return;

    this.deleting.set(true);
    this.holidaysService.deleteHoliday(h.id).subscribe({
      next: () => {
        this.deleting.set(false);
        this.isDeleteModalOpen.set(false);
        this.holidayToDelete.set(null);
        this.setSuccess(`Holiday for ${h.date} removed successfully.`);
        this.holidays.update((list) => list.filter((item) => item.id !== h.id));
      },
      error: (err) => {
        this.deleting.set(false);
        this.errorMessage.set(err?.error?.detail || 'Error deleting holiday.');
        this.isDeleteModalOpen.set(false);
      },
    });
  }

  closeModals(): void {
    this.isAddModalOpen.set(false);
    this.isDeleteModalOpen.set(false);
    this.isSyncModalOpen.set(false);
    this.holidayToDelete.set(null);
    this.formError.set(null);
  }

  isToday(dateStr: string): boolean {
    return dateStr === this.getTodayIso();
  }

  isUpcoming(dateStr: string): boolean {
    return dateStr > this.getTodayIso();
  }

  isPast(dateStr: string): boolean {
    return dateStr < this.getTodayIso();
  }

  getDayName(dateStr: string): string {
    if (!dateStr || dateStr.length < 10) return '';
    try {
      const parts = dateStr.split('-');
      const d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
      return d.toLocaleDateString('en-US', { weekday: 'long' });
    } catch {
      return '';
    }
  }

  formatDateDisplay(dateStr: string): string {
    if (!dateStr || dateStr.length < 10) return dateStr;
    try {
      const parts = dateStr.split('-');
      const d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
      return d.toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch {
      return dateStr;
    }
  }

  private getTodayIso(): string {
    return this.formatDateIso(new Date());
  }

  private formatDateIso(d: Date): string {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private setSuccess(msg: string): void {
    this.successMessage.set(msg);
    setTimeout(() => {
      if (this.successMessage() === msg) {
        this.successMessage.set(null);
      }
    }, 4000);
  }

  private clearAlerts(): void {
    this.successMessage.set(null);
    this.errorMessage.set(null);
  }
}
