import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { DashboardComponent } from './dashboard.component';
import { HeatingService } from '../../services/heating.service';
import { SettingsService } from '../../services/settings.service';
import { SchedulesService } from '../../services/schedules.service';
import { EventsService } from '../../services/events.service';

describe('DashboardComponent', () => {
  let component: DashboardComponent;
  let mockHeatingService: any;
  let mockSettingsService: any;
  let mockSchedulesService: any;
  let mockEventsService: any;

  beforeEach(async () => {
    mockHeatingService = {
      getHeatingState: () => of({
        state: 'on',
        active_map: { id: 1, name: 'Comfort', rules: { '101': 21.0 } },
        temperature_devices: [
          { id: 101, name: 'Living Room Sensor', type: 'temperature', entity_id: 'sensor.living_room_temperature', current_temperature: 21.5, created_at: '' }
        ]
      }),
      getHeatingMaps: () => of({ maps: [{ id: 1, name: 'Comfort' }, { id: 2, name: 'Eco' }], active_map_id: 1, default_map_id: 1 }),
      getHeatingCalendar: () => of({ calendar: [{ id: 1, day_of_week: 1, start_time: '08:00', end_time: '22:00', map_id: 1 }] }),
      setHeatingState: (payload: any) => of({ status: 'success', state: { state: payload.action } }),
    };

    mockSettingsService = {
      getDevices: () => of({
        devices: [
          { id: 1, name: 'Living Room Blind', type: 'blinds', entity_id: 'cover.living_room_blind', created_at: '' },
          { id: 2, name: 'Garden Sprinklers', type: 'irrigation', entity_id: 'switch.garden_irrigation_zone1', created_at: '' },
        ]
      }),
      getHomeAssistantEntities: () => of({
        connected: true,
        hass_url: '',
        entities: [
          { entity_id: 'cover.living_room_blind', friendly_name: 'Living Room Blind', domain: 'cover', state: 'open', current_position: 100 },
          { entity_id: 'switch.garden_irrigation_zone1', friendly_name: 'Garden Zone 1', domain: 'switch', state: 'off' },
        ]
      }),
      triggerDeviceAction: (id: number, action: string, position?: number) => of({
        status: 'success',
        device_id: id,
        entity_id: 'test.entity',
        action,
        position,
        state: action === 'on' ? 'on' : 'off',
        message: 'Action success'
      }),
    };

    mockSchedulesService = {
      getSchedules: () => of({
        schedules: [
          { id: 1, name: 'Auto - Blinds - Morning', use_case: 'blinds', type: 'recurrent', trigger_spec: '0 8 * * *', is_active: 1, created_at: '' },
          { id: 2, name: 'Auto - Irrigation - Evening', use_case: 'irrigation', type: 'recurrent', trigger_spec: '0 20 * * *', is_active: 1, created_at: '' },
        ]
      }),
    };

    mockEventsService = {
      getEventDefinitions: () => of({
        event_definitions: [
          { id: 1, name: 'Sunset Blinds Close', use_case: 'move_blind', type: 'sunset', is_active: 1, created_at: '' },
          { id: 2, name: 'Rain Irrigation Cancel', use_case: 'start_irrigation', type: 'rain', is_active: 1, created_at: '' },
        ]
      }),
    };

    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [
        provideRouter([]),
        { provide: HeatingService, useValue: mockHeatingService },
        { provide: SettingsService, useValue: mockSettingsService },
        { provide: SchedulesService, useValue: mockSchedulesService },
        { provide: EventsService, useValue: mockEventsService },
      ]
    }).compileComponents();

    const fixture = TestBed.createComponent(DashboardComponent);
    component = fixture.componentInstance;
    component.ngOnInit();
  });

  it('should initialize and load all section cards data', () => {
    expect(component.heatingState()).toBe('on');
    expect(component.activeMapName()).toBe('Comfort');
    expect(component.temperatureDevices().length).toBe(1);
    expect(component.blindDevices().length).toBe(1);
    expect(component.irrigationDevices().length).toBe(1);
    expect(component.blindsSchedulesCount()).toBe(1);
    expect(component.irrigationSchedulesCount()).toBe(1);
  });

  it('should toggle heating master power', () => {
    const mockEventOff = { target: { checked: false } } as unknown as Event;
    component.toggleHeatingMaster(mockEventOff);
    expect(component.heatingState()).toBe('off');
  });

  it('should get blind position and handle slider actions', () => {
    const blind = component.blindDevices()[0];
    expect(component.getDevicePosition(blind)).toBe(100);

    // Mock live input
    const inputEvent = { target: { value: '40' } } as unknown as Event;
    component.onBlindSliderInput(blind, inputEvent);
    expect(component.getDevicePosition(blind)).toBe(40);

    // Mock commit change
    const changeEvent = { target: { value: '60' } } as unknown as Event;
    component.onBlindSliderChange(blind, changeEvent);
    expect(component.getDevicePosition(blind)).toBe(60);
  });

  it('should evaluate irrigation device state and toggle power', () => {
    const irrig = component.irrigationDevices()[0];
    expect(component.isDeviceOn(irrig)).toBe(false);

    const toggleEventOn = { target: { checked: true } } as unknown as Event;
    component.toggleIrrigationDevice(irrig, toggleEventOn);
    expect(component.isDeviceOn(irrig)).toBe(true);
  });

  it('should properly format temperature values and position labels', () => {
    expect(component.formatTemp(21.48)).toBe('21.5');
    expect(component.formatTemp(null)).toBe('—');
    expect(component.getTargetTemp(101)).toBe(21.0);
    expect(component.getTargetTemp(999)).toBeNull();
    expect(component.getPositionLabel(0)).toBe('0% (Closed)');
    expect(component.getPositionLabel(100)).toBe('100% (Open)');
    expect(component.getPositionLabel(50)).toBe('50%');
  });
});
