import json
import math
import os

class ShotData:
    def __init__(self):
        self.club_speed = 0.0
        self.face_angle = 0.0
        self.path = 0.0
        self.face_contact = 0  # 0=Center, +/- are heel/toe
        self.swing_detected = False

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

    def process_raw_data(self, data):
        """
        Parses the 60-byte raw data array from OptiShot.
        Ported from shotprocessing.cpp
        """
        shot = ShotData()
        
        elapsed_time = 0
        first_front = True
        
        min_front = 7
        max_front = 0
        min_back = 7
        max_back = 0
        
        front_count = 0
        back_count = 0

        # 1. Parse Swing Speed and Sensor Extents
        # Iterate in chunks of 5 bytes
        for i in range(0, len(data), 5):
            # Check for header bytes
            if i + 4 >= len(data): break
            
            # 0x81: Origin / Sensor data
            if data[i + 2] == 0x81:
                # Check Front Sensors (byte 0)
                if data[i] != 0:
                    for j in range(8):
                        if (data[i] >> j) & 0x01:
                            min_front = min(min_front, j)
                            max_front = max(max_front, j)
                            front_count += 1
                # Check Back Sensors (byte 1)
                else:
                    for j in range(8):
                        if (data[i+1] >> j) & 0x01:
                            min_back = min(min_back, j)
                            max_back = max(max_back, j)
                            back_count += 1
            
            # 0x52: Additional Timing
            if data[i + 2] == 0x52:
                elapsed_time += (data[i+3] * 256 + data[i+4])
                # Check Back Sensors again
                for j in range(8):
                    if (data[i+1] >> j) & 0x01:
                        min_back = min(min_back, j)
                        max_back = max(max_back, j)
                        back_count += 1
            
            # 0x4A: End of segment / Front sensor timing
            if data[i + 2] == 0x4A:
                elapsed_time += (data[i+3] * 256 + data[i+4])
                # Check Front Sensors
                for j in range(8):
                    if (data[i] >> j) & 0x01:
                        min_front = min(min_front, j)
                        max_front = max(max_front, j)
                        front_count += 1
                
                # Calculate Speed on first front sensor group detection
                if first_front:
                    first_front = False
                    if elapsed_time > 0:
                        # Formula from C++: (SENSORSPACING / (time * 18)) * 2236.94
                        # 2236.94 is approx factor to convert m/s to MPH if SENSORSPACING is meters
                        # We treat SENSORSPACING as a calibration constant.
                        shot.club_speed = (self.SENSOR_SPACING / (elapsed_time * 18.0)) * 2.23694
        
        if elapsed_time == 0 or shot.club_speed == 0:
            return shot # Empty shot
        
        shot.swing_detected = True

        # 2. Calculate Face Angle (Open/Closed)
        # Based on atan(x_travel / y_travel)
        speed_per_tick = self.SENSOR_SPACING / float(elapsed_time) if elapsed_time else 0
        
        front_angle_accum = 0.0
        back_angle_accum = 0.0
        f_count = 0
        b_count = 0
        
        is_front_section = False
        # Heuristics for previous sensor position to calculate Y delta
        prev_min = 3 # Approx center default
        prev_max = 4

        for i in range(0, len(data), 5):
            if data[i] != 0 or data[i+1] != 0:
                # Determine min/max bits set in this chunk
                temp_val = data[i] if data[i] != 0 else data[i+1]
                
                # Find first bit set
                curr_min = 0
                while ((temp_val >> curr_min) & 0x1) == 0 and curr_min < 8: curr_min += 1
                
                # Find last bit set
                curr_max = 7
                while ((temp_val >> curr_max) & 0x1) == 0 and curr_max >= 0: curr_max -= 1

                # Identify if we switched to front sensors
                if data[i] != 0 and not is_front_section:
                    is_front_section = True
                    prev_min = curr_min
                    prev_max = curr_max
                    continue # Skip transition
                
                # Calculate angle for this segment
                ticks = data[i+3] * 256 + data[i+4]
                x_travel = speed_per_tick * ticks
                
                # Y travel based on sensor indices
                y_travel_min = (prev_min - curr_min) * self.LED_SPACING
                if y_travel_min == 0: y_travel_min = 10000.0 # Avoid div by zero
                
                y_travel_max = (prev_max - curr_max) * self.LED_SPACING
                if y_travel_max == 0: y_travel_max = 10000.0

                angle_min = math.atan(x_travel / y_travel_min) * 180.0 / math.pi
                angle_max = math.atan(x_travel / y_travel_max) * 180.0 / math.pi

                # Accumulate
                angle_val = angle_min if abs(angle_min) > abs(angle_max) else angle_max
                
                if is_front_section:
                    front_angle_accum += angle_val
                    f_count += 1
                else:
                    back_angle_accum += angle_val
                    b_count += 1
                
                prev_min = curr_min
                prev_max = curr_max

        # Weighted Average
        avg_front = front_angle_accum / f_count if f_count > 0 else 0
        avg_back = back_angle_accum / b_count if b_count > 0 else 0
        shot.face_angle = ((avg_front) + (avg_back * 2)) / 3.0
        
        # 3. Path & Contact
        shot.path = (max_front + min_front) - (max_back + min_back)
        
        # Simplified contact logic based on back sensors
        # 0-3 are inside/heel?, 4-7 are outside/toe? depends on handedness.
        # OptiShot raw data: 0 is usually far side, 7 is near side.
        # Center is roughly 3-4.
        center_idx = (min_back + max_back) / 2.0
        shot.face_contact = center_idx - 3.5 # 0 is center, pos is Toe, neg is Heel

        return shot

    def calculate_ball_flight(self, shot, club_name):
        ball = BallFlight()
        
        club_params = self.params.get(club_name, self.params.get("Driver")) # Default to Driver if not found
        
        # 1. Ball Speed (Smash Factor)
        smash = club_params.get("BallSpeed", 1.45)
        # Penalty for off-center hit
        contact_penalty = abs(shot.face_contact) * 0.05
        ball.ball_speed = shot.club_speed * (smash - contact_penalty)
        
        # 2. Launch Angle (VLA)
        base_vla = (club_params.get("VlaLow", 10) + club_params.get("VlaHigh", 14)) / 2.0
        # Open face increases dynamic loft
        ball.launch_angle = base_vla + (shot.face_angle * 0.3)
        
        # 3. Horizontal Angle (HLA)
        # Mostly face, some path
        ball.launch_direction = (shot.face_angle * 0.85) + (shot.path * 0.5) # path raw is abstract, scale it
        
        # 4. Spin
        spin_base = (club_params.get("BSLow", 2000) + club_params.get("BSHigh", 3000)) / 2.0
        ball.total_spin = spin_base * (shot.club_speed / 100.0) # Scale with speed
        
        # Spin Axis (Curve)
        # Difference between Face and Path
        ball.spin_axis = (shot.face_angle - (shot.path * 1.5)) * 2.5
        
        return ball
