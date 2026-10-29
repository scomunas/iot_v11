import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { vi } from 'vitest';
import { DashboardComponent } from './dashboard.component';
import { HeatingService } from '../../services/heating.service';
import { SettingsService } from '../../services/settings.service';
import { SchedulesService } from '../../services/schedules.service';
import { EventsService } from '../../services/events.service';
import { AlarmService } from '../../services/alarm.service';

describe('DashboardComponent', () => {
  let component: DashboardComponent;
  let mockHeatingService: any;
  let mockSettingsService: any;
  let mockSchedulesService: any;
  let mockEventsService: any;
  let mockAlarmService: any;

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
          { id: 3, name: 'Front Door PIR', type: 'door', entity_id: 'binary_sensor.front_door', created_at: '' },
        ]
      }),
      getHomeAssistantEntities: () => of({
        connected: true,
        hass_url: '',
        entities: [
          { entity_id: 'cover.living_room_blind', friendly_name: 'Living Room Blind', domain: 'cover', state: 'open', current_position: 100 },
          { entity_id: 'switch.garden_irrigation_zone1', friendly_name: 'Garden Zone 1', domain: 'switch', state: 'off' },
          { entity_id: 'binary_sensor.front_door', friendly_name: 'Front Door PIR', domain: 'binary_sensor', state: 'off' },
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
      getSchedules: vi.fn().mockReturnValue(of({
        schedules: [
          { id: 1, name: 'Auto - Blinds - Morning', use_case: 'blinds', type: 'recurrent', trigger_spec: '0 8 * * *', is_active: 1, created_at: '' },
          { id: 2, name: 'Auto - Irrigation - Evening', use_case: 'irrigation', type: 'recurrent', trigger_spec: '0 20 * * *', is_active: 1, created_at: '' },
          { id: 3, name: 'Fire Alarm - Front Door PIR (deferred)', use_case: 'fire_alarm', type: 'one-time', trigger_spec: '2026-10-29T12:01:00Z', is_active: 1, created_at: '' },
        ]
      })),
    };

    mockEventsService = {
      getEventDefinitions: () => of({
        event_definitions: [
          { id: 1, name: 'Sunset Blinds Close', use_case: 'move_blind', type: 'sunset', is_active: 1, created_at: '' },
          { id: 2, name: 'Rain Irrigation Cancel', use_case: 'start_irrigation', type: 'rain', is_active: 1, created_at: '' },
        ]
      }),
    };

    mockAlarmService = {
      getAlarmConfig: () => of({
        status: 'success',
        config: {
          enabled: true,
          default_trigger: 2,
          default_seconds: 60,
          delay_seconds: 30,
          notification_message: 'Alert: {entity}',
          speak_message: 'Alarm {entity}',
        }
      }),
      updateAlarmConfig: vi.fn().mockImplementation((payload: any) => of({
        status: 'success',
        message: 'Updated',
        config: {
          enabled: payload.enabled,
          default_trigger: 2,
          default_seconds: 60,
        }
      })),
      getAlarmHistory: () => of({
        status: 'success',
        events: [
          { entity: 'binary_sensor.front_door', date: '2026-10-29T12:00:00Z' }
        ]
      }),
      getAlarmRules: () => of({
        status: 'success',
        rules: [
          { id: 1, name: 'Auto - Alarm - Front Door PIR', is_active: 1, data: JSON.stringify({ entity: 'binary_sensor.front_door', trigger: 2, seconds: 60, notification: true, speak: false }) }
        ]
      }),
      parseRuleData: (data: any) => ({
        entity: 'binary_sensor.front_door',
        trigger: 2,
        seconds: 60,
        notification: true,
        speak: false,
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
        { provide: AlarmService, useValue: mockAlarmService },
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
    expect(component.alarmEnabled()).toBe(true);
    expect(component.alarmEvents().length).toBe(1);
    expect(component.alarmRulesCount()).toBe(1);
    expect(component.scheduledAlarmsToFire().length).toBe(1);
    expect(component.scheduledAlarmsToFire()[0].name).toContain('Fire Alarm');
  });

  it('should toggle alarm master state', () => {
    const mockEventOff = { target: { checked: false } } as unknown as Event;
    component.toggleAlarmMaster(mockEventOff);
    expect(mockAlarmService.updateAlarmConfig).toHaveBeenCalledWith({ enabled: false });
    expect(component.alarmEnabled()).toBe(false);
  });

  it('should properly resolve alarm device names and types', () => {
    expect(component.getAlarmDeviceName('binary_sensor.front_door')).toBe('Front Door PIR');
    expect(component.getAlarmDeviceType('binary_sensor.front_door')).toBe('door');
    expect(component.getAlarmDeviceTypeIcon('door')).toBe('🚪');
    expect(component.getAlarmDeviceTypeIcon('movement')).toBe('🚶');
  });

  it('should parse rule data and calculate event hit counts', () => {
    expect(component.alarmRules().length).toBe(1);
    const rule = component.alarmRules()[0];
    const data = component.getRuleData(rule);
    expect(data.entity).toBe('binary_sensor.front_door');
    expect(data.trigger).toBe(2);
    expect(component.getRuleEventCount('binary_sensor.front_door')).toBe(1);
    expect(component.getRuleEventCount('binary_sensor.unknown')).toBe(0);
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
