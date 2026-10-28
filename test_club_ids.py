"""Checks simulator club ids map to clubs that tuning.json knows, so no shot silently uses Driver values.

Run:  python test_club_ids.py
"""
import contextlib
import io
import os

from api_targets import _map_club
from ballphysics import PhysicsEngine

HERE = os.path.dirname(os.path.abspath(__file__))

# ids seen from MuniGolf: DR, I6, I7, SW. The rest follow the Open Connect numbering convention.
EXPECTED = {
    "DR": "Driver", "1W": "Driver", "W1": "Driver",
    "W3": "3W", "W5": "5W", "H5": "5H",
    "I3": "3I", "I4": "4I", "I5": "5I", "I6": "6I", "I7": "7I", "I8": "8I", "I9": "9I",
    "PW": "PW", "GW": "GW", "AW": "GW", "UW": "GW", "SW": "SW", "LW": "LW", "PT": "Putter",
    # clubs with no tuning entry map to the nearest tuned club
    "W2": "3W", "W4": "3W", "W7": "5W", "H2": "5H", "H3": "5H", "H4": "5H", "I1": "3I", "I2": "3I",
    # already in tuning.json form, or different case / spacing
    "8I": "8I", "3W": "3W", "i8": "8I", " I7 ": "7I", "dr": "Driver",
}


def flight(engine, club):
    metrics = {"speed": 79.0, "face_angle": 0.0, "path_deg": 0.0, "contact": 0.0}
    return engine.calculate_ball_flight(metrics, club)


def main():
    engine = PhysicsEngine(os.path.join(HERE, "tuning.json"))

    for cid, name in EXPECTED.items():
        assert _map_club(cid) == name, (cid, _map_club(cid), name)
        assert name in engine.params, f"{cid} maps to {name!r}, which tuning.json has no entry for"

    # the reported bug: an 8 iron selected in the simulator must use the 8 iron tuning, not the Driver's
    ball = flight(engine, _map_club("I8"))
    assert ball.launch_angle == engine.params["8I"]["Vla"] == 23.0
    assert ball.total_spin == engine.params["8I"]["BS"]
    assert ball.launch_angle != flight(engine, "Driver").launch_angle

    # an unknown club is not silent: it warns once, then still returns Driver values
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        first = flight(engine, "Z9")
        second = flight(engine, "Z9")
    assert buf.getvalue().count("No tuning for club 'Z9'") == 1, buf.getvalue()
    assert first.launch_angle == second.launch_angle == flight(engine, "Driver").launch_angle

    # a tuned club never warns
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        flight(engine, "7I")
    assert buf.getvalue() == ""

    print("All club id checks passed.")


if __name__ == "__main__":
    main()
