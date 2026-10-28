import json
import os
import re
import select
import socket
import sys
import time


def _exe_dir():
    """Directory of the executable (or script when running from source)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# Lives next to the exe (like tuning.json) so the overlay can save changes to it
TARGETS_FILE = os.path.join(_exe_dir(), "targets.json")

DEFAULT_CONFIG = {
    "club_source": "any",  # "any", "openconnect" or "opengolfsim": whose club selection drives OptiSender
    "openconnect": {"enabled": True, "host": "127.0.0.1", "port": 9210,
                    "device_id": "OptiSender", "send_club_data": True},
    "opengolfsim": {"enabled": False, "host": "127.0.0.1", "port": 3111},
}

RECONNECT_INTERVAL = 5.0


def load_targets_config(path=None):
    """Return DEFAULT_CONFIG overlaid with the contents of targets.json, if present."""
    path = path or TARGETS_FILE
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT_CONFIG.items()}
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                user = json.load(f)
            for key, value in user.items():
                if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                    cfg[key].update(value)
                else:
                    cfg[key] = value
        except (OSError, ValueError):
            print(f"Error loading {path}, using defaults.")
    return cfg


# Clubs an Open Connect simulator can select that have no entry in tuning.json -> nearest tuned club
_UNTUNED_FALLBACK = {
    "2W": "3W", "4W": "3W", "7W": "5W",
    "2H": "5H", "3H": "5H", "4H": "5H",
    "1I": "3I", "2I": "3I",
}


# Simulators send numbered clubs as letter + number (MuniGolf: I8, W3, H5); tuning.json names them
# number + letter (8I, 3W, 5H).
_NUMBERED_CLUB = re.compile(r"([WHI])(\d)|(\d)([WHI])")


def _map_club(cid):
    """Map a simulator club id to an OptiSender/tuning.json club name."""
    cid = cid.strip().upper()
    if cid in ("DR", "1W", "W1"): return "Driver"
    if cid == "PT": return "Putter"
    if cid in ("AW", "UW"): return "GW"
    match = _NUMBERED_CLUB.fullmatch(cid)
    if match:
        letter, number = (match.group(1), match.group(2)) if match.group(1) else (match.group(4), match.group(3))
        cid = f"{number}{letter}"
    return _UNTUNED_FALLBACK.get(cid, cid)


def save_targets_config(cfg, targets, path=None):
    """Write the config back to targets.json, with each target's current enabled state."""
    path = path or TARGETS_FILE
    for t in targets:
        cfg[t.name]["enabled"] = t.enabled
    try:
        with open(path, 'w') as f:
            json.dump(cfg, f, indent=2)
    except OSError as e:
        print(f"Could not save {path}: {e}")


class ApiTarget:
    """One simulator connection: socket, receive buffer, reconnect timer and protocol."""

    name = "base"
    label = "API"

    def __init__(self, cfg):
        self.enabled = cfg.get("enabled", False)
        self.host = cfg.get("host", "127.0.0.1")
        self.port = cfg.get("port")
        self.sock = None
        self._buffer = ""
        self._last_attempt = 0.0
        self._last_hand = None   # golfer's hand last reported on this connection

    @property
    def connected(self):
        return self.sock is not None

    @property
    def status(self):
        """"off", "connecting" (enabled, not connected yet) or "connected"."""
        if not self.enabled:
            return "off"
        return "connected" if self.sock else "connecting"

    def set_enabled(self, enabled):
        """Turn this target on or off live. Call from the main loop thread only."""
        self.enabled = bool(enabled)
        if self.enabled:
            self._last_attempt = 0.0  # connect on the next poll
        else:
            self._drop()

    def poll(self):
        """Reconnect if needed, run keep-alives and read messages. Returns a list of events:
        ("club", club_name, display_name), ("hand", "LH" or "RH") or ("result", carry, total)."""
        events = []
        if not self.enabled:
            return events
        try:
            self._connect()
            if self.sock:
                self._keep_alive()
            if self.sock:
                events = self._receive()
        except Exception as e:
            print(f"[{self.label}] Error: {e}")
            self._drop()
        return events

    def send_shot(self, ball, metrics, club):
        if not self.enabled or not self.sock:
            return False
        try:
            self.sock.sendall(json.dumps(self._shot_payload(ball, metrics, club)).encode('utf-8'))
            print(f">> Shot data sent to {self.label}.")
            return True
        except Exception as e:
            print(f"Error sending to {self.label}: {e}")
            self._drop()
            return False

    def reconnect(self):
        """Drop the connection and connect again on the next poll, which sends a fresh ready message."""
        if not self.enabled:
            return False
        self._drop()
        self._last_attempt = 0.0
        return True

    def send_ready(self):
        """Send the ready message now, without dropping the connection."""
        if not self.enabled or not self.sock:
            return False
        try:
            self._send_ready()
            print(f">> Ready sent to {self.label}.")
            return True
        except Exception as e:
            print(f"Error sending ready to {self.label}: {e}")
            self._drop()
            return False

    def close(self):
        self._drop()

    def _drop(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None
        self._buffer = ""
        self._last_hand = None   # a new connection announces the golfer's hand again

    def _hand_event(self, value):
        """[("hand", "LH"/"RH")] the first time a hand is reported on this connection and whenever it
        changes, so a manual toggle in OptiSender is not overwritten by every repeated message."""
        hand = str(value or "").strip().upper()
        if hand not in ("LH", "RH") or hand == self._last_hand:
            return []
        self._last_hand = hand
        return [("hand", hand)]

    def _connect(self):
        if self.sock is not None:
            return
        now = time.time()
        if now - self._last_attempt < RECONNECT_INTERVAL:
            return
        self._last_attempt = now
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((self.host, self.port))
            self.sock = s
            print(f"SUCCESS: Connected to {self.label} at {self.host}:{self.port}")
            self._on_connect()
        except Exception:
            self._drop()

    def _receive(self):
        events = []
        readable, _, _ = select.select([self.sock], [], [], 0)
        if not readable:
            return events
        new_data = self.sock.recv(4096).decode('utf-8')
        if not new_data:
            print(f"[{self.label}] Connection closed by remote.")
            self._drop()
            return events
        self._buffer += new_data
        decoder = json.JSONDecoder()
        while True:
            self._buffer = self._buffer.lstrip()
            if not self._buffer:
                break
            try:
                msg, end = decoder.raw_decode(self._buffer)
            except json.JSONDecodeError:
                break
            self._buffer = self._buffer[end:]
            events.extend(self._handle_message(msg))
        return events

    # Protocol hooks -------------------------------------------------------
    def _on_connect(self): pass
    def _send_ready(self): raise NotImplementedError
    def _keep_alive(self): pass
    def _handle_message(self, msg): return []
    def _shot_payload(self, ball, metrics, club): raise NotImplementedError


class OpenGolfSimTarget(ApiTarget):
    name = "opengolfsim"
    label = "OpenGolfSim API"
    HEARTBEAT_INTERVAL = 0.5

    def __init__(self, cfg):
        super().__init__(cfg)
        self._last_heartbeat = 0.0

    def _send_ready(self):
        self.sock.sendall(json.dumps({"type": "device", "status": "ready"}).encode('utf-8'))
        self._last_heartbeat = time.time()

    def _on_connect(self):
        self._send_ready()

    def _keep_alive(self):
        if time.time() - self._last_heartbeat > self.HEARTBEAT_INTERVAL:
            try:
                self._send_ready()
            except Exception:
                print(f"{self.label} heartbeat failed.")
                self._drop()

    def _handle_message(self, msg):
        if msg.get("status") != 200 and msg.get("code") != 200:
            print(f"\n[{self.label} IN] {json.dumps(msg)}")
        if msg.get("type") == "player":
            club = msg.get("data", {}).get("club", {})
            cid = club.get("id", "")
            if cid:
                return [("club", _map_club(cid), club.get("name", ""))]
        elif msg.get("type") == "result":
            res = msg.get("data", {}).get("result", {})
            print(f"\n[{self.label}] SHOT RESULT: Carry: {res.get('carry', 0):.1f} | Total: {res.get('total', 0):.1f}")
            return [("result", res.get("carry", 0), res.get("total", 0))]
        return []

    def _shot_payload(self, ball, metrics, club):
        return {
            "type": "shot",
            "shot": {
                "ballSpeed": ball.ball_speed,
                "verticalLaunchAngle": ball.launch_angle,
                "horizontalLaunchAngle": ball.launch_direction,
                "spinSpeed": ball.total_spin,
                "spinAxis": ball.spin_axis,
            },
        }


class OpenConnectTarget(ApiTarget):
    """Open Connect v1 (originated by GSPro): MuniGolf's relay, GSPro and other compatible simulators."""

    name = "openconnect"
    label = "Open Connect"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.device_id = cfg.get("device_id", "OptiSender")
        self.send_club_data = cfg.get("send_club_data", True)
        self.shot_number = 0

    def _options(self, ball_data, club_data, ready=True):
        return {
            "ContainsBallData": ball_data,
            "ContainsClubData": club_data,
            "LaunchMonitorIsReady": ready,
            "LaunchMonitorBallDetected": ready,
            "IsHeartBeat": False,
        }

    def _send_ready(self):
        ready = {
            "DeviceID": self.device_id,
            "Units": "Yards",
            "ShotNumber": self.shot_number,
            "APIversion": "1",
            "ShotDataOptions": self._options(False, False),
        }
        self.sock.sendall(json.dumps(ready).encode('utf-8'))

    def _on_connect(self):
        self._send_ready()

    def _handle_message(self, msg):
        code = msg.get("Code")
        if code == 200:
            return []
        print(f"\n[{self.label} IN] {json.dumps(msg)}")
        if code == 201:
            player = msg.get("Player", {})
            events = []
            cid = player.get("Club", "")
            if cid:
                events.append(("club", _map_club(cid), cid))
            return events + self._hand_event(player.get("Handed"))
        return []

    def _shot_payload(self, ball, metrics, club):
        self.shot_number += 1
        payload = {
            "DeviceID": self.device_id,
            "Units": "Yards",
            "ShotNumber": self.shot_number,
            "APIversion": "1",
            "BallData": {
                "Speed": round(ball.ball_speed, 1),
                "SpinAxis": round(ball.spin_axis, 1),
                "TotalSpin": round(ball.total_spin, 1),
                "HLA": round(ball.launch_direction, 1),
                "VLA": round(ball.launch_angle, 1),
            },
            "ShotDataOptions": self._options(True, self.send_club_data),
        }
        if self.send_club_data:
            payload["ClubData"] = {
                "Speed": metrics["speed"],
                "Path": metrics["path_deg"],
                # Raw sensor face angle is inverted vs. Trackman; Open Connect expects open = positive.
                "FaceToTarget": -metrics["face_angle"],
                "SpeedAtImpact": metrics["speed"],
            }
        return payload


_TARGET_CLASSES = (OpenConnectTarget, OpenGolfSimTarget)


def build_targets(cfg):
    """Instantiate every target (enabled or not) so it can be switched on live."""
    return [cls(cfg.get(cls.name, {})) for cls in _TARGET_CLASSES]
