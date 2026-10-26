import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ConfirmModalComponent } from '../../components/confirm-modal/confirm-modal.component';
import { LogEntry, LogsService } from '../../services/logs.service';

@Component({
  selector: 'app-logs',
  standalone: true,
  imports: [CommonModule, FormsModule, ConfirmModalComponent],
  templateUrl: './logs.component.html',
  styleUrl: './logs.component.scss'
})
export class LogsComponent implements OnInit, OnDestroy {
  private readonly logsService = inject(LogsService);

  readonly logs = signal<LogEntry[]>([]);
  readonly totalRecords = signal<number>(0);
  readonly currentPage = signal<number>(1);
  readonly pageSize = signal<number>(25);
  readonly totalPages = signal<number>(1);
  readonly selectedLevel = signal<string>('ALL');
  readonly searchQuery = signal<string>('');
  readonly loading = signal<boolean>(false);
  readonly autoRefresh = signal<boolean>(false);

  readonly pageSizeOptions = [10, 25, 50, 100, 200];
  readonly levelOptions = ['ALL', 'INFO', 'WARNING', 'ERROR'];

  private refreshTimer: any = null;

  readonly displayedRange = computed(() => {
    const total = this.totalRecords();
    if (total === 0) return '0 registers';
    const page = this.currentPage();
    const size = this.pageSize();
    const start = (page - 1) * size + 1;
    const end = Math.min(page * size, total);
    return `${start}–${end} of ${total} registers`;
  });

  readonly visiblePages = computed(() => {
    const current = this.currentPage();
    const total = this.totalPages();
    const pages: number[] = [];
    const maxVisible = 5;

    let start = Math.max(1, current - Math.floor(maxVisible / 2));
    let end = Math.min(total, start + maxVisible - 1);

    if (end - start + 1 < maxVisible) {
      start = Math.max(1, end - maxVisible + 1);
    }

    for (let p = start; p <= end; p++) {
      pages.push(p);
    }
    return pages;
  });

  ngOnInit(): void {
    this.loadLogs();
  }

  ngOnDestroy(): void {
    this.stopAutoRefresh();
  }

  loadLogs(page?: number): void {
    if (page !== undefined) {
      this.currentPage.set(page);
    }

    this.loading.set(true);
    const targetPage = this.currentPage();
    const size = this.pageSize();
    const level = this.selectedLevel();
    const search = this.searchQuery();

    this.logsService.getLogs(targetPage, size, level, search).subscribe({
      next: (resp) => {
        this.logs.set(resp.logs);
        this.totalRecords.set(resp.total);
        this.currentPage.set(resp.page);
        this.totalPages.set(resp.total_pages);
        this.loading.set(false);
      },
      error: (err) => {
        console.error('Failed to load logs:', err);
        this.loading.set(false);
      }
    });
  }

  onPageSizeChange(newSize: number): void {
    this.pageSize.set(Number(newSize));
    this.currentPage.set(1);
    this.loadLogs(1);
  }

  onLevelChange(level: string): void {
    this.selectedLevel.set(level);
    this.currentPage.set(1);
    this.loadLogs(1);
  }

  onSearchInput(query: string): void {
    this.searchQuery.set(query);
    this.currentPage.set(1);
    this.loadLogs(1);
  }

  goToPage(p: number): void {
    if (p >= 1 && p <= this.totalPages() && p !== this.currentPage()) {
      this.loadLogs(p);
    }
  }

  prevPage(): void {
    if (this.currentPage() > 1) {
      this.goToPage(this.currentPage() - 1);
    }
  }

  nextPage(): void {
    if (this.currentPage() < this.totalPages()) {
      this.goToPage(this.currentPage() + 1);
    }
  }

  toggleAutoRefresh(): void {
    const nextState = !this.autoRefresh();
    this.autoRefresh.set(nextState);

    if (nextState) {
      this.startAutoRefresh();
    } else {
      this.stopAutoRefresh();
    }
  }

  private startAutoRefresh(): void {
    this.stopAutoRefresh();
    this.refreshTimer = setInterval(() => {
      // Reload current page without showing full loading spinner to prevent flicker
      const targetPage = this.currentPage();
      const size = this.pageSize();
      const level = this.selectedLevel();
      const search = this.searchQuery();

      this.logsService.getLogs(targetPage, size, level, search).subscribe({
        next: (resp) => {
          this.logs.set(resp.logs);
          this.totalRecords.set(resp.total);
          this.currentPage.set(resp.page);
          this.totalPages.set(resp.total_pages);
        },
        error: (err) => console.error('Auto-refresh error:', err)
      });
    }, 4000);
  }

  private stopAutoRefresh(): void {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
  }

  // Confirmation Modal State
  readonly isClearModalOpen = signal<boolean>(false);
  readonly isClearing = signal<boolean>(false);

  clearLogs(): void {
    this.isClearModalOpen.set(true);
  }

  cancelClearLogs(): void {
    this.isClearModalOpen.set(false);
  }

  confirmClearLogs(): void {
    this.isClearing.set(true);
    this.logsService.clearLogs().subscribe({
      next: () => {
        this.isClearing.set(false);
        this.isClearModalOpen.set(false);
        this.loadLogs(1);
      },
      error: (err) => {
        this.isClearing.set(false);
        this.isClearModalOpen.set(false);
        alert(`Failed to clear logs: ${err.message}`);
      }
    });
  }
}
