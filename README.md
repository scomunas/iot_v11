# IoT Home Automation System (v11)

A modular, lightweight, and modern home automation platform designed for low-latency task scheduling, autonomous climate control, and seamless integration with **Home Assistant** and **Telegram**.

---

## Architecture Overview

The system is built as a microservices pair:

```
┌─────────────────────────────────────────────────────────────┐
│                      Angular 22 Client                      │
│      (Signals, Standalone Components, Responsive SCSS)      │
└──────────────────────────────┬──────────────────────────────┘
                               │ REST API (X-API-Key)
┌──────────────────────────────▼──────────────────────────────┐
│                    FastAPI Python Backend                   │
│          (Async Endpoints, APScheduler, Timezone)           │
├──────────────────────────────┬──────────────────────────────┤
│                              │                              │
│  ┌────────────────────────┐  │  ┌────────────────────────┐  │
│  │   SQLite Database      │  │  │ Home Assistant REST    │  │
│  │ (WAL Mode, Relational) │  │  │ (Entity States & Svc)  │  │
│  └────────────────────────┘  │  └────────────────────────┘  │
│                              │                              │
│  ┌────────────────────────┐  │  ┌────────────────────────┐  │
│  │  Telegram Bot Alerting │  │  │ In-Memory Task Engine  │  │
│  └────────────────────────┘  │  └────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

- **Backend**: Python 3.11+ / FastAPI, SQLite in WAL mode with relational integrity, APScheduler for in-memory and persistent cron/one-time task scheduling.
- **Frontend**: Angular 22, TypeScript, Signals, Standalone Components, mobile-first responsive SCSS with dark theme.
- **Integrations**: Home Assistant REST API (sensors, climate, switches, covers), Telegram Bot API for instant event alerts.

---

## Core Features & Modules

### 1. Heating Control & Thermal Management
- **Master Toggle & Deferred Pause**: Instantly toggle heating ON or OFF, or schedule deferred deactivation for preset durations (1h, 2h, 3h, 4h, 8h, 24h, custom datetime).
- **Live Temperature Sensors Grid**:
  - Displays all configured temperature sensors with full names (no truncation).
  - Shows real-time ambient temperature from Home Assistant alongside the active heatmap objective (formatted with 1 decimal place, e.g., `21.6 °C  obj: 21.0 °C`).
  - Constrained to a maximum of 4 cards per row on wide screens, scaling down to 3, 2, or 1 card on smaller screens.
  - Optional **Auto-refresh** toggle in the header that refreshes temperatures every 15 seconds.
- **Heating Maps**:
  - Define custom thermal profiles (e.g., *Comfort*, *Eco*, *Night*) with individual target minimum temperature thresholds per sensor.
  - Formatted as a clean data table with quick edit/delete actions and mobile responsive card view.
- **Weekly Heating Schedule**:
  - 24-hour visual schedule timeline across Monday through Sunday plus Holidays.
  - Interactive modal to slice days into custom parts of the day and assign heating maps, with replication to other weekdays.
- **Autonomous Regulation**:
  - The recurrent scheduler evaluates sensors against the active map rules every **5 minutes** (configurable).
  - If any monitored sensor is below its target threshold, all heating devices are powered at full heating setpoint (**30.0 °C**).
  - When all rooms satisfy their target thresholds, heating devices are automatically shut off.

### 2. Blinds & Window Covers
- Visual cover position sliders and quick actions (Open, Close, Tilt, Stop).
- Automated scheduled movements linked to sunrise, sunset, or custom time schedules.

### 3. Garden Irrigation
- Multi-zone irrigation valve management.
- Watering duration timers and automated schedules with rain delay integration.

### 4. Schedules & Timers
- **One-time Schedules**: Execute once at an exact ISO datetime and automatically mark inactive upon completion.
- **Recurrent Schedules**: Standard 5-field cron expressions (e.g., `*/5 * * * *`, `0 8 * * 1-5`).
- Pause, resume, and edit schedules on the fly with in-memory synchronization and SQLite persistence.

### 5. Event Rules Engine
- Listen for inbound webhooks or internal sensor triggers.
- Link event definitions to executable use cases (e.g., motion detected, door opened).

### 6. Holidays Calendar
- Local and national holiday management with automated inclusion in holiday-specific heating schedules and task rules.

### 7. Task Execution Logs
- Real-time audit trail of all triggered schedules, event executions, manual tests, and background jobs.
- Searchable, filterable by date, status, and use case, with pagination and detailed error stack traces.

### 8. Settings & Hardware Devices
- **Hardware Devices**: Map logical devices (*Light*, *Irrigation*, *Blinds*, *Rain*, *Heating*, *Temperature*, *Movement*, *Presence*) to Home Assistant entity IDs.
- **Use Cases & System Functions**: Define custom use cases bound to built-in executable system functions.
- **Heating Check Interval**: Configurable recurrent regulation interval (defaults to **5 minutes**).
- **Telegram Notifications**: Configure bot token and chat ID with live connection testing.

---

## Directory Structure

```
iot_v11/
├── .gitignore               # Global gitignore covering Python, Node, DB, OS, IDE
├── README.md                # System documentation
│
├── backend/                 # FastAPI Python Backend
│   ├── app/
│   │   ├── main.py          # API entry point & route handlers
│   │   ├── database.py      # SQLite schema, seed data, and CRUD operations
│   │   ├── scheduler.py     # APScheduler setup, task handlers, heating control
│   │   ├── homeassistant.py # Home Assistant REST client & entity fetcher
│   │   ├── telegram.py      # Telegram Bot notification client
│   │   └── models.py        # Pydantic request/response schemas
│   ├── db/
│   │   └── iot.db           # SQLite database file (ignored by git)
│   ├── test/
│   │   └── test_heating.py  # Full integration test suite for heating module
│   ├── requirements.txt     # Python dependencies
│   ├── .env.example         # Example backend environment configuration
│   └── README.md            # Backend-specific guide
│
└── frontend/                # Angular 22 Single-Page Application
    ├── src/
    │   ├── app/
    │   │   ├── pages/       # Dashboard, Heating, Blinds, Irrigation,
    │   │   │                # Schedules, Events, Holidays, Logs, Settings
    │   │   ├── components/  # Modals, Navbar, Confirmation dialogs
    │   │   └── services/    # Angular HTTP services for backend APIs
    │   ├── environments/    # Environment configurations (backendUrl, apiKey)
    │   └── styles.scss      # Global styles & design tokens
    ├── angular.json         # Angular CLI workspace configuration
    ├── package.json         # Node.js dependencies and scripts
    └── README.md            # Frontend-specific guide
```

---

## Getting Started

### Prerequisites
- **Python**: 3.11 or newer
- **Node.js**: 20.x or newer (npm 10+)
- **Home Assistant**: (Optional) Running instance with a Long-Lived Access Token

---

### Backend Setup

1. **Navigate to the backend directory and create a virtual environment**:
   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. **Configure environment variables**:
   Create `backend/.env` (or copy from `.env.example`):
   ```env
   API_KEY=iot-secret-key-change-me-in-production
   HOST=0.0.0.0
   PORT=8765
   ENVIRONMENT=development
   DATABASE_PATH=db/iot.db
   TIMEZONE=Europe/Madrid

   # Home Assistant Integration
   HASS_URL=http://192.168.1.100:8123
   HASS_TOKEN=your_home_assistant_long_lived_token

   # Telegram Integration (Optional)
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_telegram_chat_id
   ```

3. **Run the Backend Server**:
   ```powershell
   .\.venv\Scripts\python.exe -m app.main
   ```
   Or via Uvicorn:
   ```powershell
   .\.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8765 --reload
   ```

4. **Verify Backend**:
   - Health check: `http://localhost:8765/health`
   - Interactive OpenAPI docs: `http://localhost:8765/docs`

---

### Frontend Setup

1. **Navigate to the frontend directory and install dependencies**:
   ```powershell
   cd frontend
   npm install
   ```

2. **Configure environment**:
   Ensure `src/environments/environment.ts` points to your backend URL:
   ```typescript
   export const environment = {
     production: false,
     backendUrl: '/api/v1',
     apiKey: 'iot-secret-key-change-me-in-production',
     version: 'v11.0.2',
   };
   ```

3. **Start Development Server**:
   ```powershell
   npm start
   ```
   Open your browser at `http://localhost:4200/`.

---

## Docker Deployment (Production / Proxmox LXC)

The system includes production Dockerfiles for both services and a unified `docker-compose.yml` that mounts the persistent SQLite database from the host filesystem (e.g. `/opt/iot/data`).

### 1. Build & Start with Docker Compose
```bash
# Ensure persistent data directory exists on the host / LXC
mkdir -p /opt/iot/data /opt/iot/logs

# Build and start containers in background
docker compose up -d --build
```

### 2. Upgrading to a New Version Without Data Loss
When upgrading your backend or frontend container:
```bash
# 1. Pull or build the new version tag (e.g. v12.0.0)
docker compose up -d --build

# The new containers start immediately and mount the same /opt/iot/data/iot.db
```

### 3. Verification & Logs
```bash
# Check running container health
docker compose ps

# View backend logs
docker compose logs -f backend

# View frontend access logs
docker compose logs -f frontend
```

---

## Running Tests

### Backend Integration Tests
Tests verify database initialization, heating state preservation across reboots, heating calendar resolution, sensor evaluation, and 30.0 °C boost control:
```powershell
backend\.venv\Scripts\python.exe backend/test/test_heating.py
```

### Frontend Unit Tests
Executes Vitest suites across all components, signals, services, and modal dialogs:
```powershell
npm --prefix frontend test -- --watch=false
```

### Production Build
Compiles frontend bundle with optimizations and budget verification:
```powershell
npm --prefix frontend run build
```

---

## Security Guidelines

- **API Protection**: All private API endpoints are protected using HTTP header `X-API-Key`.
- **Timing Attacks**: The backend utilizes `secrets.compare_digest` for constant-time key validation.
- **Sensitive Data**: Never commit `.env` or SQLite `.db` files to version control. Keep `.gitignore` updated.

---

## License

Private / Internal Home Automation Project.
