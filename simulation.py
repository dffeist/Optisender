import sys
import random
import math
import queue as _queue
import threading
import tkinter as tk
from tkinter import ttk

# Must match shot_processor.py exactly so decoded metrics are accurate
SENSOR_SPACING = 185
LED_SPACING    = 15
MPH_CONV       = 2236.94

CLUB_SPEED_RANGES = {
    "Driver": (75.0,  90.0),
    "3W":     (72.0,  86.0),
    "5W":     (69.0,  83.0),
    "5H":     (68.0,  82.0),
    "3I":     (65.0,  78.0),
    "4I":     (63.0,  76.0),
    "5I":     (61.0,  74.0),
    "6I":     (59.0,  72.0),
    "7I":     (57.0,  70.0),
    "8I":     (55.0,  67.0),
    "9I":     (53.0,  65.0),
    "PW":     (51.0,  63.0),
    "GW":     (49.0,  61.0),
    "SW":     (47.0,  59.0),
    "LW":     (44.0,  56.0),
    "Putter": (10.0,  25.0),
}

# Named shot profiles: face angle range (degrees), swing path integer,
# back-sensor contact zone (LED indices), and relative selection weight.
SHOT_PROFILES = {
    "straight": {"face": (-0.5,  0.5),  "path":  0, "b_center": (3, 4), "weight": 30},
    "fade":     {"face": ( 1.0,  3.0),  "path": -1, "b_center": (3, 4), "weight": 20},
    "draw":     {"face": (-3.0, -1.0),  "path":  1, "b_center": (3, 4), "weight": 20},
    "slice":    {"face": ( 5.0, 10.0),  "path": -2, "b_center": (3, 5), "weight": 10},
    "hook":     {"face": (-10.0,-5.0),  "path":  2, "b_center": (2, 4), "weight": 10},
    "toe":      {"face": ( 0.5,  3.0),  "path":  0, "b_center": (1, 2), "weight":  5},
    "heel":     {"face": (-3.0, -0.5),  "path":  0, "b_center": (5, 6), "weight":  5},
}

_PROFILE_NAMES   = list(SHOT_PROFILES.keys())
_PROFILE_WEIGHTS = [SHOT_PROFILES[k]["weight"] for k in _PROFILE_NAMES]

CLUBS = [
    "Driver", "3W", "5W", "5H",
    "3I", "4I", "5I", "6I", "7I", "8I", "9I",
    "PW", "GW", "SW", "LW",
]

PATH_MIN = -30.0
PATH_MAX =  30.0

# ── UI theme (matches tuning_editor) ─────────────────────────────────────────
BG     = "#1e1e1e"
BG2    = "#2a2a2a"
FG     = "#e0e0e0"
ACCENT = "#4fc3f7"
FONT   = ("Consolas", 10)
FONT_B = ("Consolas", 10, "bold")
FONT_H = ("Consolas", 12, "bold")


def _pick_profile(shot_type=None):
    if shot_type and shot_type in SHOT_PROFILES:
        return shot_type, SHOT_PROFILES[shot_type]
    name = random.choices(_PROFILE_NAMES, weights=_PROFILE_WEIGHTS, k=1)[0]
    return name, SHOT_PROFILES[name]


def generate_from_metrics(speed, face_angle, path_deg, club_name="Driver", verbose=True):
    """
    Inverse of shot_processor: build a 60-byte HID packet from exact club metrics.
    Packet round-trips through shot_processor.process_raw_buffer() producing values
    close to the inputs (small error from the weighted-average face formula is
    identical to real pad behaviour).
    """
    b_min_A = 3  # centre contact — LEDs 3 and 4 lit

    # Speed → elapsed ticks
    total_ticks = max(1, int((SENSOR_SPACING * MPH_CONV) / (speed * 18.0)))

    # The real sensor is physically inverted from Trackman convention, so negate here
    # to produce sensor-equivalent output that ballphysics can correctly interpret.
    encode_face = -face_angle

    # Back-sensor B offset: skew direction encodes open/closed
    if encode_face >= 0:
        b_min_B = b_min_A - 1 if b_min_A > 0 else b_min_A + 1
    else:
        b_min_B = b_min_A + 1 if b_min_A < 7 else b_min_A - 1
    b_min_B = max(0, min(7, b_min_B))

    # Path → front LED position.
    # The back centroid is determined by both back packets (0x81 and 0x52), not b_min_A alone.
    # Use the actual decoded centroid as the reference so ±path encodes symmetrically.
    actual_back_min = min(b_min_A, b_min_B)
    actual_back_max = max(b_min_A + 1, b_min_B + 1)
    centroid_back_led = (actual_back_min + actual_back_max) / 2.0
    target_front_led  = centroid_back_led + math.tan(math.radians(path_deg)) * SENSOR_SPACING / LED_SPACING
    f_min = max(0, min(7, round(target_front_led - 0.5)))

    # Back timing encodes face angle magnitude (weighted-average formula uses *1.5)
    target_back_angle = encode_face * 1.5
    y_dist   = (b_min_A - b_min_B) * LED_SPACING
    x_travel = abs(y_dist * math.tan(math.radians(target_back_angle))) if y_dist != 0 else 0
    ticks_52 = int(x_travel * total_ticks / SENSOR_SPACING)
    ticks_52 = max(0, min(ticks_52, int(total_ticks * 0.4)))
    ticks_4A = total_ticks - ticks_52

    if verbose:
        print(f"[SIMULATION] Manual: Club={club_name}  Speed={speed:.1f}  "
              f"Face={face_angle:+.1f}°  Path={path_deg:+.1f}°")

    data = [0] * 60
    data[1]  = (1 << b_min_A) | (1 << min(7, b_min_A + 1))
    data[2]  = 0x81
    data[6]  = (1 << b_min_B) | (1 << min(7, b_min_B + 1))
    data[7]  = 0x52
    data[8]  = (ticks_52 >> 8) & 0xFF
    data[9]  = ticks_52 & 0xFF
    data[10] = (1 << f_min) | (1 << min(7, f_min + 1))
    data[12] = 0x4A
    data[13] = (ticks_4A >> 8) & 0xFF
    data[14] = ticks_4A & 0xFF
    return data


def generate_simulated_shot(club_name="Driver", shot_type=None, verbose=True, speed_pct=100):
    """
    Build a 60-byte HID packet using a randomised named shot profile.
    Used for keyboard-triggered random shots (Ctrl+Space / Ctrl+S).
    """
    speed_min, speed_max = CLUB_SPEED_RANGES.get(club_name, CLUB_SPEED_RANGES["Driver"])
    pct = max(10, min(100, speed_pct)) / 100.0
    target_center = speed_max * pct
    band = (speed_max - speed_min) * 0.05
    target_speed = random.uniform(max(speed_min * 0.5, target_center - band),
                                  target_center + band)

    profile_name, profile = _pick_profile(shot_type)
    target_face = random.uniform(*profile["face"])
    path_shift  = profile["path"]

    b_lo, b_hi  = profile["b_center"]
    b_min_A     = max(0, min(7, random.randint(b_lo, b_hi)))
    f_min       = max(0, min(7, b_min_A + path_shift))

    if verbose:
        print(f"[SIMULATION] Profile: {profile_name.capitalize():<8} | "
              f"Club: {club_name:<6} | Speed: {target_speed:.1f} mph")

    return generate_from_metrics(target_speed, target_face,
                                 math.degrees(math.atan2((f_min - b_min_A) * LED_SPACING,
                                                         SENSOR_SPACING)),
                                 club_name, verbose=False)


# ── SimulationWindow ──────────────────────────────────────────────────────────

class _ClubSelectorPopup:
    def __init__(self, parent, current_club, on_select):
        top = tk.Toplevel(parent)
        top.title("Select Club")
        top.configure(bg=BG)
        top.resizable(False, False)
        top.grab_set()

        tk.Label(top, text="Club:", bg=BG, fg=FG, font=FONT_B,
                 pady=8, padx=12).pack()

        var = tk.StringVar(value=current_club)
        cb  = ttk.Combobox(top, textvariable=var, values=CLUBS,
                           state="readonly", width=14, font=FONT)
        cb.pack(padx=12, pady=4)

        def confirm():
            on_select(var.get())
            top.destroy()

        tk.Button(top, text="OK", font=FONT_B, bg=ACCENT, fg="#000000",
                  relief="flat", cursor="hand2", width=10,
                  command=confirm).pack(pady=(4, 12))


class SimulationWindow:
    """
    Manual swing input window shown automatically when no hardware pad is detected.
    Builds exact HID packets via generate_from_metrics() and places them in
    packet_queue for OptiSender to process through the normal pipeline:
        shot_processor → ballphysics → API
    Closes automatically when the pad is reconnected.
    """

    def __init__(self, overlay, packet_queue, sim_input):
        self._overlay   = overlay
        self._queue     = packet_queue
        self._sim_input = sim_input
        self._win       = None
        self._visible   = False
        # Mirrors OptiSender's state — updated via set_handed() / set_club()
        self._left_handed = False
        self._club        = "Driver"
        # Set by OptiSender after shot processing completes; sim window polls this.
        self.ready = threading.Event()
        self.ready.set()  # ready at startup

    # ── Public API (safe to call from any thread) ─────────────────────────

    def show(self):
        self._overlay.schedule_ui(self._do_show)

    def hide(self):
        self._overlay.schedule_ui(self._do_hide)

    def set_handed(self, left_handed):
        self._left_handed = left_handed
        self._overlay.schedule_ui(self._update_hand_btn)

    def set_club(self, club):
        self._club = club
        self._overlay.schedule_ui(self._update_club_display)

    def set_ready(self):
        """Called by OptiSender after shot processing completes."""
        self.ready.set()

    # ── Internal (runs on Tk thread) ──────────────────────────────────────

    def _do_show(self):
        if self._win is None:
            self._create_window()
        self._update_hand_btn()
        self._update_club_display()
        self._win.deiconify()
        self._win.lift()
        self._win.attributes("-topmost", True)
        self._visible = True

    def _do_hide(self):
        if self._win:
            self._win.withdraw()
        self._visible = False

    def _create_window(self):
        self._win = tk.Toplevel(self._overlay._root)
        self._win.title("OptiSender — Manual Simulation")
        self._win.configure(bg=BG)
        self._win.resizable(False, False)
        # Prevent the user closing the window manually — it closes when pad reconnects
        self._win.protocol("WM_DELETE_WINDOW", lambda: None)
        self._build_ui()

    def _build_ui(self):
        win = self._win
        pad = {"padx": 16, "pady": 4}

        # Title / drag bar
        title_bar = tk.Frame(win, bg="#2a4a6b", cursor="fleur")
        title_bar.pack(fill="x")
        tk.Label(title_bar, text="Manual Simulation  —  No Pad Detected",
                 bg="#2a4a6b", fg="#ffffff", font=FONT_H, pady=6).pack(side="left", padx=10)
        title_bar.bind("<ButtonPress-1>", self._drag_start)
        title_bar.bind("<B1-Motion>",     self._drag_motion)

        # Send Shot button
        self._send_btn = tk.Button(win, text="Send Shot", font=FONT_H,
                                   bg="#2e7d32", fg="white", width=22, cursor="hand2",
                                   command=self._send)
        self._send_btn.pack(padx=16, pady=(12, 4))

        # Handedness — mirrors OptiSender state, toggle via Ctrl+H or this button
        self._hand_btn = tk.Button(win, font=FONT_B, width=22, cursor="hand2",
                                   command=self._toggle_handed)
        self._hand_btn.pack(padx=16, pady=(0, 4))

        # Club selector
        club_row = tk.Frame(win, bg=BG)
        club_row.pack(fill="x", **pad)
        tk.Label(club_row, text="Club:", bg=BG, fg=FG, font=FONT_B,
                 width=18, anchor="w").pack(side=tk.LEFT)
        self._club_lbl = tk.Label(club_row, text=self._club,
                                  bg=BG2, fg=ACCENT, font=FONT_B,
                                  width=10, anchor="w", relief="sunken")
        self._club_lbl.pack(side=tk.LEFT, padx=(4, 0))
        tk.Button(club_row, text="Change…", font=FONT, cursor="hand2",
                  command=self._open_club_selector).pack(side=tk.LEFT, padx=(6, 0))

        # Sliders
        self._speed_var = tk.DoubleVar(master=win, value=90.0)
        self._face_var  = tk.DoubleVar(master=win, value=0.0)
        self._path_var  = tk.DoubleVar(master=win, value=0.0)

        self._make_slider(win, "Club Speed (mph)", self._speed_var,  10,      120,      0.5, pad)
        self._make_slider(win, "Face Angle (°)",   self._face_var,  -20,       20,      1.0, pad)
        self._make_slider(win, "Club Path (°)",    self._path_var,  PATH_MIN, PATH_MAX, 1.0, pad)

        # Status / ready indicator
        self._status_var = tk.StringVar(master=win, value="")
        self._status_lbl = tk.Label(win, textvariable=self._status_var,
                                    bg=BG, font=FONT, wraplength=380)
        self._status_lbl.pack(padx=16, pady=(4, 12))
        self._poll_ready()

    def _make_slider(self, parent, label, var, from_, to, res, pad):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill=tk.X, **pad)
        tk.Label(frame, text=label, bg=BG, fg=FG, font=FONT,
                 width=22, anchor="w").pack(side=tk.LEFT)
        tk.Scale(frame, variable=var, from_=from_, to=to,
                 orient=tk.HORIZONTAL, resolution=res, length=220, showvalue=True,
                 bg=BG2, fg=FG, troughcolor="#0d1f30",
                 activebackground=ACCENT, highlightthickness=0).pack(side=tk.LEFT)

    def _update_hand_btn(self):
        if self._win is None:
            return
        if self._left_handed:
            self._hand_btn.config(text="Left Handed",  bg="#1565c0", fg="white")
        else:
            self._hand_btn.config(text="Right Handed", bg="#f57c00", fg="white")

    def _update_club_display(self):
        if self._win is None:
            return
        self._club_lbl.config(text=self._club)

    def _toggle_handed(self):
        # Delegate to OptiSender so the single left_handed flag stays authoritative
        self._sim_input["toggle_handed"] = True

    def _open_club_selector(self):
        _ClubSelectorPopup(self._win, self._club, self._on_club_selected)

    def _on_club_selected(self, club):
        self._club = club
        self._update_club_display()

    def _poll_ready(self):
        if self._win is None:
            return
        if self.ready.is_set():
            self._send_btn.config(state="normal", bg="#2e7d32")
            self._status_lbl.config(fg="#66bb6a")
            self._status_var.set("● Ready")
        self._win.after(100, self._poll_ready)

    def _send(self):
        speed      = self._speed_var.get()
        face_angle = self._face_var.get()
        path_deg   = self._path_var.get()
        club       = self._club

        # Sensor convention: face_angle in metrics is physically inverted from Trackman.
        # LH also flips sign so physics and overlay labelling stay consistent.
        sensor_face = face_angle  if self._left_handed else -face_angle
        sensor_path = -path_deg   if self._left_handed else  path_deg

        metrics = {
            "speed":        speed,
            "face_angle":   sensor_face,
            "path_deg":     sensor_path,
            "contact":      0.0,
            "raw_min_back": 3,
            "raw_max_back": 4,
            "path":         0,
            "smash_factor": 1.0,
        }

        self.ready.clear()
        self._send_btn.config(state="disabled", bg="#555555")
        self._status_lbl.config(fg="#ffa726")
        hand = "LH" if self._left_handed else "RH"
        self._status_var.set(
            f"◌ Processing [{hand}] {club}  Speed={speed:.1f}  "
            f"Face={face_angle:+.1f}°  Path={path_deg:+.1f}°"
        )
        self._queue.put({"metrics": metrics, "club": club})

    # ── Window drag ───────────────────────────────────────────────────────

    def _drag_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag_motion(self, event):
        x = self._win.winfo_x() + event.x - self._drag_x
        y = self._win.winfo_y() + event.y - self._drag_y
        self._win.geometry(f"+{x}+{y}")


# ── SimulatedOptiShot (legacy keyboard-driven simulation) ─────────────────────

class SimulatedOptiShot:
    """Mocks hid.device to provide simulated swing data on keyboard input."""

    def __init__(self):
        print("\n" + "*" * 40)
        print(" SIMULATION MODE ACTIVE")
        print(" Press Ctrl+Space or Ctrl+S to simulate a random swing.")
        print(" Use the Manual Simulation window for precise control.")
        print(" Press 'Q' to quit.")
        print("*" * 40 + "\n")
        try:
            import msvcrt
            self.msvcrt = msvcrt
        except ImportError:
            self.msvcrt = None
            print("Warning: msvcrt not found. Simulation input may not work on non-Windows.")

    def get_manufacturer_string(self):
        return "Virtual Golf Co."

    def get_product_string(self):
        return "SimuShot 2000"

    def write(self, data):
        pass

    def read(self, size, club_name="Driver"):
        if self.msvcrt and self.msvcrt.kbhit():
            key = self.msvcrt.getch().lower()
            if key == b'q':
                sys.exit()
            if key in (b's', b'\r'):
                return self.generate_swing_packet(club_name)
        return []

    def close(self):
        print("Simulation closed.")

    def generate_swing_packet(self, club_name="Driver"):
        return generate_simulated_shot(club_name)
