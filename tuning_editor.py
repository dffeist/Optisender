import copy
import json
import shutil
import threading
import tkinter as tk
from tkinter import ttk, messagebox

TUNING_FILE         = "tuning.json"
TUNING_DEFAULT_FILE = "tuning_default.json"

CLUBS = ["Driver", "3W", "5W", "5H", "3I", "4I", "5I",
         "6I", "7I", "8I", "9I", "PW", "GW", "SW", "LW"]

# Per-club slider ranges: (min, max, step)
CLUB_RANGES = {
    "Driver": {"BallSpeed": (1.30, 1.60, 0.01), "Vla": ( 8.0, 20.0, 0.5), "BS": (1800,  4500, 25)},
    "3W":     {"BallSpeed": (1.28, 1.55, 0.01), "Vla": ( 9.0, 22.0, 0.5), "BS": (2500,  6000, 25)},
    "5W":     {"BallSpeed": (1.27, 1.54, 0.01), "Vla": (10.0, 23.0, 0.5), "BS": (3000,  7000, 25)},
    "5H":     {"BallSpeed": (1.25, 1.52, 0.01), "Vla": (12.0, 26.0, 0.5), "BS": (2800,  7000, 25)},
    "3I":     {"BallSpeed": (1.25, 1.52, 0.01), "Vla": (11.0, 24.0, 0.5), "BS": (3000,  7500, 25)},
    "4I":     {"BallSpeed": (1.23, 1.50, 0.01), "Vla": (12.0, 25.0, 0.5), "BS": (3500,  8500, 25)},
    "5I":     {"BallSpeed": (1.21, 1.48, 0.01), "Vla": (13.0, 26.0, 0.5), "BS": (4000,  9500, 25)},
    "6I":     {"BallSpeed": (1.20, 1.47, 0.01), "Vla": (15.0, 28.0, 0.5), "BS": (4500, 10500, 25)},
    "7I":     {"BallSpeed": (1.18, 1.45, 0.01), "Vla": (17.0, 30.0, 0.5), "BS": (5000, 11000, 25)},
    "8I":     {"BallSpeed": (1.15, 1.42, 0.01), "Vla": (19.0, 33.0, 0.5), "BS": (5500, 12000, 25)},
    "9I":     {"BallSpeed": (1.12, 1.40, 0.01), "Vla": (21.0, 36.0, 0.5), "BS": (6000, 13500, 25)},
    "PW":     {"BallSpeed": (1.10, 1.38, 0.01), "Vla": (23.0, 40.0, 0.5), "BS": (7000, 15000, 25)},
    "GW":     {"BallSpeed": (1.08, 1.36, 0.01), "Vla": (25.0, 42.0, 0.5), "BS": (7500, 16000, 25)},
    "SW":     {"BallSpeed": (1.05, 1.34, 0.01), "Vla": (27.0, 46.0, 0.5), "BS": (8000, 17000, 25)},
    "LW":     {"BallSpeed": (1.02, 1.32, 0.01), "Vla": (29.0, 50.0, 0.5), "BS": (8500, 18000, 25)},
}

BG      = "#1e1e1e"
BG2     = "#2a2a2a"
FG      = "#e0e0e0"
ACCENT  = "#4fc3f7"
SUCCESS = "#66bb6a"
DANGER  = "#ef5350"
WARN    = "#ffa726"
FONT    = ("Consolas", 10)
FONT_B  = ("Consolas", 10, "bold")
FONT_H  = ("Consolas", 12, "bold")


class TuningEditor:
    """
    Floating tuning editor window for OptiSender.
    Runs as a Toplevel inside the OverlayDisplay's Tk thread — avoids the
    Python 3.13 restriction against multiple Tk() instances in different threads.
    All show/hide/toggle calls are forwarded to the overlay thread via schedule_ui().
    Physics reload signal: check .reload_needed (threading.Event) from the main loop.
    """

    def __init__(self, overlay):
        self._overlay = overlay
        self.reload_needed = threading.Event()
        self._win     = None   # tk.Toplevel, created lazily on first show
        self._visible = False
        self._params       = {}
        self._saved_params = {}
        self._current_club = CLUBS[0]
        self._load_from_disk()

        # Trace IDs for club sliders — removed/re-added on club change
        self._club_trace_ids = []

    # ── Public API (called from main OptiSender thread) ──────────────────

    def show(self):
        self._overlay.schedule_ui(self._do_show)

    def hide(self):
        self._overlay.schedule_ui(self._guard_hide)

    def toggle(self):
        self._overlay.schedule_ui(self._do_toggle)

    # ── Internal toggle (runs on Tk thread) ──────────────────────────────

    def _do_toggle(self):
        if self._visible:
            self._guard_hide()
        else:
            self._do_show()

    # ── Disk I/O ──────────────────────────────────────────────────────────

    def _load_from_disk(self):
        try:
            with open(TUNING_FILE, 'r') as f:
                data = json.load(f)
        except Exception:
            data = {}
        self._params       = copy.deepcopy(data)
        self._saved_params = copy.deepcopy(data)

    def _write_to_disk(self):
        with open(TUNING_FILE, 'w') as f:
            json.dump(self._params, f, indent=4)

    def _has_unsaved_changes(self):
        return self._params != self._saved_params

    # ── Window creation (runs on Tk thread) ──────────────────────────────

    @staticmethod
    def _k_to_pct(k):
        """
        Piecewise linear mapping with k=15 anchored at 50%:
          k=200   → 0%   (no compression, realistic)
          k=15    → 50%  (default, ±30° face reduces lateral ~50%)
          k=0.001 → 100% (full compression, near-straight)
        """
        if k >= 15.0:
            pct = (200.0 - k) / (200.0 - 15.0) * 50.0
        else:
            pct = 50.0 + (15.0 - k) / (15.0 - 0.001) * 50.0
        return max(0, min(100, round(pct)))

    @staticmethod
    def _pct_to_k(pct):
        """Inverse of _k_to_pct."""
        if pct <= 50:
            k = 200.0 - (200.0 - 15.0) * (pct / 50.0)
        else:
            k = 15.0 - (15.0 - 0.001) * ((pct - 50.0) / 50.0)
        return max(0.001, round(k, 3))

    def _do_show(self):
        # Always reload from disk so sliders reflect current saved state on open
        self._load_from_disk()
        if self._win is None:
            self._create_window()
        else:
            self._current_club = CLUBS[0]
            self._club_var.set(self._current_club)
            self._populate_sliders_from_params()
            self._build_club_sliders(self._current_club)
            self._update_dirty_label()
        self._win.deiconify()
        self._win.lift()
        self._win.attributes("-topmost", True)
        self._win.focus_force()
        self._visible = True

    def _do_hide(self):
        if self._win:
            self._win.withdraw()
        self._visible = False

    def _create_window(self):
        root = self._overlay._root
        self._win = tk.Toplevel(root)
        self._win.title("OptiSender — Tuning Editor")
        self._win.configure(bg=BG)
        self._win.geometry("500x560+200+80")
        self._win.resizable(False, False)
        self._win.protocol("WM_DELETE_WINDOW", self._on_close_button)

        self._build_ui()

    # ── UI Construction ───────────────────────────────────────────────────

    def _build_ui(self):
        win = self._win

        # Title / drag bar
        title_bar = tk.Frame(win, bg="#2a4a6b", cursor="fleur")
        title_bar.pack(fill="x")
        tk.Label(title_bar, text="OptiSender — Tuning Editor",
                 bg="#2a4a6b", fg="#ffffff", font=FONT_H, pady=6).pack(side="left", padx=10)
        title_bar.bind("<ButtonPress-1>", self._drag_start)
        title_bar.bind("<B1-Motion>",     self._drag_motion)

        # ── Global section ────────────────────────────────────────────────
        gf = tk.LabelFrame(win, text=" Global ", bg=BG, fg=ACCENT,
                           font=FONT_B, bd=1, relief="groove", padx=8, pady=4)
        gf.pack(fill="x", padx=10, pady=(8, 4))

        self._speed_cal_var = tk.DoubleVar(master=win)
        self._face_pct_var  = tk.IntVar(master=win)

        # Pre-populate global variables before building sliders to ensure correct initial positions
        self._speed_cal_var.set(self._params.get("SpeedCalibration", 1.10))
        k_val = self._params.get("FaceCompression", {}).get("k", 15.0)
        self._face_pct_var.set(self._k_to_pct(k_val))

        self._build_slider_row(gf, "Speed Calibration", self._speed_cal_var,
                               1.0, 1.2, 0.01, fmt="{:.2f}", is_club_slider=False)
        self._build_slider_row(gf, "Face Compression", self._face_pct_var,
                               0, 100, 1, fmt="{}%", is_club_slider=False)

        # ── Club selector ─────────────────────────────────────────────────
        sel_frame = tk.Frame(win, bg=BG)
        sel_frame.pack(fill="x", padx=10, pady=(4, 2))
        tk.Label(sel_frame, text="Club:", bg=BG, fg=FG,
                 font=FONT_B).pack(side="left", padx=(0, 6))
        self._club_var = tk.StringVar(master=win, value=CLUBS[0])
        cb = ttk.Combobox(sel_frame, textvariable=self._club_var, values=CLUBS,
                          state="readonly", width=12, font=FONT)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", self._on_club_changed)

        # ── Per-club sliders ──────────────────────────────────────────────
        self._club_frame = tk.LabelFrame(win, text=f" {CLUBS[0]} ", bg=BG, fg=ACCENT,
                                         font=FONT_B, bd=1, relief="groove", padx=8, pady=4)
        self._club_frame.pack(fill="x", padx=10, pady=(2, 4))

        self._bs_var  = tk.DoubleVar(master=win)
        self._vla_var = tk.DoubleVar(master=win)
        self._rpm_var = tk.DoubleVar(master=win)

        # Initialize with Driver as the default selected club
        self._current_club = CLUBS[0]
        self._build_club_sliders(self._current_club)

        # ── Button row ────────────────────────────────────────────────────
        btn_frame = tk.Frame(win, bg=BG)
        btn_frame.pack(fill="x", padx=10, pady=(4, 2))

        tk.Button(btn_frame, text="Save", bg=SUCCESS, fg="#000000",
                  font=FONT_B, relief="flat", cursor="hand2",
                  command=self._on_save).pack(side="left", padx=(0, 6), ipadx=10, ipady=4)

        tk.Button(btn_frame, text="Cancel", bg=DANGER, fg="#ffffff",
                  font=FONT_B, relief="flat", cursor="hand2",
                  command=self._on_cancel).pack(side="left", padx=(0, 6), ipadx=10, ipady=4)

        tk.Button(btn_frame, text="Revert to Defaults", bg=WARN, fg="#000000",
                  font=FONT_B, relief="flat", cursor="hand2",
                  command=self._on_revert_defaults).pack(side="right", ipadx=10, ipady=4)

        # ── Dirty indicator ───────────────────────────────────────────────
        self._dirty_lbl = tk.Label(win, text="", bg=BG, fg=WARN, font=FONT)
        self._dirty_lbl.pack(pady=(2, 6))

    def _build_slider_row(self, parent, label, var, lo, hi, step, fmt, is_club_slider):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=3)

        tk.Label(row, text=label, bg=BG, fg=FG, font=FONT,
                 width=22, anchor="w").pack(side="left")

        val_lbl = tk.Label(row, text=fmt.format(var.get()),
                           bg=BG, fg=ACCENT, font=FONT_B, width=8, anchor="e")
        val_lbl.pack(side="right")

        tk.Scale(row, variable=var, from_=lo, to=hi, resolution=step,
                 orient="horizontal", bg=BG2, fg=FG, troughcolor="#0d1f30",
                 activebackground=ACCENT, highlightthickness=0,
                 showvalue=False, length=220).pack(side="left", padx=(6, 4))

        def _update(*_):
            try:
                val_lbl.config(text=fmt.format(var.get()))
            except tk.TclError:
                return
            self._sync_params_from_sliders()
            self._update_dirty_label()

        tid = var.trace_add("write", _update)
        if is_club_slider:
            self._club_trace_ids.append((var, tid))

    def _build_club_sliders(self, club):
        # Remove stale traces from previous club build
        for var, tid in self._club_trace_ids:
            try:
                var.trace_remove("write", tid)
            except Exception:
                pass
        self._club_trace_ids.clear()

        for w in self._club_frame.winfo_children():
            w.destroy()
        self._club_frame.config(text=f" {club} ")

        r = CLUB_RANGES[club]
        p = self._params.get(club, {})
        bs_lo,  bs_hi,  bs_step  = r["BallSpeed"]
        vla_lo, vla_hi, vla_step = r["Vla"]
        rpm_lo, rpm_hi, rpm_step = r["BS"]

        self._bs_var.set(p.get("BallSpeed", bs_lo))
        self._vla_var.set(p.get("Vla", vla_lo))
        self._rpm_var.set(p.get("BS", rpm_lo))

        self._build_slider_row(self._club_frame, "Ball Speed (smash)",
                               self._bs_var, bs_lo, bs_hi, bs_step,
                               fmt="{:.2f}", is_club_slider=True)
        self._build_slider_row(self._club_frame, "Launch Angle (°)",
                               self._vla_var, vla_lo, vla_hi, vla_step,
                               fmt="{:.1f}", is_club_slider=True)
        self._build_slider_row(self._club_frame, "Base Spin (rpm)",
                               self._rpm_var, rpm_lo, rpm_hi, rpm_step,
                               fmt="{:.0f}", is_club_slider=True)

    # ── Slider <-> params sync ────────────────────────────────────────────

    def _populate_sliders_from_params(self):
        self._speed_cal_var.set(self._params.get("SpeedCalibration", 1.10))
        k = self._params.get("FaceCompression", {}).get("k", 15.0)
        self._face_pct_var.set(self._k_to_pct(k))

        club_p = self._params.get(self._current_club, {})
        r      = CLUB_RANGES[self._current_club]
        self._bs_var.set( club_p.get("BallSpeed", r["BallSpeed"][0]))
        self._vla_var.set(club_p.get("Vla",       r["Vla"][0]))
        self._rpm_var.set(club_p.get("BS",         r["BS"][0]))

    def _sync_params_from_sliders(self):
        self._params["SpeedCalibration"] = round(self._speed_cal_var.get(), 3)
        self._params.setdefault("FaceCompression", {})["k"] = self._pct_to_k(self._face_pct_var.get())
        self._params.setdefault(self._current_club, {})
        self._params[self._current_club]["BallSpeed"] = round(self._bs_var.get(),  3)
        self._params[self._current_club]["Vla"]       = round(self._vla_var.get(), 2)
        self._params[self._current_club]["BS"]        = int(round(self._rpm_var.get() / 25) * 25)

    def _update_dirty_label(self):
        if not self._dirty_lbl.winfo_exists():
            return
        if self._has_unsaved_changes():
            self._dirty_lbl.config(text="* Unsaved changes")
        else:
            self._dirty_lbl.config(text="")

    # ── Club dropdown ─────────────────────────────────────────────────────

    def _on_club_changed(self, _=None):
        # Save current sliders to the previous club before switching
        self._sync_params_from_sliders()
        # Update our focus to the new selection and rebuild sliders
        self._current_club = self._club_var.get()
        self._build_club_sliders(self._current_club)
        self._update_dirty_label()

    # ── Button handlers ───────────────────────────────────────────────────

    def _on_save(self):
        self._win.lift() # Ensure main window is on top before showing dialog
        self._win.attributes("-topmost", True) # Re-assert topmost
        self._win.focus_force()
        if not messagebox.askyesno("Save Tuning",
                                   "Write current values to tuning.json\nand reload PhysicsEngine?",
                                   parent=self._win):
            return
        self._sync_params_from_sliders()
        self._write_to_disk()
        self._saved_params = copy.deepcopy(self._params)
        self._update_dirty_label()
        self.reload_needed.set()
        messagebox.showinfo("Saved", "Tuning saved.\nPhysics engine will reload on next swing.",
                            parent=self._win)

    def _on_cancel(self):
        self._win.lift() # Ensure main window is on top before showing dialog
        self._win.attributes("-topmost", True) # Re-assert topmost
        self._win.focus_force()
        if self._has_unsaved_changes():
            if not messagebox.askyesno("Cancel Changes",
                                       "Discard all unsaved changes?",
                                       parent=self._win):
                return
        self._params = copy.deepcopy(self._saved_params)
        self._build_club_sliders(self._club_var.get())
        self._populate_sliders_from_params()
        self._update_dirty_label()
        self._do_hide()

    def _on_revert_defaults(self):
        self._win.lift() # Ensure main window is on top before showing dialog
        self._win.attributes("-topmost", True) # Re-assert topmost
        self._win.focus_force()
        if not messagebox.askyesno("Revert to Defaults",
                                   "Overwrite tuning.json with factory defaults?\nThis cannot be undone.",
                                   parent=self._win):
            return
        try:
            shutil.copy2(TUNING_DEFAULT_FILE, TUNING_FILE)
        except Exception as e:
            messagebox.showerror("Error", f"Could not copy defaults:\n{e}", parent=self._win)
            return
        self._load_from_disk()
        self._build_club_sliders(self._club_var.get())
        self._populate_sliders_from_params()
        self._update_dirty_label()
        self.reload_needed.set()
        messagebox.showinfo("Reverted",
                            "Factory defaults restored.\nPhysics engine will reload on next swing.",
                            parent=self._win)

    # ── Unsaved guard ─────────────────────────────────────────────────────

    def _guard_hide(self):
        if not self._has_unsaved_changes():
            self._do_hide()
            return

        dialog = tk.Toplevel(self._win)
        dialog.title("Unsaved Changes")
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.lift() # Bring this dialog to the front
        dialog.attributes("-topmost", True) # Ensure this dialog stays on top
        dialog.focus_force()

        tk.Label(dialog, text="You have unsaved changes.\nChoose an action to close:",
                 bg=BG, fg=FG, font=FONT, pady=12, padx=20).pack()

        row = tk.Frame(dialog, bg=BG)
        row.pack(pady=(0, 14))

        def _save_close():
            dialog.destroy()
            self._sync_params_from_sliders()
            self._write_to_disk()
            self._saved_params = copy.deepcopy(self._params)
            self._update_dirty_label()
            self.reload_needed.set()
            self._do_hide()

        def _discard_close():
            dialog.destroy()
            self._params = copy.deepcopy(self._saved_params)
            self._build_club_sliders(self._club_var.get())
            self._populate_sliders_from_params()
            self._update_dirty_label()
            self._do_hide()

        tk.Button(row, text="Save & Close", bg=SUCCESS, fg="#000000",
                  font=FONT_B, relief="flat", cursor="hand2",
                  command=_save_close).pack(side="left", padx=6, ipadx=10, ipady=4)
        tk.Button(row, text="Cancel Changes", bg=DANGER, fg="#ffffff",
                  font=FONT_B, relief="flat", cursor="hand2",
                  command=_discard_close).pack(side="left", padx=6, ipadx=10, ipady=4)

    def _on_close_button(self):
        self._guard_hide()

    # ── Window drag ───────────────────────────────────────────────────────

    def _drag_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag_motion(self, event):
        x = self._win.winfo_x() + event.x - self._drag_x
        y = self._win.winfo_y() + event.y - self._drag_y
        self._win.geometry(f"+{x}+{y}")
