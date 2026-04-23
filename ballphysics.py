import json
import math
import os

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

    def calculate_ball_flight(self, metrics, club_name, left_handed=False):
        """
        Calculates ball flight based on metrics dictionary from ShotProcessor.
        left_handed flips face_angle and path signs so physics are correct for LH players.
        """
        ball = BallFlight()

        # Extract values from metrics dictionary
        club_speed   = metrics.get('speed', 0.0)
        face_contact = metrics.get('contact', 0.0)

        # Apply handedness correction to sensor values before any calculation.
        # Raw sensor sees LH swing as a mirrored RH swing — flip both signs.
        sign = -1 if left_handed else 1
        face_angle = metrics.get('face_angle', 0.0) * sign
        path       = metrics.get('path', 0.0)       * sign

        club_params = self.params.get(club_name, self.params.get("Driver"))

        # 1. Ball Speed
        smash = club_params.get("BallSpeed", 1.45)
        contact_penalty = abs(face_contact) * 0.05
        ball.ball_speed = club_speed * (smash - contact_penalty)

        # 2. Vertical Launch Angle
        base_vla = (club_params.get("VlaLow", 10) + club_params.get("VlaHigh", 14)) / 2.0
        ball.launch_angle = base_vla + (face_angle * 0.3)

        # 3. Horizontal Launch Angle — mostly face, some path
        ball.launch_direction = (face_angle * 0.85) + (path * 0.15)

        # 4. Total Spin — base rate scaled by club speed
        spin_base = (club_params.get("BSLow", 2000) + club_params.get("BSHigh", 3000)) / 2.0
        ball.total_spin = spin_base * (club_speed / 100.0)

        # 5. Spin Axis — face-to-path difference drives curve
        # Positive = fade/slice (RH), negative = draw/hook (RH).
        # Multiplier 1.0: each degree of face-to-path ≈ 1° of spin axis tilt.
        face_to_path = face_angle - path
        ball.spin_axis = face_to_path * 1.0

        return ball
