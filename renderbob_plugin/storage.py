import json
from pathlib import Path
from typing import Any, Dict

from .constants import ADDON_ID


def _settings_path() -> Path:
    config_dir = Path.home() / ".config" / ADDON_ID
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "settings.json"


def load_settings() -> Dict[str, Any]:
    path = _settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data: Dict[str, Any]) -> None:
    path = _settings_path()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
