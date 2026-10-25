import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { HolidaysComponent } from './holidays.component';
import { HolidaysService, HolidaysResponse } from '../../services/holidays.service';

describe('HolidaysComponent', () => {
  let component: HolidaysComponent;
  let mockHolidaysService: any;

  const mockHolidays: HolidaysResponse = {
    holidays: [
      { id: 1, date: '2026-01-01', name: "New Year's Day", created_at: '2026-01-01T00:00:00Z' },
      { id: 2, date: '2026-12-25', name: 'Christmas Day', created_at: '2026-01-01T00:00:00Z' },
      { id: 3, date: '2025-05-01', name: 'Labour Day', created_at: '2025-01-01T00:00:00Z' },
    ],
  };

  beforeEach(async () => {
    mockHolidaysService = {
      getHolidays: vi.fn().mockReturnValue(of(mockHolidays)),
      createHoliday: vi.fn().mockReturnValue(
        of({ message: 'Created', holiday: { id: 4, date: '2026-08-15', name: 'Summer Fest', created_at: '2026-08-01T00:00:00Z' } })
      ),
      deleteHoliday: vi.fn().mockReturnValue(of({ message: 'Deleted', id: 1 })),
      syncYearHolidays: vi.fn().mockReturnValue(
        of({ status: 'success', message: 'Imported 29 holidays', holidays: mockHolidays.holidays })
      ),
    };

    await TestBed.configureTestingModule({
      imports: [HolidaysComponent],
      providers: [
        { provide: HolidaysService, useValue: mockHolidaysService },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(HolidaysComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should initialize and load holidays', () => {
    expect(component).toBeTruthy();
    expect(mockHolidaysService.getHolidays).toHaveBeenCalled();
    expect(component.holidays().length).toBe(3);
  });

  it('should compute available years correctly', () => {
    const years = component.availableYears();
    expect(years).toContain('2025');
    expect(years).toContain('2026');
  });

  it('should filter holidays by year', () => {
    component.selectedYear.set('2025');
    const filtered = component.filteredHolidays();
    expect(filtered.length).toBe(1);
    expect(filtered[0].date).toBe('2025-05-01');
  });

  it('should filter holidays by search query', () => {
    component.searchQuery.set('Christmas');
    const filtered = component.filteredHolidays();
    expect(filtered.length).toBe(1);
    expect(filtered[0].name).toBe('Christmas Day');
  });

  it('should open add modal and set quick date today and tomorrow', () => {
    component.openAddModal();
    expect(component.isAddModalOpen()).toBe(true);
    expect(component.newDate()).toBeTruthy();

    component.setQuickDate(0);
    expect(component.newName()).toBe('Holiday (Today)');

    component.setQuickDate(1);
    expect(component.newDate()).toBeTruthy();
  });

  it('should validate empty or invalid date before saving', () => {
    component.newDate.set('');
    component.saveHoliday();
    expect(component.formError()).toBe('Date is required.');
    expect(mockHolidaysService.createHoliday).not.toHaveBeenCalled();

    component.newDate.set('invalid-date');
    component.saveHoliday();
    expect(component.formError()).toBe('Invalid date format. Use YYYY-MM-DD.');
  });

  it('should save a new holiday and reload list', () => {
    component.newDate.set('2026-08-15');
    component.newName.set('Summer Fest');
    component.saveHoliday();

    expect(mockHolidaysService.createHoliday).toHaveBeenCalledWith({
      date: '2026-08-15',
      name: 'Summer Fest',
    });
    expect(component.isAddModalOpen()).toBe(false);
  });

  it('should open delete modal and confirm deletion', () => {
    const toDelete = mockHolidays.holidays[0];
    component.openDeleteModal(toDelete);
    expect(component.isDeleteModalOpen()).toBe(true);
    expect(component.holidayToDelete()).toEqual(toDelete);

    component.confirmDelete();
    expect(mockHolidaysService.deleteHoliday).toHaveBeenCalledWith(1);
    expect(component.isDeleteModalOpen()).toBe(false);
    expect(component.holidays().some((h) => h.id === 1)).toBe(false);
  });

  it('should open sync modal and ask user for county', () => {
    component.openSyncModal();
    expect(component.isSyncModalOpen()).toBe(true);
    expect(component.syncCounty()).toBe('ES-CT');
    expect(component.syncYear()).toBe(new Date().getFullYear());

    component.syncCounty.set('ES-MD');
    component.confirmSync();
    expect(component.isSyncModalOpen()).toBe(false);
    expect(mockHolidaysService.syncYearHolidays).toHaveBeenCalledWith({
      county: 'ES-MD',
      year: new Date().getFullYear(),
    });
  });

  it('should sync public holidays for the year and update list', () => {
    component.syncYearHolidays();
    expect(mockHolidaysService.syncYearHolidays).toHaveBeenCalled();
    expect(component.successMessage()).toBe('Imported 29 holidays');
    expect(component.syncing()).toBe(false);
  });
});
