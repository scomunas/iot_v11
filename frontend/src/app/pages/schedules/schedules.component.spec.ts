import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { SchedulesComponent } from './schedules.component';
import { SchedulesService, SchedulesResponse } from '../../services/schedules.service';
import { SettingsService } from '../../services/settings.service';

describe('SchedulesComponent Sorting', () => {
  let component: SchedulesComponent;
  let mockSchedulesService: any;
  let mockSettingsService: any;

  const mockResponse: SchedulesResponse = {
    schedules: [
      {
        id: 1,
        name: 'Zebra Sprinklers',
        type: 'recurrent',
        trigger_spec: '0 8 * * *',
        use_case: 'sprinklers',
        is_active: 1,
        created_at: '2026-10-24T00:00:00Z',
      },
      {
        id: 2,
        name: 'Alpha Climate Control',
        type: 'one-time',
        trigger_spec: '2026-10-24T12:00:00Z',
        use_case: 'climate',
        is_active: 1,
        created_at: '2026-10-24T00:00:00Z',
      },
      {
        id: 3,
        name: 'Beta Lights',
        type: 'recurrent',
        trigger_spec: '*/5 * * * *',
        use_case: 'lights',
        is_active: 1,
        created_at: '2026-10-24T00:00:00Z',
      },
    ],
    in_memory_jobs: [
      {
        job_id: 'schedule_1',
        name: 'Zebra Sprinklers',
        next_run_time: '2026-10-24T18:00:00Z',
      },
      {
        job_id: 'schedule_2',
        name: 'Alpha Climate Control',
        next_run_time: '2026-10-24T12:00:00Z',
      },
      {
        job_id: 'schedule_3',
        name: 'Beta Lights',
        next_run_time: '2026-10-24T15:00:00Z',
      },
    ],
  };

  beforeEach(async () => {
    mockSchedulesService = {
      getSchedules: () => of(mockResponse),
      createSchedule: () => of({} as any),
      updateSchedule: () => of({} as any),
      deleteSchedule: () => of({} as any),
    } as any;

    mockSettingsService = {
      getUseCases: () => of({
        use_cases: [
          { id: 1, name: 'test_create_file', function_name: 'create_datetime_file', description: 'Test', created_at: '2026-10-24' }
        ],
        available_functions: [
          { id: 'create_datetime_file', name: 'Create Datetime File', description: 'Creates timestamped text file' }
        ]
      })
    };

    await TestBed.configureTestingModule({
      imports: [SchedulesComponent],
      providers: [
        provideRouter([]),
        { provide: SchedulesService, useValue: mockSchedulesService },
        { provide: SettingsService, useValue: mockSettingsService },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(SchedulesComponent);
    component = fixture.componentInstance;
    component.ngOnInit();
  });

  it('should initialize with unsorted list', () => {
    expect(component.sortBy()).toBeNull();
    expect(component.filteredSchedules().length).toBe(3);
  });

  it('should restrict use cases strictly to configured use cases from settings', () => {
    expect(component.configuredUseCases().length).toBe(1);
    expect(component.isUseCaseConfigured('test_create_file')).toBe(true);
    expect(component.isUseCaseConfigured('unknown_use_case')).toBe(false);

    component.openCreateModal();
    expect(component.formUseCase).toBe('test_create_file');
  });

  it('should sort by name ascending and descending', () => {
    component.toggleSort('name');
    expect(component.sortBy()).toBe('name');
    expect(component.sortDirection()).toBe('asc');

    let names = component.filteredSchedules().map((s) => s.name);
    expect(names).toEqual(['Alpha Climate Control', 'Beta Lights', 'Zebra Sprinklers']);

    // Toggle to descending
    component.toggleSort('name');
    expect(component.sortDirection()).toBe('desc');

    names = component.filteredSchedules().map((s) => s.name);
    expect(names).toEqual(['Zebra Sprinklers', 'Beta Lights', 'Alpha Climate Control']);
  });

  it('should sort by next_run time ascending and descending', () => {
    component.toggleSort('next_run');
    expect(component.sortBy()).toBe('next_run');
    expect(component.sortDirection()).toBe('asc');

    // 12:00 (Alpha), 15:00 (Beta), 18:00 (Zebra)
    let ids = component.filteredSchedules().map((s) => s.id);
    expect(ids).toEqual([2, 3, 1]);

    // Toggle to descending: 18:00 (Zebra), 15:00 (Beta), 12:00 (Alpha)
    component.toggleSort('next_run');
    expect(component.sortDirection()).toBe('desc');

    ids = component.filteredSchedules().map((s) => s.id);
    expect(ids).toEqual([1, 3, 2]);
  });

  it('should format next_run in dd-MM-yyyy HH:mm format in the template', async () => {
    const fixture = TestBed.createComponent(SchedulesComponent);
    fixture.componentInstance.ngOnInit();
    fixture.detectChanges();
    await fixture.whenStable();

    const compiled = fixture.nativeElement as HTMLElement;
    const memoryBadge = compiled.querySelector('.memory-badge.active');
    expect(memoryBadge).toBeTruthy();
    const text = memoryBadge?.textContent?.trim() || '';
    // Format should match dd-MM-yyyy HH:mm (e.g. 24-10-2026 20:00 or similar local time)
    expect(text).toMatch(/\d{2}-\d{2}-\d{4} \d{2}:\d{2}/);
  });

  it('should support data field in new and edit schedule modal', () => {
    let capturedPayload: any = null;
    mockSchedulesService.createSchedule = (p: any) => {
      capturedPayload = p;
      return of({ message: 'Created', schedule: { id: 10, ...p, created_at: '' } });
    };

    component.openCreateModal();
    expect(component.formData).toBe('{}');

    component.formName = 'Morning Lawn Watering';
    component.formUseCase = 'test_create_file';
    component.formData = '{"entity_id": "switch.garden_irrigation_zone1", "seconds": 300}';
    component.saveSchedule();

    expect(capturedPayload).toBeTruthy();
    expect(capturedPayload.name).toBe('Morning Lawn Watering');
    expect(capturedPayload.data).toBe('{"entity_id": "switch.garden_irrigation_zone1", "seconds": 300}');

    // Edit modal loads data correctly
    const scheduleToEdit = {
      id: 5,
      name: 'Evening Watering',
      type: 'recurrent' as const,
      trigger_spec: '0 20 * * *',
      use_case: 'test_create_file',
      is_active: 1,
      data: '{"seconds": 600}',
      created_at: '2026-10-24',
    };
    component.openEditModal(scheduleToEdit);
    expect(component.formData).toContain('"seconds": 600');
  });
});
