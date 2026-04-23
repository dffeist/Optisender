import tkinter as tk
import queue
import threading


BG        = "#1a1a1a"
FG        = "#e0e0e0"
ACCENT    = "#4fc3f7"
DIM       = "#888888"
ON_COLOR  = "#66bb6a"
OFF_COLOR = "#ef5350"
FONT_HDR  = ("Consolas", 10, "bold")
FONT_VAL  = ("Consolas", 10)
FONT_LBL  = ("Consolas", 9)
WIDTH     = 160


class OverlayDisplay:
    """
    Narrow floating overlay for OptiSender club metrics.
    Runs in its own thread. Update via push_state(state_dict).
    """

    def __init__(self):
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def push_state(self, state: dict):
        """Thread-safe update called from the main OptiSender loop."""
        self._queue.put(state)

    # ------------------------------------------------------------------

    def _run(self):
        self._root = tk.Tk()
        self._root.title("OptiSender")
        self._root.configure(bg=BG)
        self._root.resizable(False, False)
        self._root.geometry(f"{WIDTH}x224+15+25")
        self._root.attributes("-topmost", True)
        self._always_on_top = True
        self._drag_x = 0
        self._drag_y = 0

        self._build_ui()
        self._poll()
        self._root.mainloop()

    def _build_ui(self):
        root = self._root

        # ── Title / drag bar ─────────────────────────────────────────
        title_bar = tk.Frame(root, bg="#111111", cursor="fleur")
        title_bar.pack(fill="x")
        tk.Label(title_bar, text="⛳ OptiSender", bg="#111111", fg=ACCENT,
                 font=FONT_HDR, pady=4).pack(side="left", padx=6)
        self._pin_btn = tk.Button(
            title_bar, text="📌", bg="#111111", fg=ACCENT,
            font=("Consolas", 9), relief="flat", cursor="hand2",
            command=self._toggle_pin
        )
        self._pin_btn.pack(side="right", padx=4)
        title_bar.bind("<ButtonPress-1>", self._drag_start)
        title_bar.bind("<B1-Motion>",     self._drag_motion)

        # ── Status row (Ball / Hand) ──────────────────────────────────
        status = tk.Frame(root, bg=BG)
        status.pack(fill="x", padx=5, pady=(4, 1))
        tk.Label(status, text="B:", bg=BG, fg=DIM,
                 font=FONT_LBL).pack(side="left")
        self._ball_lbl = tk.Label(status, text="ON", bg=BG,
                                  fg=ON_COLOR, font=FONT_HDR)
        self._ball_lbl.pack(side="left", padx=(1, 8))
        tk.Label(status, text="H:", bg=BG, fg=DIM,
                 font=FONT_LBL).pack(side="left")
        self._hand_lbl = tk.Label(status, text="RH", bg=BG,
                                  fg=ACCENT, font=FONT_HDR)
        self._hand_lbl.pack(side="left", padx=(1, 0))

        # ── D-toggle hint ─────────────────────────────────────────────
        self._pin_hint = tk.Label(root, text="D: always-on-top  ON",
                                  bg=BG, fg=DIM, font=("Consolas", 8))
        self._pin_hint.pack(fill="x", padx=5, pady=(0, 2))

        _sep(root)

        # ── Club header ───────────────────────────────────────────────
        self._club_lbl = tk.Label(root, text="Waiting…",
                                  bg=BG, fg=ACCENT, font=FONT_HDR,
                                  anchor="center")
        self._club_lbl.pack(fill="x", padx=5, pady=(2, 0))

        _sep(root)

        # ── Club metrics ──────────────────────────────────────────────
        metrics_frame = tk.Frame(root, bg=BG)
        metrics_frame.pack(fill="x", padx=5, pady=2)

        club_rows = [
            ("Club Spd",  "club_speed",   " mph"),
            ("Face Ang",  "face_angle",   ""),
            ("Path",      "swing_path",   ""),
            ("Contact",   "face_contact", ""),
            ("Smash",     "smash_factor", ""),
        ]

        self._vars = {}
        for display_name, key, unit in club_rows:
            row = tk.Frame(metrics_frame, bg=BG)
            row.pack(fill="x")
            tk.Label(row, text=display_name, bg=BG, fg=DIM,
                     font=FONT_LBL, width=9, anchor="w").pack(side="left")
            var = tk.StringVar(value="---")
            self._vars[key] = (var, unit)
            tk.Label(row, textvariable=var, bg=BG, fg=FG,
                     font=FONT_VAL, anchor="e").pack(side="right")

    # ------------------------------------------------------------------

    def _poll(self):
        try:
            while True:
                state = self._queue.get_nowait()
                self._apply_state(state)
        except queue.Empty:
            pass
        self._root.after(50, self._poll)

    def _apply_state(self, s: dict):
        if s.get("_toggle_pin"):
            self._toggle_pin()
            return

        using_ball = s.get("using_ball", True)
        self._ball_lbl.config(
            text="ON" if using_ball else "OFF",
            fg=ON_COLOR if using_ball else OFF_COLOR
        )
        left_handed = s.get("left_handed", False)
        self._hand_lbl.config(text="LH" if left_handed else "RH")

        club   = s.get("club", "")
        source = s.get("source", "")
        hand   = s.get("hand_label", "RH")
        if club:
            self._club_lbl.config(text=f"{club} [{source}]")

        for key in ("club_speed", "face_angle", "swing_path", "face_contact", "smash_factor"):
            value = s.get(key)
            if key in self._vars and value is not None:
                var, unit = self._vars[key]
                var.set(f"{value}{unit}" if unit else str(value))

    def _toggle_pin(self):
        self._always_on_top = not self._always_on_top
        self._root.attributes("-topmost", self._always_on_top)
        state_str = "ON" if self._always_on_top else "OFF"
        self._pin_btn.config(fg=ACCENT if self._always_on_top else DIM)
        self._pin_hint.config(text=f"D: always-on-top  {state_str}")

    def _drag_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag_motion(self, event):
        x = self._root.winfo_x() + event.x - self._drag_x
        y = self._root.winfo_y() + event.y - self._drag_y
        self._root.geometry(f"+{x}+{y}")


def _sep(parent):
    tk.Frame(parent, bg="#333333", height=1).pack(fill="x", pady=2)
