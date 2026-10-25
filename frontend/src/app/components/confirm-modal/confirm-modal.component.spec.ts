import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ConfirmModalComponent } from './confirm-modal.component';

describe('ConfirmModalComponent', () => {
  let component: ConfirmModalComponent;
  let fixture: ComponentFixture<ConfirmModalComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConfirmModalComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ConfirmModalComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should emit confirmed when onConfirm is called', () => {
    let emitted = false;
    component.confirmed.subscribe(() => {
      emitted = true;
    });

    component.onConfirm();
    expect(emitted).toBe(true);
  });

  it('should emit cancelled when onCancel is called', () => {
    let emitted = false;
    component.cancelled.subscribe(() => {
      emitted = true;
    });

    component.onCancel();
    expect(emitted).toBe(true);
  });

  it('should trigger confirmed on Enter key when modal is open', () => {
    component.isOpen = true;
    let confirmedEmitted = false;
    component.confirmed.subscribe(() => {
      confirmedEmitted = true;
    });

    const enterEvent = new KeyboardEvent('keydown', { key: 'Enter' });
    document.dispatchEvent(enterEvent);

    expect(confirmedEmitted).toBe(true);
  });

  it('should trigger cancelled on Escape key when modal is open', () => {
    component.isOpen = true;
    let cancelledEmitted = false;
    component.cancelled.subscribe(() => {
      cancelledEmitted = true;
    });

    const escEvent = new KeyboardEvent('keydown', { key: 'Escape' });
    document.dispatchEvent(escEvent);

    expect(cancelledEmitted).toBe(true);
  });

  it('should NOT trigger confirmed on Enter key when modal is closed', () => {
    component.isOpen = false;
    let confirmedEmitted = false;
    component.confirmed.subscribe(() => {
      confirmedEmitted = true;
    });

    const enterEvent = new KeyboardEvent('keydown', { key: 'Enter' });
    document.dispatchEvent(enterEvent);

    expect(confirmedEmitted).toBe(false);
  });
});
