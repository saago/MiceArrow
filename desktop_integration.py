import ctypes
import os
import queue
import threading
from ctypes import wintypes
from typing import Callable

from PIL import Image, ImageDraw

from automation import HOTKEYS


def enable_dpi_awareness() -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
    if not user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
        error = ctypes.get_last_error()
        if error != 5:  # A manifest or the host may already have set process awareness.
            raise ctypes.WinError(error)


def foreground_executable() -> str | None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    window = user32.GetForegroundWindow()
    if not window:
        return None
    pid = wintypes.DWORD()
    if not user32.GetWindowThreadProcessId(window, ctypes.byref(pid)):
        return None  # The foreground window may have closed between the two calls.
    if not pid.value or pid.value == os.getpid():
        return None  # Editing this application's settings should not change the active cursor.
    process = kernel32.OpenProcess(0x1000, False, pid.value)
    if not process:
        error = ctypes.get_last_error()
        if error in (87, 1168):  # The foreground process has already exited.
            return None
        raise ctypes.WinError(error)
    try:
        size = wintypes.DWORD(32768)
        path = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
            error = ctypes.get_last_error()
            if error in (87, 1168):
                return None
            raise ctypes.WinError(error)
        return path.value
    finally:
        kernel32.CloseHandle(process)


class GlobalHotkey:
    """Own RegisterHotKey and its message queue on a thread separate from Tk."""

    def __init__(self, on_next: Callable[[], None]) -> None:
        self.on_next = on_next
        self.requests: queue.Queue[tuple[str, queue.Queue[OSError | None]]] = queue.Queue()
        self.wake = threading.Event()
        self.stopping = threading.Event()
        self.shortcut = ""
        self.thread = threading.Thread(target=self._run, name="MiceArrow-hotkey", daemon=True)
        self.thread.start()

    def configure(self, shortcut: str) -> None:
        if shortcut and shortcut not in HOTKEYS:
            raise ValueError("קיצור המקשים אינו נתמך.")
        if not self.thread.is_alive() or self.stopping.is_set():
            raise OSError("שירות קיצור המקשים אינו פעיל.")
        result: queue.Queue[OSError | None] = queue.Queue(maxsize=1)
        self.requests.put((shortcut, result))
        self.wake.set()
        try:
            error = result.get(timeout=3)
        except queue.Empty as error:
            raise TimeoutError("רישום קיצור המקשים לא הגיב בזמן.") from error
        if error is not None:
            raise error
        self.shortcut = shortcut

    def close(self) -> None:
        self.stopping.set()
        self.wake.set()
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise TimeoutError("לא ניתן לעצור את שירות קיצור המקשים.")

    def _run(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        user32.PeekMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT,
        ]
        user32.PeekMessageW.restype = wintypes.BOOL
        active_id = 0
        active_shortcut = ""
        message = wintypes.MSG()
        try:
            while not self.stopping.is_set():
                self.wake.clear()
                while not self.requests.empty():
                    shortcut, result = self.requests.get_nowait()
                    if shortcut == active_shortcut:
                        result.put(None)
                        continue
                    next_id = 2 if active_id == 1 else 1
                    if shortcut:
                        modifiers, key = HOTKEYS[shortcut]
                        if not user32.RegisterHotKey(None, next_id, modifiers | 0x4000, key):
                            result.put(ctypes.WinError(ctypes.get_last_error()))
                            continue
                    if active_id:
                        user32.UnregisterHotKey(None, active_id)
                    active_id = next_id if shortcut else 0
                    active_shortcut = shortcut
                    result.put(None)
                while user32.PeekMessageW(ctypes.byref(message), None, 0x0312, 0x0312, 1):
                    if message.wParam == active_id:
                        self.on_next()
                self.wake.wait(0.02)
        finally:
            if active_id:
                user32.UnregisterHotKey(None, active_id)


class TrayIcon:
    def __init__(self, emit: Callable[[str], None]) -> None:
        self.emit = emit
        self.icon = None
        self.thread: threading.Thread | None = None
        self.error: Exception | None = None

    def start(self) -> None:
        if self.thread is not None:
            return
        import pystray

        image = Image.new("RGBA", (64, 64))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((1, 1, 62, 62), radius=14, fill="#0284C7")
        draw.polygon(((19, 12), (19, 47), (28, 38), (36, 54), (43, 50), (35, 35), (49, 35)), fill="white")
        self.icon = pystray.Icon(
            "MiceArrow", image, "Mice Arrow",
            menu=pystray.Menu(
                pystray.MenuItem("פתיחת Mice Arrow", lambda: self.emit("show"), default=True),
                pystray.MenuItem("הפרופיל הבא", lambda: self.emit("next")),
                pystray.MenuItem("הפעלת / השהיית מצב אוטומטי", lambda: self.emit("toggle_auto")),
                pystray.MenuItem("שחזור הסמנים המקוריים", lambda: self.emit("restore")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("יציאה", lambda: self.emit("exit")),
            ),
        )
        self.thread = threading.Thread(target=self._run, name="MiceArrow-tray", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        try:
            self.icon.run(setup=self._ready)
        except (OSError, RuntimeError) as error:
            self.error = error
            self.emit("tray_error")

    def _ready(self, icon) -> None:
        try:
            icon.visible = True
        except (OSError, RuntimeError) as error:
            self.error = error
            self.emit("tray_error")
        else:
            self.emit("tray_ready")

    def notify(self, message: str) -> None:
        if self.icon is not None and self.icon.visible:
            self.icon.notify(message, "Mice Arrow")

    def close(self) -> None:
        if self.icon is not None:
            self.icon.visible = False
            self.icon.stop()
        if self.thread is not None:
            self.thread.join(timeout=3)
            if self.thread.is_alive():
                raise TimeoutError("לא ניתן לעצור את סמל מגש המערכת.")
