"""IoT Backend Test Suite."""
import os
import shutil
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
LIVE_DB_PATH = BACKEND_DIR / "db" / "iot.db"
TEST_DB_PATH = BACKEND_DIR / "db" / "test_suite.db"

# Isolate database during test discovery / execution so tests never mutate production db/iot.db
if "DATABASE_PATH" not in os.environ:
    if LIVE_DB_PATH.exists():
        shutil.copy2(LIVE_DB_PATH, TEST_DB_PATH)
    os.environ["DATABASE_PATH"] = str(TEST_DB_PATH)
