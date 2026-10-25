import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { EventsComponent } from './events.component';
import { EventsService, EventDefinitionsResponse } from '../../services/events.service';
import { SettingsService, UseCasesResponse } from '../../services/settings.service';

describe('EventsComponent', () => {
  let component: EventsComponent;
  let mockEventsService: any;
  let mockSettingsService: any;

  const mockDefinitionsResponse: EventDefinitionsResponse = {
    event_definitions: [
      {
        id: 1,
        name: 'Morning Blinds Up',
        type: 'sunrise',
        parameter: '07:00',
        use_case: 'move_blind',
        data: JSON.stringify({ entity: 'cover.living_room_blind', position: 100 }),
        is_active: 1,
        created_at: '2026-10-24T06:00:00Z',
      },
      {
        id: 2,
        name: 'Night Blinds Down',
        type: 'sunset',
        parameter: '20:30',
        use_case: 'move_blind',
        data: JSON.stringify({ entity: 'cover.living_room_blind', position: 0 }),
        is_active: 0,
        created_at: '2026-10-24T06:00:00Z',
      },
      {
        id: 3,
        name: 'Motion Garden Light',
        type: 'motion',
        parameter: 'garden_zone',
        use_case: 'test_create_file',
        data: '{}',
        is_active: 1,
        created_at: '2026-10-24T06:00:00Z',
      },
    ],
  };

  const mockUseCasesResponse: UseCasesResponse = {
    use_cases: [
      {
        id: 1,
        name: 'move_blind',
        function_name: 'move_blind',
        description: 'Moves blind',
        created_at: '2026-10-24',
      },
      {
        id: 2,
        name: 'test_create_file',
        function_name: 'create_datetime_file',
        description: 'Test file',
        created_at: '2026-10-24',
      },
    ],
    available_functions: [
      { id: 'move_blind', name: 'Move Blind', description: 'Moves blind' },
      { id: 'create_datetime_file', name: 'Create File', description: 'File' },
    ],
  };

  beforeEach(async () => {
    mockEventsService = {
      getEventDefinitions: () => of(mockDefinitionsResponse),
      createEventDefinition: (payload: any) =>
        of({ message: 'Created', event_definition: { id: 99, ...payload, created_at: 'now' } }),
      updateEventDefinition: (id: number, payload: any) =>
        of({ message: 'Updated', event_definition: { id, ...payload, created_at: 'now' } }),
      deleteEventDefinition: () => of({ message: 'Deleted' }),
      simulateEvent: () => of({ status: 'success', message: 'Triggered', event: {}, triggered_definitions: [{ id: 1 }] }),
    };

    mockSettingsService = {
      getUseCases: () => of(mockUseCasesResponse),
      getDevices: () => of({ devices: [] }),
    };

    await TestBed.configureTestingModule({
      imports: [EventsComponent],
      providers: [
        provideRouter([]),
        { provide: EventsService, useValue: mockEventsService },
        { provide: SettingsService, useValue: mockSettingsService },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(EventsComponent);
    component = fixture.componentInstance;
    component.ngOnInit();
  });

  it('should initialize and load event definitions and use cases', () => {
    expect(component.eventDefinitions().length).toBe(3);
    expect(component.configuredUseCases().length).toBe(2);
    expect(component.availableTypes()).toEqual(['motion', 'sunrise', 'sunset']);
  });

  it('should filter definitions by search query and type', () => {
    component.searchQuery.set('morning');
    expect(component.filteredDefinitions().length).toBe(1);
    expect(component.filteredDefinitions()[0].name).toBe('Morning Blinds Up');

    component.searchQuery.set('');
    component.filterType.set('sunset');
    expect(component.filteredDefinitions().length).toBe(1);
    expect(component.filteredDefinitions()[0].type).toBe('sunset');

    component.filterType.set('all');
    expect(component.filteredDefinitions().length).toBe(3);
  });

  it('should open create modal and populate parameters aid based on use case', () => {
    component.openCreateModal();
    expect(component.isModalOpen()).toBe(true);
    expect(component.modalMode()).toBe('create');
    expect(component.formType).toBe('sunrise');
    expect(component.formUseCase).toBe('move_blind');
    expect(component.formData).toContain('cover.living_room_blind');
    expect(component.formIsActive).toBe(1);
  });

  it('should update parameters aid when changing use case', () => {
    component.openCreateModal();
    component.formData = '{}';
    component.formUseCase = 'move_blind';
    component.onUseCaseChange();
    expect(component.formData).toContain('cover.living_room_blind');
  });

  it('should create new event definition', () => {
    let capturedPayload: any = null;
    mockEventsService.createEventDefinition = (payload: any) => {
      capturedPayload = payload;
      return of({ message: 'Created', event_definition: { id: 101, ...payload, created_at: 'now' } });
    };

    component.openCreateModal();
    component.formName = 'Custom Sunrise Rule';
    component.formType = 'sunrise';
    component.formParameter = '06:15';
    component.formUseCase = 'move_blind';
    component.formHoliday = 'holiday';
    component.formData = JSON.stringify({ entity: 'cover.bedroom_blind', position: 50 });
    component.saveEventDefinition();

    expect(capturedPayload).toBeTruthy();
    expect(capturedPayload.name).toBe('Custom Sunrise Rule');
    expect(capturedPayload.type).toBe('sunrise');
    expect(capturedPayload.parameter).toBe('06:15');
    expect(capturedPayload.use_case).toBe('move_blind');
    expect(capturedPayload.holiday).toBe('holiday');
    expect(component.isModalOpen()).toBe(false);
  });

  it('should return proper holiday labels', () => {
    expect(component.getHolidayLabel('all_days')).toBe('All Days');
    expect(component.getHolidayLabel('holiday')).toBe('Holidays & Weekends');
    expect(component.getHolidayLabel('not_holiday')).toBe('Workdays Only');
    expect(component.getHolidayLabel(undefined)).toBe('All Days');
  });

  it('should open edit modal with definition values and update it', () => {
    let capturedPayload: any = null;
    mockEventsService.updateEventDefinition = (id: number, payload: any) => {
      capturedPayload = { id, payload };
      return of({ message: 'Updated', event_definition: { id, ...payload, created_at: 'now' } });
    };

    const def = component.eventDefinitions()[0];
    component.openEditModal(def);
    expect(component.isModalOpen()).toBe(true);
    expect(component.modalMode()).toBe('edit');
    expect(component.selectedId()).toBe(1);
    expect(component.formName).toBe('Morning Blinds Up');

    component.formName = 'Updated Blinds Morning';
    component.saveEventDefinition();

    expect(capturedPayload).toBeTruthy();
    expect(capturedPayload.id).toBe(1);
    expect(capturedPayload.payload.name).toBe('Updated Blinds Morning');
    expect(component.isModalOpen()).toBe(false);
  });

  it('should toggle active status of event definition', () => {
    let capturedUpdate: any = null;
    mockEventsService.updateEventDefinition = (id: number, payload: any) => {
      capturedUpdate = { id, payload };
      return of({ message: 'Updated', event_definition: { id, ...payload, created_at: 'now' } });
    };

    const def = component.eventDefinitions()[0]; // is_active = 1
    component.toggleActive(def);

    expect(capturedUpdate).toBeTruthy();
    expect(capturedUpdate.id).toBe(1);
    expect(capturedUpdate.payload.is_active).toBe(0);
  });

  it('should test trigger an event definition', () => {
    const def = component.eventDefinitions()[0];
    component.testTrigger(def);
    expect(component.successMessage()).toContain("Simulated event 'sunrise'");
  });

  it('should support event type helper buttons', () => {
    component.openCreateModal();

    // Type preset helper
    component.setEventType('sunset');
    expect(component.formType).toBe('sunset');

    component.setEventType('sunrise');
    expect(component.formType).toBe('sunrise');
  });
});
