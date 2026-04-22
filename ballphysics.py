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
        
        # Calibration constants (Inferred from C++ code logic)
        # SENSOR_SPACING determines speed accuracy.
        self.SENSOR_SPACING = self.params["Global"].get("SensorSpacing", 28500.0)
        self.LED_SPACING = self.params["Global"].get("LedSpacing", 11.5)

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
            "Global": { "BallSpeed": 1.0, "SensorSpacing": 28500.0, "LedSpacing": 11.5 },
            "Driver": { "BallSpeed": 1.48, "VlaLow": 10.0, "VlaHigh": 14.0, "BSLow": 2000, "BSHigh": 3000 }
        }

    def calculate_ball_flight(self, metrics, club_name):
        """
        Calculates ball flight based on metrics dictionary from ShotProcessor.
        """
        ball = BallFlight()
        
        # Extract values from metrics dictionary
        club_speed = metrics.get('speed', 0.0)
        face_angle = metrics.get('face_angle', 0.0)
        path = metrics.get('path', 0.0)
        face_contact = metrics.get('contact', 0.0)
        
        club_params = self.params.get(club_name, self.params.get("Driver")) # Default to Driver if not found
        
        # 1. Ball Speed (Smash Factor)
        smash = club_params.get("BallSpeed", 1.45)
        # Penalty for off-center hit
        contact_penalty = abs(face_contact) * 0.05
        ball.ball_speed = club_speed * (smash - contact_penalty)
        
        # 2. Launch Angle (VLA)
        base_vla = (club_params.get("VlaLow", 10) + club_params.get("VlaHigh", 14)) / 2.0
        # Open face increases dynamic loft
        ball.launch_angle = base_vla + (face_angle * 0.3)
        
        # 3. Horizontal Angle (HLA)
        # Mostly face, some path
        ball.launch_direction = (face_angle * 0.85) + (path * 0.5)
        
        # 4. Spin
        spin_base = (club_params.get("BSLow", 2000) + club_params.get("BSHigh", 3000)) / 2.0
        ball.total_spin = spin_base * (club_speed / 100.0) # Scale with speed
        
        # Spin Axis (Curve)
        # Difference between Face and Path
        ball.spin_axis = (face_angle - (path * 1.5)) * 2.5
        
        return ball
