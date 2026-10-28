"""Checks the toe/heel gear effect in PhysicsEngine, for right- and left-handed golfers.

Run:  python test_gear_effect.py
"""
import copy
import os

from ballphysics import PhysicsEngine
from simulation import contact_metrics
from swing_labels import describe_swing

HERE = os.path.dirname(os.path.abspath(__file__))
CLUBS = ("Driver", "3W", "5W", "5H", "3I", "7I", "9I", "PW", "SW", "LW")


def engine(pct):
    e = PhysicsEngine(os.path.join(HERE, "tuning.json"))
    e.params = copy.deepcopy(e.params)
    if pct is None:
        e.params.pop("GearEffect", None)
    else:
        e.params["GearEffect"] = pct
    return e


def flight(e, raw_contact, club="Driver", left_handed=False, face=0.0, path=0.0):
    metrics = {"speed": 90.0, "face_angle": -face, "path_deg": path, "contact": raw_contact}
    return e.calculate_ball_flight(metrics, club, left_handed)


def close(a, b):
    return abs(a - b) < 1e-9


def shift(e, raw_contact, **kw):
    """(start direction shift, spin axis shift) caused by the gear effect alone."""
    base, hit = flight(e, 0.0, **kw), flight(e, raw_contact, **kw)
    return hit.launch_direction - base.launch_direction, hit.spin_axis - base.spin_axis


def main():
    # 1. off by default, and when the slider is 0: toe/heel only cost ball speed
    for pct in (None, 0):
        e = engine(pct)
        for club in CLUBS:
            for lh in (False, True):
                base = flight(e, 0.0, club, lh, face=3, path=-2)
                for raw in (-3.5, -1.5, -0.5, 0.5, 1.5, 3.5):
                    hit = flight(e, raw, club, lh, face=3, path=-2)
                    assert (hit.launch_direction, hit.spin_axis, hit.total_spin, hit.launch_angle) == \
                           (base.launch_direction, base.spin_axis, base.total_spin, base.launch_angle), (pct, club, lh, raw)
                    assert hit.ball_speed < base.ball_speed

    full = engine(100)

    # 2. right-handed Driver, full strength: toe starts right and draws, heel starts left and fades
    assert all(close(a, b) for a, b in zip(shift(full, +1.5), (+0.75, -4.0)))
    assert all(close(a, b) for a, b in zip(shift(full, -1.5), (-0.75, +4.0)))

    # 3. dead band: Heel and Toe (half a step) have no gear effect
    assert shift(full, +0.5) == (0.0, 0.0) and shift(full, -0.5) == (0.0, 0.0)

    # 4. ramps between the points and caps beyond the last
    assert all(close(a, b) for a, b in zip(shift(full, +1.0), (0.375, -2.0)))
    assert all(close(a, b) for a, b in zip(shift(full, +2.5), (1.125, -6.0)))
    assert all(close(a, b) for a, b in zip(shift(full, +3.5), (1.5, -8.0)))
    assert all(close(a, b) for a, b in zip(shift(full, +50.0), (1.5, -8.0)))
    assert all(close(a, b) for a, b in zip(shift(full, -50.0), (-1.5, +8.0)))

    # 5. the effect adds to face and path, it does not replace them
    sh = shift(full, +1.5, face=5, path=-4)
    assert all(close(a, b) for a, b in zip(sh, (0.75, -4.0)))

    # 6. left-handed: same pad reading gives the same world-frame flight (the pad end is one physical side of
    #    the face for both golfers); only its name changes (Toe for one hand is Heel for the other)
    for raw in (-3.0, -1.5, -1.0, 1.0, 1.5, 3.0):
        assert shift(full, raw, left_handed=True) == shift(full, raw, left_handed=False), raw

    # 7. the physics agrees with the on-screen label for every pad reading and both hands:
    #    Toe starts right and draws for a right-hander, starts left and draws for a left-hander;
    #    Heel is the reverse. "Right" and "draws" are world frame (draw = curves left for RH, right for LH)
    for lh in (False, True):
        for steps in (-3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
            raw, lo, hi = contact_metrics(steps, lh)
            metrics = {"speed": 90.0, "face_angle": 0.0, "path_deg": 0.0, "contact": raw,
                       "raw_min_back": lo, "raw_max_back": hi}
            ball = full.calculate_ball_flight(metrics, "Driver", lh)
            label = describe_swing(metrics, ball, lh)["face_contact"]
            if steps == 0.0:
                assert label == "Center", (lh, steps, label)
                continue
            assert ("Toe" in label) == (steps > 0) and ("Heel" in label) == (steps < 0), (lh, steps, label)
            if abs(steps) <= 0.5:
                continue   # dead band: named Heel / Toe but no gear effect
            toward = 1.0 if steps > 0 else -1.0
            side = -1.0 if lh else 1.0
            assert ball.launch_direction * side * toward > 0, (lh, steps, ball.launch_direction)
            assert ball.spin_axis * side * toward < 0, (lh, steps, ball.spin_axis)

    # 8. club scaling at full strength: Driver 100%, woods 75%, hybrid 50%, irons and wedges 25%, putter 0
    driver = shift(full, 1.5)
    for club, scale in (("3W", 0.75), ("5W", 0.75), ("5H", 0.5), ("3I", 0.25), ("7I", 0.25), ("SW", 0.25), ("Putter", 0.0)):
        assert all(close(a, b * scale) for a, b in zip(shift(full, 1.5, club=club), driver)), club

    # 9. the slider scales the effect, and is clamped to 0..100
    half = shift(engine(50), 1.5)
    assert all(close(a, b * 0.5) for a, b in zip(half, driver))
    assert shift(engine(250), 1.5) == driver
    assert shift(engine(-20), 1.5) == (0.0, 0.0)

    # 10. an unknown club uses Driver values (with a warning) and so the Driver's gear scale
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        assert shift(full, 1.5, club="Z9") == driver

    # 11. ball speed, launch angle and spin do not change with the slider
    for raw in (-2.0, 1.5, 3.0):
        a, b = flight(engine(0), raw), flight(full, raw)
        assert (a.ball_speed, a.launch_angle, a.total_spin) == (b.ball_speed, b.launch_angle, b.total_spin)

    print("All gear effect checks passed.")


if __name__ == "__main__":
    main()
