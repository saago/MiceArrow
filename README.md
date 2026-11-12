# 🖱️ Mice Arrow

<p align="center"><strong>Create, customize, and switch Windows cursor profiles</strong></p>

<p align="center"><a href="README.md">English</a> · <a href="README.he.md">עברית</a></p>

![Windows](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-GPLv3-blue.svg)
[![Support on Ko-fi](https://img.shields.io/badge/Support%20me-Ko--fi-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/netanelelhadad)

Mice Arrow is a Windows desktop app for creating cursor profiles and applying custom cursors system-wide. Design a cursor from a PNG or ICO image, adjust its size and color, add a glow, set its click point, and switch profiles manually or automatically based on the active application.

> [!NOTE]
> Mice Arrow changes Windows cursor settings; it does not inject DLLs, install hooks, or draw an overlay in games. Applications and games that draw their own cursor may ignore the Windows cursor.

Created by **Netanel Elhadad** · [Nati3210@gmail.com](mailto:Nati3210@gmail.com)

## ✨ Features

- 🎨 Create and save multiple cursor profiles using your own PNG/ICO images or the built-in `Pointers` collection.
- 📏 Customize cursor size (1%–800%), tint, original image colors, click point, and optional glow.
- 👁️ Preview changes live at 1:1 scale without applying them to Windows.
- 🌀 Apply the cursor to Windows' standard arrow and busy-background cursors. The busy cursor combines your custom cursor with an animated ring.
- ⚡ Set a global shortcut to cycle through profiles, assign profiles to applications, and minimize the app to the system tray.
- ↩️ Restore the Windows cursor settings saved before the first application.

> **Cursor size limit:** The cursor image, including its glow, must fit within 256 × 256 pixels. Click the preview to set the click point; automatic tip detection ignores transparent image padding.

## 🚀 Run on Windows

You can download a packaged executable from the project's GitHub Releases, if one is published. Otherwise, build it from source using the instructions below.

To run from source, install Python 3.10 or later and use PowerShell in the project directory:

```powershell
python -m pip install -r requirements.txt
python mice_arrow.py
```

## 🧭 Basic usage

1. Select **New Profile** and give the profile a name.
2. Choose a PNG/ICO file, or select an image from **Ready-made Cursors**.
3. Adjust the size, color, and optional glow. Enable **Preserve original colors** to keep the image's colors.
4. Click the preview to set the cursor's click point, or use automatic tip detection.
5. Save the profile, then click **Apply Cursor to System**. The first application asks for confirmation and saves the previous Windows cursor settings.
6. Use **Restore Original Cursors** at any time to restore those saved settings.

Selecting a saved profile applies it automatically. Applying a profile persists after the app closes and Windows restarts. On Windows sign-in or after reloading the cursor scheme, Windows may resize cursors; apply the profile again if needed. No administrator privileges are normally required.

⌨️ **Keyboard shortcuts:** `Ctrl+S` saves the current profile · `Ctrl+N` creates a profile.

## ⚙️ Automation & system tray

Open **Automation & Settings** to configure:

- ⌨️ **Global profile shortcut:** `Ctrl+Alt+F8` by default; `Ctrl+Shift+F8`, `Ctrl+Alt+Right`, or no shortcut are also available.
- 🪟 **Per-application profiles:** Associate a saved profile with an application's full `.exe` path. Enable automatic switching after applying a manual profile once. Unassigned applications use the last manually applied profile.
- 📥 **System tray:** Minimize the window to the tray and double-click the tray icon to reopen it. The tray menu can switch profiles, pause automation, restore cursors, or exit. Closing the window exits by default; it can be configured to minimize instead.

Automation and hotkeys run only while Mice Arrow is open, including when minimized to the tray. Exiting the app does not restore the cursors automatically. Automatic launch with Windows is not included.

## 📦 Build from source

```powershell
python -m pip install -r requirements-build.txt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

The standalone executable is created at `dist\MiceArrow.exe`. The built-in `Pointers` collection is bundled into the executable; Python is not needed on the computer where it runs.

## 🗂️ Data & tests

User data is stored under `%APPDATA%\MiceArrow`:

| File | Contents |
| --- | --- |
| `profiles.json` | Saved cursor profiles |
| `settings.json` | Automation, application assignments, and last manual profile |
| `active.cur`, `working.ani`, `cursor_backup.json` | Applied cursors and the saved cursor backup |

Run the test suite from the project directory:

```powershell
python -m unittest discover -s tests
```
