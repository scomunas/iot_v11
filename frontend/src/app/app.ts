import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { BackendHealthService } from './services/backend-health.service';
import { environment } from '../environments/environment';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App {
  readonly title = 'IoT';
  readonly version = environment.version;
  protected readonly healthService = inject(BackendHealthService);

  readonly isMobileSidebarOpen = signal<boolean>(false);

  toggleMobileSidebar(): void {
    this.isMobileSidebarOpen.update((open) => !open);
  }

  closeMobileSidebar(): void {
    this.isMobileSidebarOpen.set(false);
  }

  refreshBackend(): void {
    this.healthService.checkHealth();
  }

  promptApiKey(): void {
    const current = environment.apiKey;
    const isDefault = current === 'iot-secret-key-change-me-in-production';
    const entered = window.prompt(
      'Enter IoT Backend API Key:\n(Leave empty to reset to default/server configuration)',
      isDefault ? '' : current
    );

    if (entered !== null) {
      if (entered.trim()) {
        environment.setApiKey(entered.trim());
      } else {
        environment.clearApiKey();
      }
      this.healthService.checkHealth();
    }
  }
}
