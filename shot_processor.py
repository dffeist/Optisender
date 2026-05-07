import math
import json
import os

class ShotProcessor:
    """
    Translates raw OptiShot sensor data into physical club metrics.
    """
    def __init__(self, tuning_file="tuning.json"):
        # Constants
        self.SENSOR_SPACING = 185     # Hardware tick units (matches RepliShot SENSORSPACING)
        self.LED_SPACING = 15         # Hardware tick units (matches RepliShot LEDSPACING)
        self.MPH_CONV = 2236.94       # Conversion to MPH

        tuning = {}
        if os.path.exists(tuning_file):
            try:
                with open(tuning_file, 'r') as f:
                    tuning = json.load(f)
            except Exception:
                pass
        self.SPEED_CAL = tuning.get("SpeedCalibration", 1.10)

    def process_raw_buffer(self, data, using_ball=True):
        """
        Parses the 60-byte HID packet.
        Returns a dictionary of metrics based on RepliShot logic.
        """
        elapsed_time = 0
        first_front = True
        potential_ball_read = False
        no_ball = False
        ball_skip_idx = 0
        swing_speed = 0.0
        smash_factor = 1.0

        min_front, max_front = 7, 0
        min_back, max_back = 7, 0

        # PASS 1: Speed, Timing, and Ball Detection
        for i in range(0, 60, 5):
            opcode = data[i + 2]
            gap = (data[i + 3] << 8) | data[i + 4]

            if opcode in [0x52, 0x4A]:
                elapsed_time += gap

            if opcode in [0x81, 0x52, 0x4A]:
                # Front bits (Byte 0), Back bits (Byte 1)
                for j in range(8):
                    if (data[i] >> j) & 0x01:
                        min_front, max_front = min(min_front, j), max(max_front, j)
                    if (data[i + 1] >> j) & 0x01:
                        min_back, max_back = min(min_back, j), max(max_back, j)

            if opcode == 0x4A:
                if first_front:
                    first_front = False
                    swing_speed = (self.SENSOR_SPACING / (elapsed_time * 18.0)) * self.MPH_CONV * self.SPEED_CAL
                elif using_ball and not no_ball:
                    if potential_ball_read:
                        if gap < 0x20:
                            # Confirm ball hit: adjust speed to exclude impact duration
                            prev_gap = (data[i - 2] << 8) | data[i - 1]
                            adj_time = elapsed_time - prev_gap
                            swing_speed = (self.SENSOR_SPACING / (adj_time * 18.0)) * self.MPH_CONV * self.SPEED_CAL
                            ball_skip_idx = i - 5
                            potential_ball_read = False
                        else:
                            no_ball = True
                    if gap > 0x25:
                        potential_ball_read = True

        if elapsed_time <= 0:
            return None

        # PASS 2: Face Angle (Trigonometric logic)
        face_angle = self._calculate_face_angle(data, elapsed_time, ball_skip_idx)
        path = (max_front - max_back) + (min_front - min_back)  # integer, used by physics
        centroid_front = ((min_front + max_front) / 2.0) * self.LED_SPACING
        centroid_back  = ((min_back  + max_back)  / 2.0) * self.LED_SPACING
        lateral_delta  = centroid_front - centroid_back
        path_deg = math.degrees(math.atan2(lateral_delta, self.SENSOR_SPACING))

        # Calculate Smash Factor (from RepliShot shotprocessing.cpp:232)
        if max_back == 0: smash_factor = 0.5
        elif max_back in [1, 2]: smash_factor = 0.94
        elif max_back == 3: smash_factor = 0.98
        elif min_back == 7: smash_factor = 0.94
        elif min_back in [6, 5]: smash_factor = 0.94
        elif min_back == 4: smash_factor = 0.98
        else: smash_factor = 1.0

        # Legacy contact metric for your API
        center_idx = (min_back + max_back) / 2.0
        face_contact = center_idx - 3.5

        return {
            "speed": round(swing_speed, 1),
            "face_angle": round(face_angle, 1),
            "path": path,
            "path_deg": round(path_deg, 1),
            "contact": face_contact, # Heel/Toe offset
            "smash_factor": smash_factor,
            "raw_min_back": min_back,
            "raw_max_back": max_back
        }

    def _calculate_face_angle(self, data, elapsed_time, ball_skip):
        """
        Python implementation of RepliShot's trigonometric face angle logic.
        """
        if elapsed_time <= 0: 
            return 0.0

        speed_per_tick = self.SENSOR_SPACING / float(elapsed_time)
        back_accum, back_count = 0.0, 0
        front_accum, front_count = 0.0, 0
        
        prev_min, prev_max = 0, 0
        is_front_section = False
        first_chunk = True

        for i in range(0, 60, 5):
            # If a ball was hit, skip all approach data per RepliShot logic
            if i < ball_skip and ball_skip > 0:
                continue
            
            temp_bits = data[i + 1] if data[i] == 0 else data[i]
            if temp_bits == 0:
                continue

            curr_min = next(j for j in range(8) if (temp_bits >> j) & 1)
            curr_max = next(j for j in reversed(range(8)) if (temp_bits >> j) & 1)

            if first_chunk:
                prev_min, prev_max = curr_min, curr_max
                first_chunk = False
                continue

            # Switch to front zone once front sensors (byte 0) are triggered
            if data[i] != 0 and not is_front_section:
                prev_min, prev_max = curr_min, curr_max
                is_front_section = True
                continue

            ticks = (data[i + 3] << 8) | data[i + 4]
            x_travel = speed_per_tick * ticks
            
            y_min = (prev_min - curr_min) * self.LED_SPACING
            y_max = (prev_max - curr_max) * self.LED_SPACING
            
            # atan(x/y) to degrees. y=1000000 used in C++ to avoid div by zero
            angle_min = math.atan(x_travel / (y_min if y_min != 0 else 1000000)) * 180 / math.pi
            angle_max = math.atan(x_travel / (y_max if y_max != 0 else 1000000)) * 180 / math.pi
            
            angle_val = angle_min if abs(angle_min) > abs(angle_max) else angle_max

            if is_front_section:
                front_accum += angle_val
                front_count += 1
            else:
                back_accum += angle_val
                back_count += 1
            
            prev_min, prev_max = curr_min, curr_max

        avg_f = (front_accum / front_count) if front_count > 0 else 0.0
        avg_b = (back_accum / back_count) if back_count > 0 else 0.0
        
        # RepliShot Weighted Average: Back sensor is twice as significant
        return (avg_f + (avg_b * 2.0)) / 3.0
