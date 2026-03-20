import sys
import random
import math

CLUB_SPEED_RANGES = {
    # (Min Amateur, Max Tour)
    "Driver": (93.0, 115.0),
    "3W": (88.0, 107.0),
    "5W": (85.0, 103.0),
    "5H": (85.0, 103.0),
    "5I": (77.0, 94.0),
    "6I": (76.0, 92.0),
    "7I": (74.0, 90.0),
    "8I": (72.0, 87.0),
    "9I": (70.0, 85.0),
    "PW": (68.0, 83.0),
    "GW": (64.0, 82.0),
    "SW": (64.0, 82.0),
    "LW": (60.0, 79.0)
}

def generate_simulated_shot(club_name="Driver"):
    # Get range for the club, default to Driver if unknown
    speed_min, speed_max = CLUB_SPEED_RANGES.get(club_name, CLUB_SPEED_RANGES["Driver"])
    
    # Pick a random base speed within the amateur-to-pro range
    base_speed = random.uniform(speed_min, speed_max)
    
    # Apply ~10% variance (0.9 to 1.1 multiplier)
    variance = random.uniform(0.9, 1.1)
    target_speed = base_speed * variance
    
    # Constants
    SENSOR_SPACING = 28500.0
    LED_SPACING = 11.5
    
    total_ticks = int((SENSOR_SPACING * 2.23694) / (target_speed * 18.0))
    
    # Target Axis (Any 10th of a degree between -7.5 and 7.5)
    target_axis = random.uniform(-7.5, 7.5)
    
    # Path Shift (-1, 0, 1) -> Path Val (approx -2, 0, 2)
    path_shift = random.randint(-1, 1)
    path_val = path_shift * 2.0 
    
    # Calculate required Face Angle to achieve target_axis
    # Formula: Axis = (Face - Path*1.5) * 2.5
    # Inverse: Face = (Axis / 2.5) + (Path * 1.5)
    target_face = (target_axis / 2.5) + (path_val * 1.5)
    
    # Calculate simulated sensor timing to produce this face angle.
    # We modulate the Back sensors to create a skew (Face Angle).
    # Face = (FrontAvg + 2*BackAvg) / 3. Assuming FrontAvg=0, BackAvg = 1.5 * TargetFace.
    target_back_angle = 1.5 * target_face
    
    contact_shift = random.randint(-1, 1) 
    b_min_A = max(0, min(7, 3 + contact_shift))
    
    # Determine BackB position to match the sign of the angle
    # Angle = atan(x/y). y = (BackA - BackB). Positive Angle requires BackA > BackB.
    if target_back_angle >= 0:
        b_min_B = b_min_A - 1 if b_min_A > 0 else b_min_A + 1
    else:
        b_min_B = b_min_A + 1 if b_min_A < 7 else b_min_A - 1
        
    y_dist = (b_min_A - b_min_B) * LED_SPACING
    # x = y * tan(angle). We use abs() because x (time) is always positive.
    x_dist = abs(y_dist * math.tan(math.radians(target_back_angle)))
    
    ticks_face = int((x_dist * total_ticks) / SENSOR_SPACING)
    # Limit ticks to 40% of total to leave room for front sensors
    ticks_face = max(0, min(ticks_face, int(total_ticks * 0.4)))
    
    remaining_ticks = total_ticks - ticks_face
    
    data = [0] * 60
    
    # Segment 1: Back Sensors A (Start) - 0x81
    data[2] = 0x81
    data[1] = (1 << b_min_A) | (1 << (min(7, b_min_A + 1)))
    
    # Segment 2: Back Sensors B (Skew + Time) - 0x52
    data[7] = 0x52
    data[6] = (1 << b_min_B) | (1 << (min(7, b_min_B + 1)))
    data[8] = (ticks_face >> 8) & 0xFF
    data[9] = ticks_face & 0xFF
    
    # Segment 3: Front Sensors (Final Time) - 0x4A
    # Placed at index 10 (data[12] is command)
    data[12] = 0x4A
    f_min = max(0, min(7, b_min_A + path_shift))
    data[10] = (1 << f_min) | (1 << (min(7, f_min + 1)))
    data[13] = (remaining_ticks >> 8) & 0xFF
    data[14] = remaining_ticks & 0xFF
    
    return data

class SimulatedOptiShot:
    """
    Mocks the hid.device class to provide simulated swing data on keyboard input.
    """
    def __init__(self):
        print("\n" + "*" * 40)
        print(" SIMULATION MODE ACTIVE")
        print(" Press 'ENTER' or 'S' to simulate a swing.")
        print(" Press 'Q' to quit.")
        print("*" * 40 + "\n")
        
        # Windows specific keyboard input for non-blocking check
        try:
            import msvcrt
            self.msvcrt = msvcrt
        except ImportError:
            self.msvcrt = None
            print("Warning: msvcrt module not found. Simulation input may not work on non-Windows.")

    def get_manufacturer_string(self):
        return "Virtual Golf Co."

    def get_product_string(self):
        return "SimuShot 2000"

    def write(self, data):
        # Simulate accepting LED commands, do nothing.
        pass

    def read(self, size):
        if self.msvcrt and self.msvcrt.kbhit():
            key = self.msvcrt.getch().lower()
            if key == b'q':
                sys.exit()
            if key == b's' or key == b'\r':
                return self.generate_swing_packet()
        return []

    def close(self):
        print("Simulation closed.")

    def generate_swing_packet(self):
        # Reuse the logic from the standalone function
        return generate_simulated_shot("Driver")
