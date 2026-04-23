import sys
import random
import math

# Must match shot_processor.py exactly so decoded metrics are accurate
SENSOR_SPACING = 185
LED_SPACING    = 15
MPH_CONV       = 2236.94

CLUB_SPEED_RANGES = {
    "Driver": (93.0, 115.0),
    "3W":     (88.0, 107.0),
    "5W":     (85.0, 103.0),
    "5H":     (85.0, 103.0),
    "3I":     (80.0,  97.0),
    "4I":     (78.0,  95.0),
    "5I":     (77.0,  94.0),
    "6I":     (76.0,  92.0),
    "7I":     (74.0,  90.0),
    "8I":     (72.0,  87.0),
    "9I":     (70.0,  85.0),
    "PW":     (68.0,  83.0),
    "GW":     (64.0,  82.0),
    "SW":     (64.0,  82.0),
    "LW":     (60.0,  79.0),
    "Putter": (20.0,  45.0),
}

# Named shot profiles: face angle range (degrees), swing path integer,
# back-sensor contact zone (LED indices), and relative selection weight.
SHOT_PROFILES = {
    "straight": {"face": (-0.5,  0.5),  "path":  0, "b_center": (3, 4), "weight": 30},
    "fade":     {"face": ( 1.0,  3.0),  "path": -1, "b_center": (3, 4), "weight": 20},
    "draw":     {"face": (-3.0, -1.0),  "path":  1, "b_center": (3, 4), "weight": 20},
    "slice":    {"face": ( 5.0, 10.0),  "path": -2, "b_center": (3, 5), "weight": 10},
    "hook":     {"face": (-10.0,-5.0),  "path":  2, "b_center": (2, 4), "weight": 10},
    "toe":      {"face": ( 0.5,  3.0),  "path":  0, "b_center": (1, 2), "weight":  5},
    "heel":     {"face": (-3.0, -0.5),  "path":  0, "b_center": (5, 6), "weight":  5},
}

_PROFILE_NAMES   = list(SHOT_PROFILES.keys())
_PROFILE_WEIGHTS = [SHOT_PROFILES[k]["weight"] for k in _PROFILE_NAMES]


def _pick_profile(shot_type=None):
    if shot_type and shot_type in SHOT_PROFILES:
        return shot_type, SHOT_PROFILES[shot_type]
    name = random.choices(_PROFILE_NAMES, weights=_PROFILE_WEIGHTS, k=1)[0]
    return name, SHOT_PROFILES[name]


def generate_simulated_shot(club_name="Driver", shot_type=None, verbose=True):
    """
    Build a 60-byte HID packet that shot_processor.py will decode into
    realistic metrics for the given club and shot profile.

    Packet layout (5-byte chunks):
      Chunk 0 [0:5]   back A start  opcode=0x81
      Chunk 1 [5:10]  back B timing opcode=0x52  (encodes face angle via LED skew + timing)
      Chunk 2 [10:15] front timing  opcode=0x4A  (completes elapsed-time for speed)
      Chunks 3-11     zeros
    """
    speed_min, speed_max = CLUB_SPEED_RANGES.get(club_name, CLUB_SPEED_RANGES["Driver"])
    target_speed = random.uniform(speed_min, speed_max) * random.uniform(0.95, 1.05)

    profile_name, profile = _pick_profile(shot_type)
    target_face = random.uniform(*profile["face"])
    path_shift  = profile["path"]

    # Inverse of shot_processor speed formula:
    # swing_speed = (SENSOR_SPACING / (elapsed_time * 18)) * MPH_CONV
    total_ticks = max(1, int((SENSOR_SPACING * MPH_CONV) / (target_speed * 18.0)))

    # Back sensor A starting LED position (determines contact zone)
    b_lo, b_hi = profile["b_center"]
    b_min_A = max(0, min(7, random.randint(b_lo, b_hi)))

    # Back sensor B offset creates the skew that encodes face angle.
    # shot_processor: angle = atan(x_travel / y_dist), y_dist = delta_LED * LED_SPACING
    # Positive face requires b_min_A > b_min_B so y_dist > 0.
    if target_face >= 0:
        b_min_B = b_min_A - 1 if b_min_A > 0 else b_min_A + 1
    else:
        b_min_B = b_min_A + 1 if b_min_A < 7 else b_min_A - 1
    b_min_B = max(0, min(7, b_min_B))

    # Front LED position encodes path:
    # path = (max_front - max_back) + (min_front - min_back)
    f_min = max(0, min(7, b_min_A + path_shift))

    # Back timing that produces target_face through the weighted average:
    # result = (front_avg + back_avg*2) / 3  →  with only back sensors: result = back_avg*2/3
    # Inverse: back_avg = target_face * 1.5
    target_back_angle = target_face * 1.5
    y_dist   = (b_min_A - b_min_B) * LED_SPACING
    x_travel = abs(y_dist * math.tan(math.radians(target_back_angle))) if y_dist != 0 else 0
    # speed_per_tick = SENSOR_SPACING / total_ticks  →  ticks = x_travel / speed_per_tick
    ticks_52 = int(x_travel * total_ticks / SENSOR_SPACING)
    ticks_52 = max(0, min(ticks_52, int(total_ticks * 0.4)))
    ticks_4A = total_ticks - ticks_52

    if verbose:
        print(f"[SIMULATION] Profile: {profile_name.capitalize():<8} | "
              f"Club: {club_name:<6} | Speed: {target_speed:.1f} mph")

    data = [0] * 60

    # Chunk 0 — back A initial position (no timing contribution)
    data[1] = (1 << b_min_A) | (1 << min(7, b_min_A + 1))
    data[2] = 0x81

    # Chunk 1 — back B with face-angle timing
    data[6] = (1 << b_min_B) | (1 << min(7, b_min_B + 1))
    data[7] = 0x52
    data[8] = (ticks_52 >> 8) & 0xFF
    data[9] = ticks_52 & 0xFF

    # Chunk 2 — front sensors with remaining timing
    data[10] = (1 << f_min) | (1 << min(7, f_min + 1))
    data[12] = 0x4A
    data[13] = (ticks_4A >> 8) & 0xFF
    data[14] = ticks_4A & 0xFF

    return data


class SimulatedOptiShot:
    """Mocks hid.device to provide simulated swing data on keyboard input."""

    def __init__(self):
        print("\n" + "*" * 40)
        print(" SIMULATION MODE ACTIVE")
        print(" Press 'ENTER' or 'S' to simulate a swing.")
        print(" Press 'Q' to quit.")
        print("*" * 40 + "\n")
        try:
            import msvcrt
            self.msvcrt = msvcrt
        except ImportError:
            self.msvcrt = None
            print("Warning: msvcrt not found. Simulation input may not work on non-Windows.")

    def get_manufacturer_string(self):
        return "Virtual Golf Co."

    def get_product_string(self):
        return "SimuShot 2000"

    def write(self, data):
        pass

    def read(self, size, club_name="Driver"):
        if self.msvcrt and self.msvcrt.kbhit():
            key = self.msvcrt.getch().lower()
            if key == b'q':
                sys.exit()
            if key in (b's', b'\r'):
                return self.generate_swing_packet(club_name)
        return []

    def close(self):
        print("Simulation closed.")

    def generate_swing_packet(self, club_name="Driver"):
        return generate_simulated_shot(club_name)
