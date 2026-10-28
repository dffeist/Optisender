import json
import math
import os

# Gear effect from a toe or heel strike (see TOE_HEEL_RESEARCH.md). Contact is measured in pad sensor
# steps off centre (about 0.59 in each). Each point is (steps off centre, start-direction shift in
# degrees, spin-axis shift in degrees) for a Driver at full strength; values between points are
# interpolated and beyond the last point they stay capped. The first point is a dead band: Heel and Toe
# (half a step, about 0.3 in) are within normal ball-placement noise, so they only lose ball speed.
GEAR_POINTS = ((0.5, 0.0, 0.0), (1.5, 0.75, 4.0), (3.5, 1.5, 8.0))
# Gear effect is far smaller on irons and wedges. Clubs not listed here use IRON_GEAR_SCALE.
GEAR_CLUB_SCALE = {"Driver": 1.0, "3W": 0.75, "5W": 0.75, "5H": 0.5, "Putter": 0.0}
IRON_GEAR_SCALE = 0.25


class BallFlight:
    def __init__(self):
        self.ball_speed = 0.0
        self.launch_angle = 0.0 # VLA
        self.launch_direction = 0.0 # HLA
        self.total_spin = 0.0
        self.spin_axis = 0.0
        self.back_spin = 0.0
        self.side_spin = 0.0

class PhysicsEngine:
    def __init__(self, tuning_file="tuning.json"):
        self.tuning_file = tuning_file
        self.params = self.load_tuning()
        self._warned_clubs = set()

    def load_tuning(self):
        if os.path.exists(self.tuning_file):
            try:
                with open(self.tuning_file, 'r') as f:
                    return json.load(f)
            except:
                print("Error loading tuning.json, using defaults.")
        return self.create_default_tuning()

    def create_default_tuning(self):
        # Fallback if file is missing
        return {
            "Driver": { "BallSpeed": 1.48, "VlaLow": 10.0, "VlaHigh": 14.0, "BSLow": 2000, "BSHigh": 2800 }
        }

    def _compress_face(self, face_angle):
        # tanh compression: near-linear for small angles (reliable sensor zone 0-10 deg),
        # progressively dampens toward +-30 deg where OptiShot sensor error is highest.
        k = self.params.get("FaceCompression", {}).get("k", 15.0)
        return k * math.tanh(face_angle / k)

    @staticmethod
    def _gear_magnitude(steps):
        """(start-direction shift, spin-axis shift) in degrees for a strike `steps` sensor steps off
        centre, at full strength. Magnitude only; the caller applies the sign for toe/heel and hand."""
        if steps <= GEAR_POINTS[0][0]:
            return 0.0, 0.0
        for (x0, h0, a0), (x1, h1, a1) in zip(GEAR_POINTS, GEAR_POINTS[1:]):
            if steps <= x1:
                t = (steps - x0) / (x1 - x0)
                return h0 + t * (h1 - h0), a0 + t * (a1 - a0)
        return GEAR_POINTS[-1][1], GEAR_POINTS[-1][2]

    def gear_strength(self, club_name):
        """0..1: the Gear Effect slider (percent, default 0 = off) times the club's scale."""
        pct = max(0.0, min(100.0, float(self.params.get("GearEffect", 0))))
        scale_club = club_name if club_name in self.params else "Driver"   # unknown clubs already use Driver values
        return (pct / 100.0) * GEAR_CLUB_SCALE.get(scale_club, IRON_GEAR_SCALE)

    def calculate_ball_flight(self, metrics, club_name, left_handed=False):
        """
        Calculates ball flight based on metrics dictionary from ShotProcessor.
        Direction and spin are world frame (positive = right of the target line) for both hands.
        Handedness matters for launch angle (it follows Open / Closed, see CONTEXT.md) and for the gear effect
        of toe/heel strikes, whose direction is mirrored for a left-hander.
        """
        ball = BallFlight()

        # Extract values from metrics dictionary
        club_speed   = metrics.get('speed', 0.0)
        face_contact = metrics.get('contact', 0.0)

        # Raw sensor face angle is physically inverted (atan geometry runs opposite
        # to Trackman convention). Negate unconditionally.
        face_angle = metrics.get('face_angle', 0.0) * -1
        path       = metrics.get('path_deg', 0.0)

        club_params = self.params.get(club_name)
        if club_params is None:
            # Never fall back to the Driver silently: its smash, launch and spin are wrong for any other club
            if club_name not in self._warned_clubs:
                self._warned_clubs.add(club_name)
                print(f"[PHYSICS] No tuning for club '{club_name}', using Driver values.")
            club_params = self.params.get("Driver")

        # 1. Ball Speed
        smash = club_params.get("BallSpeed", 1.45)
        contact_penalty = abs(face_contact) * 0.03
        ball.ball_speed = club_speed * (smash - contact_penalty)

        # 2. Vertical Launch Angle — raw face_angle retained (loft relationship, less sensor-error sensitive).
        # An open face adds loft. Open is positive world frame for a right-hander and negative for a
        # left-hander, so the sign follows the hand.
        open_face = -face_angle if left_handed else face_angle
        base_vla = club_params.get("Vla", 12.0)
        ball.launch_angle = base_vla + (open_face * 0.3)

        # Compressed face angle for direction/spin: tanh leaves small angles (~0-10 deg) nearly
        # unchanged while dampening extreme readings (+-30 deg compresses ~48%) where sensor error peaks.
        eff_face = self._compress_face(face_angle)

        # 3. Horizontal Launch Angle — mostly face, some path
        ball.launch_direction = (eff_face * 0.85) + (path * 0.15)

        # 4. Total Spin — loft-driven base rate
        spin_base = club_params.get("BS", 2500)
        ball.total_spin = spin_base

        # 5. Spin Axis — face-to-path difference drives curve
        # Positive = fade/slice (RH), negative = draw/hook (RH).
        face_to_path = eff_face - path
        ball.spin_axis = face_to_path * 1.0

        # 6. Gear effect — a toe strike starts right and draws, a heel strike starts left and fades, for a
        # right-hander; mirrored for a left-hander. Higher pad indices are the toe end for a right-hander and
        # the heel end for a left-hander (same convention as swing_labels.contact_label), so the signed
        # contact flips with the hand. Ball speed already loses a little for any off-centre strike (step 1).
        toe_steps = face_contact * (-1.0 if left_handed else 1.0)   # positive = toward the toe
        strength = self.gear_strength(club_name)
        if strength > 0.0 and toe_steps != 0.0:
            direction, axis = self._gear_magnitude(abs(toe_steps))
            toward_toe = 1.0 if toe_steps > 0 else -1.0
            hand = -1.0 if left_handed else 1.0   # world frame is mirrored for a left-hander
            ball.launch_direction += hand * toward_toe * direction * strength
            ball.spin_axis        -= hand * toward_toe * axis * strength

        return ball
