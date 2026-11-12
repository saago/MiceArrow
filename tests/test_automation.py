import json
import tempfile
import unittest
from pathlib import Path

from automation import Settings, executable_key, load_settings, save_settings, target_profile


class AutomationTests(unittest.TestCase):
    def test_missing_settings_preserve_legacy_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(Path(directory) / "missing.json")
        self.assertFalse(settings.auto_enabled)
        self.assertFalse(settings.minimize_on_close)
        self.assertEqual(settings.hotkey, "Ctrl+Alt+F8")
        self.assertEqual(settings.app_profiles, {})

    def test_settings_round_trip(self) -> None:
        settings = Settings(
            auto_enabled=True, hotkey="Ctrl+Shift+F8", minimize_on_close=True, manual_profile_id="manual",
            app_profiles={executable_key(r"C:\Games\Game.exe"): "game"},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_settings(settings, path)
            self.assertEqual(load_settings(path), settings)
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_matching_is_case_insensitive_and_uses_full_executable_path(self) -> None:
        settings = Settings(
            auto_enabled=True, manual_profile_id="manual",
            app_profiles={executable_key(r"C:\Games\Game.exe"): "game"},
        )
        self.assertEqual(target_profile(settings, r"c:\GAMES\game.EXE"), "game")
        self.assertEqual(target_profile(settings, r"D:\Games\Game.exe"), "manual")
        self.assertEqual(target_profile(settings, r"C:\Windows\notepad.exe"), "manual")
        settings.auto_enabled = False
        self.assertIsNone(target_profile(settings, r"C:\Games\Game.exe"))

    def test_loading_normalizes_existing_executable_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({"app_profiles": {r"C:\Games\Game.exe": "game"}}))
            settings = load_settings(path)
        self.assertEqual(settings.app_profiles, {r"c:\games\game.exe": "game"})

    def test_corrupt_settings_are_rejected(self) -> None:
        for raw in (
            [], {"unknown": True}, {"auto_enabled": "yes"}, {"minimize_on_close": 1},
            {"hotkey": "Ctrl+A"}, {"hotkey": []}, {"manual_profile_id": 7},
            {"app_profiles": []}, {"app_profiles": {"game.exe": "game"}},
            {"app_profiles": {r"C:\game.txt": "game"}}, {"app_profiles": {r"C:\game.exe": 1}},
        ):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "settings.json"
                path.write_text(json.dumps(raw))
                with self.assertRaises(ValueError):
                    load_settings(path)
