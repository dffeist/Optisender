import time
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
from opti_reader import OptiReader
from data_filters import OptiFilter
from shot_processor import ShotProcessor

API_IP = "127.0.0.1"
API_PORT = 3111

CLUBS = ["Driver", "3W", "5W", "5H", "3I", "4I", "5I", "6I", "7I", "8I", "9I", "PW", "GW", "SW", "LW", "Putter"]

def main():
    """
    Connects to an OptiShot device and reads swing data packets.
    Includes updated HID report formatting for hardware compatibility.
    """
    
    # Initialize Physics Engine
    physics = PhysicsEngine()
    reader = OptiReader()
    filters = OptiFilter()
    processor = ShotProcessor()
    
    print("--- OptiSender v2 with Physics ---")
    user_club = "Driver" # Default to Driver on start
    print(f"Selected Club: {user_club}")

    simulation_mode = False
    api_socket = None
    api_buffer = ""
    last_heartbeat_time = time.time()
    last_connection_attempt = 0
    
    # Simulation Input State
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
        if not reader.connect():
            raise ConnectionError("Hardware not found")
        print("\nReady for a swing. Waiting for data...")
    except (IOError, ValueError, ConnectionError) as ex:
        print(f"Connection failed: {ex}")
        print("Device not found or not accessible. Switching to SIMULATION MODE.")
        simulation_mode = True

    def try_api_connect():
        nonlocal api_socket, last_connection_attempt
        if api_socket is not None:
            return
        
        now = time.time()
        if now - last_connection_attempt < 5.0: # Retry every 5 seconds
            return
            
        last_connection_attempt = now
        try:
            api_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            api_socket.settimeout(2.0)
            api_socket.connect((API_IP, API_PORT))
            print(f"SUCCESS: Connected to OpenGolfSim API at {API_IP}:{API_PORT}")
            api_socket.sendall(json.dumps({"type": "device", "status": "ready"}).encode('utf-8'))
        except Exception:
            api_socket = None

    # Enable keyboard listener
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
        while True:
            # Check for manual club change
            if sim_input["club_shift"] != 0:
                direction = sim_input["club_shift"]
                sim_input["club_shift"] = 0 
                
                try:
                    current_idx = CLUBS.index(user_club)
                except ValueError:
                    current_idx = 0 
                
                new_idx = (current_idx + direction) % len(CLUBS)
                user_club = CLUBS[new_idx]
                print(f"*** MANUAL CLUB SELECT: {user_club} ***")

            # Attempt API reconnection if offline
            try_api_connect()

            # Send Heartbeat every 0.5 seconds
            if api_socket and (time.time() - last_heartbeat_time > 0.5):
                try:
                    api_socket.sendall(json.dumps({"type": "device", "status": "ready"}).encode('utf-8'))
                    last_heartbeat_time = time.time()
                except Exception:
                    print("API Heartbeat failed.")
                    api_socket.close()
                    api_socket = None

            # Check for incoming API messages
            if api_socket:
                try:
                    readable, _, _ = select.select([api_socket], [], [], 0)
                    if readable:
                        new_data = api_socket.recv(4096).decode('utf-8')
                        if new_data:
                            api_buffer += new_data
                            while api_buffer:
                                api_buffer = api_buffer.lstrip()
                                if not api_buffer: break
                                try:
                                    decoder = json.JSONDecoder()
                                    msg_json, end_index = decoder.raw_decode(api_buffer)
                                    if msg_json.get("status") != 200 and msg_json.get("code") != 200:
                                        print(f"\n[API IN] {json.dumps(msg_json)}")

                                    if msg_json.get("type") == "player":
                                        club_data = msg_json.get("data", {}).get("club", {})
                                        cid = club_data.get("id", "")
                                        cname = club_data.get("name", "")
                                        if cid:
                                            if cid == "DR" or cid == "1W": new_club = "Driver"
                                            elif cid == "PT": new_club = "Putter"
                                            elif cid in ["AW", "UW"]: new_club = "GW"
                                            else: new_club = cid 

                                            if new_club != user_club:
                                                user_club = new_club
                                                print(f"*** CLUB UPDATED TO: {user_club} (rec: {cname}) ***")

                                    elif msg_json.get("type") == "result":
                                        res_data = msg_json.get("data", {}).get("result", {})
                                        print(f"\n[API] SHOT RESULT: Carry: {res_data.get('carry', 0):.1f} | Total: {res_data.get('total', 0):.1f}")

                                    api_buffer = api_buffer[end_index:]
                                except json.JSONDecodeError:
                                    break
                        else:
                            api_socket.close()
                            api_socket = None
                except Exception as e:
                    print(f"API Receive Error: {e}")
                    if api_socket: 
                        api_socket.close()
                        api_socket = None

            # Get Swing Data
            data = None
            if not simulation_mode:
                data = reader.read_raw()
            else:
                if sim_input["trigger"]:
                    print("\n[SIMULATION] Triggering simulated swing...")
                    data = simulation.generate_simulated_shot(user_club)
                    sim_input["trigger"] = False

            if data:
                # Apply duplicate and validity filters
                if filters.is_duplicate(data) or not filters.is_valid_swing(data):
                    continue

                print(f"--- Valid Swing Detected ---")
                metrics = processor.process_raw_buffer(data)
                
                if metrics:
                    ball = physics.calculate_ball_flight(metrics, user_club)

                    # Derive path label
                    path_val = metrics['path']
                    if abs(path_val) > 3:
                        path_label = "Very Inside/Out" if path_val > 0 else "Very Outside/In"
                    elif abs(path_val) > 1:
                        path_label = "Inside/Out" if path_val > 0 else "Outside/In"
                    else:
                        path_label = "On Plane"

                    # Derive face angle label
                    face = metrics['face_angle']
                    if face > 0.5:
                        face_label = f"Closed {face:.1f}°"
                    elif face < -0.5:
                        face_label = f"Open {abs(face):.1f}°"
                    else:
                        face_label = f"Square {abs(face):.1f}°"

                    # Derive face contact label
                    min_b = metrics['raw_min_back']
                    max_b = metrics['raw_max_back']
                    if max_b == 0:   contact_label = "Missed"
                    elif max_b <= 2: contact_label = "Extreme Toe"
                    elif max_b == 3: contact_label = "Toe"
                    elif min_b >= 5: contact_label = "Far Heel"
                    elif min_b == 4: contact_label = "Heel"
                    else:            contact_label = "Center"

                    # Derive shot shape from spin axis
                    axis = ball.spin_axis
                    if axis > 10:    shape_label = "Slice"
                    elif axis > 3:   shape_label = "Fade"
                    elif axis > -3:  shape_label = "Straight"
                    elif axis > -10: shape_label = "Draw"
                    else:            shape_label = "Hook"

                    source = 'SIMULATED' if simulation_mode else 'OptiShot'
                    W = 38
                    print("\n" + "=" * W)
                    print(f"  CLUB: {user_club}  [{source}]")
                    print("=" * W)
                    print(f"  {'CLUB METRICS':}")
                    print(f"    Club Speed  : {metrics['speed']:.1f} mph")
                    print(f"    Face Angle  : {face_label}")
                    print(f"    Swing Path  : {path_val:+d}  ({path_label})")
                    print(f"    Face Contact: {contact_label}")
                    print(f"    Smash Factor: {metrics['smash_factor']:.2f}")
                    print("-" * W)
                    print(f"  {'BALL FLIGHT':}")
                    print(f"    Ball Speed  : {ball.ball_speed:.1f} mph")
                    print(f"    Launch (V)  : {ball.launch_angle:.1f}°")
                    print(f"    Launch (H)  : {ball.launch_direction:+.1f}°")
                    print(f"    Total Spin  : {ball.total_spin:.0f} rpm")
                    print(f"    Spin Axis   : {ball.spin_axis:+.1f}°")
                    print(f"    Shot Shape  : {shape_label}")
                    print("=" * W + "\n")
                    
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
                
                # Device LED Feedback Loop
                if not simulation_mode:
                    try:
                        reader.set_led_red()
                        time.sleep(2.5) # Wait for simulation to be ready
                        reader.set_led_green()
                        print("\nReady for a swing. Waiting for data...")
                    except Exception:
                        print("Device communication lost.")
                        break
                else:
                    time.sleep(1)

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        if not simulation_mode:
            try:
                reader.disconnect()
            except Exception:
                pass
        if api_socket:
            api_socket.close()
        if listener:
            listener.stop()

if __name__ == '__main__':
    main()