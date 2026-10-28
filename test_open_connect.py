"""Checks OpenConnectTarget against a mock Open Connect v1 relay (no MuniGolf or hardware needed).

Run:  python test_open_connect.py
"""
import json
import socket
import threading
import time
from types import SimpleNamespace

import api_targets
from api_targets import OpenConnectTarget, load_targets_config, build_targets


class MockRelay:
    """Listens like MuniGolf's relay / GSPro Connect: answers {"Code": 200} to every message."""

    def __init__(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]
        self.received = []
        self.conn = None
        self._stop = False
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while not self._stop:
            try:
                self.server.settimeout(0.2)
                self.conn, _ = self.server.accept()
            except (socket.timeout, OSError):
                continue
            self.conn.settimeout(0.2)
            decoder, buf = json.JSONDecoder(), ""
            while not self._stop and self.conn:
                try:
                    chunk = self.conn.recv(4096).decode("utf-8")
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                while buf.strip():
                    try:
                        msg, end = decoder.raw_decode(buf.lstrip())
                    except json.JSONDecodeError:
                        break
                    buf = buf.lstrip()[end:]
                    self.received.append(msg)
                    try:
                        self.conn.sendall(json.dumps({"Code": 200, "Message": "ok"}).encode("utf-8"))
                    except OSError:
                        break

    def push(self, msg):
        self.conn.sendall(json.dumps(msg).encode("utf-8"))

    def drop_client(self):
        self.conn.close()

    def close(self):
        self._stop = True
        self.server.close()


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def pump(target, seconds=0.3, events=None):
    end = time.time() + seconds
    while time.time() < end:
        got = target.poll()
        if events is not None:
            events.extend(got)
        time.sleep(0.02)


def main():
    api_targets.RECONNECT_INTERVAL = 0.2
    relay = MockRelay()
    target = OpenConnectTarget({"enabled": True, "host": "127.0.0.1", "port": relay.port,
                                "device_id": "OptiSender", "send_club_data": True})

    # connect -> ready message, no ball data
    pump(target)
    assert target.status == "connected", target.status
    assert wait_for(lambda: relay.received), "no ready message"
    ready = relay.received[0]
    assert ready["APIversion"] == "1" and ready["DeviceID"] == "OptiSender" and ready["Units"] == "Yards"
    assert ready["ShotDataOptions"]["ContainsBallData"] is False
    assert ready["ShotDataOptions"]["LaunchMonitorIsReady"] is True

    # shot -> Open Connect v1 payload, ShotNumber increments, 200 reply produces no events
    ball = SimpleNamespace(ball_speed=120.46, launch_angle=20.64, launch_direction=-1.4,
                           total_spin=7800.0, spin_axis=-0.5)
    metrics = {"speed": 92.0, "path_deg": -1.0, "face_angle": 1.5}
    events = []
    assert target.send_shot(ball, metrics, "7I")
    assert target.send_shot(ball, metrics, "7I")
    pump(target, events=events)
    assert wait_for(lambda: len(relay.received) >= 3), "shots not received"
    shot1, shot2 = relay.received[1], relay.received[2]
    assert (shot1["ShotNumber"], shot2["ShotNumber"]) == (1, 2)
    assert shot1["BallData"] == {"Speed": 120.5, "SpinAxis": -0.5, "TotalSpin": 7800.0, "HLA": -1.4, "VLA": 20.6}
    assert shot1["ClubData"] == {"Speed": 92.0, "Path": -1.0, "FaceToTarget": -1.5, "SpeedAtImpact": 92.0}
    assert shot1["ShotDataOptions"]["ContainsBallData"] and shot1["ShotDataOptions"]["ContainsClubData"]
    assert events == [], events

    # 201 player message -> club event (also when glued to a 200 in one TCP read)
    relay.push({"Code": 201, "Message": "GSPro Player Information", "Player": {"Handed": "RH", "Club": "DR"}})
    pump(target, events=events)
    assert events == [("club", "Driver", "DR")], events
    events.clear()
    relay.push({"Code": 200})
    relay.push({"Code": 201, "Player": {"Handed": "RH", "Club": "AW"}})
    pump(target, events=events)
    assert events == [("club", "GW", "AW")], events

    # 5xx is not fatal
    relay.push({"Code": 501, "Message": "failure"})
    pump(target)
    assert target.status == "connected"

    # relay drops the client -> target notices and reconnects with a fresh ready message
    count = len(relay.received)
    relay.drop_client()
    pump(target, 0.3)
    assert wait_for(lambda: (pump(target, 0.1) or target.status == "connected") and len(relay.received) > count, 5.0), \
        "did not reconnect"

    # disabled target neither connects nor sends
    target.set_enabled(False)
    assert target.status == "off" and not target.send_shot(ball, metrics, "7I")

    target.close()
    relay.close()

    # defaults: Open Connect first and on, OpenGolfSim off
    cfg = load_targets_config(path="does-not-exist.json")
    names = [t.name for t in build_targets(cfg)]
    assert names == ["openconnect", "opengolfsim"], names
    assert cfg["openconnect"]["enabled"] and cfg["openconnect"]["port"] == 921
    assert not cfg["opengolfsim"]["enabled"]
    print("All Open Connect checks passed.")


if __name__ == "__main__":
    main()
