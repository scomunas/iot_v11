import { ComponentFixture, TestBed } from '@angular/core/testing';
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
  let fixture: ComponentFixture<HeatingComponent>;
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
    helper_entity: 'input_boolean.calefaccion',
    helper_state: 'on',
    deactivated_until: null,
    updated_at: '2026-10-25T17:00:00Z',
    active_map_id: 1,
    active_map: mockHeatingMap,
    devices: [],
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
      getHeatingHistory: vi.fn().mockImplementation(() => {
        const now = Date.now();
        const iso = (minsAgo: number) => new Date(now - minsAgo * 60000).toISOString();
        return of({
          hours: 48,
          temperature_samples: [
            { id: 1, recorded_at: iso(120), kind: 'temperature', entity_id: 'sensor.a', name: 'Living', temperature: 20.5, state: null },
            { id: 2, recorded_at: iso(60), kind: 'temperature', entity_id: 'sensor.a', name: 'Living', temperature: 21.5, state: null },
            { id: 3, recorded_at: iso(120), kind: 'temperature', entity_id: 'sensor.b', name: 'Bedroom', temperature: 18.0, state: null },
            { id: 4, recorded_at: iso(60), kind: 'temperature', entity_id: 'sensor.b', name: 'Bedroom', temperature: 19.0, state: null },
          ],
          actuator_samples: [
            { id: 5, recorded_at: iso(120), kind: 'actuator', entity_id: 'switch.boiler', name: 'switch.boiler', temperature: null, state: 'on' },
            { id: 6, recorded_at: iso(120), kind: 'actuator', entity_id: 'climate.rad', name: 'climate.rad', temperature: null, state: 'off' },
            { id: 7, recorded_at: iso(60), kind: 'actuator', entity_id: 'switch.boiler', name: 'switch.boiler', temperature: null, state: 'on' },
            { id: 8, recorded_at: iso(60), kind: 'actuator', entity_id: 'climate.rad', name: 'climate.rad', temperature: null, state: 'on' },
          ],
          actuators: [
            { entity_id: 'switch.boiler', name: 'Boiler', raw_state: 'on', state: 'on' },
            { entity_id: 'climate.rad', name: 'Radiator', raw_state: 'off', state: 'off' },
          ],
        });
      }),
      getHeatingState: vi.fn().mockReturnValue(of(mockHeatingStatusResponse)),
      getHeatingSettings: vi.fn().mockReturnValue(of({
        heating_helper_entity: 'input_boolean.calefaccion',
        heating_interval_minutes: 5,
      })),
      updateHeatingSettings: vi.fn().mockReturnValue(of({
        status: 'success',
        message: 'Updated',
        settings: {
          heating_helper_entity: 'input_boolean.calefaccion',
          heating_interval_minutes: 5,
        },
      })),
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

    fixture = TestBed.createComponent(HeatingComponent);
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

  it('should load 48h history and build one colored line per sensor and stacked actuator bars', () => {
    expect(mockHeatingService.getHeatingHistory).toHaveBeenCalledWith(48);
    const chart = component.historyChart();
    expect(chart).toBeTruthy();
    expect(chart!.lines.length).toBe(2);
    const colors = chart!.lines.map((l) => l.color);
    expect(new Set(colors).size).toBe(2);
    expect(chart!.lines.map((l) => l.name).sort()).toEqual(['Bedroom', 'Living']);
    expect(chart!.hasActuators).toBe(true);
    // Boiler on in 2 buckets (2h ago & 1h ago), radiator on in 1 bucket (1h ago)
    expect(chart!.bars.length).toBe(3);
    expect(chart!.rightTicks.length).toBe(3); // 0..2 actuators
    const colorsUsed = new Set(chart!.bars.map((b) => b.color));
    expect(colorsUsed.size).toBe(2);
  });

  it('should expose current heater actuator states', () => {
    const acts = component.heaterActuators();
    expect(acts.length).toBe(2);
    expect(acts.find((a) => a.entity_id === 'switch.boiler')?.state).toBe('on');
    expect(acts.find((a) => a.entity_id === 'climate.rad')?.state).toBe('off');
    expect(component.getActuatorColor('switch.boiler')).not.toBe(component.getActuatorColor('climate.rad'));
  });

  it('should render cards in order: 1) history chart, 2) heater actuators, 3) temperature sensors, 4) weekly schedule', () => {
    component.activeTab.set('schedules');
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const cards = el.querySelectorAll('.calendar-section-content > .card');
    expect(cards.length).toBeGreaterThanOrEqual(4);
    expect(cards[0].classList.contains('heating-history-card')).toBe(true);
    expect(cards[1].classList.contains('heater-actuators-card')).toBe(true);
    expect(cards[2].classList.contains('temp-sensors-card')).toBe(true);
    expect(cards[3].classList.contains('weekly-schedule-card')).toBe(true);
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

  it('should reload all heating data when global refresh is called', () => {
    mockHeatingService.getHeatingState.mockClear();
    mockHeatingService.getHeatingHistory.mockClear();
    mockHeatingService.getHeatingMaps.mockClear();
    mockHeatingService.getHeatingCalendar.mockClear();

    component.loadAllData();

    expect(mockHeatingService.getHeatingState).toHaveBeenCalled();
    expect(mockHeatingService.getHeatingHistory).toHaveBeenCalledWith(48);
    expect(mockHeatingService.getHeatingMaps).toHaveBeenCalled();
    expect(mockHeatingService.getHeatingCalendar).toHaveBeenCalled();
  });
});
