import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { HeatingComponent } from './heating.component';
import {
  HeatingMap,
  HeatingMapsResponse,
  HeatingService,
  HeatingStatusResponse,
} from '../../services/heating.service';
import { SchedulesService } from '../../services/schedules.service';
import { SettingsService } from '../../services/settings.service';
import { EventsService } from '../../services/events.service';

describe('HeatingComponent', () => {
  let component: HeatingComponent;
  let mockHeatingService: any;
  let mockSchedulesService: any;
  let mockSettingsService: any;
  let mockEventsService: any;

  const mockHeatingMap: HeatingMap = {
    id: 1,
    name: 'Comfort',
    description: 'Comfort settings',
    rules: { '104': 21.0 },
    is_default: 1,
    created_at: '2026-10-25T16:00:00Z',
    updated_at: '2026-10-25T16:00:00Z',
  };

  const mockHeatingStatusResponse: HeatingStatusResponse = {
    state: 'on',
    deactivated_until: null,
    updated_at: '2026-10-25T17:00:00Z',
    active_map_id: 1,
    active_map: mockHeatingMap,
    devices: [
      {
        id: 1,
        name: 'Living Room Radiator',
        type: 'heating',
        entity_id: 'climate.living_room',
        created_at: '2026-10-25T16:00:00Z',
      },
    ],
    temperature_devices: [
      {
        id: 104,
        name: 'Temperatura Comedor',
        type: 'temperature',
        entity_id: 'sensor.temperatura_comedor_grados',
        created_at: '2026-10-25T16:00:00Z',
      },
    ],
    pending_resume_schedules: [],
  };

  const mockHeatingMapsResponse: HeatingMapsResponse = {
    maps: [mockHeatingMap],
    active_map_id: 1,
    default_map_id: 1,
  };

  beforeEach(async () => {
    mockHeatingService = {
      getHeatingState: vi.fn().mockReturnValue(of(mockHeatingStatusResponse)),
      setHeatingState: vi.fn().mockReturnValue(of({
        status: 'success',
        message: 'Heating updated',
        state: { id: 1, state: 'off', deactivated_until: null, updated_at: '2026-10-25T17:10:00Z' },
      })),
      getHeatingMaps: vi.fn().mockReturnValue(of(mockHeatingMapsResponse)),
      createHeatingMap: vi.fn().mockReturnValue(of({
        message: 'Map created',
        map: { id: 2, name: 'Eco', rules: { '104': 18.0 }, is_default: 0, created_at: '', updated_at: '' },
      })),
      updateHeatingMap: vi.fn().mockReturnValue(of({
        message: 'Map updated',
        map: { ...mockHeatingMap, name: 'Comfort Updated' },
      })),
      deleteHeatingMap: vi.fn().mockReturnValue(of({ message: 'Map deleted' })),
      activateHeatingMap: vi.fn().mockReturnValue(of({
        message: 'Map activated',
        state: { active_map_id: 1 },
        active_map: mockHeatingMap,
      })),
      setDefaultHeatingMap: vi.fn().mockReturnValue(of({
        message: 'Map set as default',
        map: { ...mockHeatingMap, is_default: 1 },
      })),
      getHeatingCalendar: vi.fn().mockReturnValue(of({
        calendar: [
          { id: 1, day_of_week: 0, start_time: '00:00', end_time: '24:00', map_id: 1, map_name: 'Comfort' },
        ],
        resolved_map: mockHeatingMap,
        current_time: '12:00',
        current_date: '2026-10-25',
        current_day_of_week: 0,
        is_today_holiday: false,
        days: [
          { id: 0, name: 'Monday', short: 'Mon' },
          { id: 1, name: 'Tuesday', short: 'Tue' },
          { id: 2, name: 'Wednesday', short: 'Wed' },
          { id: 3, name: 'Thursday', short: 'Thu' },
          { id: 4, name: 'Friday', short: 'Fri' },
          { id: 5, name: 'Saturday', short: 'Sat' },
          { id: 6, name: 'Sunday', short: 'Sun' },
          { id: 7, name: 'Holidays', short: 'Hol' },
        ],
      })),
      updateHeatingCalendarDay: vi.fn().mockReturnValue(of({
        status: 'success',
        message: 'Updated',
        calendar: [
          { id: 1, day_of_week: 0, start_time: '00:00', end_time: '08:00', map_id: 1, map_name: 'Comfort' },
          { id: 2, day_of_week: 0, start_time: '08:00', end_time: '24:00', map_id: 1, map_name: 'Comfort' },
        ],
        resolved_map: mockHeatingMap,
      })),
    };

    mockSchedulesService = {
      getSchedules: vi.fn().mockReturnValue(of({ schedules: [], in_memory_jobs: [] })),
      createSchedule: vi.fn().mockReturnValue(of({ schedule: { id: 10, name: 'Auto - Heating Map - Comfort' } })),
      updateSchedule: vi.fn().mockReturnValue(of({ schedule: { id: 10, name: 'Updated' } })),
      deleteSchedule: vi.fn().mockReturnValue(of({ message: 'Schedule deleted' })),
    };

    mockSettingsService = {
      getUseCases: vi.fn().mockReturnValue(of({ use_cases: [] })),
    };

    mockEventsService = {
      getEventDefinitions: vi.fn().mockReturnValue(of({ event_definitions: [] })),
      createEventDefinition: vi.fn().mockReturnValue(of({ event_definition: { id: 5, name: 'Auto - Heating Map Event' } })),
      updateEventDefinition: vi.fn().mockReturnValue(of({ event_definition: { id: 5 } })),
      deleteEventDefinition: vi.fn().mockReturnValue(of({ message: 'Event deleted' })),
    };

    await TestBed.configureTestingModule({
      imports: [HeatingComponent],
      providers: [
        provideRouter([]),
        { provide: HeatingService, useValue: mockHeatingService },
        { provide: SchedulesService, useValue: mockSchedulesService },
        { provide: SettingsService, useValue: mockSettingsService },
        { provide: EventsService, useValue: mockEventsService },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(HeatingComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create component and load heating state, maps, calendar, and temperature devices', () => {
    expect(component).toBeTruthy();
    expect(mockHeatingService.getHeatingState).toHaveBeenCalled();
    expect(mockHeatingService.getHeatingMaps).toHaveBeenCalled();
    expect(mockHeatingService.getHeatingCalendar).toHaveBeenCalled();
    expect(component.heatingState()).toBe('on');
    expect(component.heatingMaps().length).toBe(1);
    expect(component.heatingMaps()[0].name).toBe('Comfort');
    expect(component.temperatureDevices().length).toBe(1);
    expect(component.calendarDays().length).toBe(8);
  });

  it('should switch between Part 1 (Heating Maps) and Part 2 (Weekly Calendar) tabs', () => {
    expect(component.activeTab()).toBe('maps');
    component.activeTab.set('schedules');
    expect(component.activeTab()).toBe('schedules');
  });

  it('should open create map modal and save a new heating map', () => {
    component.openCreateMapModal();
    expect(component.isMapModalOpen()).toBe(true);
    expect(component.mapModalMode()).toBe('create');

    component.formMapName = 'Night Eco';
    component.formMapDescription = 'Night temperature settings';
    component.formDeviceRules[104] = { enabled: true, min_temperature: 18.5 };

    component.saveHeatingMap();
    expect(mockHeatingService.createHeatingMap).toHaveBeenCalledWith({
      name: 'Night Eco',
      description: 'Night temperature settings',
      rules: { '104': 18.5 },
      is_default: 0,
    });
    expect(component.isMapModalOpen()).toBe(false);
  });

  it('should activate a heating map', () => {
    component.activateMap(mockHeatingMap);
    expect(mockHeatingService.activateHeatingMap).toHaveBeenCalledWith(1);
  });

  it('should set default heating map', () => {
    component.setDefaultMap(mockHeatingMap);
    expect(mockHeatingService.setDefaultHeatingMap).toHaveBeenCalledWith(1);
  });

  it('should load heating calendar and open day parts editor modal', () => {
    const monday = component.calendarDays()[0];
    component.openEditDayModal(monday);
    expect(component.isDayModalOpen()).toBe(true);
    expect(component.editingDay()?.name).toBe('Monday');

    // Add another slot to day
    component.addSlotToDay();
    expect(component.editingDaySlots.length).toBe(2);

    // Replicate to Tuesday (id=1)
    component.editingDayCopyTargets[1] = true;

    // Save day schedule
    component.saveDaySchedule();
    expect(mockHeatingService.updateHeatingCalendarDay).toHaveBeenCalledWith(
      expect.objectContaining({
        day_of_week: 0,
        copy_to_days: [1],
      })
    );
    expect(component.isDayModalOpen()).toBe(false);
  });

  it('should toggle auto-refresh on and off and refresh every 15 seconds', () => {
    vi.useFakeTimers();
    expect(component.autoRefreshEnabled()).toBe(false);

    // Toggle ON
    const eventOn = { target: { checked: true } } as unknown as Event;
    component.toggleAutoRefresh(eventOn);
    expect(component.autoRefreshEnabled()).toBe(true);
    expect(mockHeatingService.getHeatingState).toHaveBeenCalled();

    // Advance 15 seconds
    mockHeatingService.getHeatingState.mockClear();
    vi.advanceTimersByTime(15000);
    expect(mockHeatingService.getHeatingState).toHaveBeenCalledTimes(1);

    // Advance another 15 seconds
    vi.advanceTimersByTime(15000);
    expect(mockHeatingService.getHeatingState).toHaveBeenCalledTimes(2);

    // Toggle OFF
    const eventOff = { target: { checked: false } } as unknown as Event;
    component.toggleAutoRefresh(eventOff);
    expect(component.autoRefreshEnabled()).toBe(false);

    // Verify it stops polling
    mockHeatingService.getHeatingState.mockClear();
    vi.advanceTimersByTime(15000);
    expect(mockHeatingService.getHeatingState).not.toHaveBeenCalled();

    // Clean up
    component.ngOnDestroy();
    vi.useRealTimers();
  });
});
