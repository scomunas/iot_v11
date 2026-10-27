import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { IrrigationComponent, IRRIGATION_SCHEDULE_NAME } from './irrigation.component';
import { SchedulesService, SchedulesResponse } from '../../services/schedules.service';
import { SettingsService, DevicesResponse, UseCasesResponse } from '../../services/settings.service';
import { EventsService, EventDefinitionsResponse } from '../../services/events.service';

describe('IrrigationComponent', () => {
  let component: IrrigationComponent;
  let mockSchedulesService: any;
  let mockSettingsService: any;
  let mockEventsService: any;

  const mockSchedulesResponse: SchedulesResponse = {
    schedules: [
      {
        id: 1,
        name: 'Auto - Irrigation',
        type: 'recurrent',
        trigger_spec: '0 6 * * *',
        use_case: 'irrigation',
        is_active: 1,
        data: JSON.stringify({ entity_id: 'switch.garden_irrigation_zone1', seconds: 300 }),
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
        name: 'Auto - Irrigation',
        type: 'recurrent',
        trigger_spec: '0 20 */2 * *',
        use_case: 'irrigation',
        is_active: 0,
        data: JSON.stringify({ entity_id: 'switch.greenhouse_sprinklers', seconds: 600 }),
        created_at: '2026-10-24T00:00:00Z',
      },
    ],
    in_memory_jobs: [
      {
        job_id: 'schedule_1',
        name: 'Auto - Irrigation',
        next_run_time: '2026-10-25T06:00:00Z',
      },
    ],
  };

  const mockDevicesResponse: DevicesResponse = {
    devices: [
      {
        id: 10,
        name: 'Garden Sprinklers Zone 1',
        type: 'irrigation',
        entity_id: 'switch.garden_irrigation_zone1',
        created_at: '2026-10-24',
      },
      {
        id: 11,
        name: 'Greenhouse Sprinklers',
        type: 'irrigation',
        entity_id: 'switch.greenhouse_sprinklers',
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
        name: 'irrigation',
        function_name: 'start_irrigation',
        description: 'Irrigation cycle',
        section: 'irrigation',
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
      { id: 'start_irrigation', name: 'Start Irrigation', description: 'Irrigation' },
      { id: 'create_datetime_file', name: 'Create Datetime File', description: 'File' },
    ],
  };

  const mockEventDefinitionsResponse: EventDefinitionsResponse = {
    event_definitions: [
      {
        id: 101,
        name: 'Auto - Irrigation - Sunset',
        type: 'sunset',
        parameter: '+00:15',
        use_case: 'irrigation',
        data: JSON.stringify({ entity_id: 'switch.garden_irrigation_zone1', seconds: 180 }),
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
      getHomeAssistantEntities: () => of({ connected: true, hass_url: '', entities: [{ entity_id: 'switch.garden_irrigation_zone1', friendly_name: 'Garden Zone 1', domain: 'switch', state: 'off' }], error: null }),
      createDevice: (payload: any) => of({ message: 'Created', device: { id: 13, ...payload } }),
      updateDevice: (id: number, payload: any) => of({ message: 'Updated', device: { id, ...payload } }),
      deleteDevice: () => of({ message: 'Deleted' }),
      triggerDeviceAction: (id: number, action: 'on' | 'off' | 'toggle') => of({ status: 'success', device_id: id, entity_id: 'switch.garden_irrigation_zone1', action: action === 'toggle' ? 'on' : action, state: action === 'toggle' ? 'on' : action, message: `Device turned ${action}` }),
    };

    mockEventsService = {
      getEventDefinitions: () => of(mockEventDefinitionsResponse),
      createEventDefinition: () => of({ message: 'Created', event_definition: {} as any }),
      updateEventDefinition: () => of({ message: 'Updated', event_definition: {} as any }),
      deleteEventDefinition: () => of({ message: 'Deleted' }),
    };

    await TestBed.configureTestingModule({
      imports: [IrrigationComponent],
      providers: [
        provideRouter([]),
        { provide: SchedulesService, useValue: mockSchedulesService },
        { provide: SettingsService, useValue: mockSettingsService },
        { provide: EventsService, useValue: mockEventsService },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(IrrigationComponent);
    component = fixture.componentInstance;
    component.ngOnInit();
  });

  it('should filter schedules to only include those named Auto - Irrigation', () => {
    expect(component.allSchedules().length).toBe(3);
    expect(component.irrigationSchedules().length).toBe(2);
    expect(component.irrigationSchedules().every((s) => s.name === IRRIGATION_SCHEDULE_NAME)).toBe(true);
  });

  it('should filter and prioritize irrigation devices from settings', () => {
    expect(component.devices().length).toBe(3);
    expect(component.irrigationDevices().length).toBe(2);
    expect(component.irrigationDevices()[0].name).toBe('Garden Sprinklers Zone 1');
  });

  it('should format friendly device names, duration, and readable frequency', () => {
    const s1 = component.irrigationSchedules()[0];
    expect(component.getDeviceFriendlyName('switch.garden_irrigation_zone1')).toContain('Garden Sprinklers Zone 1');
    expect(component.getDurationDisplay(s1)).toBe('5 min (300s)');
    expect(component.getReadableFrequency(s1.trigger_spec)).toBe('Daily at 06:00');
  });

  it('should return proper holiday labels for events in card summary and table', () => {
    expect(component.getHolidayLabel('all_days')).toBe('All Days');
    expect(component.getHolidayLabel('holiday')).toBe('Holidays & Weekends');
    expect(component.getHolidayLabel('not_holiday')).toBe('Workdays Only');
    expect(component.getHolidayLabel(undefined)).toBe('All Days');
  });

  it('should provide summary of schedules and events for each device card', () => {
    const dev1 = component.irrigationDevices()[0];
    const schedules1 = component.getSchedulesForDevice(dev1);
    const events1 = component.getEventsForDevice(dev1);

    expect(schedules1.length).toBe(1);
    expect(schedules1[0].id).toBe(1);
    expect(events1.length).toBe(1);
    expect(events1[0].type).toBe('sunset');

    const dev2 = component.irrigationDevices()[1];
    expect(component.getSchedulesForDevice(dev2).length).toBe(1);
    expect(component.getEventsForDevice(dev2).length).toBe(0);
  });

  it('should open and close device detail view displaying the 2 tables', () => {
    expect(component.activeDevice()).toBeNull();

    const dev1 = component.irrigationDevices()[0];
    component.openDeviceDetail(dev1);
    expect(component.activeDevice()).toEqual(dev1);
    expect(component.activeDeviceSchedules().length).toBe(1);
    expect(component.activeDeviceEvents().length).toBe(1);

    component.closeDeviceDetail();
    expect(component.activeDevice()).toBeNull();
  });

  it('should create schedule with recurrency and duration locked to active device', () => {
    let capturedPayload: any = null;
    mockSchedulesService.createSchedule = (payload: any) => {
      capturedPayload = payload;
      return of({ message: 'Created', schedule: { id: 99, ...payload } });
    };

    const dev1 = component.irrigationDevices()[0];
    component.openDeviceDetail(dev1);
    component.openCreateModal(dev1);

    expect(component.isScheduleModalOpen()).toBe(true);
    expect(component.scheduleModalMode()).toBe('create');

    component.formFrequencyPreset = 'twice_daily';
    component.formStartTime = '07:00';
    component.onFrequencyChange();
    component.formDurationSeconds = 600;

    component.saveSchedule();

    expect(capturedPayload).toBeTruthy();
    expect(capturedPayload.name).toBe('Auto - Irrigation - Garden Sprinklers Zone 1');
    expect(capturedPayload.type).toBe('recurrent');
    expect(capturedPayload.use_case).toBe('irrigation');
    expect(capturedPayload.trigger_spec).toBe('0 7,19 * * *');

    const parsedData = JSON.parse(capturedPayload.data);
    expect(parsedData.entity_id).toBe(dev1.entity_id);
    expect(parsedData.seconds).toBe(600);
  });

  it('should open edit schedule modal populating fields from schedule', () => {
    const s1 = component.irrigationSchedules()[0];
    component.openEditModal(s1);
    expect(component.isScheduleModalOpen()).toBe(true);
    expect(component.scheduleModalMode()).toBe('edit');
    expect(component.selectedScheduleId()).toBe(1);
    expect(component.formEntityId).toBe('switch.garden_irrigation_zone1');
    expect(component.formDurationSeconds).toBe(300);
    expect(component.formStartTime).toBe('06:00');
  });

  it('should create event definition with name schema Auto - Irrigation - DeviceName', () => {
    let capturedEventPayload: any = null;
    mockEventsService.createEventDefinition = (payload: any) => {
      capturedEventPayload = payload;
      return of({ message: 'Created', event_definition: { id: 102, ...payload } });
    };

    const dev1 = component.irrigationDevices()[0];
    component.openDeviceDetail(dev1);
    component.openCreateEventModal(dev1);

    expect(component.isEventModalOpen()).toBe(true);
    expect(component.eventModalMode()).toBe('create');

    component.formEventType = 'sunrise';
    component.formEventParameter = '+00:30';
    component.formEventDurationSeconds = 450;

    component.saveEvent();

    expect(capturedEventPayload).toBeTruthy();
    expect(capturedEventPayload.name).toBe('Auto - Irrigation - Garden Sprinklers Zone 1');
    expect(capturedEventPayload.type).toBe('sunrise');
    expect(capturedEventPayload.parameter).toBe('+00:30');
    expect(capturedEventPayload.use_case).toBe('irrigation');

    const parsedData = JSON.parse(capturedEventPayload.data);
    expect(parsedData.entity_id).toBe(dev1.entity_id);
    expect(parsedData.seconds).toBe(450);
  });

  it('should create device and auto-select into 2 tables view', () => {
    component.openCreateDeviceModal();
    expect(component.isDeviceModalOpen()).toBe(true);

    component.formDeviceName = 'Patio Valve';
    component.formDeviceEntityId = 'switch.patio_valve';
    component.saveDevice();

    expect(component.isDeviceModalOpen()).toBe(false);
    expect(component.activeDevice()?.name).toBe('Patio Valve');
  });

  it('should toggle schedule active status', () => {
    let capturedUpdate: any = null;
    mockSchedulesService.updateSchedule = (id: number, payload: any) => {
      capturedUpdate = { id, payload };
      return of({ message: 'Updated', schedule: payload });
    };

    const s1 = component.irrigationSchedules()[0]; // is_active = 1
    component.toggleScheduleActive(s1);
    expect(capturedUpdate.id).toBe(1);
    expect(capturedUpdate.payload.is_active).toBe(0);
  });

  it('should evaluate device on/off state and manually toggle device state', () => {
    const dev = component.irrigationDevices()[0];
    expect(component.isDeviceOn(dev)).toBe(false);

    // Mock toggle event to ON
    const mockEventOn = { target: { checked: true } } as unknown as Event;
    component.toggleDeviceManual(dev, mockEventOn);

    expect(component.isDeviceOn(dev)).toBe(true);

    // Mock toggle event to OFF
    const mockEventOff = { target: { checked: false } } as unknown as Event;
    component.toggleDeviceManual(dev, mockEventOff);

    expect(component.isDeviceOn(dev)).toBe(false);
  });
});
