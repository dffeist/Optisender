import hid
import time

class OptiReader:
    """
    Handles low-level HID communication with the OptiShot 2 hardware.
    """
    VID = 0x0547
    PID = 0x3294

    # Command Constants
    CMD_SENSORS_ON  = 0x50
    CMD_LED_RED     = 0x51
    CMD_LED_GREEN   = 0x52
    CMD_SENSORS_OFF = 0x80

    def __init__(self):
        self.device = None
        self.is_connected = False

    def connect(self):
        """
        Opens the HID device and performs the initialization sequence
        found in opti_init (usbcode.cpp).
        """
        try:
            self.device = hid.device()
            self.device.open(self.VID, self.PID)
            self.device.set_nonblocking(1)

            self._send_command(self.CMD_SENSORS_ON)
            time.sleep(0.1)
            self.set_led_green()

            self.is_connected = True
            print(f"OptiShot connected: {self.device.get_product_string()}")
            return True
        except Exception as e:
            print(f"HID Connection Error: {e}")
            self.is_connected = False
            return False

    def _send_command(self, cmd_byte):
        """
        Sends a 61-byte report to the device.
        Index 0: Report ID (0x00)
        Index 1: Command Byte
        """
        if not self.device:
            return
        report = [0x00, cmd_byte] + [0x00] * 59
        try:
            self.device.write(report)
        except Exception as e:
            print(f"HID Write Error: {e}")
            self.is_connected = False

    def set_led_red(self):
        """Turns the hardware LED red (busy/processing)."""
        self._send_command(self.CMD_LED_RED)

    def set_led_green(self):
        """Turns the hardware LED green (ready for swing)."""
        self._send_command(self.CMD_LED_GREEN)

    def read_raw(self):
        """
        Reads a 60-byte raw data packet from the sensors.
        Returns a list[int] on success, None if no data available.
        """
        if not self.device:
            return None
        try:
            data = self.device.read(60)
            return data if data else None
        except Exception as e:
            print(f"HID Read Error: {e}")
            self.is_connected = False
            return None

    def keep_alive(self):
        """Sends a sensors-on command to prevent the device from sleeping."""
        self._send_command(self.CMD_SENSORS_ON)

    def reconnect(self):
        """Closes any stale handle then attempts a fresh connection."""
        try:
            if self.device:
                self.device.close()
        except Exception:
            pass
        self.device = None
        self.is_connected = False
        return self.connect()

    def disconnect(self):
        """
        Turns off sensors/LED and closes the device handle.
        Modeled after opti_shutdown (usbcode.cpp).
        """
        if self.device:
            try:
                self._send_command(self.CMD_SENSORS_OFF)
                self.device.close()
            except Exception:
                pass
            finally:
                self.device = None
                self.is_connected = False
                print("OptiShot disconnected.")

    def __del__(self):
        if self.is_connected:
            self.disconnect()
