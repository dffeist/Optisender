import tkinter as tk
import tkinter.font as tkfont
import queue
import threading


BG        = "#1a1a1a"
FG        = "#e0e0e0"
ACCENT    = "#4fc3f7"
DIM       = "#888888"
ON_COLOR  = "#66bb6a"
OFF_COLOR = "#ef5350"
FONT_HDR  = ("Consolas", 20, "bold")
FONT_VAL  = ("Consolas", 20)
FONT_LBL  = ("Consolas", 18)
WARN_COLOR = "#ffa726"
WIDTH     = 160
FULL_HEIGHT = 648
TARGET_ROWS = [("openconnect", "Open Connect"), ("opengolfsim", "OpenGolfSim")]
FIT_WIDTH = WIDTH - 14   # label width available after the frame padding
MIN_VAL_SIZE = 8


class OverlayDisplay:
    """
    Narrow floating overlay for OptiSender club metrics.
    Runs in its own thread. Update via push_state(state_dict).
    """

    def __init__(self, sim_input=None):
        self._queue = queue.Queue()
        self._sim_input = sim_input
        self._tk_ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def schedule_ui(self, func):
        """Schedule a callable to run on the Tk thread. Safe to call from any thread."""
        self._tk_ready.wait()
        self._root.after(0, func)

    def push_state(self, state: dict):
        """Thread-safe update called from the main OptiSender loop."""
        self._queue.put(state)

    # ------------------------------------------------------------------

    def _run(self):
        self._root = tk.Tk()
        self._tk_ready.set()
        self._root.title("OptiSender")
        self._root.overrideredirect(True)  # remove OS title bar and buttons
        self._root.configure(bg=BG)
        self._root.geometry(f"{WIDTH}x{FULL_HEIGHT}+13+27")
        self._root.attributes("-topmost", True)
        self._always_on_top = True
        self._collapsed = False
        self._left_handed = False
        self._drag_x = 0
        self._drag_y = 0

        self._build_ui()
        self._poll()
        self._root.mainloop()

    def _build_ui(self):
        root = self._root

        # ── Title / drag bar ─────────────────────────────────────────
        title_bar = tk.Frame(root, bg="#2a4a6b", cursor="fleur")
        title_bar.pack(fill="x")
        self._title_bar = title_bar
        title_lbl = tk.Label(title_bar, text="⛳ OptiSender  ✥", bg="#2a4a6b", fg="#ffffff",
                             font=("Consolas", 11, "bold"), pady=4, cursor="fleur")
        title_lbl.pack(side="left", padx=6)
        self._pin_btn = tk.Button(
            title_bar, text="📌", bg="#2a4a6b", fg="#ffffff",
            font=("Consolas", 9), relief="flat", cursor="hand2",
            activebackground="#3a5a7b", activeforeground="#ffffff",
            command=self._toggle_pin
        )
        self._pin_btn.pack(side="right", padx=4)
        for widget in (title_bar, title_lbl):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>",     self._drag_motion)
            widget.bind("<Double-Button-1>", self._toggle_collapse)

        # ── Connection status ─────────────────────────────────────────
        self._conn_lbl = tk.Label(root, text="● Connected", bg=BG,
                                  fg=ON_COLOR, font=("Consolas", 10, "bold"), anchor="center")
        self._conn_lbl.pack(fill="x", padx=5, pady=(4, 1))

        # ── Status row (Ball / Hand) ──────────────────────────────────
        status = tk.Frame(root, bg=BG)
        status.pack(fill="x", padx=5, pady=(2, 1))
        tk.Label(status, text="B:", bg=BG, fg=DIM,
                 font=FONT_LBL).pack(side="left")
        self._ball_lbl = tk.Label(status, text="ON", bg=BG,
                                  fg=ON_COLOR, font=FONT_HDR)
        self._ball_lbl.pack(side="left", padx=(1, 8))
        tk.Label(status, text="H:", bg=BG, fg=DIM,
                 font=FONT_LBL).pack(side="left")
        self._hand_lbl = tk.Label(status, text="RH", bg=BG,
                                  fg="#f57c00", font=FONT_HDR)
        self._hand_lbl.pack(side="left", padx=(1, 0))

        # ── Tuning Editor Button ──────────────────────────────────────
        self._tuning_btn = tk.Button(
            root, text="Tuning", bg="#2a4a6b", fg="#ffffff",
            font=("Consolas", 10, "bold"), relief="flat", cursor="hand2",
            activebackground="#3a5a7b", activeforeground="#ffffff",
            command=self._handle_tuning_click
        )
        self._tuning_btn.pack(fill="x", padx=5, pady=(0, 2))

        # ── API targets (checkbox = send to that simulator; dot = connection) ──
        self._target_vars = {}
        self._target_dots = {}
        for name, text in TARGET_ROWS:
            row = tk.Frame(root, bg=BG)
            row.pack(fill="x", padx=5, pady=0)
            var = tk.BooleanVar(value=False)
            self._target_vars[name] = var
            tk.Checkbutton(
                row, text=text, variable=var, bg=BG, fg=FG, selectcolor="#333333",
                activebackground=BG, activeforeground=FG, font=("Consolas", 9),
                anchor="w", cursor="hand2",
                command=lambda n=name: self._handle_target_click(n)
            ).pack(side="left")
            dot = tk.Label(row, text="●", bg=BG, fg=DIM, font=("Consolas", 10, "bold"))
            dot.pack(side="right")
            self._target_dots[name] = dot

        # ── Reconnect / manual ready for every enabled target ─────────
        actions = tk.Frame(root, bg=BG)
        actions.pack(fill="x", padx=5, pady=(2, 0))
        for text, action in (("Reconnect", "reconnect"), ("Send Ready", "ready")):
            tk.Button(
                actions, text=text, bg="#2a4a6b", fg="#ffffff",
                font=("Consolas", 8, "bold"), relief="flat", cursor="hand2",
                activebackground="#3a5a7b", activeforeground="#ffffff",
                command=lambda a=action: self._handle_target_action(a)
            ).pack(side="left", fill="x", expand=True, padx=1)

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
        self._val_fonts = {}
        for display_name, key, unit in club_rows:
            cell = tk.Frame(metrics_frame, bg=BG)
            cell.pack(fill="x", pady=2)
            tk.Label(cell, text=display_name, bg=BG, fg=DIM,
                     font=FONT_LBL, anchor="center").pack(fill="x")
            var = tk.StringVar(value="---")
            val_font = tkfont.Font(family="Consolas", size=14 if key == "face_angle" else FONT_VAL[1])
            self._vars[key] = (var, unit)
            self._val_fonts[key] = (val_font, val_font.cget("size"))
            tk.Label(cell, textvariable=var, bg=BG, fg=FG,
                     font=val_font, anchor="center").pack(fill="x")

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

        if "targets" in s:
            colors = {"connected": ON_COLOR, "connecting": WARN_COLOR, "off": DIM}
            for name, info in s["targets"].items():
                if name in self._target_vars:
                    self._target_vars[name].set(info["enabled"])
                    self._target_dots[name].config(fg=colors.get(info["status"], DIM))
            if len(s) == 1:
                return

        if "simulation_mode" in s:
            sim = s["simulation_mode"]
            self._conn_lbl.config(
                text="◌ Simulation" if sim else "● Connected",
                fg=DIM if sim else ON_COLOR
            )

        using_ball = s.get("using_ball", True)
        self._ball_lbl.config(
            text="ON" if using_ball else "OFF",
            fg=ON_COLOR if using_ball else OFF_COLOR
        )
        left_handed = s.get("left_handed", self._left_handed)
        self._left_handed = left_handed
        self._hand_lbl.config(
            text="LH" if left_handed else "RH",
            fg="#1565c0" if left_handed else "#f57c00"
        )

        club   = s.get("club", "")
        source = s.get("source", "")
        hand   = s.get("hand_label", "RH")
        if club:
            self._club_lbl.config(text=club)

        # Switching hands makes the last shot's labels wrong for the new hand — blank them.
        if s.get("clear_shot"):
            for var, _ in self._vars.values():
                var.set("---")

        # Values arrive already named for the golfer's hand (see swing_labels.py).
        for key in ("club_speed", "face_angle", "swing_path", "face_contact", "smash_factor"):
            value = s.get(key)
            if key in self._vars and value is not None:
                var, unit = self._vars[key]
                text = f"{value}{unit}" if unit else str(value)
                var.set(text)
                self._fit_font(key, text)

    def _fit_font(self, key, text):
        """Shrink the value font from its base size until the text fits the overlay width."""
        font, base = self._val_fonts[key]
        size = base
        font.configure(size=size)
        while size > MIN_VAL_SIZE and font.measure(text) > FIT_WIDTH:
            size -= 1
            font.configure(size=size)

    def _handle_tuning_click(self):
        if self._sim_input:
            self._sim_input["toggle_tuning"] = True

    def _handle_target_click(self, name):
        if self._sim_input:
            self._sim_input["target_changes"].put((name, self._target_vars[name].get()))

    def _handle_target_action(self, action):
        if self._sim_input:
            self._sim_input["target_actions"].put(action)

    def _toggle_collapse(self, event=None):
        """Double-click on the title bar: shrink the window to just the bar, or restore it."""
        self._collapsed = not self._collapsed
        self._root.update_idletasks()
        height = self._title_bar.winfo_reqheight() if self._collapsed else FULL_HEIGHT
        self._root.geometry(f"{WIDTH}x{height}")  # size only, so the window keeps its position

    def _toggle_pin(self):
        self._always_on_top = not self._always_on_top
        self._root.attributes("-topmost", self._always_on_top)
        self._pin_btn.config(fg=ACCENT if self._always_on_top else DIM)

    def _drag_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag_motion(self, event):
        x = self._root.winfo_x() + event.x - self._drag_x
        y = self._root.winfo_y() + event.y - self._drag_y
        self._root.geometry(f"+{x}+{y}")


def _sep(parent):
    tk.Frame(parent, bg="#333333", height=1).pack(fill="x", pady=2)
