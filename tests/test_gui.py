import os
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from automation import Settings, executable_key
from cursor_core import Profile, _cursor_dimensions, render_profile
from mice_arrow import MiceArrowApp, _builtin_pointer_names


@unittest.skipUnless(os.name == "nt", "Windows GUI required")
class GuiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name) / "cursor.png"
        image = Image.new("RGBA", (32, 24))
        for y in range(3, 20):
            for x in range(4, 18):
                image.putpixel((x, y), (255, 255, 255, 255))
        image.save(self.source)
        self.root = tk.Tk()
        self.root.attributes("-alpha", 0)
        self.callback_errors = []
        self.root.report_callback_exception = lambda *error: self.callback_errors.append(error)
        self.addCleanup(patch.stopall)
        patch("mice_arrow.load_settings", return_value=Settings()).start()
        self.save_settings = patch("mice_arrow.save_settings").start()
        with patch("mice_arrow.load_profiles", return_value=[]):
            self.app = MiceArrowApp(self.root)
        self.root.update()
        self.addCleanup(self.app._close)
        self.addCleanup(self._assert_no_callback_errors)
        self.profile = Profile("test", "Test", str(self.source))
        self.app.profiles = [self.profile]
        self.app._refresh_profiles(self.profile.id)
        self.app._preview(quiet=True)

    def _assert_no_callback_errors(self) -> None:
        self.assertEqual(self.callback_errors, [])

    def test_controls_fit_minimum_window(self) -> None:
        self.root.geometry("1040x800")
        self.root.update()
        self.assertLessEqual(self.root.winfo_reqwidth(), 1040)
        self.assertLessEqual(self.root.winfo_reqheight(), 800)
        self.assertGreater(self.app.preview_canvas.winfo_width(), 200)

    def test_primary_action_and_help_use_clear_hebrew_text(self) -> None:
        widgets = list(self.root.winfo_children())
        index = 0
        while index < len(widgets):
            widgets.extend(widgets[index].winfo_children())
            index += 1
        controls = {widget.cget("text"): widget for widget in widgets if "text" in widget.keys()}
        self.assertIn("כשהמחשב עסוק, הסמן המותאם\nמופיע לצד העיגול המסתובב.", controls)
        self.assertNotIn("החלה על Windows", controls)
        self.assertIn("נוצר על ידי נתנאל אלחדד", controls)
        self.assertIn("Nati3210@gmail.com", controls)
        with patch.object(self.app, "_apply_profile") as apply:
            controls["החלת הסמן במערכת"].invoke()
        apply.assert_called_once()

    def test_live_preview_and_glow_profile_settings(self) -> None:
        self.app.glow_enabled_var.set(True)
        self.app.glow_radius_var.set("4")
        self.app.glow_color_var.set("#00FF80")
        self.app.glow_opacity_var.set(60)
        self.root.tk.call("after", 220)
        self.root.update()
        self.assertEqual(self.app.preview_render_size, (56, 48))
        self.assertEqual(self.app.preview_tip, (16, 15))
        profile = self.app._profile_from_form()
        self.assertTrue(profile.glow_enabled)
        self.assertEqual(profile.glow_color, "#00FF80")
        self.assertEqual(profile.glow_opacity, 0.6)

    def test_original_color_preference_is_included_in_profile(self) -> None:
        self.app.preserve_original_color_var.set(True)
        profile = self.app._profile_from_form()
        self.assertTrue(profile.preserve_original_color)
        self.app.preserve_original_color_var.set(False)
        self.assertFalse(self.app._profile_from_form().preserve_original_color)

    def test_builtin_pointer_selection_uses_a_persistent_copy(self) -> None:
        filename = _builtin_pointer_names()[0]
        persistent = Path(self.directory.name) / "Pointers" / filename
        with (
            patch("mice_arrow._copy_builtin_pointer", return_value=persistent) as copy_pointer,
            patch.object(self.app, "_schedule_preview"),
        ):
            self.app.path_var.set(filename)
            self.app._select_builtin_pointer()
        copy_pointer.assert_called_once_with(filename)
        self.assertEqual(self.app.path_var.get(), str(persistent))
        self.assertIsNone(self.app.hotspot_x)
        self.assertIsNone(self.app.hotspot_y)

    def test_pointer_picker_shows_named_thumbnails_and_selects_without_applying(self) -> None:
        self.app._open_pointer_picker()
        window = self.app.pointer_window
        self.app._open_pointer_picker()
        self.assertIs(self.app.pointer_window, window)
        self.root.update()
        tree = next(widget for widget in window.winfo_children() if widget.winfo_class() == "Treeview")
        names = _builtin_pointer_names()
        self.assertEqual(list(tree.get_children()), names)
        self.assertEqual(len(self.app.pointer_images), len(names))
        for filename in names:
            self.assertTrue(tree.item(filename, "image"))
            self.assertEqual(tree.item(filename, "text").strip(), Path(filename).stem)
        filename = names[-1]
        tree.selection_set(filename)
        with (
            patch("mice_arrow.APP_DATA", Path(self.directory.name)),
            patch("mice_arrow.apply_system_cursor") as apply,
        ):
            self.assertTrue(tree.bind("<Return>"))
            actions = next(widget for widget in window.winfo_children() if widget.winfo_class() == "TFrame")
            choose = next(widget for widget in actions.winfo_children() if widget.cget("text") == "בחירה")
            choose.invoke()
            self.root.update()
        self.assertIsNone(self.app.pointer_window)
        self.assertEqual(Path(self.app.path_var.get()).name, filename)
        self.assertTrue(Path(self.app.path_var.get()).is_file())
        apply.assert_not_called()
        self.app._preview(quiet=True)
        self.assertIsNotNone(self.app.preview_bounds)

    def test_pointer_picker_cancel_keeps_form_unchanged(self) -> None:
        before = self.app.path_var.get()
        self.app._open_pointer_picker()
        window = self.app.pointer_window
        self.root.update()
        actions = next(widget for widget in window.winfo_children() if widget.winfo_class() == "TFrame")
        cancel = next(widget for widget in actions.winfo_children() if widget.cget("text") == "ביטול")
        cancel.invoke()
        self.assertIsNone(self.app.pointer_window)
        self.assertEqual(self.app.path_var.get(), before)
        self.assertEqual(self.app.pointer_images, [])

    def test_pointer_picker_reports_image_errors(self) -> None:
        with (
            patch("mice_arrow.Image.open", side_effect=OSError("invalid image")),
            patch("mice_arrow.messagebox.showerror") as showerror,
        ):
            self.app._open_pointer_picker()
        self.assertIsNone(self.app.pointer_window)
        showerror.assert_called_once()

    def test_preview_remains_one_to_one_for_large_cursor_and_small_canvas(self) -> None:
        self.app.scale_var.set("8")
        self.app.preview_canvas.configure(width=210, height=210)
        self.root.geometry("1040x800")
        self.root.update()
        self.app._preview(quiet=True)
        self.assertEqual(self.app.preview_render_size, (256, 192))
        self.assertEqual((self.app.preview_image.width(), self.app.preview_image.height()), (256, 192))
        left, top, right, bottom = self.app.preview_bounds
        self.assertEqual((right - left, bottom - top), (256, 192))
        self.assertIn("1:1", self.app.preview_info_var.get())

    def test_hotspot_click_accounts_for_glow_padding(self) -> None:
        self.app.glow_enabled_var.set(True)
        self.app._preview(quiet=True)
        left, top, _right, _bottom = self.app.preview_bounds
        self.app._choose_hotspot(SimpleNamespace(x=left + 22, y=top + 21))
        self.assertAlmostEqual(self.app.hotspot_x, 4 / 31)
        self.assertAlmostEqual(self.app.hotspot_y, 3 / 23)
        _image, hotspot = render_profile(self.app._profile_from_form())
        self.assertEqual(hotspot, (22, 21))
        self.app.glow_enabled_var.set(False)
        _image, hotspot = render_profile(self.app._profile_from_form())
        self.assertEqual(hotspot, (4, 3))

    def test_glow_padding_cannot_be_chosen_as_hotspot(self) -> None:
        self.app.glow_enabled_var.set(True)
        self.app._preview(quiet=True)
        left, top, _right, _bottom = self.app.preview_bounds
        self.app._choose_hotspot(SimpleNamespace(x=left + 1, y=top + 1))
        self.assertIsNone(self.app.hotspot_x)
        self.assertIsNone(self.app.hotspot_y)

    def test_invalid_live_input_is_visible_without_modal_error(self) -> None:
        self.app.scale_var.set("nan")
        with patch("mice_arrow.messagebox.showerror") as showerror:
            self.app._preview(quiet=True)
        self.assertIsNone(self.app.preview_bounds)
        self.assertTrue(self.app.preview_canvas.find_all())
        showerror.assert_not_called()

    def test_apply_writes_both_cursor_files(self) -> None:
        arrow = Path(self.directory.name) / "active.cur"
        working = Path(self.directory.name) / "working.ani"
        with (
            patch("mice_arrow.CURSOR_FILE", arrow),
            patch("mice_arrow.WORKING_CURSOR_FILE", working),
            patch("mice_arrow.CURSOR_BACKUP_FILE", Path(self.directory.name) / "backup.json"),
            patch("mice_arrow.messagebox.askyesno", return_value=True),
            patch("mice_arrow.apply_system_cursor") as apply,
            patch("mice_arrow.save_profiles"),
        ):
            self.app._apply_profile(self.profile)
        self.assertTrue(arrow.is_file())
        self.assertTrue(working.is_file())
        apply.assert_called_once_with(arrow, working)

    def test_applied_cursor_file_has_exactly_the_preview_dimensions_with_glow(self) -> None:
        self.app.scale_var.set("3")
        self.app.glow_enabled_var.set(True)
        self.app._preview(quiet=True)
        preview_size = (self.app.preview_image.width(), self.app.preview_image.height())
        profile = self.app._profile_from_form()
        arrow = Path(self.directory.name) / "sized.cur"
        with (
            patch("mice_arrow.CURSOR_FILE", arrow),
            patch("mice_arrow.WORKING_CURSOR_FILE", Path(self.directory.name) / "sized.ani"),
            patch("mice_arrow.CURSOR_BACKUP_FILE", self.source),
            patch("mice_arrow.apply_system_cursor"),
            patch("mice_arrow.save_profiles"),
        ):
            self.assertTrue(self.app._apply_profile(profile))
        self.assertEqual(_cursor_dimensions(arrow.read_bytes()), (132, 108))
        self.assertEqual(preview_size, (132, 108))

    def test_cancel_apply_does_not_write_files(self) -> None:
        arrow = Path(self.directory.name) / "active.cur"
        with (
            patch("mice_arrow.CURSOR_FILE", arrow),
            patch("mice_arrow.CURSOR_BACKUP_FILE", Path(self.directory.name) / "backup.json"),
            patch("mice_arrow.messagebox.askyesno", return_value=False),
            patch("mice_arrow.apply_system_cursor") as apply,
        ):
            self.app._apply_profile(self.profile)
        self.assertFalse(arrow.exists())
        apply.assert_not_called()

    def test_auto_switch_matches_app_and_returns_to_last_manual_profile(self) -> None:
        game = Profile("game", "Game", str(self.source))
        self.app.profiles.append(game)
        self.app.settings = Settings(
            auto_enabled=True, manual_profile_id=self.profile.id,
            app_profiles={executable_key(r"C:\Games\game.exe"): game.id},
        )
        self.app.active_profile_id = self.profile.id
        applied = []

        def apply(profile, automatic=False):
            self.assertTrue(automatic)
            self.app.active_profile_id = profile.id
            applied.append(profile.id)
            return True

        with (
            patch("mice_arrow.foreground_executable", side_effect=[
                r"C:\Games\game.exe", r"c:\games\GAME.EXE", None, r"C:\Windows\notepad.exe",
            ]),
            patch.object(self.app, "_apply_profile", side_effect=apply),
        ):
            for _ in range(4):
                self.app._auto_switch()
        self.assertEqual(applied, ["game", "test"])
        self.assertEqual(self.app.current_id, "test")
        self.assertEqual(self.app.settings.manual_profile_id, "test")

    def test_manual_override_lasts_until_foreground_application_changes(self) -> None:
        self.app.settings = Settings(
            auto_enabled=True, manual_profile_id="test", app_profiles={r"c:\game.exe": "game"},
        )
        self.app.last_foreground_exe = r"c:\game.exe"
        self.app.manual_override_exe = r"c:\game.exe"
        self.app.active_profile_id = "test"
        with (
            patch("mice_arrow.foreground_executable", side_effect=[r"C:\game.exe", r"C:\other.exe"]),
            patch.object(self.app, "_apply_profile") as apply,
        ):
            self.app._auto_switch()
            self.assertEqual(self.app.manual_override_exe, r"c:\game.exe")
            self.app._auto_switch()
            self.assertIsNone(self.app.manual_override_exe)
        apply.assert_not_called()

    def test_automatic_apply_does_not_replace_manual_fallback_or_editor(self) -> None:
        game = Profile("game", "Game", str(self.source))
        self.app.settings.manual_profile_id = "test"
        with (
            patch("mice_arrow.CURSOR_FILE", Path(self.directory.name) / "auto.cur"),
            patch("mice_arrow.WORKING_CURSOR_FILE", Path(self.directory.name) / "auto.ani"),
            patch("mice_arrow.CURSOR_BACKUP_FILE", self.source),
            patch("mice_arrow.apply_system_cursor"),
            patch("mice_arrow.save_profiles") as save_profiles,
        ):
            self.assertTrue(self.app._apply_profile(game, automatic=True))
        self.assertEqual(self.app.current_id, "test")
        self.assertEqual(self.app.active_profile_id, "game")
        self.assertEqual(self.app.settings.manual_profile_id, "test")
        save_profiles.assert_not_called()
        self.save_settings.assert_not_called()

    def test_automatic_apply_requires_prior_manual_consent(self) -> None:
        with (
            patch("mice_arrow.CURSOR_BACKUP_FILE", Path(self.directory.name) / "missing.json"),
            patch("mice_arrow.messagebox.askyesno") as ask,
            patch("mice_arrow.apply_system_cursor") as apply,
        ):
            with self.assertRaises(ValueError):
                self.app._apply_profile(self.profile, automatic=True)
        ask.assert_not_called()
        apply.assert_not_called()

    def test_next_profile_cycles_and_wraps(self) -> None:
        second = Profile("second", "Second", str(self.source))
        self.app.profiles.extend([Profile("empty", "New", ""), second])
        self.app.active_profile_id = "test"
        with patch.object(self.app, "_apply_profile") as apply:
            self.app._next_profile()
            self.assertEqual(apply.call_args.args[0], second)
            self.app.active_profile_id = "second"
            self.app._next_profile()
            self.assertEqual(apply.call_args.args[0], self.profile)

    def test_settings_validate_manual_fallback_and_profile_references(self) -> None:
        for updated in (
            Settings(auto_enabled=True),
            Settings(app_profiles={r"c:\game.exe": "deleted"}),
        ):
            with self.subTest(settings=updated):
                with self.assertRaises(ValueError):
                    self.app._commit_settings(updated)
        self.save_settings.assert_not_called()

    def test_hotkey_conflict_does_not_save_settings(self) -> None:
        service = Mock(shortcut="Ctrl+Alt+F8")
        service.configure.side_effect = OSError("shortcut in use")
        self.app.hotkeys = service
        with self.assertRaisesRegex(OSError, "shortcut in use"):
            self.app._commit_settings(Settings(hotkey="Ctrl+Shift+F8"))
        self.assertEqual(self.app.settings.hotkey, "Ctrl+Alt+F8")
        self.save_settings.assert_not_called()

    def test_failed_settings_write_rolls_back_hotkey_registration(self) -> None:
        service = Mock(shortcut="Ctrl+Alt+F8")
        self.app.hotkeys = service
        self.save_settings.side_effect = OSError("disk full")
        with self.assertRaisesRegex(OSError, "disk full"):
            self.app._commit_settings(Settings(hotkey="Ctrl+Shift+F8"))
        self.assertEqual(
            [call.args[0] for call in service.configure.call_args_list],
            ["Ctrl+Shift+F8", "Ctrl+Alt+F8"],
        )
        self.assertEqual(self.app.settings.hotkey, "Ctrl+Alt+F8")

    def test_background_failure_pauses_and_persists_automation(self) -> None:
        self.app.settings.auto_enabled = True
        with (
            patch.object(self.app, "_auto_switch", side_effect=OSError("access denied")),
            patch("mice_arrow.messagebox.showerror") as showerror,
        ):
            self.app._desktop_tick()
        self.assertFalse(self.app.settings.auto_enabled)
        self.save_settings.assert_called_once()
        showerror.assert_called_once()
        self.assertIn("access denied", self.app.status_var.get())

    def test_minimize_waits_for_confirmed_tray_visibility(self) -> None:
        self.app.tray = Mock(error=None)
        self.app._minimize_to_tray()
        self.assertTrue(self.app.hide_pending)
        self.assertNotEqual(self.root.state(), "withdrawn")
        self.app.events.put("tray_ready")
        self.app._desktop_tick()
        self.assertTrue(self.app.tray_ready)
        self.assertEqual(self.root.state(), "withdrawn")
        self.app.events.put("show")
        self.app._desktop_tick()
        self.assertEqual(self.root.state(), "normal")

    def test_tray_failure_keeps_window_accessible(self) -> None:
        self.app.tray = Mock(error=None)
        self.app.tray.start.side_effect = OSError("tray unavailable")
        with patch("mice_arrow.messagebox.showerror") as showerror:
            self.app._minimize_to_tray()
        self.assertFalse(self.app.hide_pending)
        self.assertNotEqual(self.root.state(), "withdrawn")
        showerror.assert_called_once()

    def test_close_preference_minimizes_and_explicit_exit_closes(self) -> None:
        self.app.settings.minimize_on_close = True
        with patch.object(self.app, "_minimize_to_tray") as minimize, patch.object(self.app, "_close") as close:
            self.app._request_close()
            minimize.assert_called_once()
            close.assert_not_called()
            self.app.events.put("exit")
            self.app._desktop_tick()
            close.assert_called_once()

    def test_restore_disables_automation_and_clears_active_profile(self) -> None:
        self.app.settings.auto_enabled = True
        self.app.active_profile_id = "test"
        with patch("mice_arrow.restore_system_cursors") as restore:
            self.app._restore()
        restore.assert_called_once()
        self.assertFalse(self.app.settings.auto_enabled)
        self.assertIsNone(self.app.active_profile_id)

    def test_deleting_manual_profile_removes_mappings_and_pauses_automation(self) -> None:
        self.app.settings = Settings(
            auto_enabled=True, manual_profile_id="test", app_profiles={r"c:\game.exe": "test"},
        )
        with patch("mice_arrow.messagebox.askyesno", return_value=True), patch("mice_arrow.save_profiles"):
            self.app._delete_profile()
        self.assertEqual(self.app.profiles, [])
        self.assertEqual(self.app.settings.app_profiles, {})
        self.assertIsNone(self.app.settings.manual_profile_id)
        self.assertFalse(self.app.settings.auto_enabled)

    def test_settings_dialog_opens_once_and_displays_mappings(self) -> None:
        self.app._open_settings()
        window = self.app.settings_window
        self.app._open_settings()
        self.assertIs(self.app.settings_window, window)
        self.root.update()
        self.assertLessEqual(window.winfo_reqwidth(), 800)
        self.assertLessEqual(window.winfo_reqheight(), 600)

    def test_settings_dialog_saves_executable_mapping_and_preferences(self) -> None:
        self.app.settings.manual_profile_id = "test"
        self.app._open_settings()
        window = self.app.settings_window
        widgets = list(window.winfo_children())
        index = 0
        while index < len(widgets):
            widgets.extend(widgets[index].winfo_children())
            index += 1
        controls = {widget.cget("text"): widget for widget in widgets if "text" in widget.keys()}
        controls["החלפת פרופיל לפי היישום הפעיל"].invoke()
        controls["כפתור הסגירה ימזער למגש במקום לצאת"].invoke()
        with patch("mice_arrow.filedialog.askopenfilename", return_value=r"C:\Games\game.exe"):
            controls["שיוך EXE לפרופיל הנבחר"].invoke()
        with patch("mice_arrow.CURSOR_BACKUP_FILE", self.source):
            controls["שמירה"].invoke()
        self.assertTrue(self.app.settings.auto_enabled)
        self.assertTrue(self.app.settings.minimize_on_close)
        self.assertEqual(self.app.settings.app_profiles, {r"c:\games\game.exe": "test"})
        self.save_settings.assert_called_once()
        self.assertIsNone(self.app.settings_window)

    def test_hotkey_and_tray_events_use_the_same_profile_switch_action(self) -> None:
        with patch.object(self.app, "_next_profile") as next_profile:
            self.app.events.put("next")
            self.app._desktop_tick()
        next_profile.assert_called_once()


if __name__ == "__main__":
    unittest.main()
