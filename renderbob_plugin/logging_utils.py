from pathlib import Path
from datetime import datetime, timezone

from .constants import ADDON_ID, LOG_FILE_NAME


def _log_path() -> Path:
    log_dir = Path.home() / ".config" / ADDON_ID
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / LOG_FILE_NAME


def log_info(message: str) -> None:
    _write("INFO", message)


def log_error(message: str) -> None:
    _write("ERROR", message)


def _write(level: str, message: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    line = f"{timestamp} [{level}] {message}\n"
    _log_path().open("a", encoding="utf-8").write(line)
