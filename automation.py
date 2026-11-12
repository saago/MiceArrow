import json
import ntpath
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cursor_core import APP_DATA, _write_json_atomically


SETTINGS_FILE = APP_DATA / "settings.json"
HOTKEYS = {
    "Ctrl+Alt+F8": (0x0002 | 0x0001, 0x77),
    "Ctrl+Shift+F8": (0x0002 | 0x0004, 0x77),
    "Ctrl+Alt+Right": (0x0002 | 0x0001, 0x27),
}


def executable_key(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(path.strip()))


@dataclass
class Settings:
    auto_enabled: bool = False
    hotkey: str = "Ctrl+Alt+F8"
    minimize_on_close: bool = False
    manual_profile_id: str | None = None
    app_profiles: dict[str, str] = field(default_factory=dict)


def load_settings(path: Path = SETTINGS_FILE) -> Settings:
    if not path.exists():
        return Settings()
    with path.open(encoding="utf-8") as file:
        raw = json.load(file)
    if not isinstance(raw, dict):
        raise ValueError("קובץ הגדרות האוטומציה אינו תקין.")
    if set(raw) - set(Settings.__dataclass_fields__):
        raise ValueError("קובץ הגדרות האוטומציה מכיל שדות לא מוכרים.")
    settings = Settings(**raw)
    validate_settings(settings)
    settings.app_profiles = {executable_key(key): value for key, value in settings.app_profiles.items()}
    return settings


def validate_settings(settings: Settings) -> None:
    if not isinstance(settings.auto_enabled, bool) or not isinstance(settings.minimize_on_close, bool):
        raise ValueError("הגדרות האוטומציה אינן תקינות.")
    if not isinstance(settings.hotkey, str) or settings.hotkey not in ("", *HOTKEYS):
        raise ValueError("קיצור המקשים אינו נתמך.")
    if settings.manual_profile_id is not None and not isinstance(settings.manual_profile_id, str):
        raise ValueError("מזהה הפרופיל הידני אינו תקין.")
    if not isinstance(settings.app_profiles, dict):
        raise ValueError("רשימת שיוכי היישומים אינה תקינה.")
    for path, profile_id in settings.app_profiles.items():
        if (
            not isinstance(path, str) or not ntpath.isabs(path) or not path.lower().endswith(".exe")
            or not isinstance(profile_id, str) or not profile_id
        ):
            raise ValueError("יש לשייך נתיב מלא של קובץ EXE לפרופיל קיים.")


def save_settings(settings: Settings, path: Path = SETTINGS_FILE) -> None:
    validate_settings(settings)
    _write_json_atomically(path, asdict(settings))


def target_profile(settings: Settings, executable: str) -> str | None:
    if not settings.auto_enabled:
        return None
    return settings.app_profiles.get(executable_key(executable), settings.manual_profile_id)
