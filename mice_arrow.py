import colorsys
import math
import os
import queue
import shutil
import sys
import tkinter as tk
import uuid
from dataclasses import replace
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageTk

from automation import HOTKEYS, Settings, executable_key, load_settings, save_settings, target_profile
from desktop_integration import GlobalHotkey, TrayIcon, enable_dpi_awareness, foreground_executable
from cursor_core import (
    APP_DATA,
    CURSOR_BACKUP_FILE,
    CURSOR_FILE,
    WORKING_CURSOR_FILE,
    Profile,
    apply_system_cursor,
    load_profiles,
    render_profile,
    restore_system_cursors,
    save_profiles,
    write_cur,
    write_working_cursor,
)


def _builtin_pointer_directory() -> Path:
    application_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return application_root / "Pointers"


def _builtin_pointer_names() -> list[str]:
    directory = _builtin_pointer_directory()
    return sorted(path.name for path in directory.glob("*.png") if path.is_file())


def _copy_builtin_pointer(filename: str) -> Path:
    if Path(filename).name != filename or not filename.lower().endswith(".png"):
        raise ValueError("יש לבחור סמן מובנה מהרשימה.")
    source = _builtin_pointer_directory() / filename
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = APP_DATA / "Pointers" / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


class MiceArrowApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Mice Arrow — התאמת סמן")
        self.root.geometry("1120x820")
        self.root.minsize(1040, 800)
        self.profiles = load_profiles()
        self.settings = load_settings()
        self.active_profile_id: str | None = None
        self.events: queue.Queue[str] = queue.Queue()
        self.hotkeys: GlobalHotkey | None = None
        self.tray: TrayIcon | None = None
        self.desktop_job: str | None = None
        self.tray_ready = False
        self.hide_pending = False
        self.closing = False
        self.settings_window: tk.Toplevel | None = None
        self.pointer_window: tk.Toplevel | None = None
        self.pointer_images: list[ImageTk.PhotoImage] = []
        self.last_foreground_exe: str | None = None
        self.manual_override_exe: str | None = None
        self.current_id: str | None = None
        self.preview_image: ImageTk.PhotoImage | None = None
        self.wheel_image: ImageTk.PhotoImage | None = None
        self.hotspot_x: float | None = None
        self.hotspot_y: float | None = None
        self.hotspot_image_path = ""
        self.preview_bounds: tuple[int, int, int, int] | None = None
        self.preview_tip = (0, 0)
        self.preview_source_size = (1, 1)
        self.preview_render_size = (1, 1)
        self.preview_padding = 0
        self.preview_job: str | None = None
        self.preview_light = False

        self.name_var = tk.StringVar()
        self.path_var = tk.StringVar()
        self.scale_var = tk.StringVar(value="1.0")
        self.scale_percent_var = tk.StringVar(value="100%")
        self.color_var = tk.StringVar(value="#FFFFFF")
        self.preserve_original_color_var = tk.BooleanVar(value=False)
        self.glow_enabled_var = tk.BooleanVar(value=False)
        self.glow_color_var = tk.StringVar(value="#38BDF8")
        self.glow_radius_var = tk.StringVar(value="6")
        self.glow_opacity_var = tk.DoubleVar(value=80)
        self.preview_info_var = tk.StringVar(value="תצוגה חיה")
        self.profile_count_var = tk.StringVar()
        self.status_var = tk.StringVar(value="בחירת פרופיל תחיל את הסמן שלו במערכת.")
        self.color_var.trace_add("write", self._update_color_wheel_marker)

        self._build_ui()
        self.scale_var.trace_add("write", self._sync_scale_controls)
        for variable in (
            self.path_var, self.scale_var, self.color_var, self.glow_enabled_var,
            self.preserve_original_color_var, self.glow_color_var, self.glow_radius_var,
            self.glow_opacity_var,
        ):
            variable.trace_add("write", self._schedule_preview)
        self._sync_scale_controls()
        self._refresh_profiles()
        self._clear_preview("צור פרופיל ובחר תמונת סמן")
        self.root.bind("<Control-s>", lambda _event: self._save_current())
        self.root.bind("<Control-n>", lambda _event: self._new_profile())
        self.root.protocol("WM_DELETE_WINDOW", self._request_close)
        self.root.bind("<Unmap>", self._window_minimized)

    def start_desktop_services(self) -> None:
        self.hotkeys = GlobalHotkey(lambda: self.events.put("next"))
        try:
            self.hotkeys.configure(self.settings.hotkey)
        except OSError as error:
            messagebox.showerror(
                "קיצור המקשים אינו זמין",
                f"{error}\nניתן לבחור קיצור אחר בחלון ״אוטומציה והגדרות״.",
            )
        manual = next((profile for profile in self.profiles if profile.id == self.settings.manual_profile_id), None)
        if manual is not None:
            self._refresh_profiles(manual.id)
        elif self.settings.auto_enabled:
            self.settings.auto_enabled = False
            self.status_var.set("האוטומציה הושהתה: יש להחיל פרופיל ידני קיים לפני הפעלתה.")
        self._desktop_tick()

    def _desktop_tick(self) -> None:
        if self.desktop_job is not None:
            self.root.after_cancel(self.desktop_job)
        self.desktop_job = None
        for _ in range(50):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "exit":
                self._close()
                return
            if event == "show":
                self._show_window()
            elif event == "next":
                self._next_profile()
            elif event == "restore":
                self._restore()
            elif event == "toggle_auto":
                self._toggle_auto()
            elif event == "tray_ready":
                self.tray_ready = True
                if self.hide_pending:
                    self.hide_pending = False
                    self.root.withdraw()
            elif event == "tray_error":
                self.hide_pending = False
                self.tray_ready = False
                self._show_window()
                messagebox.showerror("מגש המערכת אינו זמין", str(self.tray.error) if self.tray else "")
        if self.settings.auto_enabled:
            try:
                self._auto_switch()
            except (OSError, ValueError) as error:
                self.settings.auto_enabled = False
                text = f"האוטומציה הושהתה: {error}"
                try:
                    save_settings(self.settings)
                except (OSError, ValueError) as save_error:
                    text += f"\nשמירת ההשהיה נכשלה: {save_error}"
                self.status_var.set(text)
                self._show_window()
                messagebox.showerror("החלפה אוטומטית נכשלה", text)
        if not self.closing:
            self.desktop_job = self.root.after(250, self._desktop_tick)

    def _auto_switch(self) -> None:
        executable = foreground_executable()
        if executable is None:
            return
        key = executable_key(executable)
        if key != self.last_foreground_exe:
            self.manual_override_exe = None
            self.last_foreground_exe = key
        if key == self.manual_override_exe:
            return
        profile_id = target_profile(self.settings, executable)
        if profile_id == self.active_profile_id and profile_id is not None:
            return
        profile = next((item for item in self.profiles if item.id == profile_id), None)
        if profile is None:
            raise ValueError("הפרופיל המשויך או הפרופיל הידני אינם קיימים. יש לעדכן את הגדרות האוטומציה.")
        self._apply_profile(profile, automatic=True)

    def _next_profile(self) -> None:
        profiles = [profile for profile in self.profiles if profile.image_path]
        if not profiles:
            self._show_window()
            messagebox.showinfo("מעבר בין פרופילים", "יש לשמור לפחות פרופיל אחד עם תמונת סמן.")
            return
        index = next((i for i, profile in enumerate(profiles) if profile.id == self.active_profile_id), -1)
        self._apply_profile(profiles[(index + 1) % len(profiles)])

    def _toggle_auto(self) -> None:
        try:
            updated = replace(self.settings, auto_enabled=not self.settings.auto_enabled)
            self._commit_settings(updated)
            self.status_var.set("החלפה אוטומטית פעילה." if updated.auto_enabled else "החלפה אוטומטית מושהית.")
            if self.tray is not None:
                self.tray.notify(self.status_var.get())
        except (OSError, ValueError) as error:
            self._show_window()
            messagebox.showerror("שינוי מצב האוטומציה נכשל", str(error))

    def _commit_settings(self, updated: Settings) -> None:
        ids = {profile.id for profile in self.profiles}
        if updated.auto_enabled and (
            updated.manual_profile_id not in ids or not CURSOR_BACKUP_FILE.exists()
        ):
            raise ValueError("יש להחיל פרופיל ידני ולאשר את שינוי סמני Windows לפני הפעלת האוטומציה.")
        if set(updated.app_profiles.values()) - ids:
            raise ValueError("אחד הפרופילים המשויכים כבר אינו קיים. יש להסיר את השיוך.")
        previous_hotkey = self.hotkeys.shortcut if self.hotkeys is not None else self.settings.hotkey
        if self.hotkeys is not None:
            self.hotkeys.configure(updated.hotkey)
        try:
            save_settings(updated)
        except (OSError, ValueError):
            if self.hotkeys is not None:
                self.hotkeys.configure(previous_hotkey)
            raise
        self.settings = updated
        self.manual_override_exe = None

    def _window_minimized(self, event: tk.Event) -> None:
        if event.widget is self.root and self.root.state() == "iconic" and not self.closing:
            self._minimize_to_tray()

    def _minimize_to_tray(self) -> None:
        self.hide_pending = True
        if self.tray_ready:
            self.hide_pending = False
            self.root.withdraw()
            return
        try:
            if self.tray is None:
                self.tray = TrayIcon(self.events.put)
            if self.tray.error is not None:
                self.tray.close()
                self.tray = TrayIcon(self.events.put)
            self.tray.start()
        except (OSError, RuntimeError, ImportError) as error:
            self.hide_pending = False
            self._show_window()
            messagebox.showerror("מזעור למגש נכשל", str(error))

    def _show_window(self) -> None:
        self.hide_pending = False
        self.root.deiconify()
        self.root.lift()

    def _request_close(self) -> None:
        if self.settings.minimize_on_close:
            self._minimize_to_tray()
        else:
            self._close()

    def _open_settings(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        window = tk.Toplevel(self.root)
        self.settings_window = window
        window.title("Mice Arrow — אוטומציה והגדרות")
        window.geometry("800x600")
        window.minsize(720, 560)
        window.configure(background="#0F172A")
        window.transient(self.root)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)
        auto_var = tk.BooleanVar(value=self.settings.auto_enabled)
        close_var = tk.BooleanVar(value=self.settings.minimize_on_close)
        hotkey_var = tk.StringVar(value=self.settings.hotkey or "ללא")
        ttk.Checkbutton(frame, text="החלפת פרופיל לפי היישום הפעיל", variable=auto_var).grid(row=0, column=0, sticky="e")
        ttk.Label(
            frame, text="יישום ללא שיוך יחזיר את הפרופיל הידני האחרון. יש להחיל אותו לפני הפעלת האוטומציה.",
            anchor="e", wraplength=700,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 10))
        options = ttk.Frame(frame)
        options.grid(row=2, column=0, sticky="ew")
        ttk.Combobox(
            options, textvariable=hotkey_var, values=(*HOTKEYS, "ללא"), state="readonly", width=22,
        ).pack(side="left")
        ttk.Label(options, text="קיצור גלובלי לפרופיל הבא").pack(side="right")
        ttk.Checkbutton(frame, text="כפתור הסגירה ימזער למגש במקום לצאת", variable=close_var).grid(row=3, column=0, sticky="e", pady=8)
        ttk.Label(frame, text="שיוכי יישומים לקובצי EXE", anchor="e").grid(row=4, column=0, sticky="ew", pady=(8, 4))

        table_frame = ttk.Frame(frame)
        table_frame.grid(row=5, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        table = ttk.Treeview(table_frame, columns=("exe", "profile"), show="headings", selectmode="browse", height=7)
        table.heading("exe", text="נתיב היישום")
        table.heading("profile", text="פרופיל")
        table.column("exe", width=450, minwidth=200)
        table.column("profile", width=170, minwidth=100)
        table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        table.configure(yscrollcommand=scroll.set)
        bindings = dict(self.settings.app_profiles)
        choices = [profile for profile in self.profiles if profile.image_path]
        profile_choice = ttk.Combobox(
            frame, state="readonly", values=[f"{profile.name} · {profile.id[:8]}" for profile in choices],
        )
        profile_choice.grid(row=6, column=0, sticky="ew", pady=8)
        if choices:
            profile_choice.current(0)

        def refresh_bindings() -> None:
            table.delete(*table.get_children())
            names = {profile.id: profile.name for profile in self.profiles}
            for path, profile_id in sorted(bindings.items()):
                table.insert("", "end", iid=path, values=(path, names.get(profile_id, "פרופיל חסר")))

        def add_binding() -> None:
            index = profile_choice.current()
            if index < 0:
                messagebox.showerror("שיוך יישום", "יש ליצור ולשמור פרופיל תחילה.", parent=window)
                return
            path = filedialog.askopenfilename(parent=window, title="בחירת יישום", filetypes=[("יישומי Windows", "*.exe")])
            if path:
                bindings[executable_key(path)] = choices[index].id
                refresh_bindings()

        def remove_binding() -> None:
            for path in table.selection():
                bindings.pop(path)
            refresh_bindings()

        def save() -> None:
            updated = replace(
                self.settings, auto_enabled=auto_var.get(), minimize_on_close=close_var.get(),
                hotkey="" if hotkey_var.get() == "ללא" else hotkey_var.get(), app_profiles=bindings,
            )
            try:
                self._commit_settings(updated)
            except (OSError, ValueError) as error:
                messagebox.showerror("שמירת ההגדרות נכשלה", str(error), parent=window)
                return
            self.status_var.set("ההגדרות נשמרו. החלפה אוטומטית " + ("פעילה." if updated.auto_enabled else "מושהית."))
            window.destroy()
            self.settings_window = None

        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, sticky="ew")
        ttk.Button(buttons, text="שיוך EXE לפרופיל הנבחר", command=add_binding).pack(side="right")
        ttk.Button(buttons, text="הסרת שיוך", command=remove_binding).pack(side="right", padx=8)
        ttk.Button(buttons, text="שמירה", style="Accent.TButton", command=save).pack(side="left")
        ttk.Label(
            frame, text="בחירה ידנית או קיצור גלובלי גוברים על השיוך עד למעבר ליישום אחר.\n"
            "מגש המערכת: פתיחה בלחיצה כפולה; תפריט בלחיצה ימנית. ״יציאה״ סוגרת את שירותי הרקע.",
            anchor="e", justify="right", style="Muted.TLabel", wraplength=700,
        ).grid(row=8, column=0, sticky="ew", pady=(12, 0))
        refresh_bindings()

    def _build_ui(self) -> None:
        self.root.configure(background="#0F172A")
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background="#0F172A", foreground="#E2E8F0")
        style.configure("TFrame", background="#0F172A")
        style.configure("Card.TFrame", background="#1E293B")
        style.configure("Card.TLabel", background="#1E293B")
        style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"), foreground="#F8FAFC")
        style.configure("Muted.TLabel", foreground="#94A3B8")
        style.configure("TLabelframe", background="#0F172A", bordercolor="#334155")
        style.configure("TLabelframe.Label", foreground="#7DD3FC", font=("Segoe UI", 11, "bold"))
        style.configure("TEntry", fieldbackground="#1E293B", insertcolor="#F8FAFC", padding=7)
        style.configure("TSpinbox", fieldbackground="#1E293B", arrowcolor="#E2E8F0", padding=5)
        style.configure("TCombobox", fieldbackground="#1E293B", arrowcolor="#E2E8F0", padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", "#1E293B")], foreground=[("readonly", "#E2E8F0")])
        self.root.option_add("*TCombobox*Listbox.background", "#1E293B")
        self.root.option_add("*TCombobox*Listbox.foreground", "#E2E8F0")
        style.configure("Treeview", background="#1E293B", fieldbackground="#1E293B", rowheight=28)
        style.map("Treeview", background=[("selected", "#0369A1")], foreground=[("selected", "white")])
        style.configure("Treeview.Heading", background="#334155", padding=6)
        style.configure("TButton", background="#334155", padding=(12, 8), borderwidth=0)
        style.map("TButton", background=[("active", "#475569")], foreground=[("disabled", "#64748B")])
        style.configure("Accent.TButton", background="#0284C7", foreground="white", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#0369A1")])
        style.configure("TCheckbutton", padding=5)
        style.map("TCheckbutton", background=[("active", "#1E293B")])

        container = ttk.Frame(self.root, padding=16)
        container.pack(fill="both", expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(1, weight=1)
        header = ttk.Frame(container)
        header.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Label(header, text="Mice Arrow", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="אוטומציה והגדרות", command=self._open_settings).pack(side="right")
        ttk.Button(header, text="מזעור למגש", command=self._minimize_to_tray).pack(side="right", padx=8)

        left = ttk.LabelFrame(container, text="פרופילים", padding=12, width=190)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)
        ttk.Label(left, textvariable=self.profile_count_var, style="Muted.TLabel").grid(row=0, column=0, sticky="e", pady=(0, 10))
        self.profile_list = tk.Listbox(
            left, exportselection=False, width=20, background="#1E293B", foreground="#E2E8F0",
            selectbackground="#0369A1", selectforeground="white", borderwidth=0,
            highlightthickness=0, font=("Segoe UI", 11), activestyle="none",
        )
        self.profile_list.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=self.profile_list.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.profile_list.configure(yscrollcommand=scrollbar.set)
        self.profile_list.bind("<<ListboxSelect>>", self._select_profile)
        ttk.Button(left, text="+  פרופיל חדש", command=self._new_profile).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 6))
        ttk.Button(left, text="מחיקת פרופיל", command=self._delete_profile).grid(row=3, column=0, columnspan=2, sticky="ew")

        right = ttk.LabelFrame(container, text="עיצוב והתאמה", padding=12)
        right.grid(row=1, column=1, sticky="nsew", padx=(0, 16))
        right.columnconfigure(0, weight=1)
        ttk.Label(right, text="שם הפרופיל", anchor="e").grid(row=0, column=0, sticky="ew")
        ttk.Entry(right, textvariable=self.name_var, justify="right").grid(row=1, column=0, sticky="ew", pady=(4, 8))

        ttk.Label(right, text="תמונת סמן  ·  PNG / ICO", anchor="e").grid(row=2, column=0, sticky="ew")
        source = ttk.Frame(right)
        source.grid(row=3, column=0, sticky="ew", pady=(2, 6))
        source.columnconfigure(0, weight=1)
        ttk.Entry(source, textvariable=self.path_var, width=18).grid(row=0, column=0, sticky="ew")
        ttk.Button(source, text="סמנים מוכנים", command=self._open_pointer_picker).grid(row=0, column=1, padx=(4, 0))
        ttk.Button(source, text="קובץ…", command=self._browse).grid(row=0, column=2, padx=(4, 0))

        ttk.Label(right, text="גודל הסמן", anchor="e").grid(row=4, column=0, sticky="ew")
        size_controls = ttk.Frame(right)
        size_controls.grid(row=5, column=0, sticky="ew", pady=(4, 8))
        size_controls.columnconfigure(0, weight=1)
        self.scale_slider = tk.Scale(
            size_controls,
            from_=0.01,
            to=8.0,
            resolution=0.01,
            orient="horizontal",
            showvalue=False,
            highlightthickness=0,
            background="#0F172A", troughcolor="#334155", activebackground="#38BDF8",
            command=self._scale_slider_changed,
        )
        self.scale_slider.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(size_controls, textvariable=self.scale_percent_var, width=6, anchor="e").grid(row=0, column=1)
        ttk.Spinbox(
            size_controls,
            from_=0.01,
            to=8.0,
            increment=0.01,
            textvariable=self.scale_var,
            width=7,
        ).grid(row=0, column=2, padx=(8, 0))
        color_heading = ttk.Frame(right)
        color_heading.grid(row=6, column=0, sticky="ew")
        color_heading.columnconfigure(0, weight=1)
        ttk.Label(color_heading, text="צבע הסמן", anchor="e").grid(row=0, column=0, sticky="ew")
        ttk.Checkbutton(
            color_heading,
            text="שמור על הצבעים המקוריים",
            variable=self.preserve_original_color_var,
        ).grid(row=0, column=1, sticky="e")
        color_picker = ttk.Frame(right)
        color_picker.grid(row=7, column=0, sticky="ew", pady=4)
        self.color_wheel = tk.Canvas(color_picker, width=128, height=128, background="#0F172A", highlightthickness=0, cursor="crosshair")
        self.color_wheel.pack(side="left")
        self.color_wheel.bind("<Button-1>", self._choose_wheel_color)
        self.color_wheel.bind("<B1-Motion>", self._choose_wheel_color)
        color_details = ttk.Frame(color_picker)
        color_details.pack(side="right", padx=6)
        self.color_swatch = tk.Canvas(color_details, width=40, height=40, highlightthickness=0)
        self.color_swatch.pack(pady=(0, 8))
        ttk.Entry(color_details, textvariable=self.color_var, width=10, justify="center").pack()
        ttk.Button(color_details, text="צבע מדויק", command=self._choose_cursor_color).pack(pady=6)
        self._draw_color_wheel()

        glow = ttk.LabelFrame(right, text="GLOW  ·  הילה", padding=10)
        glow.grid(row=8, column=0, sticky="ew", pady=(8, 0))
        glow.columnconfigure(0, weight=1)
        ttk.Checkbutton(glow, text="הפעלת הילה סביב הסמן", variable=self.glow_enabled_var).grid(row=0, column=0, columnspan=2, sticky="e")
        glow_color = ttk.Frame(glow)
        glow_color.grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(glow_color, textvariable=self.glow_color_var, width=10).pack(side="left")
        ttk.Button(glow_color, text="בחירה", command=self._choose_glow_color).pack(side="left", padx=5)
        ttk.Label(glow, text="צבע").grid(row=1, column=1, sticky="e")
        ttk.Spinbox(glow, from_=1, to=16, textvariable=self.glow_radius_var, width=6).grid(row=2, column=0, sticky="w", pady=4)
        ttk.Label(glow, text="רוחב (px)").grid(row=2, column=1, sticky="e")
        ttk.Scale(glow, from_=0, to=100, variable=self.glow_opacity_var).grid(row=3, column=0, sticky="ew", padx=(0, 10), pady=4)
        ttk.Label(glow, text="עוצמה").grid(row=3, column=1, sticky="e")

        preview = ttk.LabelFrame(
            container, text="תצוגה מקדימה חיה", padding=14,
        )
        preview.grid(row=1, column=2, sticky="nsew")
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(1, weight=1)
        ttk.Label(preview, textvariable=self.preview_info_var, style="Muted.TLabel", anchor="e").grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.preview_canvas = tk.Canvas(preview, width=285, height=300, background="#111827", highlightthickness=0)
        self.preview_canvas.grid(row=1, column=0, sticky="nsew")
        self.preview_canvas.bind("<Button-1>", self._choose_hotspot)
        self.preview_canvas.bind("<Configure>", self._schedule_preview)
        ttk.Label(preview, text="לחץ על השפיץ לקביעת נקודת הלחיצה.\nהצלב האדום מסמן את המיקום המדויק.", justify="right", anchor="e").grid(row=2, column=0, sticky="ew", pady=12)
        ttk.Button(preview, text="החלפת רקע בהיר / כהה", command=self._toggle_preview_background).grid(row=3, column=0, sticky="ew", pady=4)
        ttk.Button(preview, text="זיהוי אוטומטי של השפיץ", command=self._reset_hotspot).grid(row=4, column=0, sticky="ew", pady=4)
        ttk.Label(
            preview,
            text="כשהמחשב עסוק, הסמן המותאם\nמופיע לצד העיגול המסתובב.",
            justify="right", anchor="e", style="Muted.TLabel",
        ).grid(row=5, column=0, sticky="ew", pady=12)

        actions = ttk.Frame(container)
        actions.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(16, 10))
        ttk.Button(actions, text="החלת הסמן במערכת", style="Accent.TButton", command=self._apply).pack(side="right")
        ttk.Button(actions, text="שמירת פרופיל  ·  Ctrl+S", command=self._save_current).pack(side="right", padx=8)
        ttk.Button(actions, text="שחזור הסמנים המקוריים", command=self._restore).pack(side="left")

        ttk.Label(container, textvariable=self.status_var, anchor="e", wraplength=1000).grid(row=3, column=0, columnspan=3, sticky="ew")
        credits = ttk.Frame(container)
        credits.grid(row=4, column=0, columnspan=3, sticky="e", pady=(8, 0))
        ttk.Label(credits, text="נוצר על ידי נתנאל אלחדד", style="Muted.TLabel").pack(side="right")
        ttk.Label(credits, text="Nati3210@gmail.com", style="Muted.TLabel").pack(side="right", padx=(0, 12))

    def _choose_cursor_color(self) -> None:
        _rgb, color = colorchooser.askcolor(self.color_var.get(), parent=self.root, title="צבע הסמן")
        if color:
            self.color_var.set(color.upper())

    def _choose_glow_color(self) -> None:
        _rgb, color = colorchooser.askcolor(parent=self.root, title="צבע ההילה")
        if color:
            self.glow_color_var.set(color.upper())

    def _toggle_preview_background(self) -> None:
        self.preview_light = not self.preview_light
        self.preview_canvas.configure(background="#F1F5F9" if self.preview_light else "#111827")

    def _reset_hotspot(self) -> None:
        self.hotspot_x = self.hotspot_y = None
        self._schedule_preview()

    def _schedule_preview(self, *_args: object) -> None:
        self.preview_bounds = None
        if self.preview_job is not None:
            self.root.after_cancel(self.preview_job)
        self.preview_job = self.root.after(180, self._live_preview)

    def _live_preview(self) -> None:
        self.preview_job = None
        if self.current_id and self.path_var.get().strip():
            self._preview(quiet=True)
        else:
            self._clear_preview("בחר תמונת PNG או ICO כדי להתחיל")

    def _scale_slider_changed(self, value: str) -> None:
        scale = round(float(value), 2)
        self.scale_var.set(f"{scale:.2f}".rstrip("0").rstrip("."))

    def _sync_scale_controls(self, *_args: object) -> None:
        try:
            scale = float(self.scale_var.get())
        except ValueError:
            return
        if not math.isfinite(scale):
            return
        self.scale_percent_var.set(f"{round(scale * 100)}%")
        if 0.01 <= scale <= 8.0 and abs(self.scale_slider.get() - scale) >= 0.005:
            self.scale_slider.set(scale)

    def _refresh_profiles(self, select_id: str | None = None) -> None:
        self.profile_list.delete(0, tk.END)
        self.profile_count_var.set(f"{len(self.profiles)} פרופילים")
        selected_index = None
        for index, profile in enumerate(self.profiles):
            self.profile_list.insert(tk.END, profile.name or "(ללא שם)")
            if profile.id == select_id:
                selected_index = index
        if selected_index is not None:
            self.profile_list.selection_set(selected_index)
            self.profile_list.activate(selected_index)
            self._load_profile(self.profiles[selected_index])

    def _select_profile(self, _event: tk.Event) -> None:
        selection = self.profile_list.curselection()
        if selection:
            profile = self.profiles[selection[0]]
            if profile.id == self.current_id and profile.id == self.active_profile_id:
                return
            self._load_profile(profile)
            if profile.image_path and Path(profile.image_path).is_file():
                self._apply_profile(profile)

    def _load_profile(self, profile: Profile) -> None:
        self.current_id = profile.id
        self.name_var.set(profile.name)
        self.path_var.set(profile.image_path)
        self.scale_var.set(str(profile.scale))
        self.hotspot_x = profile.hotspot_x
        self.hotspot_y = profile.hotspot_y
        self.hotspot_image_path = profile.image_path
        self.color_var.set(profile.color)
        self.preserve_original_color_var.set(profile.preserve_original_color)
        self.glow_enabled_var.set(profile.glow_enabled)
        self.glow_color_var.set(profile.glow_color)
        self.glow_radius_var.set(str(profile.glow_radius))
        self.glow_opacity_var.set(profile.glow_opacity * 100)
        self._clear_preview("בחר תמונה כדי להציג תצוגה מקדימה")
        self.preview_image = None

    def _new_profile(self) -> None:
        profile = Profile(id=str(uuid.uuid4()), name="פרופיל חדש", image_path="")
        self.profiles.append(profile)
        self._refresh_profiles(profile.id)

    def _delete_profile(self) -> None:
        selection = self.profile_list.curselection()
        if not selection:
            return
        profile = self.profiles[selection[0]]
        if not messagebox.askyesno("מחיקת פרופיל", f"למחוק את הפרופיל ״{profile.name}״?"):
            return
        updated_settings = replace(
            self.settings,
            app_profiles={key: value for key, value in self.settings.app_profiles.items() if value != profile.id},
        )
        if updated_settings.manual_profile_id == profile.id:
            updated_settings.manual_profile_id = None
            updated_settings.auto_enabled = False
        remaining = [existing for existing in self.profiles if existing.id != profile.id]
        try:
            save_settings(updated_settings)
            save_profiles(remaining)
        except (OSError, ValueError) as error:
            messagebox.showerror("מחיקת הפרופיל נכשלה", str(error))
            return
        self.settings = updated_settings
        self.profiles = remaining
        self.current_id = None
        self._refresh_profiles()
        self._clear_form()
        if self.active_profile_id == profile.id:
            self.active_profile_id = None
        self.status_var.set("הפרופיל ושיוכי היישומים שלו נמחקו.")

    def _clear_form(self) -> None:
        self.name_var.set("")
        self.path_var.set("")
        self.scale_var.set("1.0")
        self.hotspot_x = None
        self.hotspot_y = None
        self.hotspot_image_path = ""
        self.color_var.set("#FFFFFF")
        self.preserve_original_color_var.set(False)
        self.glow_enabled_var.set(False)
        self.glow_color_var.set("#38BDF8")
        self.glow_radius_var.set("6")
        self.glow_opacity_var.set(80)
        self._clear_preview("בחר תמונה כדי להציג תצוגה מקדימה")
        self.preview_image = None

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="בחירת תמונת סמן",
            filetypes=[("תמונות נתמכות", "*.png *.ico"), ("PNG", "*.png"), ("ICO", "*.ico")],
        )
        if path:
            self.path_var.set(path)
            self.hotspot_x = None
            self.hotspot_y = None
            self.hotspot_image_path = path
            self._schedule_preview()

    def _open_pointer_picker(self) -> None:
        if self.pointer_window is not None and self.pointer_window.winfo_exists():
            self.pointer_window.lift()
            return
        window = tk.Toplevel(self.root)
        self.pointer_window = window
        window.title("בחירת סמן מוכן")
        window.transient(self.root)
        window.geometry("580x600")
        window.minsize(480, 360)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        ttk.Label(window, text="בחר סמן ולחץ על בחירה, או לחץ עליו פעמיים.", anchor="e").grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=10,
        )
        style = ttk.Style(window)
        style.configure("Pointers.Treeview", rowheight=60)
        tree = ttk.Treeview(window, show="tree", selectmode="browse", style="Pointers.Treeview")
        tree.column("#0", width=460, minwidth=360)
        tree.grid(row=1, column=0, sticky="nsew", padx=(12, 0))
        scrollbar = ttk.Scrollbar(window, orient="vertical", command=tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", padx=(0, 12))
        tree.configure(yscrollcommand=scrollbar.set)
        self.pointer_images = []

        def close() -> None:
            window.destroy()
            self.pointer_window = None
            self.pointer_images = []

        window.protocol("WM_DELETE_WINDOW", close)
        window.bind("<Escape>", lambda _event: close())
        try:
            for filename in _builtin_pointer_names():
                with Image.open(_builtin_pointer_directory() / filename) as source:
                    image = source.convert("RGBA")
                image.thumbnail((48, 48), Image.Resampling.LANCZOS)
                thumbnail = Image.new("RGBA", (56, 56), "#64748B")
                thumbnail.alpha_composite(image, ((56 - image.width) // 2, (56 - image.height) // 2))
                photo = ImageTk.PhotoImage(thumbnail, master=window)
                self.pointer_images.append(photo)
                tree.insert("", "end", iid=filename, text="  " + Path(filename).stem, image=photo)
        except (OSError, ValueError) as error:
            close()
            messagebox.showerror("טעינת הסמנים נכשלה", str(error))
            return

        def choose(_event: tk.Event | None = None) -> None:
            selected = tree.selection()
            if selected and self._select_builtin_pointer(selected[0]):
                close()

        tree.bind("<Double-1>", choose)
        tree.bind("<Return>", choose)
        actions = ttk.Frame(window, padding=12)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(actions, text="בחירה", command=choose).pack(side="right")
        ttk.Button(actions, text="ביטול", command=close).pack(side="left")
        children = tree.get_children()
        if children:
            tree.selection_set(children[0])
            tree.focus(children[0])
        tree.focus_set()

    def _select_builtin_pointer(self, filename: str | None = None) -> bool:
        filename = self.path_var.get() if filename is None else filename
        if filename not in _builtin_pointer_names():
            return False
        try:
            path = _copy_builtin_pointer(filename)
        except (OSError, ValueError) as error:
            messagebox.showerror("בחירת סמן מובנה נכשלה", str(error))
            return False
        self.path_var.set(str(path))
        self.hotspot_x = None
        self.hotspot_y = None
        self.hotspot_image_path = str(path)
        self._schedule_preview()
        return True

    def _profile_from_form(self) -> Profile:
        if not self.current_id:
            raise ValueError("בחר או צור פרופיל תחילה.")
        name = self.name_var.get().strip()
        image_path = self.path_var.get().strip()
        if not name:
            raise ValueError("יש להזין שם לפרופיל.")
        if not image_path or not Path(image_path).is_file():
            raise ValueError("יש לבחור קובץ תמונה קיים.")
        try:
            scale = float(self.scale_var.get())
        except ValueError as error:
            raise ValueError("הגודל חייב להיות מספר בין 0.01 ל־8.") from error
        try:
            glow_radius = int(self.glow_radius_var.get())
        except ValueError as error:
            raise ValueError("רוחב ההילה חייב להיות מספר שלם בין 1 ל־16.") from error
        if image_path != self.hotspot_image_path:
            self.hotspot_x = None
            self.hotspot_y = None
            self.hotspot_image_path = image_path
        profile = Profile(
            self.current_id,
            name,
            image_path,
            scale,
            self.color_var.get().strip().upper(),
            self.hotspot_x,
            self.hotspot_y,
            self.glow_enabled_var.get(),
            self.glow_color_var.get().strip().upper(),
            glow_radius,
            self.glow_opacity_var.get() / 100,
            self.preserve_original_color_var.get(),
        )
        render_profile(profile)
        return profile

    def _save_current(self) -> None:
        try:
            profile = self._profile_from_form()
            index = next((i for i, existing in enumerate(self.profiles) if existing.id == profile.id), None)
            if index is None:
                self.profiles.append(profile)
            else:
                self.profiles[index] = profile
            self._persist()
            self._refresh_profiles(profile.id)
        except (OSError, ValueError) as error:
            messagebox.showerror("שמירת פרופיל נכשלה", str(error))

    def _preview(self, quiet: bool = False) -> None:
        try:
            profile = self._profile_from_form()
            image, tip = render_profile(profile)
            self.preview_padding = profile.glow_radius * 3 if profile.glow_enabled else 0
            self.preview_source_size = (
                image.width - self.preview_padding * 2, image.height - self.preview_padding * 2,
            )
            self.preview_render_size = image.size
            display = image.copy()
            canvas_width = max(1, self.preview_canvas.winfo_width())
            canvas_height = max(1, self.preview_canvas.winfo_height())
            self.preview_image = ImageTk.PhotoImage(display)
            left = (canvas_width - display.width) // 2
            top = (canvas_height - display.height) // 2
            right, bottom = left + display.width, top + display.height
            self.preview_bounds = (left, top, right, bottom)
            self.preview_tip = tip
            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(left, top, image=self.preview_image, anchor="nw")
            marker_x = left + round(tip[0] * (display.width - 1) / max(1, image.width - 1))
            marker_y = top + round(tip[1] * (display.height - 1) / max(1, image.height - 1))
            self._draw_hotspot_marker(marker_x, marker_y)
            self.preview_info_var.set(f"{image.width} × {image.height} px  ·  1:1")
        except (OSError, ValueError) as error:
            self._clear_preview(str(error))
            self.preview_info_var.set("יש לתקן את ההגדרות")
            if not quiet:
                messagebox.showerror("תצוגה מקדימה נכשלה", str(error))

    def _draw_hotspot_marker(self, x: int, y: int) -> None:
        self.preview_canvas.delete("hotspot")
        self.preview_canvas.create_oval(
            x - 5, y - 5, x + 5, y + 5,
            outline="#ff3030", width=2, tags="hotspot",
        )
        self.preview_canvas.create_line(
            x - 8, y, x + 8, y,
            fill="#ff3030", width=1, tags="hotspot",
        )
        self.preview_canvas.create_line(
            x, y - 8, x, y + 8,
            fill="#ff3030", width=1, tags="hotspot",
        )

    def _choose_hotspot(self, event: tk.Event) -> None:
        if self.preview_bounds is None:
            return
        left, top, right, bottom = self.preview_bounds
        if not (left <= event.x < right and top <= event.y < bottom):
            return
        try:
            image_path = self.path_var.get().strip()
            display_width, display_height = right - left, bottom - top
            source_width, source_height = self.preview_source_size
            x = round((event.x - left) * (self.preview_render_size[0] - 1) / max(1, display_width - 1)) - self.preview_padding
            y = round((event.y - top) * (self.preview_render_size[1] - 1) / max(1, display_height - 1)) - self.preview_padding
            if not (0 <= x < source_width and 0 <= y < source_height):
                self.status_var.set("בחר נקודת לחיצה בתוך תמונת הסמן, לא בתוך ההילה.")
                return
            self.hotspot_x = x / max(1, source_width - 1)
            self.hotspot_y = y / max(1, source_height - 1)
            self.hotspot_image_path = image_path
            self.preview_tip = (x + self.preview_padding, y + self.preview_padding)
            self._draw_hotspot_marker(event.x, event.y)
        except (OSError, ValueError) as error:
            messagebox.showerror("בחירת השפיץ נכשלה", str(error))

    def _clear_preview(self, text: str) -> None:
        self.preview_bounds = None
        self.preview_canvas.delete("all")
        width = max(240, self.preview_canvas.winfo_width())
        height = max(190, self.preview_canvas.winfo_height())
        self.preview_canvas.create_text(width // 2, height // 2, text=text, fill="#7890A4", width=width - 30)

    def _draw_color_wheel(self) -> None:
        size = 128
        center = (size - 1) / 2
        radius = 58
        wheel = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        pixels = wheel.load()
        for y in range(size):
            for x in range(size):
                dx, dy = x - center, center - y
                saturation = math.hypot(dx, dy) / radius
                if saturation <= 1:
                    hue = (math.atan2(dy, dx) / (2 * math.pi)) % 1
                    red, green, blue = colorsys.hsv_to_rgb(hue, saturation, 1)
                    pixels[x, y] = (round(red * 255), round(green * 255), round(blue * 255), 255)
        self.wheel_image = ImageTk.PhotoImage(wheel)
        self.color_wheel.create_image(0, 0, image=self.wheel_image, anchor="nw", tags="wheel")
        self._update_color_wheel_marker()

    def _choose_wheel_color(self, event: tk.Event) -> None:
        center = 63.5
        radius = 58
        dx, dy = event.x - center, center - event.y
        distance = math.hypot(dx, dy)
        saturation = min(1.0, distance / radius)
        hue = (math.atan2(dy, dx) / (2 * math.pi)) % 1
        rgb = colorsys.hsv_to_rgb(hue, saturation, 1)
        self.color_var.set("#{:02X}{:02X}{:02X}".format(*(round(channel * 255) for channel in rgb)))

    def _update_color_wheel_marker(self, *_args: object) -> None:
        if not hasattr(self, "color_wheel"):
            return
        color = self.color_var.get().strip()
        try:
            red, green, blue = (int(color[index:index + 2], 16) / 255 for index in (1, 3, 5))
            if len(color) != 7 or color[0] != "#":
                return
        except (ValueError, IndexError):
            return
        hue, saturation, _value = colorsys.rgb_to_hsv(red, green, blue)
        angle = hue * 2 * math.pi
        x = 63.5 + math.cos(angle) * saturation * 58
        y = 63.5 - math.sin(angle) * saturation * 58
        self.color_wheel.delete("selection")
        self.color_wheel.create_oval(
            x - 5, y - 5, x + 5, y + 5,
            outline="black", width=2, tags="selection",
        )
        self.color_wheel.create_oval(
            x - 3, y - 3, x + 3, y + 3,
            outline="white", width=1, tags="selection",
        )
        self.color_swatch.delete("all")
        self.color_swatch.create_rectangle(1, 1, 39, 39, fill=color, outline="")

    def _apply(self) -> None:
        try:
            self._apply_profile(self._profile_from_form())
        except (OSError, ValueError) as error:
            messagebox.showerror("החלת הסמן נכשלה", str(error))

    def _apply_profile(self, profile: Profile, automatic: bool = False) -> bool:
        try:
            image, hotspot = render_profile(profile)
            if automatic and not CURSOR_BACKUP_FILE.exists():
                raise ValueError("יש להחיל פרופיל ידנית ולאשר את שינוי סמני Windows לפני הפעלת האוטומציה.")
            if not CURSOR_BACKUP_FILE.exists() and not messagebox.askyesno(
                "שמירת סמן ב־Windows",
                "בחירת הפרופיל תשנה את סמן החץ ואת סמן העבודה ברקע עם העיגול המסתובב, "
                "גם אחרי סגירת התוכנה והפעלה מחדש. "
                "הסמנים המקוריים יגובו ויוחזרו בלחיצה על ״שחזור הסמנים המקוריים״. להמשיך?",
            ):
                return False
            write_cur(image, CURSOR_FILE, hotspot)
            write_working_cursor(image, WORKING_CURSOR_FILE, hotspot)
            apply_system_cursor(CURSOR_FILE, WORKING_CURSOR_FILE)
            self.active_profile_id = profile.id
            if not automatic:
                self.manual_override_exe = self.last_foreground_exe
                self._persist_profile(profile)
                updated = replace(self.settings, manual_profile_id=profile.id)
                save_settings(updated)
                self.settings = updated
            source = "אוטומטי" if automatic else "ידני"
            self.status_var.set(f"הפרופיל ״{profile.name}״ פעיל · {source}")
            return True
        except (OSError, ValueError) as error:
            if automatic:
                raise
            messagebox.showerror("החלת הסמן נכשלה", str(error))
            return False

    def _restore(self) -> None:
        try:
            updated = replace(self.settings, auto_enabled=False)
            save_settings(updated)
            self.settings = updated
            restore_system_cursors()
            self.active_profile_id = None
            self.status_var.set("הגדרות הסמנים המקוריות של Windows שוחזרו.")
        except (OSError, ValueError) as error:
            messagebox.showerror("שחזור הסמן נכשל", str(error))

    def _persist_profile(self, profile: Profile) -> None:
        index = next((i for i, existing in enumerate(self.profiles) if existing.id == profile.id), None)
        if index is None:
            self.profiles.append(profile)
        else:
            self.profiles[index] = profile
        self._persist()
        self._refresh_profiles(profile.id)

    def _persist(self) -> None:
        save_profiles(self.profiles)

    def _close(self) -> None:
        self.closing = True
        if self.desktop_job is not None:
            self.root.after_cancel(self.desktop_job)
            self.desktop_job = None
        if self.preview_job is not None:
            self.root.after_cancel(self.preview_job)
            self.preview_job = None
        for service in (self.hotkeys, self.tray):
            if service is not None:
                try:
                    service.close()
                except OSError as error:
                    messagebox.showerror("עצירת שירות הרקע נכשלה", str(error))
        self.root.destroy()


def main() -> None:
    if os.name != "nt":
        messagebox.showerror("מערכת לא נתמכת", "החלת סמן המערכת זמינה ב־Windows בלבד.")
        return
    APP_DATA.mkdir(parents=True, exist_ok=True)
    enable_dpi_awareness()
    root = tk.Tk()
    try:
        app = MiceArrowApp(root)
        app.start_desktop_services()
    except (OSError, ValueError) as error:
        messagebox.showerror("טעינת פרופילים נכשלה", str(error))
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
