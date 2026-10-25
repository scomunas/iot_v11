import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { BlindsComponent, BLINDS_SCHEDULE_NAME } from './blinds.component';
import { SchedulesService, SchedulesResponse } from '../../services/schedules.service';
import { SettingsService, DevicesResponse, UseCasesResponse } from '../../services/settings.service';
import { EventsService, EventDefinitionsResponse } from '../../services/events.service';

describe('BlindsComponent', () => {
  let component: BlindsComponent;
  let mockSchedulesService: any;
  let mockSettingsService: any;
  let mockEventsService: any;

  const mockSchedulesResponse: SchedulesResponse = {
    schedules: [
      {
        id: 1,
        name: 'Auto - Blinds - Living Room Blind',
        type: 'recurrent',
        trigger_spec: '0 8 * * *',
        use_case: 'move_blind',
        is_active: 1,
        data: JSON.stringify({ entity: 'cover.living_room_blind', position: 100 }),
        created_at: '2026-10-24T00:00:00Z',
      },
      {
        id: 2,
        name: 'Daily Backup Task',
        type: 'recurrent',
        trigger_spec: '0 2 * * *',
        use_case: 'test_create_file',
        is_active: 1,
        data: '{}',
        created_at: '2026-10-24T00:00:00Z',
      },
      {
        id: 3,
        name: 'Auto - Blinds - Bedroom Blind',
        type: 'recurrent',
        trigger_spec: '0 21 * * *',
        use_case: 'move_blind',
        is_active: 0,
        data: JSON.stringify({ entity: 'cover.bedroom_blind', position: 0 }),
        created_at: '2026-10-24T00:00:00Z',
      },
    ],
    in_memory_jobs: [
      {
        job_id: 'schedule_1',
        name: 'Auto - Blinds - Living Room Blind',
        next_run_time: '2026-10-25T08:00:00Z',
      },
    ],
  };

  const mockDevicesResponse: DevicesResponse = {
    devices: [
      {
        id: 10,
        name: 'Living Room Blind',
        type: 'blinds',
        entity_id: 'cover.living_room_blind',
        created_at: '2026-10-24',
      },
      {
        id: 11,
        name: 'Bedroom Blind',
        type: 'blinds',
        entity_id: 'cover.bedroom_blind',
        created_at: '2026-10-24',
      },
      {
        id: 12,
        name: 'Living Room Ceiling',
        type: 'light',
        entity_id: 'light.living_room_ceiling',
        created_at: '2026-10-24',
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
        section: 'blinds',
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
      { id: 'create_datetime_file', name: 'Create Datetime File', description: 'File' },
    ],
  };

  const mockEventDefinitionsResponse: EventDefinitionsResponse = {
    event_definitions: [
      {
        id: 101,
        name: 'Auto - Blinds - Living Room Blind',
        type: 'sunset',
        parameter: '',
        use_case: 'move_blind',
        data: JSON.stringify({ entity: 'cover.living_room_blind', position: 0, not_before: '20:00' }),
        is_active: 1,
        created_at: '2026-10-24',
      },
    ],
  };

  beforeEach(async () => {
    mockSchedulesService = {
      getSchedules: () => of(mockSchedulesResponse),
      createSchedule: () => of({ message: 'Created', schedule: {} as any }),
      updateSchedule: () => of({ message: 'Updated', schedule: {} as any }),
      deleteSchedule: () => of({ message: 'Deleted' }),
    };

    mockSettingsService = {
      getDevices: () => of(mockDevicesResponse),
      getUseCases: () => of(mockUseCasesResponse),
      getHomeAssistantEntities: () => of({ connected: true, hass_url: '', entities: [], error: null }),
      createDevice: (payload: any) => of({ message: 'Created', device: { id: 14, ...payload } }),
      updateDevice: (id: number, payload: any) => of({ message: 'Updated', device: { id, ...payload } }),
      deleteDevice: () => of({ message: 'Deleted' }),
    };

    mockEventsService = {
      getEventDefinitions: () => of(mockEventDefinitionsResponse),
      createEventDefinition: () => of({ message: 'Created', event_definition: {} as any }),
      updateEventDefinition: () => of({ message: 'Updated', event_definition: {} as any }),
      deleteEventDefinition: () => of({ message: 'Deleted' }),
    };

    await TestBed.configureTestingModule({
      imports: [BlindsComponent],
      providers: [
        provideRouter([]),
        { provide: SchedulesService, useValue: mockSchedulesService },
        { provide: SettingsService, useValue: mockSettingsService },
        { provide: EventsService, useValue: mockEventsService },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(BlindsComponent);
    component = fixture.componentInstance;
    component.ngOnInit();
  });

  it('should filter schedules to only include those starting with Auto - Blinds', () => {
    expect(component.allSchedules().length).toBe(3);
    expect(component.blindsSchedules().length).toBe(2);
    expect(component.blindsSchedules().every((s) => s.name.startsWith(BLINDS_SCHEDULE_NAME))).toBe(true);
  });

  it('should filter strictly to only blind devices from settings', () => {
    expect(component.devices().length).toBe(3);
    expect(component.blindDevices().length).toBe(2);
    expect(component.blindDevices().every((d) => d.type === 'blinds')).toBe(true);
    expect(component.blindDevices().some((d) => d.type === 'light')).toBe(false);
    expect(component.blindDevices()[0].name).toBe('Living Room Blind');
  });

  it('should format friendly device names, position label, and readable frequency', () => {
    const s1 = component.blindsSchedules()[0];
    expect(component.getDeviceFriendlyName('cover.living_room_blind')).toContain('Living Room Blind');
    expect(component.getPosition(s1)).toBe(100);
    expect(component.getPositionLabel(100)).toBe('100% (Fully Open)');
    expect(component.getPositionLabel(0)).toBe('0% (Closed)');
    expect(component.getPositionLabel(50)).toBe('50%');
    expect(component.getReadableFrequency(s1.trigger_spec)).toBe('Daily at 08:00');
  });

  it('should return proper holiday labels for events in card summary and table', () => {
    expect(component.getHolidayLabel('all_days')).toBe('All Days');
    expect(component.getHolidayLabel('holiday')).toBe('Holidays & Weekends');
    expect(component.getHolidayLabel('not_holiday')).toBe('Workdays Only');
    expect(component.getHolidayLabel(undefined)).toBe('All Days');
  });

  it('should provide summary of schedules and events for each device card', () => {
    const dev1 = component.blindDevices()[0];
    const schedules1 = component.getSchedulesForDevice(dev1);
    const events1 = component.getEventsForDevice(dev1);

    expect(schedules1.length).toBe(1);
    expect(schedules1[0].id).toBe(1);
    expect(events1.length).toBe(1);
    expect(events1[0].type).toBe('sunset');

    const dev2 = component.blindDevices()[1];
    expect(component.getSchedulesForDevice(dev2).length).toBe(1);
    expect(component.getEventsForDevice(dev2).length).toBe(0);
  });

  it('should open and close device detail view displaying the 2 tables', () => {
    expect(component.activeDevice()).toBeNull();

    const dev1 = component.blindDevices()[0];
    component.openDeviceDetail(dev1);
    expect(component.activeDevice()).toEqual(dev1);
    expect(component.activeDeviceSchedules().length).toBe(1);
    expect(component.activeDeviceEvents().length).toBe(1);

    component.closeDeviceDetail();
    expect(component.activeDevice()).toBeNull();
  });

  it('should open create modal with fixed name schema and recurrent type', () => {
    component.openCreateModal();
    expect(component.isModalOpen()).toBe(true);
    expect(component.modalMode()).toBe('create');
    expect(component.fixedScheduleName).toBe('Auto - Blinds');
    expect(component.fixedScheduleType).toBe('recurrent');
    expect(component.formUseCase).toBe('move_blind');
    expect(component.formEntityId).toBe('cover.living_room_blind');
    expect(component.formPosition).toBe(100);
  });

  it('should set position using preset buttons', () => {
    component.openCreateModal();
    component.setPosition(50);
    expect(component.formPosition).toBe(50);
    component.setPosition(0);
    expect(component.formPosition).toBe(0);
  });

  it('should create schedule with exact device name Auto - Blinds - DeviceName', () => {
    let capturedPayload: any = null;
    mockSchedulesService.createSchedule = (payload: any) => {
      capturedPayload = payload;
      return of({ message: 'Created', schedule: { id: 88, ...payload } });
    };

    const dev1 = component.blindDevices()[0];
    component.openDeviceDetail(dev1);
    component.openCreateModal(dev1);
    component.formPosition = 75;
    component.formStartTime = '07:00';
    component.formFrequencyPreset = 'daily';
    component.saveSchedule();

    expect(capturedPayload).toBeTruthy();
    expect(capturedPayload.name).toBe('Auto - Blinds - Living Room Blind');
    expect(capturedPayload.type).toBe('recurrent');
    expect(capturedPayload.trigger_spec).toBe('0 7 * * *');
    expect(capturedPayload.use_case).toBe('move_blind');
    expect(capturedPayload.is_active).toBe(1);

    const parsedData = JSON.parse(capturedPayload.data);
    expect(parsedData.entity).toBe('cover.living_room_blind');
    expect(parsedData.position).toBe(75);
  });

  it('should create event definition with exact device name Auto - Blinds - DeviceName and not_before', () => {
    let capturedEventPayload: any = null;
    mockEventsService.createEventDefinition = (payload: any) => {
      capturedEventPayload = payload;
      return of({ message: 'Created', event_definition: { id: 102, ...payload } });
    };

    const dev1 = component.blindDevices()[0];
    component.openDeviceDetail(dev1);
    component.openCreateEventModal(dev1);

    expect(component.isEventModalOpen()).toBe(true);
    expect(component.eventModalMode()).toBe('create');

    component.formEventType = 'sunset';
    component.formEventPosition = 0;
    component.formEventNotBefore = '20:30';

    component.saveEvent();

    expect(capturedEventPayload).toBeTruthy();
    expect(capturedEventPayload.name).toBe('Auto - Blinds - Living Room Blind');
    expect(capturedEventPayload.type).toBe('sunset');
    expect(capturedEventPayload.use_case).toBe('move_blind');

    const parsedData = JSON.parse(capturedEventPayload.data);
    expect(parsedData.entity).toBe('cover.living_room_blind');
    expect(parsedData.position).toBe(0);
    expect(parsedData.not_before).toBe('20:30');
  });

  it('should open edit modal populating fields from schedule', () => {
    const s1 = component.blindsSchedules()[0];
    component.openEditModal(s1);
    expect(component.isScheduleModalOpen()).toBe(true);
    expect(component.scheduleModalMode()).toBe('edit');
    expect(component.selectedScheduleId()).toBe(1);
    expect(component.formEntityId).toBe('cover.living_room_blind');
    expect(component.formPosition).toBe(100);
    expect(component.formStartTime).toBe('08:00');
  });

  it('should toggle schedule active status', () => {
    let capturedUpdate: any = null;
    mockSchedulesService.updateSchedule = (id: number, payload: any) => {
      capturedUpdate = { id, payload };
      return of({ message: 'Updated', schedule: payload });
    };

    const s1 = component.blindsSchedules()[0]; // is_active = 1
    component.toggleScheduleActive(s1);
    expect(capturedUpdate.id).toBe(1);
    expect(capturedUpdate.payload.is_active).toBe(0);
  });
});
