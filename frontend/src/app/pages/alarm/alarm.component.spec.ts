import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AlarmComponent } from './alarm.component';
import { AlarmService } from '../../services/alarm.service';
import { SettingsService } from '../../services/settings.service';
import { of } from 'rxjs';

describe('AlarmComponent', () => {
  let component: AlarmComponent;
  let fixture: ComponentFixture<AlarmComponent>;

  const mockAlarmService = {
    getAlarmConfig: vi.fn().mockReturnValue(
      of({
        status: 'success',
        config: {
          enabled: true,
          notification_message: 'Alert on {entity}! {count} events in {seconds}s',
          speak_message: 'Alarma en {entity}',
          default_trigger: 2,
          default_seconds: 60,
        },
      })
    ),
    updateAlarmConfig: vi.fn().mockReturnValue(
      of({
        status: 'success',
        message: 'Saved',
        config: {
          enabled: true,
          notification_message: 'Alert on {entity}!',
          speak_message: 'Alarma en {entity}',
          default_trigger: 3,
          default_seconds: 45,
        },
      })
    ),
    getAlarmRules: vi.fn().mockReturnValue(
      of({
        status: 'success',
        rules: [
          {
            id: 1,
            name: 'Alarm - Front Door',
            type: 'binary_sensor.front_door',
            parameter: 'on',
            use_case: 'check_alarm',
            data: JSON.stringify({
              entity: 'binary_sensor.front_door',
              trigger: 2,
              seconds: 60,
              notification: true,
              speak: true,
            }),
            holiday: 'all_days',
            notify: 0,
            speak: 0,
            is_active: 1,
            created_at: '2026-10-28T12:00:00Z',
          },
        ],
      })
    ),
    createAlarmRule: vi.fn().mockReturnValue(
      of({
        message: 'Created',
        event_definition: {
          id: 2,
          name: 'Alarm - Living Room Motion',
          type: 'binary_sensor.living_room_motion',
          parameter: '',
          use_case: 'check_alarm',
          data: JSON.stringify({
            entity: 'binary_sensor.living_room_motion',
            trigger: 3,
            seconds: 30,
            notification: true,
            speak: false,
          }),
          holiday: 'all_days',
          notify: 0,
          speak: 0,
          is_active: 1,
          created_at: '2026-10-28T12:01:00Z',
        },
      })
    ),
    updateAlarmRule: vi.fn().mockReturnValue(
      of({
        message: 'Updated',
        event_definition: {
          id: 1,
          name: 'Alarm - Front Door Updated',
          type: 'binary_sensor.front_door',
          parameter: 'open',
          use_case: 'check_alarm',
          data: JSON.stringify({
            entity: 'binary_sensor.front_door',
            trigger: 4,
            seconds: 120,
            notification: true,
            speak: true,
          }),
          holiday: 'all_days',
          notify: 0,
          speak: 0,
          is_active: 1,
          created_at: '2026-10-28T12:00:00Z',
        },
      })
    ),
    deleteAlarmRule: vi.fn().mockReturnValue(of({ message: 'Deleted' })),
    toggleRuleActive: vi.fn().mockReturnValue(
      of({
        message: 'Toggled',
        event_definition: {
          id: 1,
          name: 'Alarm - Front Door',
          type: 'binary_sensor.front_door',
          parameter: 'on',
          use_case: 'check_alarm',
          data: '{}',
          holiday: 'all_days',
          notify: 0,
          speak: 0,
          is_active: 0,
          created_at: '2026-10-28T12:00:00Z',
        },
      })
    ),
    getAlarmHistory: vi.fn().mockReturnValue(
      of({
        status: 'success',
        events: [
          { entity: 'binary_sensor.front_door', date: '2026-10-28T12:00:00Z' },
        ],
      })
    ),
    clearAlarmHistory: vi.fn().mockReturnValue(
      of({ status: 'success', message: 'Cleared' })
    ),
    testAlarm: vi.fn().mockReturnValue(
      of({
        status: 'success',
        result: {
          alarm_triggered: true,
          message: 'Alarm simulated',
        },
      })
    ),
    parseRuleData: vi.fn().mockImplementation((data: any) => {
      try {
        const p = typeof data === 'string' ? JSON.parse(data) : data;
        return {
          entity: p?.entity || '',
          trigger: p?.trigger || 2,
          seconds: p?.seconds || 60,
          notification: p?.notification !== false,
          speak: Boolean(p?.speak),
        };
      } catch {
        return { entity: '', trigger: 2, seconds: 60, notification: true, speak: false };
      }
    }),
  };

  const mockSettingsService = {
    getHomeAssistantEntities: vi.fn().mockReturnValue(
      of({
        entities: [
          { entity_id: 'binary_sensor.front_door', friendly_name: 'Front Door', domain: 'binary_sensor' },
          { entity_id: 'binary_sensor.living_room_motion', friendly_name: 'Living Room Motion', domain: 'binary_sensor' },
        ],
      })
    ),
    getDevices: vi.fn().mockReturnValue(
      of({
        devices: [
          { id: 1, name: 'Front Door Sensor', type: 'door', entity_id: 'binary_sensor.front_door' },
          { id: 2, name: 'Living Room Motion', type: 'movement', entity_id: 'binary_sensor.living_room_motion' },
          { id: 3, name: 'Garden Sprinkler', type: 'irrigation', entity_id: 'switch.garden' },
        ],
      })
    ),
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AlarmComponent],
      providers: [
        { provide: AlarmService, useValue: mockAlarmService },
        { provide: SettingsService, useValue: mockSettingsService },
        provideRouter([]),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AlarmComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should initialize and load alarm configuration, rules, and history', () => {
    expect(component).toBeTruthy();
    expect(mockAlarmService.getAlarmConfig).toHaveBeenCalled();
    expect(mockAlarmService.getAlarmRules).toHaveBeenCalled();
    expect(mockAlarmService.getAlarmHistory).toHaveBeenCalled();
    expect(component.configEnabled).toBe(true);
    expect(component.rules().length).toBe(1);
    expect(component.history().length).toBe(1);
  });

  it('should insert dynamic tags into notification and speak message models', () => {
    component.configNotificationMessage = 'Attention';
    component.insertTagIntoNotification('{entity}');
    expect(component.configNotificationMessage).toBe('Attention {entity}');

    component.configSpeakMessage = '';
    component.insertTagIntoSpeak('{count}');
    expect(component.configSpeakMessage).toBe('{count}');
  });

  it('should save general alarm configuration', () => {
    component.configEnabled = true;
    component.configNotificationMessage = 'Alert on {entity}!';
    component.configDefaultTrigger = 3;
    component.saveGeneralConfig();

    expect(mockAlarmService.updateAlarmConfig).toHaveBeenCalled();
    expect(component.savingConfig()).toBe(false);
  });

  it('should open create modal with default values and create an alarm rule', () => {
    component.openCreateRuleModal();
    expect(component.isRuleModalOpen()).toBe(true);
    expect(component.ruleModalMode()).toBe('create');

    component.formRuleName = 'Alarm - Living Room Motion';
    component.formRuleEntity = 'binary_sensor.living_room_motion';
    component.formRuleTrigger = 3;
    component.formRuleSeconds = 30;
    component.formRuleNotification = true;
    component.formRuleSpeak = false;

    component.saveRule();
    expect(mockAlarmService.createAlarmRule).toHaveBeenCalledWith({
      name: 'Alarm - Living Room Motion',
      entity: 'binary_sensor.living_room_motion',
      event_type: 'alarm',
      parameter: 'binary_sensor.living_room_motion',
      trigger: 3,
      seconds: 30,
      notification: true,
      speak: false,
      holiday: 'all_days',
      is_active: 1,
    });
    expect(component.sensorDevices().length).toBe(2);
    expect(component.isRuleModalOpen()).toBe(false);
    expect(component.rules().length).toBe(2);
  });

  it('should auto-generate standard rule name like irrigation or blinds when selecting sensor', () => {
    component.openCreateRuleModal();
    component.formRuleEntity = 'binary_sensor.living_room_motion';
    component.onEntitySelectChange();

    expect(component.getStandardRuleName()).toBe('Auto - Alarm - Living Room Motion');
    expect(component.getSelectedSensorDisplayName()).toBe('Living Room Motion');

    component.saveRule();
    expect(mockAlarmService.createAlarmRule).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Auto - Alarm - Living Room Motion',
        entity: 'binary_sensor.living_room_motion',
      })
    );
  });

  it('should toggle rule active state', () => {
    const rule = component.rules()[0];
    component.toggleRule(rule);
    expect(mockAlarmService.toggleRuleActive).toHaveBeenCalledWith(rule);
  });

  it('should clear in-memory history', () => {
    component.clearHistory();
    expect(mockAlarmService.clearAlarmHistory).toHaveBeenCalled();
    expect(component.history().length).toBe(0);
  });

  it('should toggle alarm master activation state', () => {
    const event = { target: { checked: false } } as unknown as Event;
    component.onToggleAlarm(event);
    expect(mockAlarmService.updateAlarmConfig).toHaveBeenCalledWith({ enabled: false });
  });

  it('should return device name and type correctly from configured devices', () => {
    expect(component.getDeviceName('binary_sensor.front_door')).toBe('Front Door Sensor');
    expect(component.getDeviceType('binary_sensor.front_door')).toBe('door');
    expect(component.getDeviceTypeIcon('door')).toBe('🚪');

    expect(component.getDeviceName('binary_sensor.living_room_motion')).toBe('Living Room Motion');
    expect(component.getDeviceType('binary_sensor.living_room_motion')).toBe('movement');
    expect(component.getDeviceTypeIcon('movement')).toBe('🚶');

    expect(component.getDeviceName('unknown.sensor')).toBe('unknown.sensor');
  });

  it('should support speak activation without custom speech message on rule', () => {
    component.openCreateRuleModal();
    component.formRuleSpeak = true;
    expect(component.formRuleSpeak).toBe(true);

    component.formRuleEntity = 'binary_sensor.front_door';
    component.saveRule();
    expect(mockAlarmService.createAlarmRule).toHaveBeenCalledWith(
      expect.objectContaining({
        entity: 'binary_sensor.front_door',
        speak: true,
      })
    );
  });
});
