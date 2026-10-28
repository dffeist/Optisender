"""Checks PhysicsEngine launch angle and direction for right- and left-handed golfers.

Run:  python test_ballphysics.py
"""
import os

from ballphysics import PhysicsEngine

HERE = os.path.dirname(os.path.abspath(__file__))


def flight(engine, world_face, path=0.0, club="Driver", left_handed=False):
    # The engine takes the raw pad face angle, which is the world frame value negated.
    metrics = {"speed": 90.0, "face_angle": -world_face, "path_deg": path, "contact": 0.0}
    return engine.calculate_ball_flight(metrics, club, left_handed)


def main():
    engine = PhysicsEngine(os.path.join(HERE, "tuning.json"))
    base = engine.params["Driver"]["Vla"]

    # right-handed: world +5 is Open, which adds loft (unchanged behaviour, and the default)
    assert abs(flight(engine, +5).launch_angle - (base + 1.5)) < 1e-9
    assert abs(flight(engine, -5).launch_angle - (base - 1.5)) < 1e-9
    metrics = {"speed": 90.0, "face_angle": -5.0, "path_deg": 0.0, "contact": 0.0}
    assert engine.calculate_ball_flight(metrics, "Driver").launch_angle == flight(engine, +5).launch_angle

    # left-handed: world +5 is Closed, which removes loft; world -5 is Open, which adds it
    assert abs(flight(engine, +5, left_handed=True).launch_angle - (base - 1.5)) < 1e-9
    assert abs(flight(engine, -5, left_handed=True).launch_angle - (base + 1.5)) < 1e-9

    # same golfer-frame swing gives the same launch for either hand (mirror images)
    for face in (-10, -5, -1, 0, 1, 5, 10):
        assert abs(flight(engine, face).launch_angle - flight(engine, -face, left_handed=True).launch_angle) < 1e-9

    # a square face launches the same for both hands
    assert flight(engine, 0).launch_angle == flight(engine, 0, left_handed=True).launch_angle == base

    # everything except launch angle is world frame and identical for both hands
    for club in ("Driver", "7I", "SW"):
        for face in (-5, 0, 5):
            for path in (-5, 0, 5):
                rh = flight(engine, face, path, club)
                lh = flight(engine, face, path, club, left_handed=True)
                assert (rh.ball_speed, rh.launch_direction, rh.total_spin, rh.spin_axis) == \
                       (lh.ball_speed, lh.launch_direction, lh.total_spin, lh.spin_axis), (club, face, path)

    print("All ball physics checks passed.")


if __name__ == "__main__":
    main()
