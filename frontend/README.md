# IoT Frontend

Modern Angular application for the **IoT** home automation management system.

## Features

- **Angular 22** with standalone components, signals, and typed routing.
- **Mobile-First Responsive Design**:
  - Automatically adapts for smartphones, tablets, and desktop displays.
  - Collapsible off-canvas navigation drawer with touch-friendly hamburger button on mobile devices.
  - Fluid card layouts and touch-friendly controls (min 44px touch targets).
  - Responsive tables with smooth touch horizontal scrolling.
  - Stacking modal forms on smartphone screens.
- **Left Sidebar Layout**:
  - **Top**: Displays `iot-logo.png` and the **IoT** app title.
  - **Middle**: Navigation sections (**Dashboard**, **Schedules**).
  - **Bottom**:
    - **System Status**: Clean indicators for **Backend**, **Scheduler**, and **Database** querying `/health` (`http://localhost:8000/health`) using the secure `X-API-Key`. Includes auto-refresh and manual refresh.
    - **App Version**: `v11.1.1`
- **Dashboard Overview**:
  - Service status, SQLite database connection status, and scheduler engine status.
  - Home Assistant integration readiness card.

---

## Development Server

Start the Angular development server:

```powershell
cd frontend
npm start
```

Navigate to `http://localhost:4200/`.

---

## Configuration

Backend connection settings can be adjusted in [`src/environments/environment.ts`](src/environments/environment.ts):

```typescript
export const environment = {
  production: false,
  backendUrl: 'http://localhost:8000',
  apiKey: 'iot-secret-key-change-me-in-production',
  version: 'v11.1.1',
};
```

---

## Building & Testing

- **Build**:
  ```powershell
  cd frontend
  npm run build
  ```

- **Run Unit Tests**:
  ```powershell
  cd frontend
  npm test -- --watch=false
  ```
