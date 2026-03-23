import hid
import time
import sys
import random
import socket
import json
import select
try:
    from pynput import keyboard
except ImportError:
    keyboard = None
    print("Warning: pynput not found. Install via 'pip install pynput'.")

import simulation
from ballphysics import PhysicsEngine

# OptiShot 2 Vendor ID and Product ID, as seen in usbcode.cpp
VID = 0x0547
PID = 0x3294

API_IP = "127.0.0.1"
API_PORT = 3111

CLUBS = ["Driver", "3W", "5W", "5H", "3I", "4I", "5I", "6I", "7I", "8I", "9I", "PW", "GW", "SW", "LW", "Putter"]

def main():
    """
    Connects to an OptiShot device and reads swing data packets.
    """
    
    # Initialize Physics Engine
    physics = PhysicsEngine()
    
    print("--- OptiSender v2 with Physics ---")
    user_club = "Driver" # Default to Driver on start
    print(f"Selected Club: {user_club}")

    device = None
    device_open = False
    simulation_mode = False
    api_socket = None
    api_buffer = ""
    last_heartbeat_time = time.time()
    
    # Simulation Input State (Mutable object to be accessible in callback)
    sim_input = {"trigger": False, "club_shift": 0}

    def on_press(key):
        try:
            if hasattr(key, 'char') and key.char.lower() == 's':
                sim_input["trigger"] = True
        except AttributeError:
            pass
        if key == keyboard.Key.enter:
            sim_input["trigger"] = True
        if key == keyboard.Key.up:
            sim_input["club_shift"] = 1
        elif key == keyboard.Key.down:
            sim_input["club_shift"] = -1

    listener = None

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

    # Enable keyboard listener for Simulation triggers AND Manual Club selection
    if keyboard:
        print("\n[INPUT] Keyboard control active.")
        print("  UP/DOWN: Cycle Manual Club Selection")
        if simulation_mode:
            print("  S / ENTER: Trigger Simulated Swing")
        listener = keyboard.Listener(on_press=on_press)
        listener.start()
    else:
        print("\n[INPUT] 'pynput' not found. Manual controls disabled.")

    try:
        # This loop is the Python equivalent of the while(keep_polling)
        # loop inside the optiPolling function in usbcode.cpp
        while True:
            # Check for manual club change
            if sim_input["club_shift"] != 0:
                direction = sim_input["club_shift"]
                sim_input["club_shift"] = 0 # Reset
                
                try:
                    current_idx = CLUBS.index(user_club)
                except ValueError:
                    current_idx = 0 # Default to Driver if unknown
                
                new_idx = (current_idx + direction) % len(CLUBS)
                user_club = CLUBS[new_idx]
                print(f"*** MANUAL CLUB SELECT: {user_club} ***")

            # Send Heartbeat/Trigger message every 0.5 seconds
            if api_socket and (time.time() - last_heartbeat_time > 0.5):
                try:
                    # Sending "ready" status acts as a heartbeat/null message to trigger replies
                    api_socket.sendall(json.dumps({"type": "device", "status": "ready"}).encode('utf-8'))
                    last_heartbeat_time = time.time()
                except Exception:
                    print("API Heartbeat failed.")
                    api_socket.close()
                    api_socket = None

            # Check for incoming API messages (Player/Club Updates)
            if api_socket:
                try:
                    # Non-blocking check for data
                    readable, _, _ = select.select([api_socket], [], [], 0)
                    if readable:
                        new_data = api_socket.recv(4096).decode('utf-8')
                        if new_data:
                            api_buffer += new_data
                            # Process all complete JSON objects that might be in the buffer
                            while api_buffer:
                                # 1. Strip leading whitespace/newlines so raw_decode finds the JSON start
                                api_buffer = api_buffer.lstrip()
                                if not api_buffer:
                                    break

                                try:
                                    decoder = json.JSONDecoder()
                                    msg_json, end_index = decoder.raw_decode(api_buffer)

                                    # A complete message was decoded
                                    
                                    # Only print message if it's NOT a generic status 200 heartbeat ack
                                    if msg_json.get("status") != 200 and msg_json.get("code") != 200:
                                        print(f"\n[API IN] {json.dumps(msg_json)}")

                                    if msg_json.get("type") == "player":
                                        print("\n[API] PLAYER UPDATE RECEIVED")
                                        club_data = msg_json.get("data", {}).get("club", {})
                                        cid = club_data.get("id", "")
                                        cname = club_data.get("name", "")
                                        
                                        if cid: # Only update if a club ID was found
                                            # Map API ID to Internal ID
                                            if cid == "DR" or cid == "1W": new_club = "Driver"
                                            elif cid == "PT": new_club = "Putter"
                                            elif cid in ["AW", "UW"]: new_club = "GW"
                                            else: new_club = cid # Direct match for 3W, 5I, PW, etc.

                                            if new_club != user_club:
                                                user_club = new_club
                                                print(f"*** CLUB UPDATED TO: {user_club} (rec: {cname}) ***")

                                    elif msg_json.get("type") == "result":
                                        print("\n[API] PREVIOUS SHOT RESULT RECEIVED")
                                        res_data = msg_json.get("data", {}).get("result", {})
                                        print(f"  Carry:   {res_data.get('carry', 0):.1f}")
                                        print(f"  Total:   {res_data.get('total', 0):.1f}")
                                        print(f"  Offline: {res_data.get('lateral', 0):.1f}")
                                        print("  (Club selection ignored from result packet)")

                                    # Trim the processed message from the buffer
                                    api_buffer = api_buffer[end_index:]
                                except json.JSONDecodeError:
                                    # Incomplete message in buffer, break and wait for more data
                                    break
                        else:
                            # Empty string means remote side closed connection
                            print("API Connection Closed by Server.")
                            api_socket.close()
                            api_socket = None
                except Exception as e:
                    print(f"API Receive Error: {e}")
                    if api_socket: 
                        api_socket.close()
                        api_socket = None

            data = None
            if not simulation_mode:
                # Read a 60-byte report.
                data = device.read(60)
            else:
                # Simulation mode: non-blocking check for input
                if sim_input["trigger"]:
                    print("\n[SIMULATION] Triggering simulated swing (Manual)...")
                    data = simulation.generate_simulated_shot(user_club)
                    sim_input["trigger"] = False

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
                            print(f"\n[API OUT] Sending Shot: {json.dumps(payload, indent=2)}")
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

            # A small delay to prevent the loop from consuming 100% CPU, applicable to both modes
            time.sleep(0.01)

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
        if listener:
            listener.stop()

if __name__ == '__main__':
    main()
