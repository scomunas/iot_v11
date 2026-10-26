import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { LogsComponent } from './logs.component';
import { LogsService, PaginatedLogsResponse } from '../../services/logs.service';

describe('LogsComponent', () => {
  let component: LogsComponent;
  let mockLogsService: any;

  const mockResponse: PaginatedLogsResponse = {
    logs: [
      {
        id: 1,
        timestamp: '2026-10-24 12:00:00',
        level: 'INFO',
        logger: 'iot_backend',
        message: 'Starting up IoT Backend...',
      },
      {
        id: 2,
        timestamp: '2026-10-24 12:00:01',
        level: 'WARNING',
        logger: 'app.scheduler',
        message: 'Battery warning: 15% threshold',
      },
      {
        id: 3,
        timestamp: '2026-10-24 12:00:02',
        level: 'ERROR',
        logger: 'app.database',
        message: 'Failed to connect to secondary replication',
      },
    ],
    total: 50,
    page: 1,
    page_size: 25,
    total_pages: 5,
  };

  beforeEach(async () => {
    mockLogsService = {
      getLogs: (page: number = 1, pageSize: number = 25, level?: string, search?: string) =>
        of({ ...mockResponse, page, page_size: pageSize }),
      clearLogs: () => of({ message: 'Cleared' }),
    };

    await TestBed.configureTestingModule({
      imports: [LogsComponent],
      providers: [
        { provide: LogsService, useValue: mockLogsService },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(LogsComponent);
    component = fixture.componentInstance;
    component.ngOnInit();
  });

  it('should initialize and load paginated logs', () => {
    expect(component.logs().length).toBe(3);
    expect(component.totalRecords()).toBe(50);
    expect(component.currentPage()).toBe(1);
    expect(component.pageSize()).toBe(25);
    expect(component.totalPages()).toBe(5);
    expect(component.displayedRange()).toBe('1–25 of 50 registers');
  });

  it('should change page size and reset to page 1', () => {
    component.onPageSizeChange(50);
    expect(component.pageSize()).toBe(50);
    expect(component.currentPage()).toBe(1);
  });

  it('should filter by level and search query', () => {
    component.onLevelChange('ERROR');
    expect(component.selectedLevel()).toBe('ERROR');

    component.onSearchInput('battery');
    expect(component.searchQuery()).toBe('battery');
  });

  it('should navigate between pages', () => {
    component.totalPages.set(3);
    component.currentPage.set(1);

    component.nextPage();
    expect(component.currentPage()).toBe(2);

    component.prevPage();
    expect(component.currentPage()).toBe(1);

    component.goToPage(3);
    expect(component.currentPage()).toBe(3);
  });
});
