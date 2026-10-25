# IoT Backend Service

A simple, lightweight Python backend for home IoT automation.

## Features

- **Framework**: FastAPI + Uvicorn
- **Security**: Secured with API Key header (`X-API-Key`) using constant-time string comparison (`secrets.compare_digest`)
- **Configuration**: Environment variables loaded from `.env`
- **Database**: Local SQLite database with WAL mode and foreign key support
- **In-Memory Scheduler**: APScheduler running in the event loop, backed by SQLite persistence (restores active jobs on reboot)
- **Endpoints**:
  - `GET /health` (Protected)
  - `GET /schedules` (Protected)
  - `POST /schedules` (Protected)
  - `DELETE /schedules/{schedule_id}` (Protected)

---

## Setup & Running

### 1. Virtual Environment Setup

Inside `backend`:
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Environment Variables

A `.env` file is included. You can customize the values or copy from `.env.example`:

```env
API_KEY=iot-secret-key-change-me-in-production
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=development
DATABASE_PATH=db/iot.db
```

### 3. Start the Server

From `backend` folder:
```powershell
cd backend
.\.venv\Scripts\python.exe -m app.main
```
Or with Uvicorn:
```powershell
cd backend
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```

---

## Schedule Management

Schedules are held **in memory** for immediate, low-latency execution and persisted in **SQLite**. If the backend restarts, active schedules are restored from the database automatically into memory.

### Schedule Types:
- `one-time`: Triggered once at a specific ISO datetime (e.g. `2026-10-24T18:00:00Z`). When executed, it automatically marks the schedule as inactive in the database.
- `recurrent`: Triggered repeatedly via a standard 5-part cron expression (e.g. `*/5 * * * *`, `0 8 * * *`).

### Registering Task Handlers (in Python):

Use the `@register_task_handler` decorator to attach logic to any `use_case`:

```python
from scheduler import register_task_handler

@register_task_handler("turn_off_ac")
async def handle_turn_off_ac(schedule_id, name, schedule_type, use_case):
    # Call Home Assistant or device API here
    print(f"Turning off AC for schedule {schedule_id}")
```

---

## API Endpoints

### 1. Health Check
```bash
curl -X GET "http://localhost:8000/health" -H "X-API-Key: iot-secret-key-change-me-in-production"
```

### 2. List Schedules & Memory Status
```bash
curl -X GET "http://localhost:8000/schedules" -H "X-API-Key: iot-secret-key-change-me-in-production"
```

### 3. Create a Schedule

**Recurrent (Cron):**
```bash
curl -X POST "http://localhost:8000/schedules" \
  -H "X-API-Key: iot-secret-key-change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Check Living Room Sensors",
    "type": "recurrent",
    "trigger_spec": "*/10 * * * *",
    "use_case": "check_sensors"
  }'
```

**One-Time (Datetime):**
```bash
curl -X POST "http://localhost:8000/schedules" \
  -H "X-API-Key: iot-secret-key-change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Turn off garden sprinklers",
    "type": "one-time",
    "trigger_spec": "2026-10-24T20:00:00Z",
    "use_case": "sprinklers_off"
  }'
```

### 4. Delete / Cancel a Schedule
```bash
curl -X DELETE "http://localhost:8000/schedules/1" -H "X-API-Key: iot-secret-key-change-me-in-production"
```

---

## Automated Tests

Run the test suites from `backend`:
```powershell
cd backend
.\.venv\Scripts\python.exe test\test_health.py
.\.venv\Scripts\python.exe test\test_scheduler.py
```
