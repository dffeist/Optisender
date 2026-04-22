class OptiFilter:
    def __init__(self):
        self.prev_data = None

    def is_duplicate(self, current_data):
        """
        Prevents processing the same trigger event multiple times by comparing
        the current packet against the last processed packet.
        """
        if self.prev_data is not None and current_data == self.prev_data:
            return True
        # Store a copy to avoid reference comparisons
        self.prev_data = list(current_data) if current_data is not None else None
        return False

    def is_valid_swing(self, data):
        """
        A valid swing requires both the back sensor row (0x81) and the 
        front sensor row (0x4A) to be triggered within the same data packet.
        """
        if not data or len(data) < 60:
            return False
            
        back_orig = False
        front = False
        
        # OptiShot data is structured in 5-byte chunks
        for i in range(0, 60, 5):
            sensor_type = data[i + 2]
            if sensor_type == 0x81:
                if data[i] == 0:  # Byte 0 indicates original back pad state
                    back_orig = True
            elif sensor_type == 0x4A:
                front = True
                
        return back_orig and front
