import ctypes
import json
import os
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageOps


APP_DATA = Path(os.environ.get("APPDATA", Path.home())) / "MiceArrow"
PROFILE_FILE = APP_DATA / "profiles.json"
CURSOR_FILE = APP_DATA / "active.cur"
WORKING_CURSOR_FILE = APP_DATA / "working.ani"
CURSOR_BACKUP_FILE = APP_DATA / "cursor_backup.json"

POINTER_RENAMES = {
    "1 (1).png": "חץ מסגרת טורקיז.png",
    "1 (2).png": "מטוס קרב אפור.png",
    "1 (3).png": "רקטה כתומה.png",
    "1 (4).png": "רקטה מצוירת כחולה ואדומה.png",
    "1 (5).png": "מעבורת חלל.png",
    "1 (6).png": "חללית עם להבת מנוע.png",
    "1 (7).png": "מטה עץ עם נחש ירוק.png",
    "1 (8).png": "שרביט זהוב עם אבן אדומה.png",
    "1 (9).png": "חנית דקה עם חוד כסוף.png",
    "1 (10).png": "שרביט עץ עם ידית מעוקלת.png",
    "1 (11).png": "שרביט עץ מגולף.png",
    "1 (12).png": "חרב זהובה.png",
    "1 (13).png": "חרב קריסטל כחולה.png",
    "1 (14).png": "חרב פיקסלים טורקיז.png",
    "1 (15).png": "חץ מסגרת שחורה.png",
    "1 (16).png": "חץ צבעוני עם סליל זהוב.png",
    "1 (17).png": "חץ קריסטל סגול.png",
    "1 (18).png": "סמל חללית כסוף עם כוכב.png",
    "2 (1).png": "רובה סער שחור וחום.png",
    "2 (2).png": "חנית כוכב כסופה.png",
    "2 (3).png": "רובה שחור קומפקטי.png",
    "2 (4).png": "רקטה צבאית ירוקה.png",
    "2 (5).png": "כדור תחמושת זהוב.png",
    "2 (6).png": "אקדח שחור.png",
    "2 (7).png": "פגיון כסוף מעוטר.png",
    "2 (8).png": "עוגן מתכת.png",
    "2 (9).png": "פטיש כסוף עם ידית עץ.png",
    "2 (10).png": "כדור תחמושת מצויר.png",
    "2 (11).png": "חנית שחורה מעוטרת.png",
    "2 (12).png": "חנית זהובה עם חוד לבן.png",
    "2 (13).png": "פטיש קסום כחול וזהוב.png",
    "2 (14).png": "חרב כסופה עם אבני חן סגולות.png",
    "2 (15).png": "מצטה עם פס אדום.png",
    "2 (16).png": "טיל ירוק עם סנפירים לבנים.png",
    "2 (17).png": "אקדח עתיק עם ידית עץ.png",
    "2 (18).png": "רובה ציד קצר דו קני.png",
    "2 (19).png": "אלה עם ראש קוצים.png",
    "2 (20).png": "רובה קלצניקוב.png",
    "2 (21).png": "רובה צלפים עם כוונת.png",
    "2 (22).png": "משגר רקטות.png",
    "Arrow.png": "חץ תלת ממדי כחול.png",
}


@dataclass
class Profile:
    id: str
    name: str
    image_path: str
    scale: float = 1.0
    color: str = "#FFFFFF"
    hotspot_x: float | None = None
    hotspot_y: float | None = None
    glow_enabled: bool = False
    glow_color: str = "#38BDF8"
    glow_radius: int = 6
    glow_opacity: float = 0.8
    preserve_original_color: bool = False


def load_profiles(path: Path = PROFILE_FILE) -> list[Profile]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        raw: Any = json.load(file)
    if not isinstance(raw, list):
        raise ValueError("קובץ הפרופילים חייב להכיל רשימה.")
    profiles = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("נמצא פרופיל לא תקין.")
        profile = Profile(**item)
        source = Path(profile.image_path)
        if not source.is_file() and source.parent.name.lower() == "pointers":
            renamed = POINTER_RENAMES.get(source.name)
            if renamed is not None and source.with_name(renamed).is_file():
                profile.image_path = str(source.with_name(renamed))
        profiles.append(profile)
    return profiles


def save_profiles(profiles: list[Profile], path: Path = PROFILE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".json.tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump([asdict(profile) for profile in profiles], file, ensure_ascii=False, indent=2)
    temporary_path.replace(path)


def render_cursor(
    source_path: str | Path, scale: float, color: str, preserve_original_color: bool = False
) -> Image.Image:
    if not 0.01 <= scale <= 8.0:
        raise ValueError("הגודל חייב להיות בין 0.01 ל־8.")
    if len(color) != 7 or color[0] != "#":
        raise ValueError("יש להזין צבע בפורמט ‎#RRGGBB.")
    try:
        rgb = tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))
    except ValueError as error:
        raise ValueError("יש להזין צבע בפורמט ‎#RRGGBB.") from error

    with Image.open(source_path) as source:
        image = source.convert("RGBA")
    if image.width > 256 or image.height > 256:
        image.thumbnail((256, 256), Image.Resampling.LANCZOS)

    width = max(1, round(image.width * scale))
    height = max(1, round(image.height * scale))
    if width > 256 or height > 256:
        raise ValueError("הסמן המעובד גדול מדי; הקטן את הגודל.")
    image = image.resize((width, height), Image.Resampling.LANCZOS)

    if preserve_original_color:
        return image
    alpha = image.getchannel("A")
    grayscale = ImageOps.grayscale(image)
    tinted = ImageOps.colorize(grayscale, black=(0, 0, 0), white=rgb).convert("RGBA")
    tinted.putalpha(alpha)
    return tinted


def detect_cursor_tip(image: Image.Image) -> tuple[int, int]:
    """Find the top-left visible pixel, ignoring transparent image padding."""
    alpha = image.convert("RGBA").getchannel("A")
    visible = alpha.point(lambda value: 255 if value >= 128 else 0)
    bounds = visible.getbbox()
    if bounds is None:
        raise ValueError("התמונה אינה מכילה פיקסלים גלויים.")
    left, top, right, _bottom = bounds
    for y in range(top, visible.height):
        for x in range(left, right):
            if visible.getpixel((x, y)):
                return x, y
    raise ValueError("לא ניתן לזהות נקודת שפיץ בתמונה.")


def hotspot_from_normalized(image: Image.Image, x: float, y: float) -> tuple[int, int]:
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise ValueError("נקודת הלחיצה חייבת להיות בתוך התמונה.")
    return round(x * (image.width - 1)), round(y * (image.height - 1))


def render_profile(profile: Profile) -> tuple[Image.Image, tuple[int, int]]:
    image = render_cursor(
        profile.image_path, profile.scale, profile.color, profile.preserve_original_color
    )
    if profile.hotspot_x is not None and profile.hotspot_y is not None:
        hotspot = hotspot_from_normalized(image, profile.hotspot_x, profile.hotspot_y)
    else:
        hotspot = detect_cursor_tip(image)
    if not profile.glow_enabled:
        return image, hotspot
    if not isinstance(profile.glow_radius, int) or not 1 <= profile.glow_radius <= 16:
        raise ValueError("רוחב ההילה חייב להיות בין 1 ל־16 פיקסלים.")
    if not 0.0 <= profile.glow_opacity <= 1.0:
        raise ValueError("עוצמת ההילה חייבת להיות בין 0 ל־100%.")
    try:
        if len(profile.glow_color) != 7 or not profile.glow_color.startswith("#"):
            raise ValueError
        rgb = tuple(int(profile.glow_color[i:i + 2], 16) for i in (1, 3, 5))
    except ValueError as error:
        raise ValueError("צבע ההילה חייב להיות בפורמט #RRGGBB.") from error
    padding = profile.glow_radius * 3
    size = (image.width + padding * 2, image.height + padding * 2)
    if max(size) > 256:
        raise ValueError("הסמן כולל ההילה גדול מ־256 פיקסלים; הקטן את הסמן או את רוחב ההילה.")
    foreground = Image.new("RGBA", size)
    foreground.paste(image, (padding, padding))
    alpha = foreground.getchannel("A")
    # Expand before blurring so even thin cursor strokes have a visible halo.
    halo = alpha.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(profile.glow_radius))
    halo = halo.point(lambda value: round(value * profile.glow_opacity))
    glow = Image.new("RGBA", size, (*rgb, 0))
    glow.putalpha(halo)
    return Image.alpha_composite(glow, foreground), (hotspot[0] + padding, hotspot[1] + padding)


def _cur_bytes(image: Image.Image, hotspot: tuple[int, int]) -> bytes:
    image = image.convert("RGBA")
    width, height = image.size
    if not (1 <= width <= 256 and 1 <= height <= 256):
        raise ValueError("ממדי סמן CUR חייבים להיות בין 1 ל־256 פיקסלים.")
    hot_x, hot_y = hotspot
    if not (0 <= hot_x < width and 0 <= hot_y < height):
        raise ValueError("נקודת הלחיצה נמצאת מחוץ לסמן.")

    pixels = image.load()
    xor_data = bytearray()
    and_data = bytearray()
    mask_row_size = ((width + 31) // 32) * 4
    for y in range(height - 1, -1, -1):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            xor_data.extend((blue, green, red, alpha))
        mask_row = bytearray(mask_row_size)
        for x in range(width):
            if pixels[x, y][3] == 0:
                mask_row[x // 8] |= 0x80 >> (x % 8)
        and_data.extend(mask_row)

    bitmap_size = 40 + len(xor_data) + len(and_data)
    directory = struct.pack("<HHH", 0, 2, 1)
    entry = struct.pack(
        "<BBBBHHII",
        width % 256,
        height % 256,
        0,
        0,
        hot_x,
        hot_y,
        bitmap_size,
        22,
    )
    bitmap_header = struct.pack(
        "<IIIHHIIIIII",
        40,
        width,
        height * 2,
        1,
        32,
        0,
        len(xor_data),
        0,
        0,
        0,
        0,
    )
    return directory + entry + bitmap_header + xor_data + and_data


def _write_bytes_atomically(destination: str | Path, contents: bytes) -> None:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_suffix(destination.suffix + ".tmp")
    temporary_path.write_bytes(contents)
    temporary_path.replace(destination)


def write_cur(image: Image.Image, destination: str | Path, hotspot: tuple[int, int] = (0, 0)) -> None:
    _write_bytes_atomically(destination, _cur_bytes(image, hotspot))


def _riff_chunk(tag: bytes, data: bytes) -> bytes:
    return tag + struct.pack("<I", len(data)) + data + b"\0" * (len(data) % 2)


def write_working_cursor(
    image: Image.Image, destination: str | Path, hotspot: tuple[int, int], color: str = "#38BDF8"
) -> None:
    """Write an animated arrow + activity ring, preserving the arrow's hotspot."""
    ring_size = max(12, min(32, round(max(image.size) * 0.4)))
    if image.width + 2 + ring_size > 256:
        original_size = image.size
        image = image.copy()
        image.thumbnail((256 - ring_size - 2, 256), Image.Resampling.LANCZOS)
        hotspot = (
            round(hotspot[0] * (image.width - 1) / max(1, original_size[0] - 1)),
            round(hotspot[1] * (image.height - 1) / max(1, original_size[1] - 1)),
        )
    left = image.width + 2
    size = (max(image.width, left + ring_size), max(image.height, ring_size + 2))
    frames = bytearray()
    for frame_index in range(12):
        frame = Image.new("RGBA", size)
        frame.paste(image, (0, 0))
        ring = Image.new("RGBA", (ring_size * 4, ring_size * 4))
        draw = ImageDraw.Draw(ring)
        bounds = (6, 6, ring.width - 6, ring.height - 6)
        draw.ellipse(bounds, outline=(120, 144, 164, 120), width=8)
        draw.arc(bounds, frame_index * 30, frame_index * 30 + 110, fill=color, width=9)
        ring = ring.resize((ring_size, ring_size), Image.Resampling.LANCZOS)
        frame.alpha_composite(ring, (left, 1))
        frames.extend(_riff_chunk(b"icon", _cur_bytes(frame, hotspot)))
    header = struct.pack("<9I", 36, 12, 12, 0, 0, 32, 1, 5, 1)
    contents = b"ACON" + _riff_chunk(b"anih", header) + _riff_chunk(b"LIST", b"fram" + frames)
    _write_bytes_atomically(destination, _riff_chunk(b"RIFF", contents))


def _read_cursor_value(winreg: Any, name: str) -> dict[str, Any]:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Control Panel\Cursors", 0, winreg.KEY_QUERY_VALUE
        ) as key:
            value, value_type = winreg.QueryValueEx(key, name)
            return {"exists": True, "value": value, "type": value_type}
    except FileNotFoundError:
        return {"exists": False}


def _load_cursor_backup() -> dict[str, dict[str, Any]]:
    with CURSOR_BACKUP_FILE.open("r", encoding="utf-8") as file:
        raw = json.load(file)
    if not isinstance(raw, dict):
        raise ValueError("גיבוי הגדרות הסמן אינו תקין.")
    # Older releases backed up only Arrow as a single record.
    records = {"Arrow": raw} if "exists" in raw else raw.get("cursors")
    if not isinstance(records, dict) or not records or set(records) - {"Arrow", "AppStarting"}:
        raise ValueError("גיבוי הגדרות הסמן אינו תקין.")
    for record in records.values():
        if not isinstance(record, dict) or not isinstance(record.get("exists"), bool):
            raise ValueError("גיבוי הגדרות הסמן אינו תקין.")
        if record["exists"] and (
            not isinstance(record.get("value"), str) or not isinstance(record.get("type"), int)
        ):
            raise ValueError("גיבוי הגדרות הסמן אינו תקין.")
    return records


def _cursor_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) >= 22 and data[:6] == struct.pack("<HHH", 0, 2, 1):
        return data[6] or 256, data[7] or 256
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"ACON":
        offset = 12
        while offset + 8 <= len(data):
            tag = data[offset:offset + 4]
            length = struct.unpack_from("<I", data, offset + 4)[0]
            end = offset + 8 + length
            if end > len(data):
                break
            if tag == b"LIST" and data[offset + 8:offset + 12] == b"fram":
                frame = offset + 12
                while frame + 8 <= end:
                    frame_length = struct.unpack_from("<I", data, frame + 4)[0]
                    frame_end = frame + 8 + frame_length
                    if frame_end > end:
                        break
                    if data[frame:frame + 4] == b"icon":
                        return _cursor_dimensions(data[frame + 8:frame_end])
                    frame = frame_end + frame_length % 2
            offset = end + length % 2
    raise ValueError("לא ניתן לקרוא את ממדי קובץ הסמן.")


def _load_cursor_exact(user32: Any, path: Path) -> int:
    width, height = _cursor_dimensions(path.read_bytes())
    load_image = user32.LoadImageW
    load_image.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
    ]
    load_image.restype = ctypes.c_void_p
    # Default scheme loading resizes even single-image CUR files to the system cursor metrics.
    handle = load_image(None, str(path), 2, width, height, 0x0010)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def _set_system_cursors(paths: dict[str, Path]) -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetSystemCursor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.SetSystemCursor.restype = ctypes.c_int
    user32.DestroyCursor.argtypes = [ctypes.c_void_p]
    user32.DestroyCursor.restype = ctypes.c_int
    roles = {"Arrow": 32512, "AppStarting": 32650}
    handles: dict[str, int] = {}
    try:
        for name, path in paths.items():
            handles[name] = _load_cursor_exact(user32, path)
        for name, handle in list(handles.items()):
            if not user32.SetSystemCursor(handle, roles[name]):
                raise ctypes.WinError(ctypes.get_last_error())
            del handles[name]  # Windows owns and destroys handles after a successful call.
    finally:
        for handle in handles.values():
            user32.DestroyCursor(handle)


def apply_system_cursor(cursor_path: str | Path, working_path: str | Path | None = None) -> None:
    if os.name != "nt":
        raise OSError("החלת סמן המערכת זמינה ב־Windows בלבד.")
    paths = {"Arrow": Path(cursor_path).resolve()}
    if working_path is not None:
        paths["AppStarting"] = Path(working_path).resolve()
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    import winreg

    previous = {name: _read_cursor_value(winreg, name) for name in paths}
    original_backup = _load_cursor_backup() if CURSOR_BACKUP_FILE.exists() else None
    backup = dict(original_backup or {})
    for name, record in previous.items():
        backup.setdefault(name, record)
    _write_json_atomically(CURSOR_BACKUP_FILE, {"cursors": backup})

    try:
        for name, path in paths.items():
            _write_cursor_value(winreg, name, {"exists": True, "value": str(path), "type": winreg.REG_SZ})
        _refresh_system_cursors()
        _set_system_cursors(paths)
    except (OSError, ValueError):
        for name, record in previous.items():
            _write_cursor_value(winreg, name, record)
        _refresh_system_cursors()
        if original_backup is None:
            CURSOR_BACKUP_FILE.unlink()
        else:
            _write_json_atomically(CURSOR_BACKUP_FILE, {"cursors": original_backup})
        raise


def restore_system_cursors() -> None:
    if os.name != "nt":
        raise OSError("שחזור סמני המערכת זמין ב־Windows בלבד.")

    if CURSOR_BACKUP_FILE.exists():
        previous = _load_cursor_backup()

        import winreg

        current = {name: _read_cursor_value(winreg, name) for name in previous}
        try:
            for name, record in previous.items():
                _write_cursor_value(winreg, name, record)
            _refresh_system_cursors()
        except OSError:
            for name, record in current.items():
                _write_cursor_value(winreg, name, record)
            _refresh_system_cursors()
            raise
        CURSOR_BACKUP_FILE.unlink()
        return

    _refresh_system_cursors()


def _write_cursor_value(winreg: Any, name: str, record: dict[str, Any]) -> None:
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        r"Control Panel\Cursors",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if record["exists"]:
            winreg.SetValueEx(key, name, 0, record["type"], record["value"])
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass


def _write_json_atomically(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False)
    temporary_path.replace(path)


def _refresh_system_cursors() -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    system_parameters_info = user32.SystemParametersInfoW
    system_parameters_info.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
    system_parameters_info.restype = ctypes.c_int
    if not system_parameters_info(0x0057, 0, None, 0):
        error_code = ctypes.get_last_error()
        if error_code:
            raise ctypes.WinError(error_code)
        raise OSError("Windows סירב לרענן את סמני המערכת.")
