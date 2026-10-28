"""
Generate SwingData.csv: OptiSender ball flight for a Ninety Golfer (see CONTEXT.md).

Club speed is the top of each club's CLUB_SPEED_RANGES in simulation.py. Ball data comes from the
real PhysicsEngine and tuning.json, so it matches what OptiSender sends. Face Angle and Club Path
are World frame values for a right-handed golfer (positive = right of the Target Line). Distances
come from a small drag + Magnus trajectory model in this file; OptiSender has no distance model.
"""
import csv
import itertools
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from ballphysics import PhysicsEngine
from simulation import CLUB_SPEED_RANGES
from swing_labels import shot_shape_label

CLUBS = ["Driver", "3W", "5W", "5H", "3I", "4I", "5I", "6I", "7I", "8I", "9I", "PW", "GW", "SW"]
FACE_ANGLES = (-5.0, 0.0, 5.0)
CLUB_PATHS = (-5.0, 0.0, 5.0)
# Contact as the engine sees it: (min_back + max_back) / 2 - 3.5. Heel is pad index 3, Toe index 4.
CONTACTS = (("Toe", 0.5), ("Center", 0.0), ("Heel", -0.5))

# Conditions: sea level, 70 F, no wind
AIR_DENSITY = 1.19          # kg/m^3
BALL_MASS = 0.04593         # kg
BALL_RADIUS = 0.02135       # m
BALL_AREA = math.pi * BALL_RADIUS ** 2
GRAVITY = 9.81
CD = 0.24
SPIN_DECAY_PER_S = 0.04     # fraction of spin lost per second of flight
MPH_TO_MS = 0.44704
M_TO_YD = 1.0936133
DT = 0.002


def signed(value, digits=1):
    """Format with an explicit sign, without ever printing -0.0."""
    return f"{round(value, digits) + 0.0:+.{digits}f}"


def lift_coefficient(spin_ratio):
    return max(0.0, 1.99 * spin_ratio - 3.25 * spin_ratio ** 2) if spin_ratio < 0.306 else 0.304


def fly(ball_speed_mph, vla_deg, hla_deg, total_spin_rpm, spin_axis_deg):
    """Integrate the flight. x = downrange, y = up, z = right of the Target Line (metres).
    Returns carry, offline at landing, apex height, flight time, descent angle and landing
    spin, with distances in yards."""
    v0 = ball_speed_mph * MPH_TO_MS
    vla, hla, axis = map(math.radians, (vla_deg, hla_deg, spin_axis_deg))
    vx, vy, vz = (v0 * math.cos(vla) * math.cos(hla), v0 * math.sin(vla), v0 * math.cos(vla) * math.sin(hla))
    x = z = 0.0
    y = 0.0
    spin = total_spin_rpm * 2 * math.pi / 60.0
    t = apex = 0.0
    k = 0.5 * AIR_DENSITY * BALL_AREA / BALL_MASS
    while True:
        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        # Spin vector: backspin along +z, sidespin along -y so a positive axis curves right.
        wx, wy, wz = 0.0, -math.sin(axis), math.cos(axis)
        # Magnus direction = spin x velocity (normalised)
        mx, my, mz = wy * vz - wz * vy, wz * vx - wx * vz, wx * vy - wy * vx
        mnorm = math.sqrt(mx * mx + my * my + mz * mz) or 1.0
        cl = lift_coefficient(BALL_RADIUS * spin / speed) if speed > 0 else 0.0
        ax = -k * CD * speed * vx + k * cl * speed * speed * mx / mnorm
        ay = -k * CD * speed * vy + k * cl * speed * speed * my / mnorm - GRAVITY
        az = -k * CD * speed * vz + k * cl * speed * speed * mz / mnorm
        vx, vy, vz = vx + ax * DT, vy + ay * DT, vz + az * DT
        x, y, z = x + vx * DT, y + vy * DT, z + vz * DT
        spin *= 1.0 - SPIN_DECAY_PER_S * DT
        t += DT
        apex = max(apex, y)
        if y < 0.0 and t > 0.1:
            break
    horizontal = math.hypot(vx, vz)
    return {
        "carry": x * M_TO_YD,
        "offline": z * M_TO_YD,
        "apex": apex * M_TO_YD * 3.0,       # feet
        "time": t,
        "descent": math.degrees(math.atan2(-vy, horizontal)),
        "heading": math.atan2(vz, vx),
        "land_spin": spin * 60.0 / (2 * math.pi),
    }


def roll_out(flight):
    """Roll after landing on a medium-firm fairway: shallow, low-spin shots run out, steep
    high-spin shots stop. Rolls along the landing heading."""
    fraction = max(0.015, 0.24 - 0.0045 * flight["descent"] - 0.00001 * flight["land_spin"])
    roll = flight["carry"] * fraction
    return roll, roll * math.tan(flight["heading"])


def main():
    physics = PhysicsEngine(os.path.join(HERE, "tuning.json"))
    rows = []
    for club in CLUBS:
        club_speed = CLUB_SPEED_RANGES[club][1]
        for face, path, (contact_name, contact) in itertools.product(FACE_ANGLES, CLUB_PATHS, CONTACTS):
            # The engine takes the raw pad face angle, which is the World frame value negated.
            metrics = {"speed": club_speed, "face_angle": -face, "path_deg": path, "contact": contact}
            ball = physics.calculate_ball_flight(metrics, club)
            flight = fly(ball.ball_speed, ball.launch_angle, ball.launch_direction,
                         ball.total_spin, ball.spin_axis)
            roll, roll_offline = roll_out(flight)
            rows.append({
                "Club": club,
                "ClubSpeed_mph": f"{club_speed:.1f}",
                "FaceAngle_deg": f"{face:+.1f}",
                "ClubPath_deg": f"{path:+.1f}",
                "FaceToPath_deg": signed(face - path),
                "Contact": contact_name,
                "ContactValue": f"{contact:+.1f}",
                "BallSpeed_mph": f"{ball.ball_speed:.1f}",
                "SmashFactor": f"{ball.ball_speed / club_speed:.3f}",
                "VLA_deg": f"{ball.launch_angle:.1f}",
                "HLA_deg": signed(ball.launch_direction),
                "TotalSpin_rpm": f"{ball.total_spin:.0f}",
                "SpinAxis_deg": signed(ball.spin_axis),
                "BackSpin_rpm": f"{ball.total_spin * math.cos(math.radians(ball.spin_axis)):.0f}",
                "SideSpin_rpm": signed(ball.total_spin * math.sin(math.radians(ball.spin_axis)), 0),
                "ShotShape_RH": shot_shape_label(ball, False),
                "Apex_ft": f"{flight['apex']:.0f}",
                "FlightTime_s": f"{flight['time']:.1f}",
                "Carry_yd": f"{flight['carry']:.1f}",
                "CarryOffline_yd": signed(flight["offline"]),
                "Total_yd": f"{flight['carry'] + roll:.1f}",
                "TotalOffline_yd": signed(flight["offline"] + roll_offline),
            })
    out = os.path.join(HERE, "SwingData.csv")
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
