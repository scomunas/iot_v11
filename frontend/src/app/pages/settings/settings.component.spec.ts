import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { SettingsComponent } from './settings.component';
import {
  DevicesResponse,
  HomeAssistantEntitiesResponse,
  SettingsService,
  UseCasesResponse,
} from '../../services/settings.service';

describe('SettingsComponent', () => {
  let component: SettingsComponent;
  let mockSettingsService: any;

  const mockResponse: UseCasesResponse = {
    use_cases: [
      {
        id: 1,
        name: 'test_create_file',
        function_name: 'create_datetime_file',
        description: 'Test file generator',
        section: null,
        created_at: '2026-10-24 10:00:00',
      },
      {
        id: 2,
        name: 'start_irrigation',
        function_name: 'start_irrigation',
        description: 'Irrigation task',
        section: 'irrigation',
        created_at: '2026-10-24 10:00:00',
      },
    ],
    available_sections: ['irrigation', 'blinds', 'rain'],
    available_functions: [
      {
        id: 'create_datetime_file',
        name: 'Create Datetime File (test)',
        description: 'Creates a .txt file named with current local datetime in backend/output/',
      },
      {
        id: 'start_irrigation',
        name: 'Start Irrigation',
        description: 'Turns ON entity_id, waits for seconds, and turns OFF entity_id',
      },
      {
        id: 'move_blind',
        name: 'Move Blind',
        description: 'Moves blind/cover entity to target position (0-100%)',
      },
    ],
  };

  const mockDevicesResponse: DevicesResponse = {
    devices: [
      {
        id: 1,
        name: 'Garden Sprinkler',
        type: 'irrigation',
        entity_id: 'switch.garden_irrigation_zone1',
        created_at: '2026-10-24 10:00:00',
      },
      {
        id: 2,
        name: 'Living Room Ceiling',
        type: 'light',
        entity_id: 'light.living_room_ceiling',
        created_at: '2026-10-24 10:00:00',
      },
    ],
  };

  const mockHassResponse: HomeAssistantEntitiesResponse = {
    connected: true,
    hass_url: 'http://localhost:8123',
    entities: [
      {
        entity_id: 'light.living_room_ceiling',
        friendly_name: 'Living Room Ceiling Light',
        domain: 'light',
        state: 'off',
      },
      {
        entity_id: 'switch.garden_irrigation_zone1',
        friendly_name: 'Garden Irrigation Zone 1',
        domain: 'switch',
        state: 'off',
      },
      {
        entity_id: 'sensor.living_room_temp',
        friendly_name: 'Living Room Temp',
        domain: 'sensor',
        state: '21.5',
      },
    ],
    error: null,
  };

  beforeEach(async () => {
    mockSettingsService = {
      getUseCases: () => of(mockResponse),
      createUseCase: () => of({ message: 'Created', use_case: { id: 2, name: 'new_uc', function_name: 'create_datetime_file', created_at: '' } }),
      updateUseCase: () => of({ message: 'Updated', use_case: { id: 1, name: 'updated', function_name: 'create_datetime_file', created_at: '' } }),
      deleteUseCase: () => of({ message: 'Deleted' }),
      testUseCase: vi.fn().mockReturnValue(of({ message: 'Executed', result_file: 'backend/output/2026-10-24_11-30-00.txt' })),
      getDevices: () => of(mockDevicesResponse),
      createDevice: () => of({ message: 'Created', device: { id: 3, name: 'Hallway Light', type: 'light', entity_id: 'light.hallway', created_at: '' } }),
      updateDevice: () => of({ message: 'Updated', device: { id: 1, name: 'Garden Sprinkler Zone 1', type: 'irrigation', entity_id: 'switch.garden_irrigation_zone1', created_at: '' } }),
      deleteDevice: () => of({ message: 'Deleted' }),
      getHomeAssistantEntities: () => of(mockHassResponse),
      getTelegramStatus: vi.fn().mockReturnValue(
        of({
          configured: true,
          bot_token_configured: true,
          chat_id_configured: true,
          bot_token_masked: '1234...wxyz',
          chat_id_masked: '987...21',
          message: 'Telegram active',
        })
      ),
      sendTelegramAlert: vi.fn().mockReturnValue(
        of({
          success: true,
          message: 'Alert sent successfully to Telegram!',
        })
      ),
      getSystemSettings: vi.fn().mockReturnValue(
        of({
          settings: { heating_interval_minutes: 15 },
        })
      ),
      updateSystemSettings: vi.fn().mockReturnValue(
        of({
          message: 'Settings updated successfully',
          settings: { heating_interval_minutes: 20 },
        })
      ),
    };

    await TestBed.configureTestingModule({
      imports: [SettingsComponent],
      providers: [
        { provide: SettingsService, useValue: mockSettingsService },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(SettingsComponent);
    component = fixture.componentInstance;
    component.ngOnInit();
  });

  it('should initialize and load use cases and functions', () => {
    expect(component.useCases().length).toBe(2);
    expect(component.availableFunctions().length).toBe(3);
    expect(component.availableFunctions().some((f) => f.id === 'move_blind')).toBe(true);
    expect(component.useCases()[0].name).toBe('test_create_file');
    expect(component.useCases()[1].section).toBe('irrigation');
  });

  it('should initialize and load devices and Home Assistant entities', () => {
    expect(component.devices().length).toBe(2);
    expect(component.hassEntities().length).toBe(3);
    expect(component.hassConnected()).toBe(true);
    expect(component.devices()[0].type).toBe('irrigation');
  });

  it('should open test modal with parameters, run test execution and display result', () => {
    component.openTestModal(mockResponse.use_cases[1]); // start_irrigation
    expect(component.isTestModalOpen()).toBe(true);
    expect(component.testingUseCase()?.name).toBe('start_irrigation');
    expect(component.testParamsJson()).toContain('switch.garden_irrigation_zone1');

    // Run execution with parameters
    component.executeTest();
    expect(component.isTestModalOpen()).toBe(false);
    expect(component.testResult()).toBeTruthy();
    expect(mockSettingsService.testUseCase).toHaveBeenCalledWith(2, expect.objectContaining({ entity_id: 'switch.garden_irrigation_zone1' }));

    component.clearTestResult();
    expect(component.testResult()).toBeNull();
  });

  it('should open create use case modal with defaults and section empty', () => {
    component.openCreateModal();
    expect(component.isModalOpen()).toBe(true);
    expect(component.modalMode()).toBe('create');
    expect(component.formFunctionName).toBe('create_datetime_file');
    expect(component.formSection).toBe('');
  });

  it('should open edit use case modal with populated section', () => {
    component.openEditModal(mockResponse.use_cases[1]);
    expect(component.isModalOpen()).toBe(true);
    expect(component.modalMode()).toBe('edit');
    expect(component.formName).toBe('start_irrigation');
    expect(component.formSection).toBe('irrigation');
  });

  it('should open create device modal with defaults and filter entities', () => {
    component.openCreateDeviceModal();
    expect(component.isDeviceModalOpen()).toBe(true);
    expect(component.deviceModalMode()).toBe('create');
    expect(component.formDeviceType).toBe('light');

    // Filter entities
    component.entityFilter.set('irrigation');
    expect(component.filteredEntities().length).toBe(1);
    expect(component.filteredEntities()[0].entity_id).toBe('switch.garden_irrigation_zone1');
  });

  it('should open edit device modal with selected device data', () => {
    component.openEditDeviceModal(mockDevicesResponse.devices[0]);
    expect(component.isDeviceModalOpen()).toBe(true);
    expect(component.deviceModalMode()).toBe('edit');
    expect(component.formDeviceName).toBe('Garden Sprinkler');
    expect(component.formDeviceType).toBe('irrigation');
    expect(component.formDeviceEntityId).toBe('switch.garden_irrigation_zone1');
  });

  it('should support blinds, rain, and heating device types in deviceTypes and badge info', () => {
    const blindsInfo = component.getDeviceTypeInfo('blinds');
    expect(blindsInfo).toBeTruthy();
    expect(blindsInfo.label).toBe('Blinds');
    expect(component.deviceTypes.some((t) => t.id === 'blinds')).toBe(true);

    const rainInfo = component.getDeviceTypeInfo('rain');
    expect(rainInfo).toBeTruthy();
    expect(rainInfo.label).toBe('Rain');
    expect(rainInfo.icon).toBe('🌧️');
    expect(component.deviceTypes.some((t) => t.id === 'rain')).toBe(true);

    const heatingInfo = component.getDeviceTypeInfo('heating');
    expect(heatingInfo).toBeTruthy();
    expect(heatingInfo.label).toBe('Heating');
    expect(heatingInfo.icon).toBe('🔥');
    expect(component.deviceTypes.some((t) => t.id === 'heating')).toBe(true);
  });
});
