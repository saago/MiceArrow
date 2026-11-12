import ctypes
import os
import queue
import unittest
from ctypes import wintypes

from automation import HOTKEYS
from desktop_integration import GlobalHotkey, TrayIcon, foreground_executable


@unittest.skipUnless(os.name == "nt", "Windows desktop integration required")
class DesktopIntegrationTests(unittest.TestCase):
    def test_native_hotkey_registration_dispatch_conflict_and_cleanup(self) -> None:
        events: queue.Queue[str] = queue.Queue()
        first = GlobalHotkey(lambda: events.put("next"))
        second = GlobalHotkey(lambda: events.put("second"))
        self.addCleanup(second.close)
        self.addCleanup(first.close)
        shortcut = None
        for candidate in HOTKEYS:
            try:
                first.configure(candidate)
            except OSError:
                continue
            shortcut = candidate
            break
        if shortcut is None:
            self.skipTest("All supported shortcuts are already registered by other applications")
        with self.assertRaises(OSError):
            second.configure(shortcut)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostThreadMessageW.restype = wintypes.BOOL
        self.assertTrue(user32.PostThreadMessageW(first.thread.native_id, 0x0312, 1, 0))
        self.assertEqual(events.get(timeout=2), "next")
        first.configure("")
        self.assertTrue(user32.PostThreadMessageW(first.thread.native_id, 0x0312, 1, 0))
        with self.assertRaises(queue.Empty):
            events.get(timeout=0.15)
        second.configure(shortcut)
        second.close()
        first.configure(shortcut)

    def test_invalid_hotkey_is_rejected(self) -> None:
        service = GlobalHotkey(lambda: None)
        self.addCleanup(service.close)
        with self.assertRaises(ValueError):
            service.configure("Ctrl+A")
        service.close()
        with self.assertRaises(OSError):
            service.configure("Ctrl+Alt+F8")

    def test_foreground_detection_returns_an_executable_or_transient_none(self) -> None:
        executable = foreground_executable()
        if executable is not None:
            self.assertTrue(os.path.isabs(executable))
            self.assertTrue(executable.lower().endswith(".exe"))

    def test_tray_is_ready_before_hide_event_and_stops_cleanly(self) -> None:
        events: queue.Queue[str] = queue.Queue()
        tray = TrayIcon(events.put)
        self.addCleanup(tray.close)
        tray.start()
        event = events.get(timeout=10)
        self.assertEqual(event, "tray_ready", str(tray.error))
        self.assertTrue(tray.icon.visible)
        tray.close()
        self.assertFalse(tray.thread.is_alive())
        self.assertFalse(tray.icon.visible)
