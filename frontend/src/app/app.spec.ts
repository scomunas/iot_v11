import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { App } from './app';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
      ]
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('should render the app title IoT in the sidebar', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.app-title')?.textContent).toContain('IoT');
  });

  it('should display version v11.0.4', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.version-value')?.textContent).toContain('v11.0.4');
  });

  it('should display Backend, Scheduler, Database, and Home Assistant status items in the sidebar bottom', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    const serviceNames = Array.from(compiled.querySelectorAll('.system-status-widget .status-name')).map(
      (el) => el.textContent?.trim()
    );
    expect(serviceNames).toEqual(['Backend', 'Scheduler', 'Database', 'Home Assistant']);

    const sidebarText = compiled.querySelector('.sidebar-bottom')?.textContent || '';
    expect(sidebarText).not.toContain('Online');
    expect(sidebarText).not.toContain('db connected');
    expect(sidebarText).not.toContain('cron running');
  });

  it('should toggle mobile sidebar drawer when hamburger button is clicked', async () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app.isMobileSidebarOpen()).toBe(false);

    app.toggleMobileSidebar();
    expect(app.isMobileSidebarOpen()).toBe(true);

    fixture.detectChanges();
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.sidebar.mobile-open')).toBeTruthy();

    app.closeMobileSidebar();
    expect(app.isMobileSidebarOpen()).toBe(false);
  });
});
