import collections
import logging
import math
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional


class LogEntry:
    __slots__ = ("id", "timestamp", "level", "logger_name", "message")

    def __init__(self, entry_id: int, timestamp: str, level: str, logger_name: str, message: str):
        self.id = entry_id
        self.timestamp = timestamp
        self.level = level
        self.logger_name = logger_name
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "level": self.level,
            "logger": self.logger_name,
            "message": self.message,
        }


class MemoryLogHandler(logging.Handler):
    """
    In-memory thread-safe ring-buffer log handler that captures log records
    for paginated display in the UI.
    """

    def __init__(self, capacity: int = 5000):
        super().__init__()
        self.capacity = capacity
        self.buffer = collections.deque(maxlen=capacity)
        self.lock = threading.RLock()
        self._id_counter = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            formatted_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
            msg = record.getMessage()

            if record.exc_info and record.exc_text:
                msg = f"{msg}\n{record.exc_text}"

            with self.lock:
                self._id_counter += 1
                entry = LogEntry(
                    entry_id=self._id_counter,
                    timestamp=formatted_time,
                    level=record.levelname,
                    logger_name=record.name,
                    message=msg,
                )
                self.buffer.append(entry)
        except Exception:
            pass

    def get_paginated(
        self,
        page: int = 1,
        page_size: int = 25,
        level: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self.lock:
            entries = list(self.buffer)

        # Reverse entries so newest logs appear first
        entries.reverse()

        # Filter by log level if specified and not 'all'
        if level and level.upper() != "ALL":
            target_level = level.upper()
            entries = [e for e in entries if e.level == target_level]

        # Filter by search string if specified
        if search:
            query = search.lower().strip()
            entries = [
                e
                for e in entries
                if query in e.message.lower() or query in e.logger_name.lower() or query in e.level.lower()
            ]

        total = len(entries)
        total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1

        # Adjust page bounds
        if page > total_pages and total_pages > 0:
            page = total_pages
        if page < 1:
            page = 1

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_slice = entries[start_idx:end_idx]

        return {
            "logs": [e.to_dict() for e in page_slice],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def clear(self) -> None:
        with self.lock:
            self.buffer.clear()


# Global memory log handler instance
memory_log_handler = MemoryLogHandler(capacity=5000)


def setup_logging(backend_dir: Path) -> None:
    """Configure root logger with in-memory buffer."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if memory_log_handler not in root_logger.handlers:
        memory_log_handler.setFormatter(formatter)
        memory_log_handler.setLevel(logging.INFO)
        root_logger.addHandler(memory_log_handler)
