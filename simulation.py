import sys
import random

def generate_simulated_shot():
    target_speed = random.uniform(85.0, 115.0)
    elapsed_time = int((28500.0 * 2.23694) / (target_speed * 18.0))
    
    data = [0] * 60
    
    data[2] = 0x81
    
    contact_shift = random.randint(-1, 1) 
    b_min = max(0, min(7, 3 + contact_shift))
    b_max = max(0, min(7, 4 + contact_shift))
    data[1] = (1 << b_min) | (1 << b_max)
    
    data[7] = 0x4A
    
    path_shift = random.randint(-1, 1)
    f_min = max(0, min(7, b_min + path_shift))
    f_max = max(0, min(7, b_max + path_shift))
    data[5] = (1 << f_min) | (1 << f_max)
    
    data[8] = (elapsed_time >> 8) & 0xFF
    data[9] = elapsed_time & 0xFF
    
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
        target_speed = random.uniform(85.0, 115.0)
        elapsed_time = int((28500.0 * 2.23694) / (target_speed * 18.0))
        
        data = [0] * 60
        
        data[2] = 0x81
        
        contact_shift = random.randint(-1, 1) 
        b_min = max(0, min(7, 3 + contact_shift))
        b_max = max(0, min(7, 4 + contact_shift))
        data[1] = (1 << b_min) | (1 << b_max)
        
        data[7] = 0x4A
        
        path_shift = random.randint(-1, 1)
        f_min = max(0, min(7, b_min + path_shift))
        f_max = max(0, min(7, b_max + path_shift))
        data[5] = (1 << f_min) | (1 << f_max)
        
        data[8] = (elapsed_time >> 8) & 0xFF
        data[9] = elapsed_time & 0xFF
        
        return data
