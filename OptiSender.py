import hid
import time
import sys
import random
import socket
import json
import simulation
from ballphysics import PhysicsEngine

# OptiShot 2 Vendor ID and Product ID, as seen in usbcode.cpp
VID = 0x0547
PID = 0x3294

API_IP = "127.0.0.1"
API_PORT = 3111

def main():
    """
    Connects to an OptiShot device and reads swing data packets.
    """
    
    # Initialize Physics Engine
    physics = PhysicsEngine()
    
    print("--- OptiSender v2 with Physics ---")
    user_club = input("Enter Club (Driver, 3W, 5W, 5H, 5I..9I, PW, GW, SW, LW, Putter): ").strip()
    if not user_club: 
        user_club = "Driver"
    print(f"Selected Club: {user_club}")

    device = None
    device_open = False
    simulation_mode = False
    api_socket = None

    try:
        print(f"Attempting to open device with VID=0x{VID:04X} PID=0x{PID:04X}")

        # Open the device
        device = hid.device()
        device.open(VID, PID)
        device_open = True

        print(f"Device opened successfully!")
        print(f"  Manufacturer: {device.get_manufacturer_string()}")
        print(f"  Product:      {device.get_product_string()}")

        # This is equivalent to hid_set_nonblocking(dev, 1) in usbcode.cpp
        device.set_nonblocking(1)

        # This is equivalent to the opti_init sequence that turns the LED green
        # and prepares the device for reading.
        # 0x50: Turn on sensors
        # 0x52: Turn LED Green
        print("Initializing OptiShot sensors and LED...")
        device.write([0x50] + [0x00] * 59) # Command must be full report length
        time.sleep(0.1)
        device.write([0x52] + [0x00] * 59)
        time.sleep(0.1)

        print("\nReady for a swing. Waiting for data...")

    except (IOError, ValueError) as ex:
        print(f"Connection failed: {ex}")
        print("Device not found or not accessible. Switching to SIMULATION MODE.")
        simulation_mode = True

    # Initialize API Connection (Attempt regardless of Hardware or Simulation mode)
    try:
        print(f"Attempting API Connection to {API_IP}:{API_PORT}...")
        api_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        api_socket.settimeout(2.0) # Don't hang forever if API is down
        api_socket.connect((API_IP, API_PORT))
        print(f"SUCCESS: Connected to OpenGolfSim API at {API_IP}:{API_PORT}")
        api_socket.sendall(json.dumps({"type": "device", "status": "ready"}).encode('utf-8'))
    except Exception as e:
        print(f"API Connection FAILED (running offline): {e}")

    try:
        # This loop is the Python equivalent of the while(keep_polling)
        # loop inside the optiPolling function in usbcode.cpp
        while True:
            data = None
            if not simulation_mode:
                # Read a 60-byte report.
                data = device.read(60)
            else:
                print("\n[SIMULATION] Press Enter to simulate a swing... (Ctrl+C to exit)")
                input()
                data = simulation.generate_simulated_shot(user_club)

            if data:
                # A swing has been detected. The device sends a non-empty packet.
                print(f"--- Swing Data Received ({len(data)} bytes) ---")
                
                # Here, you would pass 'data' to a Python function equivalent
                # to processShotData() in shotprocessing.cpp
                # 1. Process Raw Data -> Club Data
                shot_data = physics.process_raw_data(data)
                
                if shot_data.swing_detected:
                    # 2. Calculate Ball Flight
                    ball = physics.calculate_ball_flight(shot_data, user_club)
                    
                    # 3. Output Results
                    print("\n" + "="*30)
                    print(f" CLUB INPUT: {user_club}")
                    print("-" * 30)
                    print(f" CLUB DATA ({'SIMULATED' if simulation_mode else 'OptiShot'}):")
                    print(f"  Speed:   {shot_data.club_speed:.1f} mph")
                    print(f"  Face:    {shot_data.face_angle:.1f} deg (Neg=Closed/Pos=Open)")
                    print(f"  Path:    {shot_data.path:.1f} (Raw index delta)")
                    print(f"  Contact: {shot_data.face_contact:.1f} (0=Center)")
                    print("-" * 30)
                    print(f" BALL FLIGHT (Calculated):")
                    print(f"  Speed:   {ball.ball_speed:.1f} mph")
                    print(f"  Launch:  {ball.launch_angle:.1f} deg")
                    print(f"  HLA:     {ball.launch_direction:.1f} deg")
                    print(f"  Spin:    {ball.total_spin:.0f} rpm")
                    print(f"  Axis:    {ball.spin_axis:.1f} deg (Curve)")
                    print("="*30 + "\n")
                    
                    # 4. Send Shot to API
                    if api_socket:
                        payload = {
                            "type": "shot",
                            "shot": {
                                "ballSpeed": ball.ball_speed,
                                "verticalLaunchAngle": ball.launch_angle,
                                "horizontalLaunchAngle": ball.launch_direction,
                                "spinSpeed": ball.total_spin,
                                "spinAxis": ball.spin_axis
                            }
                        }
                        try:
                            api_socket.sendall(json.dumps(payload).encode('utf-8'))
                            print(">> Shot data sent to API.")
                        except Exception as e:
                            print(f"Error sending to API: {e}")
                else:
                    print("Swing detected but data signal too weak or partial.")

                if not simulation_mode:
                    # The device LED turns red during processing. We can simulate this.
                    # 0x51: Turn LED Red
                    try:
                        device.write([0x51] + [0x00] * 59)
                    except Exception:
                        print("Device communication lost.")
                        break

                    # In RepliShot, there's a SHOTSLEEPTIME of 2.5 seconds
                    # to process the shot and wait before accepting a new one.
                    time.sleep(2.5)

                    # Turn the LED green again, ready for the next shot.
                    print("\nReady for a swing. Waiting for data...")
                    try:
                        device.write([0x52] + [0x00] * 59)
                    except Exception:
                        break
                else:
                    time.sleep(1)

            # A small delay to prevent the loop from consuming 100% CPU
            if not simulation_mode:
                time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        if device_open and device and not simulation_mode:
            # Turn off LED and sensors before closing
            try:
                device.write([0x80] + [0x00] * 59)
                device.close()
                print("Device closed.")
            except Exception:
                pass
        if api_socket:
            api_socket.close()

if __name__ == '__main__':
    main()
