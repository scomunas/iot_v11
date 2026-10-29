import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Define backend base directory and load backend/.env
BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DATABASE_PATH = os.getenv("DATABASE_PATH", "db/iot.db")

logger = logging.getLogger(__name__)


def get_db_path() -> Path:
    """Return the absolute Path object for the configured database path."""
    raw_path = Path(os.getenv("DATABASE_PATH", DATABASE_PATH))
    if not raw_path.is_absolute():
        return (BACKEND_DIR / raw_path).resolve()
    return raw_path.resolve()


def get_db_connection() -> sqlite3.Connection:
    """Create and return a configured connection to the SQLite database with 10s timeout."""
    conn = sqlite3.connect(get_db_path(), timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    """Context manager ensuring connection is committed and properly closed."""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    Initialize SQLite database file, enable PRAGMAs, and create the schedules table.
    """
    db_file = get_db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Initializing SQLite database at: %s", db_file)
    with get_db() as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('one-time', 'recurrent')),
                trigger_spec TEXT NOT NULL,
                use_case TEXT NOT NULL,
                data TEXT NOT NULL DEFAULT '{}',
                notify INTEGER NOT NULL DEFAULT 0,
                notification_message TEXT DEFAULT '',
                speak INTEGER NOT NULL DEFAULT 0,
                speak_message TEXT DEFAULT '',
                block INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            """
        )
        # Ensure 'data', 'notify', 'notification_message', 'speak', 'speak_message', and 'block' columns exist in schedules (migration)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(schedules)")
        cols = [c[1] for c in cursor.fetchall()]
        if "data" not in cols:
            logger.info("Migrating schedules table: adding 'data' column")
            conn.execute("ALTER TABLE schedules ADD COLUMN data TEXT NOT NULL DEFAULT '{}'")
        if "notify" not in cols:
            logger.info("Migrating schedules table: adding 'notify' column")
            conn.execute("ALTER TABLE schedules ADD COLUMN notify INTEGER NOT NULL DEFAULT 0")
        if "notification_message" not in cols:
            logger.info("Migrating schedules table: adding 'notification_message' column")
            conn.execute("ALTER TABLE schedules ADD COLUMN notification_message TEXT DEFAULT ''")
        if "speak" not in cols:
            logger.info("Migrating schedules table: adding 'speak' column")
            conn.execute("ALTER TABLE schedules ADD COLUMN speak INTEGER NOT NULL DEFAULT 0")
        if "speak_message" not in cols:
            logger.info("Migrating schedules table: adding 'speak_message' column")
            conn.execute("ALTER TABLE schedules ADD COLUMN speak_message TEXT DEFAULT ''")
        if "block" not in cols:
            logger.info("Migrating schedules table: adding 'block' column")
            conn.execute("ALTER TABLE schedules ADD COLUMN block INTEGER NOT NULL DEFAULT 0")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS use_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                function_name TEXT NOT NULL,
                description TEXT,
                section TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        # Ensure 'section' column exists in use_cases (migration)
        cursor.execute("PRAGMA table_info(use_cases)")
        uc_cols = [c[1] for c in cursor.fetchall()]
        if "section" not in uc_cols:
            logger.info("Migrating use_cases table: adding 'section' column")
            conn.execute("ALTER TABLE use_cases ADD COLUMN section TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('light', 'irrigation', 'temperature', 'movement', 'presence', 'blinds', 'rain', 'door')),
                entity_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                parameter TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_definitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                parameter TEXT NOT NULL DEFAULT '',
                use_case TEXT NOT NULL,
                data TEXT NOT NULL DEFAULT '{}',
                holiday TEXT NOT NULL DEFAULT 'all_days',
                notify INTEGER NOT NULL DEFAULT 0,
                notification_message TEXT DEFAULT '',
                speak INTEGER NOT NULL DEFAULT 0,
                speak_message TEXT DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            """
        )
        # Ensure 'holiday', 'notify', 'notification_message', 'speak', and 'speak_message' columns exist in event_definitions (migration)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(event_definitions)")
        ed_cols = [c[1] for c in cursor.fetchall()]
        if "holiday" not in ed_cols:
            logger.info("Migrating event_definitions table: adding 'holiday' column")
            conn.execute("ALTER TABLE event_definitions ADD COLUMN holiday TEXT NOT NULL DEFAULT 'all_days'")
        if "notify" not in ed_cols:
            logger.info("Migrating event_definitions table: adding 'notify' column")
            conn.execute("ALTER TABLE event_definitions ADD COLUMN notify INTEGER NOT NULL DEFAULT 0")
        if "notification_message" not in ed_cols:
            logger.info("Migrating event_definitions table: adding 'notification_message' column")
            conn.execute("ALTER TABLE event_definitions ADD COLUMN notification_message TEXT DEFAULT ''")
        if "speak" not in ed_cols:
            logger.info("Migrating event_definitions table: adding 'speak' column")
            conn.execute("ALTER TABLE event_definitions ADD COLUMN speak INTEGER NOT NULL DEFAULT 0")
        if "speak_message" not in ed_cols:
            logger.info("Migrating event_definitions table: adding 'speak_message' column")
            conn.execute("ALTER TABLE event_definitions ADD COLUMN speak_message TEXT DEFAULT ''")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holidays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                name TEXT,
                created_at TEXT NOT NULL
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS heating_state (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                deactivated_until TEXT,
                active_map_id INTEGER,
                updated_at TEXT NOT NULL
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS heating_maps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT '',
                rules TEXT NOT NULL DEFAULT '{}',
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS heating_calendar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day_of_week INTEGER NOT NULL CHECK(day_of_week BETWEEN 0 AND 7),
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                map_id INTEGER NOT NULL REFERENCES heating_maps(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL
            );
            """
        )

        # Migration: Ensure heating_state does not store 'state' column (heating state is derived dynamically from helper entity)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(heating_state)")
        hs_cols = [c[1] for c in cursor.fetchall()]
        if "state" in hs_cols:
            logger.info("Migrating heating_state table to remove 'state' column...")
            cursor.execute(
                """
                CREATE TABLE heating_state_migration (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    deactivated_until TEXT,
                    active_map_id INTEGER,
                    updated_at TEXT NOT NULL
                );
                """
            )
            cursor.execute("INSERT INTO heating_state_migration (id, deactivated_until, active_map_id, updated_at) SELECT id, deactivated_until, active_map_id, updated_at FROM heating_state")
            cursor.execute("DROP TABLE heating_state")
            cursor.execute("ALTER TABLE heating_state_migration RENAME TO heating_state")
            logger.info("heating_state table successfully migrated without 'state' column.")
        elif "active_map_id" not in hs_cols:
            logger.info("Migrating heating_state table: adding 'active_map_id' column")
            conn.execute("ALTER TABLE heating_state ADD COLUMN active_map_id INTEGER")

        # Migration: Remove 'heating' from devices table CHECK constraint and migrate any heating device to heating_helper_entity setting
        cursor = conn.cursor()
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='devices'")
        devices_sql_row = cursor.fetchone()
        if devices_sql_row and ("'heating'" in devices_sql_row[0] or "'door'" not in devices_sql_row[0]):
            logger.info("Migrating devices table to remove 'heating' from CHECK constraint...")
            cursor.execute("SELECT entity_id FROM devices WHERE type = 'heating' LIMIT 1")
            old_heat_dev = cursor.fetchone()
            if old_heat_dev and old_heat_dev[0]:
                cursor.execute("SELECT value FROM settings WHERE key = 'heating_helper_entity'")
                curr_helper = cursor.fetchone()
                if not curr_helper or not curr_helper[0]:
                    now_u = datetime.now(timezone.utc).isoformat()
                    cursor.execute(
                        "INSERT INTO settings (key, value, updated_at) VALUES ('heating_helper_entity', ?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (old_heat_dev[0], now_u)
                    )
            cursor.execute("DELETE FROM devices WHERE type = 'heating'")
            cursor.execute(
                """
                CREATE TABLE devices_migration (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL CHECK(type IN ('light', 'irrigation', 'temperature', 'movement', 'presence', 'blinds', 'rain', 'door')),
                    entity_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            cursor.execute("INSERT INTO devices_migration (id, name, type, entity_id, created_at) SELECT id, name, type, entity_id, created_at FROM devices WHERE type != 'heating'")
            cursor.execute("DROP TABLE devices")
            cursor.execute("ALTER TABLE devices_migration RENAME TO devices")
            logger.info("Devices table successfully migrated without 'heating'.")
        # Seed default test use case if table is empty
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM use_cases")
        if cursor.fetchone()[0] == 0:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO use_cases (name, function_name, description, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "test_create_file",
                    "create_datetime_file",
                    "Creates a .txt file named with current datetime upon execution",
                    now_utc,
                ),
            )

        # Ensure legacy typo function_name is updated to start_irrigation
        conn.execute("UPDATE use_cases SET function_name = 'start_irrigation' WHERE function_name = 'start_irrigatioin'")

        # Seed default irrigation use case if none exists
        cursor.execute("SELECT COUNT(*) FROM use_cases WHERE function_name = 'start_irrigation'")
        if cursor.fetchone()[0] == 0:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO use_cases (name, function_name, description, section, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "irrigation",
                    "start_irrigation",
                    "Triggers irrigation cycle for configured entity and duration",
                    "irrigation",
                    now_utc,
                ),
            )

        # Seed default blinds use case if none exists
        cursor.execute("SELECT COUNT(*) FROM use_cases WHERE function_name = 'move_blind'")
        if cursor.fetchone()[0] == 0:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO use_cases (name, function_name, description, section, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "move_blind",
                    "move_blind",
                    "Moves blind/cover entity to target position (0-100%)",
                    "blinds",
                    now_utc,
                ),
            )

        # Seed default check_alarm use case if none exists
        cursor.execute("SELECT COUNT(*) FROM use_cases WHERE function_name = 'check_alarm'")
        if cursor.fetchone()[0] == 0:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO use_cases (name, function_name, description, section, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "check_alarm",
                    "check_alarm",
                    "Evaluates sensor activity against threshold rules and fires alarm alerts",
                    "alarm",
                    now_utc,
                ),
            )

        # Seed default fire_alarm use case if none exists
        cursor.execute("SELECT COUNT(*) FROM use_cases WHERE function_name = 'fire_alarm'")
        if cursor.fetchone()[0] == 0:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO use_cases (name, function_name, description, section, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "fire_alarm",
                    "fire_alarm",
                    "Fires alarm alert notifications and voice announcements as configured",
                    "alarm",
                    now_utc,
                ),
            )

        # Assign sections for irrigation and blinds use cases if blank
        conn.execute(
            """
            UPDATE use_cases
            SET section = 'irrigation'
            WHERE (function_name = 'start_irrigation' OR LOWER(name) LIKE '%irrigat%')
              AND (section IS NULL OR section = '')
            """
        )
        conn.execute(
            """
            UPDATE use_cases
            SET section = 'blinds'
            WHERE (function_name = 'move_blind' OR LOWER(name) LIKE '%blind%' OR LOWER(name) LIKE '%persiana%')
              AND (section IS NULL OR section = '')
            """
        )
        # Seed default add_holiday use case if none exists
        cursor.execute("SELECT COUNT(*) FROM use_cases WHERE function_name = 'add_holiday'")
        if cursor.fetchone()[0] == 0:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO use_cases (name, function_name, description, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "add_holiday",
                    "add_holiday",
                    "Adds today or tomorrow to the holidays list",
                    now_utc,
                ),
            )
        # Seed default get_year_holidays use case if none exists
        cursor.execute("SELECT COUNT(*) FROM use_cases WHERE function_name = 'get_year_holidays'")
        if cursor.fetchone()[0] == 0:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO use_cases (name, function_name, description, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "get_year_holidays",
                    "get_year_holidays",
                    "Fetches Spanish public holidays for the year from Nager.Date API filtered by county (defaults to ES-CT) and imports them into holidays table without duplicates",
                    now_utc,
                ),
            )
        # Migration: Remove notification use cases from use_cases table
        conn.execute("DELETE FROM use_cases WHERE function_name = 'send_telegram_alert'")
        conn.execute("UPDATE use_cases SET section = 'general' WHERE section = 'notification'")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

        # Seed default heating_helper_entity setting if not present
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM settings WHERE key = 'heating_helper_entity'")
        if cursor.fetchone()[0] == 0:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                ("heating_helper_entity", "", now_utc),
            )

        # Seed default heating_heater_entities setting if not present
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM settings WHERE key = 'heating_heater_entities'")
        if cursor.fetchone()[0] == 0:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                ("heating_heater_entities", "[]", now_utc),
            )

        # Seed default heating_interval_minutes setting if not present
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM settings WHERE key = 'heating_interval_minutes'")
        if cursor.fetchone()[0] == 0:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                ("heating_interval_minutes", "5", now_utc),
            )

        # Seed default Heating use case (executing control_heating under heating)
        cursor.execute("SELECT id FROM use_cases WHERE name = 'Heating'")
        existing_h = cursor.fetchone()
        if not existing_h:
            cursor.execute("SELECT id FROM use_cases WHERE name = 'Heating Control'")
            existing_hc = cursor.fetchone()
            if existing_hc:
                conn.execute(
                    "UPDATE use_cases SET name = 'Heating', function_name = 'control_heating', section = 'heating' WHERE id = ?",
                    (existing_hc[0],),
                )
            else:
                now_utc = datetime.now(timezone.utc).isoformat()
                cursor.execute(
                    """
                    INSERT INTO use_cases (name, function_name, description, section, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        "Heating",
                        "control_heating",
                        "Reviews active heating map and regulates heating devices with map temperature",
                        "heating",
                        now_utc,
                    ),
                )
        else:
            conn.execute(
                "UPDATE use_cases SET function_name = 'control_heating', section = 'heating' WHERE id = ?",
                (existing_h[0],),
            )

        # Clean up unused heating use cases and remove default start_heating use case
        conn.execute("DELETE FROM use_cases WHERE name IN ('Heating Recurrent', 'set_heating_map', 'start_heating') OR function_name = 'start_heating'")
        conn.execute("UPDATE use_cases SET section = 'heating' WHERE section IN ('heating_control', 'heating_recurrent')")
        conn.execute("UPDATE use_cases SET name = 'Heating' WHERE name = 'Heating Control'")

        # Ensure default notification_only use case exists with do_nothing function
        cursor.execute("SELECT id FROM use_cases WHERE function_name = 'do_nothing'")
        if not cursor.fetchone():
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO use_cases (name, function_name, description, section, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "Notification Only",
                    "do_nothing",
                    "Performs no system action. Useful for schedules or event triggers used solely to send notifications",
                    "general",
                    now_utc,
                ),
            )

        # Ensure Heating use case is assigned to 'heating' section
        conn.execute(
            """
            UPDATE use_cases
            SET section = 'heating'
            WHERE (function_name = 'control_heating' OR LOWER(name) LIKE '%heating%')
              AND (section IS NULL OR section = '' OR section IN ('heating_control', 'heating_recurrent'))
            """
        )

        # Seed initial heating_maps record if empty
        cursor.execute("SELECT COUNT(*) FROM heating_maps")
        if cursor.fetchone()[0] == 0:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute("SELECT id FROM devices WHERE type = 'temperature'")
            temp_dev_rows = cursor.fetchall()
            initial_rules = {str(r[0]): 21.0 for r in temp_dev_rows}

            cursor.execute(
                """
                INSERT INTO heating_maps (name, description, rules, is_default, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                (
                    "Comfort",
                    "Default comfort heating map",
                    json.dumps(initial_rules),
                    now_utc,
                    now_utc,
                ),
            )
            default_map_id = cursor.lastrowid
        else:
            cursor.execute("SELECT id FROM heating_maps WHERE is_default = 1")
            row = cursor.fetchone()
            default_map_id = row[0] if row else None

        # Seed initial heating_state record if empty
        cursor.execute("SELECT COUNT(*) FROM heating_state WHERE id = 1")
        if cursor.fetchone()[0] == 0:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO heating_state (id, state, deactivated_until, active_map_id, updated_at)
                VALUES (1, 'off', NULL, ?, ?)
                """,
                (default_map_id, now_utc),
            )
        elif default_map_id is not None:
            conn.execute("UPDATE heating_state SET active_map_id = ? WHERE id = 1 AND active_map_id IS NULL", (default_map_id,))

        # Seed initial heating_calendar records if empty
        cursor.execute("SELECT COUNT(*) FROM heating_calendar")
        if cursor.fetchone()[0] == 0 and default_map_id is not None:
            now_utc = datetime.now(timezone.utc).isoformat()
            for day_idx in range(8):  # 0=Mon .. 6=Sun, 7=Holidays
                cursor.execute(
                    """
                    INSERT INTO heating_calendar (day_of_week, start_time, end_time, map_id, created_at)
                    VALUES (?, '00:00', '24:00', ?, ?)
                    """,
                    (day_idx, default_map_id, now_utc),
                )
    logger.info("SQLite database initialized successfully.")


def db_create_schedule(
    name: str,
    schedule_type: str,
    trigger_spec: str,
    use_case: str,
    data: Optional[Any] = "{}",
    notify: int = 0,
    notification_message: Optional[str] = None,
    speak: int = 0,
    speak_message: Optional[str] = None,
    block: int = 0,
) -> Dict[str, Any]:
    """Persist a new schedule into SQLite."""
    now_utc = datetime.now(timezone.utc).isoformat()
    clean_data = data if data is not None else "{}"
    if isinstance(clean_data, dict):
        clean_data = json.dumps(clean_data)
    elif not isinstance(clean_data, str):
        clean_data = str(clean_data)

    clean_notify = 1 if notify else 0
    clean_notif_msg = (notification_message or "").strip()
    clean_speak = 1 if speak else 0
    clean_speak_msg = (speak_message or "").strip()
    clean_block = 1 if block else 0

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO schedules (name, type, trigger_spec, use_case, data, notify, notification_message, speak, speak_message, block, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (name, schedule_type, trigger_spec, use_case, clean_data, clean_notify, clean_notif_msg, clean_speak, clean_speak_msg, clean_block, now_utc),
        )
        new_id = cursor.lastrowid
        cursor.execute("SELECT * FROM schedules WHERE id = ?", (new_id,))
        row = cursor.fetchone()
        return dict(row)


def db_get_active_schedules() -> List[Dict[str, Any]]:
    """Retrieve all active schedules for restoring into memory."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM schedules WHERE is_active = 1")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def db_list_schedules() -> List[Dict[str, Any]]:
    """Retrieve all schedules (active and inactive)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM schedules ORDER BY id DESC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def db_get_schedule(schedule_id: int) -> Optional[Dict[str, Any]]:
    """Get a single schedule by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def db_deactivate_schedule(schedule_id: int) -> bool:
    """Mark a schedule as inactive (e.g. after one-time execution or deletion)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE schedules SET is_active = 0 WHERE id = ?", (schedule_id,))
        return cursor.rowcount > 0


def db_update_schedule(
    schedule_id: int,
    name: str,
    schedule_type: str,
    trigger_spec: str,
    use_case: str,
    is_active: int = 1,
    data: Optional[Any] = None,
    notify: Optional[int] = None,
    notification_message: Optional[str] = None,
    speak: Optional[int] = None,
    speak_message: Optional[str] = None,
    block: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Update an existing schedule in SQLite."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
        current = cursor.fetchone()
        if not current:
            return None
        current_dict = dict(current)

        clean_data = current_dict.get("data", "{}")
        if data is not None:
            clean_data = json.dumps(data) if isinstance(data, dict) else str(data)

        clean_notify = current_dict.get("notify", 0)
        if notify is not None:
            clean_notify = 1 if notify else 0

        clean_notif_msg = current_dict.get("notification_message", "")
        if notification_message is not None:
            clean_notif_msg = notification_message.strip()

        clean_speak = current_dict.get("speak", 0)
        if speak is not None:
            clean_speak = 1 if speak else 0

        clean_speak_msg = current_dict.get("speak_message", "")
        if speak_message is not None:
            clean_speak_msg = speak_message.strip()

        clean_block = current_dict.get("block", 0)
        if block is not None:
            clean_block = 1 if block else 0

        cursor.execute(
            """
            UPDATE schedules
            SET name = ?, type = ?, trigger_spec = ?, use_case = ?, is_active = ?, data = ?, notify = ?, notification_message = ?, speak = ?, speak_message = ?, block = ?
            WHERE id = ?
            """,
            (name, schedule_type, trigger_spec, use_case, is_active, clean_data, clean_notify, clean_notif_msg, clean_speak, clean_speak_msg, clean_block, schedule_id),
        )
        if cursor.rowcount == 0:
            return None
        cursor.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def db_set_schedule_block(schedule_id: int, block: int) -> Optional[Dict[str, Any]]:
    """Set the block status of a schedule."""
    clean_block = 1 if block else 0
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE schedules SET block = ? WHERE id = ?", (clean_block, schedule_id))
        if cursor.rowcount == 0:
            return None
        cursor.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def db_delete_schedule(schedule_id: int) -> bool:
    """Permanently delete a schedule from SQLite."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        return cursor.rowcount > 0


# ==========================================
# Use Cases Operations
# ==========================================

def db_list_use_cases() -> List[Dict[str, Any]]:
    """Retrieve all configured use cases."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM use_cases ORDER BY id ASC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def db_list_use_cases_by_section(section: str) -> List[Dict[str, Any]]:
    """Retrieve all use cases belonging to a specific section (e.g. 'notification', 'irrigation', etc.)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM use_cases WHERE LOWER(section) = LOWER(?) ORDER BY id ASC", (section.strip(),))
        return [dict(row) for row in cursor.fetchall()]


def db_get_use_case(use_case_id: int) -> Optional[Dict[str, Any]]:
    """Get a single use case by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM use_cases WHERE id = ?", (use_case_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def db_get_use_case_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Get a use case by its unique name."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM use_cases WHERE name = ?", (name,))
        row = cursor.fetchone()
        return dict(row) if row else None


def db_create_use_case(
    name: str,
    function_name: str,
    description: Optional[str] = None,
    section: Optional[str] = None,
) -> Dict[str, Any]:
    """Create and persist a new use case with optional section."""
    now_utc = datetime.now(timezone.utc).isoformat()
    clean_section = section.strip() if section and section.strip() else None
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO use_cases (name, function_name, description, section, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name.strip(), function_name.strip(), description.strip() if description else "", clean_section, now_utc),
        )
        new_id = cursor.lastrowid
        cursor.execute("SELECT * FROM use_cases WHERE id = ?", (new_id,))
        row = cursor.fetchone()
        return dict(row)


def db_update_use_case(
    use_case_id: int,
    name: str,
    function_name: str,
    description: Optional[str] = None,
    section: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Update an existing use case with optional section."""
    clean_section = section.strip() if section and section.strip() else None
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE use_cases
            SET name = ?, function_name = ?, description = ?, section = ?
            WHERE id = ?
            """,
            (name.strip(), function_name.strip(), description.strip() if description else "", clean_section, use_case_id),
        )
        if cursor.rowcount == 0:
            return None
        cursor.execute("SELECT * FROM use_cases WHERE id = ?", (use_case_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def db_delete_use_case(use_case_id: int) -> bool:
    """Delete a use case by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM use_cases WHERE id = ?", (use_case_id,))
        return cursor.rowcount > 0


# ==========================================
# Devices CRUD
# ==========================================

VALID_DEVICE_TYPES = ("light", "irrigation", "temperature", "movement", "presence", "blinds", "rain", "door")


def db_list_devices(device_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all configured devices ordered by ID, optionally filtered by type."""
    with get_db() as conn:
        cursor = conn.cursor()
        if device_type:
            cursor.execute("SELECT * FROM devices WHERE type = ? ORDER BY id ASC", (device_type.strip(),))
        else:
            cursor.execute("SELECT * FROM devices ORDER BY id ASC")
        return [dict(row) for row in cursor.fetchall()]


def db_get_device(device_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve a single device by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices WHERE id = ?", (device_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def db_create_device(name: str, device_type: str, entity_id: str) -> Dict[str, Any]:
    """Create and insert a new device."""
    if device_type not in VALID_DEVICE_TYPES:
        raise ValueError(f"Invalid device type '{device_type}'. Must be one of: {', '.join(VALID_DEVICE_TYPES)}")

    now_utc = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO devices (name, type, entity_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name.strip(), device_type.strip(), entity_id.strip(), now_utc),
        )
        new_id = cursor.lastrowid
        cursor.execute("SELECT * FROM devices WHERE id = ?", (new_id,))
        row = cursor.fetchone()
        return dict(row)


def db_update_device(
    device_id: int,
    name: str,
    device_type: str,
    entity_id: str,
) -> Optional[Dict[str, Any]]:
    """Update an existing device."""
    if device_type not in VALID_DEVICE_TYPES:
        raise ValueError(f"Invalid device type '{device_type}'. Must be one of: {', '.join(VALID_DEVICE_TYPES)}")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE devices
            SET name = ?, type = ?, entity_id = ?
            WHERE id = ?
            """,
            (name.strip(), device_type.strip(), entity_id.strip(), device_id),
        )
        if cursor.rowcount == 0:
            return None
        cursor.execute("SELECT * FROM devices WHERE id = ?", (device_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def db_delete_device(device_id: int) -> bool:
    """Delete a device by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        return cursor.rowcount > 0


def db_create_event(event_type: str, parameter: str = "") -> Dict[str, Any]:
    """Record an incoming event in SQLite."""
    now_utc = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO events (type, parameter, created_at)
            VALUES (?, ?, ?)
            """,
            (event_type.strip(), parameter.strip(), now_utc),
        )
        new_id = cursor.lastrowid
        cursor.execute("SELECT * FROM events WHERE id = ?", (new_id,))
        row = cursor.fetchone()
        return dict(row)


def db_list_events(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieve recorded events ordered by most recent first."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]


def db_create_event_definition(
    name: str,
    event_type: str,
    parameter: str = "",
    use_case: str = "",
    data: Any = "{}",
    holiday: str = "all_days",
    notify: int = 0,
    notification_message: Optional[str] = None,
    speak: int = 0,
    speak_message: Optional[str] = None,
    is_active: int = 1,
) -> Dict[str, Any]:
    """Create and insert a new event definition."""
    now_utc = datetime.now(timezone.utc).isoformat()
    if not isinstance(data, str):
        data_str = json.dumps(data)
    else:
        data_str = data.strip() if data else "{}"

    clean_holiday = holiday.strip() if holiday and holiday.strip() in ("all_days", "holiday", "not_holiday") else "all_days"
    clean_notify = 1 if notify else 0
    clean_notif_msg = (notification_message or "").strip()
    clean_speak = 1 if speak else 0
    clean_speak_msg = (speak_message or "").strip()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO event_definitions (name, type, parameter, use_case, data, holiday, notify, notification_message, speak, speak_message, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name.strip(), event_type.strip(), parameter.strip(), use_case.strip(), data_str, clean_holiday, clean_notify, clean_notif_msg, clean_speak, clean_speak_msg, int(is_active), now_utc),
        )
        new_id = cursor.lastrowid
        cursor.execute("SELECT * FROM event_definitions WHERE id = ?", (new_id,))
        row = cursor.fetchone()
        return dict(row)


def db_list_event_definitions() -> List[Dict[str, Any]]:
    """Retrieve all event definitions ordered by ID descending."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM event_definitions ORDER BY id DESC")
        return [dict(row) for row in cursor.fetchall()]


def db_get_event_definition(definition_id: int) -> Optional[Dict[str, Any]]:
    """Get a single event definition by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM event_definitions WHERE id = ?", (definition_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def db_get_active_event_definitions_by_type(event_type: str) -> List[Dict[str, Any]]:
    """Get active event definitions matching a given event type."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM event_definitions WHERE LOWER(type) = LOWER(?) AND is_active = 1 ORDER BY id ASC",
            (event_type.strip(),),
        )
        return [dict(row) for row in cursor.fetchall()]


def db_update_event_definition(
    definition_id: int,
    name: str,
    event_type: str,
    parameter: str = "",
    use_case: str = "",
    data: Any = "{}",
    holiday: str = "all_days",
    notify: Optional[int] = None,
    notification_message: Optional[str] = None,
    speak: Optional[int] = None,
    speak_message: Optional[str] = None,
    is_active: int = 1,
) -> Optional[Dict[str, Any]]:
    """Update an existing event definition."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM event_definitions WHERE id = ?", (definition_id,))
        current = cursor.fetchone()
        if not current:
            return None
        current_dict = dict(current)

        if not isinstance(data, str):
            data_str = json.dumps(data)
        else:
            data_str = data.strip() if data else "{}"

        clean_holiday = holiday.strip() if holiday and holiday.strip() in ("all_days", "holiday", "not_holiday") else "all_days"
        clean_notify = current_dict.get("notify", 0)
        if notify is not None:
            clean_notify = 1 if notify else 0

        clean_notif_msg = current_dict.get("notification_message", "")
        if notification_message is not None:
            clean_notif_msg = notification_message.strip()

        clean_speak = current_dict.get("speak", 0)
        if speak is not None:
            clean_speak = 1 if speak else 0

        clean_speak_msg = current_dict.get("speak_message", "")
        if speak_message is not None:
            clean_speak_msg = speak_message.strip()

        cursor.execute(
            """
            UPDATE event_definitions
            SET name = ?, type = ?, parameter = ?, use_case = ?, data = ?, holiday = ?, notify = ?, notification_message = ?, speak = ?, speak_message = ?, is_active = ?
            WHERE id = ?
            """,
            (name.strip(), event_type.strip(), parameter.strip(), use_case.strip(), data_str, clean_holiday, clean_notify, clean_notif_msg, clean_speak, clean_speak_msg, int(is_active), definition_id),
        )
        if cursor.rowcount == 0:
            return None
        cursor.execute("SELECT * FROM event_definitions WHERE id = ?", (definition_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def db_delete_event_definition(definition_id: int) -> bool:
    """Delete an event definition by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM event_definitions WHERE id = ?", (definition_id,))
        return cursor.rowcount > 0


# ==============================================================================
# Holidays Management
# ==============================================================================

def db_list_holidays() -> List[Dict[str, Any]]:
    """List all holidays ordered by date ascending."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, date, name, created_at FROM holidays ORDER BY date ASC")
        return [dict(row) for row in cursor.fetchall()]


def db_get_holiday(holiday_id: int) -> Optional[Dict[str, Any]]:
    """Get a holiday by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, date, name, created_at FROM holidays WHERE id = ?", (holiday_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def db_get_holiday_by_date(date_str: str) -> Optional[Dict[str, Any]]:
    """Get a holiday by its date string (YYYY-MM-DD)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, date, name, created_at FROM holidays WHERE date = ?", (date_str.strip(),))
        row = cursor.fetchone()
        return dict(row) if row else None


def db_create_holiday(date: str, name: Optional[str] = None) -> Dict[str, Any]:
    """Persist a new holiday date (YYYY-MM-DD) into SQLite."""
    clean_date = date.strip()
    try:
        datetime.strptime(clean_date, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date format '{date}'. Expected YYYY-MM-DD.")

    clean_name = name.strip() if name else ""
    now_utc = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, date, name, created_at FROM holidays WHERE date = ?", (clean_date,))
        existing = cursor.fetchone()
        if existing:
            raise ValueError(f"Holiday for date '{clean_date}' already exists.")

        cursor.execute(
            """
            INSERT INTO holidays (date, name, created_at)
            VALUES (?, ?, ?)
            """,
            (clean_date, clean_name, now_utc),
        )
        new_id = cursor.lastrowid
        cursor.execute("SELECT id, date, name, created_at FROM holidays WHERE id = ?", (new_id,))
        row = cursor.fetchone()
        return dict(row)


def db_delete_holiday(holiday_id: int) -> bool:
    """Delete a holiday by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM holidays WHERE id = ?", (holiday_id,))
        return cursor.rowcount > 0


def db_is_holiday(date_str: str) -> bool:
    """Check if a date (YYYY-MM-DD) exists in the holidays table."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM holidays WHERE date = ?", (date_str.strip(),))
        return cursor.fetchone() is not None


# ==========================================
# Heating State & Maps Operations
# ==========================================

def _format_heating_map(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    """Format heating map database row, parsing rules JSON."""
    if not row:
        return None
    d = dict(row)
    if "rules" in d and isinstance(d["rules"], str):
        try:
            d["rules"] = json.loads(d["rules"])
        except Exception:
            d["rules"] = {}
    return d


def db_list_heating_maps() -> List[Dict[str, Any]]:
    """Retrieve all heating maps ordered by is_default DESC, name ASC."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM heating_maps ORDER BY is_default DESC, name ASC")
        return [_format_heating_map(row) for row in cursor.fetchall() if row]


def db_get_heating_map(map_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve a single heating map by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM heating_maps WHERE id = ?", (map_id,))
        row = cursor.fetchone()
        return _format_heating_map(row)


def db_get_heating_map_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Retrieve a heating map by name (case-insensitive)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM heating_maps WHERE LOWER(name) = LOWER(?)", (name.strip(),))
        row = cursor.fetchone()
        return _format_heating_map(row)


def db_get_default_heating_map() -> Optional[Dict[str, Any]]:
    """Retrieve the designated default heating map."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM heating_maps WHERE is_default = 1 LIMIT 1")
        row = cursor.fetchone()
        if not row:
            cursor.execute("SELECT * FROM heating_maps ORDER BY id ASC LIMIT 1")
            row = cursor.fetchone()
        return _format_heating_map(row)


def db_create_heating_map(
    name: str,
    description: str = "",
    rules: Any = "{}",
    is_default: int = 0,
) -> Dict[str, Any]:
    """Create and persist a new heating map."""
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Heating map name cannot be empty")

    existing = db_get_heating_map_by_name(clean_name)
    if existing:
        raise ValueError(f"Heating map '{clean_name}' already exists")

    if isinstance(rules, (dict, list)):
        rules_str = json.dumps(rules)
    elif isinstance(rules, str):
        rules_str = rules.strip() or "{}"
    else:
        rules_str = "{}"

    now_utc = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()

        # If there are no maps yet, make this one default
        cursor.execute("SELECT COUNT(*) FROM heating_maps")
        count = cursor.fetchone()[0]
        make_default = 1 if (is_default == 1 or count == 0) else 0

        if make_default == 1:
            conn.execute("UPDATE heating_maps SET is_default = 0")

        cursor.execute(
            """
            INSERT INTO heating_maps (name, description, rules, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (clean_name, description.strip() if description else "", rules_str, make_default, now_utc, now_utc),
        )
        new_id = cursor.lastrowid
        cursor.execute("SELECT * FROM heating_maps WHERE id = ?", (new_id,))
        created = _format_heating_map(cursor.fetchone())

        # If heating_state has no active_map_id, set it
        cursor.execute("SELECT active_map_id FROM heating_state WHERE id = 1")
        state_row = cursor.fetchone()
        if not state_row or state_row[0] is None:
            conn.execute("UPDATE heating_state SET active_map_id = ? WHERE id = 1", (new_id,))

        return created


def db_update_heating_map(
    map_id: int,
    name: str,
    description: Optional[str] = None,
    rules: Optional[Any] = None,
    is_default: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Update an existing heating map."""
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Heating map name cannot be empty")

    existing = db_get_heating_map(map_id)
    if not existing:
        return None

    # Check for name uniqueness
    by_name = db_get_heating_map_by_name(clean_name)
    if by_name and by_name["id"] != map_id:
        raise ValueError(f"Heating map with name '{clean_name}' already exists")

    now_utc = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()

        if is_default == 1:
            conn.execute("UPDATE heating_maps SET is_default = 0 WHERE id != ?", (map_id,))

        rules_str = existing["rules"]
        if rules is not None:
            if isinstance(rules, (dict, list)):
                rules_str = json.dumps(rules)
            elif isinstance(rules, str):
                rules_str = rules.strip() or "{}"

        desc_str = description.strip() if description is not None else existing.get("description", "")
        def_val = is_default if is_default is not None else existing.get("is_default", 0)

        cursor.execute(
            """
            UPDATE heating_maps
            SET name = ?, description = ?, rules = ?, is_default = ?, updated_at = ?
            WHERE id = ?
            """,
            (clean_name, desc_str, rules_str, def_val, now_utc, map_id),
        )
        cursor.execute("SELECT * FROM heating_maps WHERE id = ?", (map_id,))
        return _format_heating_map(cursor.fetchone())


def db_delete_heating_map(map_id: int) -> bool:
    """Delete a heating map by ID."""
    existing = db_get_heating_map(map_id)
    if not existing:
        return False

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM heating_maps WHERE id = ?", (map_id,))

        # If deleted map was default, appoint another map as default
        if existing.get("is_default") == 1:
            cursor.execute("SELECT id FROM heating_maps ORDER BY id ASC LIMIT 1")
            remaining = cursor.fetchone()
            if remaining:
                cursor.execute("UPDATE heating_maps SET is_default = 1 WHERE id = ?", (remaining[0],))

        # If deleted map was active in heating_state, set to current default
        cursor.execute("SELECT active_map_id FROM heating_state WHERE id = 1")
        st_row = cursor.fetchone()
        if st_row and st_row[0] == map_id:
            cursor.execute("SELECT id FROM heating_maps WHERE is_default = 1 LIMIT 1")
            def_row = cursor.fetchone()
            next_active = def_row[0] if def_row else None
            cursor.execute("UPDATE heating_state SET active_map_id = ? WHERE id = 1", (next_active,))

        return True


def db_set_default_heating_map(map_id: int) -> Optional[Dict[str, Any]]:
    """Set a specific heating map as default."""
    existing = db_get_heating_map(map_id)
    if not existing:
        return None

    now_utc = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE heating_maps SET is_default = 0")
        cursor.execute("UPDATE heating_maps SET is_default = 1, updated_at = ? WHERE id = ?", (now_utc, map_id))
        cursor.execute("SELECT * FROM heating_maps WHERE id = ?", (map_id,))
        return _format_heating_map(cursor.fetchone())


def db_set_active_heating_map(map_id: int) -> Dict[str, Any]:
    """Set the currently active heating map."""
    target_map = db_get_heating_map(map_id)
    if not target_map:
        raise ValueError(f"Heating map #{map_id} not found")

    now_utc = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE heating_state
            SET active_map_id = ?, updated_at = ?
            WHERE id = 1
            """,
            (map_id, now_utc),
        )
    return db_get_heating_state()


def db_get_heating_state() -> Dict[str, Any]:
    """
    Retrieve heating system state (row id=1), including active heating map.
    Notice: heating on/off state is NOT stored in SQLite db. Instead, it is dynamically
    queried from the configured heating helper entity in Home Assistant.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM heating_state WHERE id = 1")
        row = cursor.fetchone()
        if not row:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT OR REPLACE INTO heating_state (id, deactivated_until, active_map_id, updated_at)
                VALUES (1, NULL, NULL, ?)
                """,
                (now_utc,),
            )
            cursor.execute("SELECT * FROM heating_state WHERE id = 1")
            row = cursor.fetchone()

        state_dict = dict(row)

        # Helper entity & dynamic live state from Home Assistant
        helper_entity = db_get_setting("heating_helper_entity", "") or ""
        state_dict["helper_entity"] = helper_entity
        dynamic_state = "off"
        if helper_entity:
            try:
                from app.homeassistant import get_entity_state
            except ImportError:
                from homeassistant import get_entity_state
            try:
                st = get_entity_state(helper_entity)
                if st and st.strip().lower() in ("on", "heat"):
                    dynamic_state = "on"
            except Exception as exc:
                logger.warning("Could not query helper entity '%s' state: %s", helper_entity, exc)

        state_dict["state"] = dynamic_state
        state_dict["helper_state"] = dynamic_state

        # Check active map
        active_map_id = state_dict.get("active_map_id")
        active_map = None
        if active_map_id:
            active_map = db_get_heating_map(active_map_id)

        # Fallback to default map if none active
        if not active_map:
            active_map = db_get_default_heating_map()
            if active_map:
                conn.execute("UPDATE heating_state SET active_map_id = ? WHERE id = 1", (active_map["id"],))
                state_dict["active_map_id"] = active_map["id"]

        state_dict["active_map"] = active_map
        return state_dict


def db_set_heating_state(
    state: Optional[str] = None,
    deactivated_until: Optional[str] = None,
    active_map_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Update heating system settings (deactivated_until / active_map_id).
    Notice: heating on/off state is NOT persisted in SQLite; state is derived dynamically
    from the configured helper entity in Home Assistant.
    """
    now_utc = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()

        current = db_get_heating_state()
        map_id_val = active_map_id if active_map_id is not None else current.get("active_map_id")

        cursor.execute(
            """
            INSERT INTO heating_state (id, deactivated_until, active_map_id, updated_at)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                deactivated_until = excluded.deactivated_until,
                active_map_id = excluded.active_map_id,
                updated_at = excluded.updated_at
            """,
            (deactivated_until, map_id_val, now_utc),
        )

    return db_get_heating_state()


def db_get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve a single system setting by key."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return str(row[0]) if row else default


def db_set_setting(key: str, value: Any) -> Dict[str, Any]:
    """Set or update a system setting in SQLite."""
    now_utc = datetime.now(timezone.utc).isoformat()
    val_str = str(value)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, val_str, now_utc),
        )
        return {"key": key, "value": val_str, "updated_at": now_utc}


def db_get_all_settings() -> Dict[str, Any]:
    """Retrieve all system settings as a dictionary."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        rows = cursor.fetchall()
        result = {}
        for r in rows:
            val = r[1]
            if val.isdigit():
                result[r[0]] = int(val)
            else:
                try:
                    result[r[0]] = float(val)
                except ValueError:
                    if (val.startswith("[") and val.endswith("]")) or (val.startswith("{") and val.endswith("}")):
                        try:
                            result[r[0]] = json.loads(val)
                        except Exception:
                            try:
                                import ast
                                result[r[0]] = ast.literal_eval(val)
                            except Exception:
                                result[r[0]] = val
                    else:
                        result[r[0]] = val
        return result


def db_list_heating_calendar() -> List[Dict[str, Any]]:
    """Retrieve all heating calendar slots with joined heating map name."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.id, c.day_of_week, c.start_time, c.end_time, c.map_id, c.created_at,
                   m.name as map_name, m.is_default as map_is_default, m.description as map_description
            FROM heating_calendar c
            LEFT JOIN heating_maps m ON c.map_id = m.id
            ORDER BY c.day_of_week ASC, c.start_time ASC
            """
        )
        return [dict(r) for r in cursor.fetchall() if r]


def db_set_heating_calendar_day(day_of_week: int, slots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Replace all time slots for a given day_of_week (0-7).
    Normalizes '00:00' end times to '24:00' and sorts by start_time.
    """
    if day_of_week < 0 or day_of_week > 7:
        raise ValueError("day_of_week must be between 0 (Monday) and 7 (Holidays)")

    now_utc = datetime.now(timezone.utc).isoformat()
    clean_slots = []
    for s in slots:
        start_t = str(s.get("start_time", "00:00")).strip()
        end_t = str(s.get("end_time", "24:00")).strip()
        if end_t in ("00:00", "0:00"):
            end_t = "24:00"
        map_id = int(s.get("map_id"))
        clean_slots.append((day_of_week, start_t, end_t, map_id, now_utc))

    clean_slots.sort(key=lambda x: x[1])

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM heating_calendar WHERE day_of_week = ?", (day_of_week,))
        cursor.executemany(
            """
            INSERT INTO heating_calendar (day_of_week, start_time, end_time, map_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            clean_slots,
        )

    return [s for s in db_list_heating_calendar() if s["day_of_week"] == day_of_week]


def db_set_heating_calendar_bulk(slots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Bulk update all heating calendar slots."""
    now_utc = datetime.now(timezone.utc).isoformat()
    clean_slots = []
    for s in slots:
        day_of_week = int(s.get("day_of_week", 0))
        if day_of_week < 0 or day_of_week > 7:
            continue
        start_t = str(s.get("start_time", "00:00")).strip()
        end_t = str(s.get("end_time", "24:00")).strip()
        if end_t in ("00:00", "0:00"):
            end_t = "24:00"
        map_id = int(s.get("map_id"))
        clean_slots.append((day_of_week, start_t, end_t, map_id, now_utc))

    clean_slots.sort(key=lambda x: (x[0], x[1]))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM heating_calendar")
        cursor.executemany(
            """
            INSERT INTO heating_calendar (day_of_week, start_time, end_time, map_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            clean_slots,
        )

    return db_list_heating_calendar()


def db_resolve_current_heating_map(target_dt: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """
    Review weekly heating calendar and determine which heating map applies for the given datetime.
    Uses target_dt or current local time in Europe/Madrid.
    1. If target_dt is a public holiday, checks slots where day_of_week = 7 (Holidays).
    2. Otherwise checks slots where day_of_week = target_dt.weekday() (0=Mon .. 6=Sun).
    3. Finds slot matching start_time <= current_time < end_time.
    4. Falls back to default heating map if no slot matches.
    """
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Madrid")
    dt = target_dt or datetime.now(tz)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    else:
        dt = dt.astimezone(tz)

    date_str = dt.strftime("%Y-%m-%d")
    time_str = dt.strftime("%H:%M")
    is_holiday = db_is_holiday(date_str)
    day_of_week = dt.weekday()

    with get_db() as conn:
        cursor = conn.cursor()

        # If today is a holiday, first check holiday slots (day_of_week = 7)
        if is_holiday:
            cursor.execute(
                """
                SELECT m.*
                FROM heating_calendar c
                JOIN heating_maps m ON c.map_id = m.id
                WHERE c.day_of_week = 7 AND c.start_time <= ? AND (c.end_time > ? OR c.end_time = '24:00')
                ORDER BY c.start_time ASC
                LIMIT 1
                """,
                (time_str, time_str),
            )
            row = cursor.fetchone()
            if row:
                return _format_heating_map(row)

        # Look up regular day of week slot
        cursor.execute(
            """
            SELECT m.*
            FROM heating_calendar c
            JOIN heating_maps m ON c.map_id = m.id
            WHERE c.day_of_week = ? AND c.start_time <= ? AND (c.end_time > ? OR c.end_time = '24:00')
            ORDER BY c.start_time ASC
            LIMIT 1
            """,
            (day_of_week, time_str, time_str),
        )
        row = cursor.fetchone()
        if row:
            return _format_heating_map(row)

    # Fallback to default heating map
    return db_get_default_heating_map()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    init_db()
    print(f"Database successfully initialized at: {get_db_path()}")
