"""
Seed realistic heating history data for the last 48 hours into SQLite database.
Generates:
- Temperature readings for configured temperature sensors (with realistic diurnal sinusoidal curves + noise)
- Actuator ON/OFF state samples for heater actuators (morning/evening heating schedules)
"""

import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database import db_seed_heating_history

if __name__ == "__main__":
    print("Seeding heating history for the last 48 hours...")
    count = db_seed_heating_history(hours=48.0, interval_minutes=15)
    print(f"Successfully generated and inserted {count} heating history samples.")
