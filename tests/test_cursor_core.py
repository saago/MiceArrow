import json
import ctypes
import os
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from PIL import Image

from cursor_core import (
    Profile,
    POINTER_RENAMES,
    detect_cursor_tip,
    hotspot_from_normalized,
    load_profiles,
    render_cursor,
    render_profile,
    apply_system_cursor,
    restore_system_cursors,
    _refresh_system_cursors,
    _cursor_dimensions,
    _load_cursor_exact,
    _set_system_cursors,
    save_profiles,
    write_cur,
    write_working_cursor,
)
from mice_arrow import _copy_builtin_pointer


class CursorCoreTests(unittest.TestCase):
    def test_cursor_dimensions_match_both_generated_formats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for size in ((1, 1), (48, 24), (96, 80), (256, 256)):
                for extension, writer in (("cur", write_cur), ("ani", write_working_cursor)):
                    with self.subTest(size=size, extension=extension):
                        path = Path(directory) / f"cursor.{extension}"
                        writer(Image.new("RGBA", size, "white"), path, (0, 0))
                        dimensions = _cursor_dimensions(path.read_bytes())
                        if extension == "cur":
                            self.assertEqual(dimensions, size)
                        else:
                            self.assertTrue(all(1 <= value <= 256 for value in dimensions))

    def test_invalid_cursor_dimensions_are_rejected(self) -> None:
        for contents in (b"", b"invalid", b"RIFF\0\0\0\0ACON", b"\0\0\2\0\1\0"):
            with self.subTest(contents=contents), self.assertRaises(ValueError):
                _cursor_dimensions(contents)

    @unittest.skipUnless(os.name == "nt", "Windows native cursor sizing required")
    def test_exact_native_loader_preserves_dimensions_and_hotspot(self) -> None:
        from ctypes import wintypes

        class IconInfo(ctypes.Structure):
            _fields_ = [
                ("icon", wintypes.BOOL), ("x", wintypes.DWORD), ("y", wintypes.DWORD),
                ("mask", wintypes.HBITMAP), ("color", wintypes.HBITMAP),
            ]

        class Bitmap(ctypes.Structure):
            _fields_ = [
                ("type", wintypes.LONG), ("width", wintypes.LONG), ("height", wintypes.LONG),
                ("stride", wintypes.LONG), ("planes", wintypes.WORD), ("bits", wintypes.WORD),
                ("pixels", ctypes.c_void_p),
            ]

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        user32.GetIconInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(IconInfo)]
        user32.GetIconInfo.restype = wintypes.BOOL
        user32.DestroyCursor.argtypes = [ctypes.c_void_p]
        gdi32.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
        with tempfile.TemporaryDirectory() as directory:
            for size in ((16, 8), (48, 24), (96, 80), (256, 256)):
                for extension, writer in (("cur", write_cur), ("ani", write_working_cursor)):
                    with self.subTest(size=size, extension=extension):
                        path = Path(directory) / f"exact.{extension}"
                        writer(Image.new("RGBA", size, "white"), path, (3, 5))
                        expected_size = _cursor_dimensions(path.read_bytes())
                        handle = _load_cursor_exact(user32, path)
                        info = IconInfo()
                        try:
                            self.assertTrue(user32.GetIconInfo(handle, ctypes.byref(info)))
                            bitmap = Bitmap()
                            self.assertTrue(gdi32.GetObjectW(info.color, ctypes.sizeof(bitmap), ctypes.byref(bitmap)))
                            self.assertEqual((bitmap.width, bitmap.height), expected_size)
                            expected_hotspot = (3, 5) if size[0] != 256 or extension == "cur" else (3, 4)
                            self.assertEqual((info.x, info.y), expected_hotspot)
                        finally:
                            if info.mask:
                                gdi32.DeleteObject(info.mask)
                            if info.color:
                                gdi32.DeleteObject(info.color)
                            user32.DestroyCursor(handle)

    def test_exact_cursor_installation_uses_system_roles_and_transfers_ownership(self) -> None:
        user32 = Mock()
        user32.SetSystemCursor.return_value = 1
        paths = {"Arrow": Path("arrow.cur"), "AppStarting": Path("working.ani")}
        with patch("cursor_core.ctypes.WinDLL", return_value=user32), patch(
            "cursor_core._load_cursor_exact", side_effect=[101, 102]
        ):
            _set_system_cursors(paths)
        self.assertEqual([call.args for call in user32.SetSystemCursor.call_args_list], [(101, 32512), (102, 32650)])
        user32.DestroyCursor.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows errors required")
    def test_failed_installation_releases_unconsumed_cursor_handles(self) -> None:
        user32 = Mock()
        user32.SetSystemCursor.side_effect = [1, 0]
        with (
            patch("cursor_core.ctypes.WinDLL", return_value=user32),
            patch("cursor_core._load_cursor_exact", side_effect=[101, 102]),
            patch("cursor_core.ctypes.get_last_error", return_value=5),
        ):
            with self.assertRaises(OSError):
                _set_system_cursors({"Arrow": Path("arrow.cur"), "AppStarting": Path("working.ani")})
        user32.DestroyCursor.assert_called_once_with(102)

    def test_write_cur_creates_valid_header_and_bitmap_dimensions(self) -> None:
        image = Image.new("RGBA", (16, 12), (255, 0, 0, 255))
        image.putpixel((0, 0), (0, 0, 0, 0))
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "cursor.cur"
            write_cur(image, path, (3, 4))
            contents = path.read_bytes()

        self.assertEqual(struct.unpack_from("<HHH", contents), (0, 2, 1))
        self.assertEqual(contents[6:14], bytes((16, 12, 0, 0, 3, 0, 4, 0)))
        self.assertEqual(struct.unpack_from("<IIIHH", contents, 22), (40, 16, 24, 1, 32))
        self.assertEqual(struct.unpack_from("<HH", contents, 10), (3, 4))
        self.assertGreater(len(contents), 22 + 40 + 16 * 12 * 4)

    def test_detect_cursor_tip_ignores_transparent_padding(self) -> None:
        image = Image.new("RGBA", (20, 18), (0, 0, 0, 0))
        image.putpixel((7, 5), (255, 255, 255, 255))
        image.putpixel((8, 5), (255, 255, 255, 255))
        image.putpixel((6, 6), (255, 255, 255, 255))
        self.assertEqual(detect_cursor_tip(image), (7, 5))

    def test_detect_cursor_tip_rejects_empty_image(self) -> None:
        with self.assertRaises(ValueError):
            detect_cursor_tip(Image.new("RGBA", (8, 8), (0, 0, 0, 0)))

    def test_normalized_hotspot_maps_to_rendered_image(self) -> None:
        self.assertEqual(hotspot_from_normalized(Image.new("RGBA", (20, 10)), 0.5, 1.0), (10, 9))

    def test_render_cursor_scales_and_preserves_transparency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source.png"
            source_image = Image.new("RGBA", (10, 8), (255, 255, 255, 255))
            for x in range(2):
                for y in range(2):
                    source_image.putpixel((x, y), (255, 255, 255, 0))
            source_image.save(source)
            image = render_cursor(source, 2.0, "#00FF00")

        self.assertEqual(image.size, (20, 16))
        self.assertLess(image.getpixel((0, 0))[3], 255)
        self.assertEqual(image.getpixel((10, 8)), (0, 255, 0, 255))

    def test_render_cursor_can_preserve_original_colors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source.png"
            original = Image.new("RGBA", (2, 1))
            original.putpixel((0, 0), (210, 30, 80, 255))
            original.putpixel((1, 0), (20, 120, 240, 96))
            original.save(source)

            preserved = render_cursor(source, 1.0, "#00FF00", preserve_original_color=True)
            tinted = render_cursor(source, 1.0, "#00FF00")

        self.assertEqual(preserved.getpixel((0, 0)), (210, 30, 80, 255))
        self.assertEqual(preserved.getpixel((1, 0)), (20, 120, 240, 96))
        self.assertEqual(tinted.getpixel((0, 0)), (0, 90, 0, 255))
        self.assertEqual(tinted.getpixel((1, 0))[3], 96)

    def test_builtin_pointer_copy_is_persistent_and_rejects_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundled = Path(directory) / "bundled"
            app_data = Path(directory) / "app-data"
            bundled.mkdir()
            source = bundled / "Arrow.png"
            Image.new("RGBA", (2, 2), (25, 50, 75, 255)).save(source)
            with (
                patch("mice_arrow._builtin_pointer_directory", return_value=bundled),
                patch("mice_arrow.APP_DATA", app_data),
            ):
                destination = _copy_builtin_pointer("Arrow.png")
                with self.assertRaises(ValueError):
                    _copy_builtin_pointer("..\\outside.png")

            self.assertEqual(destination, app_data / "Pointers" / "Arrow.png")
            self.assertEqual(destination.read_bytes(), source.read_bytes())

    def test_scale_range_supports_fine_and_large_sizes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source.png"
            Image.new("RGBA", (32, 32), (255, 255, 255, 255)).save(source)
            tiny = render_cursor(source, 0.01, "#FFFFFF")
            small = render_cursor(source, 0.25, "#FFFFFF")
            large = render_cursor(source, 8.0, "#FFFFFF")
        self.assertEqual(tiny.size, (1, 1))
        self.assertEqual(small.size, (8, 8))
        self.assertEqual(large.size, (256, 256))

    def test_profiles_round_trip_as_json(self) -> None:
        profile = Profile("id-1", "משחק", "cursor.png", 1.5, "#FF0000")
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "profiles.json"
            save_profiles([profile], path)
            self.assertEqual(load_profiles(path), [profile])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))[0]["name"], "משחק")

    def test_renamed_pointer_profiles_load_and_existing_copies_are_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pointers = Path(directory) / "Pointers"
            pointers.mkdir()
            old_path = pointers / "Arrow.png"
            new_path = pointers / POINTER_RENAMES[old_path.name]
            Image.new("RGBA", (16, 16), "white").save(new_path)
            profiles_path = Path(directory) / "profiles.json"
            save_profiles([Profile("test", "Old pointer", str(old_path))], profiles_path)
            migrated = load_profiles(profiles_path)[0]
            self.assertEqual(migrated.image_path, str(new_path))
            render_profile(migrated)
            Image.new("RGBA", (16, 16), "red").save(old_path)
            self.assertEqual(load_profiles(profiles_path)[0].image_path, str(old_path))

    def test_all_renamed_pointer_images_exist_and_render(self) -> None:
        pointers = Path(__file__).resolve().parents[1] / "Pointers"
        self.assertEqual(len(POINTER_RENAMES), len(set(POINTER_RENAMES.values())))
        for filename in POINTER_RENAMES.values():
            with self.subTest(filename=filename):
                path = pointers / filename
                self.assertTrue(path.is_file())
                render_profile(Profile("test", filename, str(path), preserve_original_color=True))

    def test_profiles_without_hotspot_remain_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "profiles.json"
            path.write_text(
                '[{"id":"old","name":"ישן","image_path":"cursor.png","scale":1.0,"color":"#FFFFFF"}]',
                encoding="utf-8",
            )
            profile = load_profiles(path)[0]
        self.assertIsNone(profile.hotspot_x)
        self.assertIsNone(profile.hotspot_y)
        self.assertFalse(profile.glow_enabled)
        self.assertEqual(profile.glow_radius, 6)

    def test_glow_preserves_cursor_pixels_and_offsets_hotspot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            original = Image.new("RGBA", (16, 16))
            original.putpixel((4, 3), (255, 255, 255, 255))
            original.save(source)
            profile = Profile("test", "Glow", str(source), glow_enabled=True, glow_radius=2)
            image, hotspot = render_profile(profile)
            self.assertEqual(image.size, (28, 28))
            self.assertEqual(hotspot, (10, 9))
            self.assertEqual(image.getpixel(hotspot), (255, 255, 255, 255))
            halo_pixel = image.getpixel((9, 9))
            self.assertEqual(halo_pixel[:3], (56, 189, 248))
            self.assertGreater(halo_pixel[3], 0)
            self.assertLess(halo_pixel[3], 255)
            profile.glow_opacity = 0
            no_glow, _ = render_profile(profile)
            self.assertEqual(no_glow.getpixel((9, 9))[3], 0)

    def test_glow_keeps_manual_hotspot_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            Image.new("RGBA", (16, 12), "white").save(source)
            profile = Profile(
                "test", "Glow", str(source), hotspot_x=1.0, hotspot_y=0.0,
                glow_enabled=True, glow_radius=3, glow_color="#FF0080", glow_opacity=0.5,
            )
            path = Path(directory) / "profiles.json"
            save_profiles([profile], path)
            self.assertEqual(load_profiles(path), [profile])
            image, hotspot = render_profile(profile)
            self.assertEqual(image.size, (34, 30))
            self.assertEqual(hotspot, (24, 9))

    def test_glow_rejects_invalid_settings_and_oversized_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            Image.new("RGBA", (32, 32), "white").save(source)
            for changes in (
                {"glow_radius": 0}, {"glow_radius": 17}, {"glow_radius": 2.5},
                {"glow_color": "#GG0000"}, {"glow_color": "red"},
                {"glow_opacity": -0.1}, {"glow_opacity": 1.1},
                {"glow_opacity": float("nan")}, {"scale": 8.0},
            ):
                with self.subTest(changes=changes):
                    profile = Profile("test", "Glow", str(source), glow_enabled=True, **changes)
                    with self.assertRaises(ValueError):
                        render_profile(profile)

    def test_partial_alpha_is_not_masked_out_of_cur(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cursor.cur"
            write_cur(Image.new("RGBA", (1, 1), (255, 0, 0, 30)), path)
            self.assertEqual(path.read_bytes()[-4:], b"\0\0\0\0")

    def test_working_cursor_contains_distinct_animated_frames_and_hotspot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "working.ani"
            write_working_cursor(Image.new("RGBA", (20, 24), "white"), path, (3, 5))
            data = path.read_bytes()
        self.assertEqual(data[:4], b"RIFF")
        self.assertEqual(struct.unpack_from("<I", data, 4)[0], len(data) - 8)
        self.assertEqual(data[8:16], b"ACONanih")
        self.assertEqual(struct.unpack_from("<9I", data, 20), (36, 12, 12, 0, 0, 32, 1, 5, 1))
        self.assertEqual(data[56:60], b"LIST")
        self.assertEqual(data[64:68], b"fram")
        offset = 68
        frames = []
        while offset < len(data):
            self.assertEqual(data[offset:offset + 4], b"icon")
            length = struct.unpack_from("<I", data, offset + 4)[0]
            frame = data[offset + 8:offset + 8 + length]
            self.assertEqual(struct.unpack_from("<HHH", frame), (0, 2, 1))
            self.assertEqual(struct.unpack_from("<HH", frame, 10), (3, 5))
            self.assertGreaterEqual(frame[6], 20)
            self.assertGreaterEqual(frame[7], 24)
            frames.append(frame)
            offset += 8 + length + length % 2
        self.assertEqual(len(frames), 12)
        self.assertEqual(len(set(frames)), 12)
        self.assertEqual(offset, len(data))

    @unittest.skipUnless(os.name == "nt", "Windows cursor loader required")
    def test_windows_loads_generated_cur_and_animated_cursor(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.LoadCursorFromFileW.argtypes = [ctypes.c_wchar_p]
        user32.LoadCursorFromFileW.restype = ctypes.c_void_p
        user32.DestroyCursor.argtypes = [ctypes.c_void_p]
        user32.DestroyCursor.restype = ctypes.c_int
        with tempfile.TemporaryDirectory() as directory:
            for extension, writer in (("cur", write_cur), ("ani", write_working_cursor)):
                with self.subTest(extension=extension):
                    path = Path(directory) / f"cursor.{extension}"
                    writer(Image.new("RGBA", (32, 32), "white"), path, (4, 6))
                    handle = user32.LoadCursorFromFileW(str(path))
                    self.assertTrue(handle, f"Windows error {ctypes.get_last_error()}")
                    if handle:
                        self.assertTrue(user32.DestroyCursor(handle))

    def test_large_working_cursor_reserves_space_for_ring_and_scales_hotspot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "working.ani"
            write_working_cursor(Image.new("RGBA", (256, 256), "white"), path, (255, 255))
            data = path.read_bytes()
        frame_start = 76
        self.assertEqual(data[frame_start + 6], 0)  # CUR encodes 256 as zero.
        self.assertEqual(struct.unpack_from("<HH", data, frame_start + 10), (221, 221))

    def test_invalid_scale_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            render_cursor("unused.png", 0.009, "#FFFFFF")

    def test_system_cursor_refresh_uses_supported_flags(self) -> None:
        system_parameters_info = Mock(return_value=1)
        fake_user32 = type("FakeUser32", (), {"SystemParametersInfoW": system_parameters_info})()
        with patch("cursor_core.ctypes.WinDLL", return_value=fake_user32):
            _refresh_system_cursors()
        system_parameters_info.assert_called_once_with(0x0057, 0, None, 0)


@unittest.skipUnless(os.name == "nt", "Windows registry integration required")
class CursorSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.backup = self.root / "backup.json"
        self.arrow = self.root / "active.cur"
        self.working = self.root / "working.ani"
        self.arrow.touch()
        self.working.touch()
        self.original = {
            "Arrow": {"exists": True, "value": r"%SystemRoot%\arrow.cur", "type": 2},
            "AppStarting": {"exists": False},
        }
        self.values = dict(self.original)
        self.addCleanup(patch.stopall)
        patch("cursor_core.CURSOR_BACKUP_FILE", self.backup).start()
        patch("cursor_core._read_cursor_value", side_effect=lambda _reg, name: dict(self.values[name])).start()
        self.write = patch("cursor_core._write_cursor_value", side_effect=self._write).start()
        self.refresh = patch("cursor_core._refresh_system_cursors").start()
        self.set_cursors = patch("cursor_core._set_system_cursors").start()

    def _write(self, _reg: object, name: str, record: dict) -> None:
        self.values[name] = dict(record)

    def test_apply_and_restore_both_roles_without_overwriting_original_backup(self) -> None:
        apply_system_cursor(self.arrow, self.working)
        self.assertEqual(self.values["Arrow"]["value"], str(self.arrow.resolve()))
        self.assertEqual(self.values["AppStarting"]["value"], str(self.working.resolve()))
        self.set_cursors.assert_called_once_with({"Arrow": self.arrow.resolve(), "AppStarting": self.working.resolve()})
        self.assertEqual(json.loads(self.backup.read_text())["cursors"], self.original)
        apply_system_cursor(self.arrow, self.working)
        self.assertEqual(json.loads(self.backup.read_text())["cursors"], self.original)
        restore_system_cursors()
        self.assertEqual(self.values, self.original)
        self.assertFalse(self.backup.exists())

    def test_legacy_backup_is_extended_and_restores_original_arrow(self) -> None:
        legacy = {"exists": True, "value": "original.cur", "type": 1}
        self.backup.write_text(json.dumps(legacy))
        apply_system_cursor(self.arrow, self.working)
        restore_system_cursors()
        self.assertEqual(self.values["Arrow"], legacy)
        self.assertEqual(self.values["AppStarting"], self.original["AppStarting"])

    def test_legacy_backup_can_be_restored_without_applying(self) -> None:
        self.backup.write_text(json.dumps(self.original["Arrow"]))
        restore_system_cursors()
        self.assertEqual([call.args[1] for call in self.write.call_args_list], ["Arrow"])
        self.assertFalse(self.backup.exists())

    def test_refresh_failure_rolls_back_both_roles(self) -> None:
        self.refresh.side_effect = [OSError("refresh failed"), None]
        with self.assertRaisesRegex(OSError, "refresh failed"):
            apply_system_cursor(self.arrow, self.working)
        self.assertEqual(self.values, self.original)
        self.assertFalse(self.backup.exists())

    def test_exact_size_application_failure_rolls_back_registry_and_backup(self) -> None:
        self.set_cursors.side_effect = OSError("native cursor failed")
        with self.assertRaisesRegex(OSError, "native cursor failed"):
            apply_system_cursor(self.arrow, self.working)
        self.assertEqual(self.values, self.original)
        self.assertFalse(self.backup.exists())

    def test_partial_registry_write_failure_rolls_back_both_roles(self) -> None:
        count = 0

        def fail_second_write(reg: object, name: str, record: dict) -> None:
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("write failed")
            self._write(reg, name, record)

        self.write.side_effect = fail_second_write
        with self.assertRaisesRegex(OSError, "write failed"):
            apply_system_cursor(self.arrow, self.working)
        self.assertEqual(self.values, self.original)
        self.assertFalse(self.backup.exists())

    def test_failed_upgrade_keeps_legacy_backup(self) -> None:
        legacy = self.original["Arrow"]
        self.backup.write_text(json.dumps(legacy))
        self.refresh.side_effect = [OSError("refresh failed"), None]
        with self.assertRaises(OSError):
            apply_system_cursor(self.arrow, self.working)
        self.assertEqual(json.loads(self.backup.read_text())["cursors"], {"Arrow": legacy})
        self.assertEqual(self.values, self.original)

    def test_failed_restore_retains_backup_and_active_values(self) -> None:
        apply_system_cursor(self.arrow, self.working)
        active = dict(self.values)
        self.refresh.side_effect = [OSError("restore failed"), None]
        with self.assertRaises(OSError):
            restore_system_cursors()
        self.assertEqual(self.values, active)
        self.assertTrue(self.backup.exists())

    def test_corrupt_backup_does_not_change_registry(self) -> None:
        for raw in ([], {}, {"cursors": {"Wait": {"exists": False}}}, {"exists": True}):
            with self.subTest(raw=raw):
                self.backup.write_text(json.dumps(raw))
                with self.assertRaises(ValueError):
                    apply_system_cursor(self.arrow, self.working)
                self.write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
