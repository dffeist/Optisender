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
from overlay_display import OverlayDisplay

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
    last_keep_alive_time = time.time()
    last_reconnect_attempt = 0
    KEEP_ALIVE_INTERVAL = 30.0   # seconds between keep-alive pings
    RECONNECT_INTERVAL  = 10.0   # seconds between reconnect attempts
    
    # Simulation Input State
    sim_input = {"trigger": False, "club_shift": 0, "toggle_ball": False, "toggle_handed": False, "toggle_pin": False}
    using_ball = True
    left_handed = False
    print("Ball Mode: ON (press 'B' to toggle)")
    print("Handedness: Right-Handed (press 'H' to toggle)")

    overlay = OverlayDisplay()
    overlay.push_state({"using_ball": using_ball, "left_handed": left_handed, "club": user_club, "source": "Ready", "hand_label": "LH" if left_handed else "RH", "simulation_mode": simulation_mode})

    def on_press(key):
        try:
            if hasattr(key, 'char') and key.char.lower() == 's':
                sim_input["trigger"] = True
            elif hasattr(key, 'char') and key.char.lower() == 'b':
                sim_input["toggle_ball"] = True
            elif hasattr(key, 'char') and key.char.lower() == 'h':
                sim_input["toggle_handed"] = True
            elif hasattr(key, 'char') and key.char.lower() == 'd':
                sim_input["toggle_pin"] = True
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
        print("  B: Toggle Ball On/Off")
        print("  H: Toggle Left/Right Handed")
        print("  D: Toggle Overlay Always-On-Top")
        if simulation_mode:
            print("  S / ENTER: Trigger Simulated Swing")
        listener = keyboard.Listener(on_press=on_press)
        listener.start()
    else:
        print("\n[INPUT] 'pynput' not found. Manual controls disabled.")

    try:
        while True:
            # Check for ball toggle
            if sim_input["toggle_ball"]:
                sim_input["toggle_ball"] = False
                using_ball = not using_ball
                print(f"*** BALL MODE: {'ON' if using_ball else 'OFF'} ***")
                overlay.push_state({"using_ball": using_ball, "left_handed": left_handed})

            # Check for handedness toggle
            if sim_input["toggle_handed"]:
                sim_input["toggle_handed"] = False
                left_handed = not left_handed
                print(f"*** HANDEDNESS: {'Left-Handed' if left_handed else 'Right-Handed'} ***")
                overlay.push_state({"using_ball": using_ball, "left_handed": left_handed})

            # Check for overlay pin toggle
            if sim_input["toggle_pin"]:
                sim_input["toggle_pin"] = False
                overlay.push_state({"_toggle_pin": True})

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
                overlay.push_state({"club": user_club, "source": "Manual", "hand_label": "LH" if left_handed else "RH"})

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
                                                overlay.push_state({"club": user_club, "source": "API", "hand_label": "LH" if left_handed else "RH"})

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

            now = time.time()

            # Keep-alive ping to prevent device sleep
            if not simulation_mode and reader.is_connected:
                if now - last_keep_alive_time > KEEP_ALIVE_INTERVAL:
                    reader.keep_alive()
                    last_keep_alive_time = now

            # Reconnect logic: if device disconnected, fall to sim and retry
            if not simulation_mode and not reader.is_connected:
                print("[DEVICE] OptiShot disconnected — switching to SIMULATION MODE.")
                print("  S / ENTER: Trigger Simulated Swing while reconnecting...")
                simulation_mode = True
                last_reconnect_attempt = now
                overlay.push_state({"simulation_mode": True})

            if simulation_mode and not reader.is_connected:
                if now - last_reconnect_attempt > RECONNECT_INTERVAL:
                    last_reconnect_attempt = now
                    print("[DEVICE] Attempting to reconnect to OptiShot...")
                    if reader.reconnect():
                        simulation_mode = False
                        last_keep_alive_time = now
                        print("[DEVICE] OptiShot reconnected — resuming hardware input.")
                        print("\nReady for a swing. Waiting for data...")
                        overlay.push_state({"simulation_mode": False})

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
                metrics = processor.process_raw_buffer(data, using_ball=using_ball)
                
                if metrics:
                    ball = physics.calculate_ball_flight(metrics, user_club, left_handed=left_handed)

                    # path_deg for display; raw path integer stays in metrics for physics
                    path_val = metrics['path_deg']
                    eff_path = -path_val if left_handed else path_val

                    # Derive face angle label
                    # For LH: positive face angle = open (away from target), negative = closed
                    face = metrics['face_angle']
                    eff_face = -face if left_handed else face
                    if eff_face > 0.5:
                        face_label = f"Closed {abs(face):.1f}°"
                    elif eff_face < -0.5:
                        face_label = f"Open {abs(face):.1f}°"
                    else:
                        face_label = f"Square {abs(face):.1f}°"

                    # Derive face contact label
                    # For LH: toe/heel are physically reversed on the sensor
                    min_b = metrics['raw_min_back']
                    max_b = metrics['raw_max_back']
                    if max_b == 0:   contact_label = "Missed"
                    elif left_handed:
                        if max_b <= 2: contact_label = "Extreme Heel"
                        elif max_b == 3: contact_label = "Heel"
                        elif min_b >= 5: contact_label = "Far Toe"
                        elif min_b == 4: contact_label = "Toe"
                        else:            contact_label = "Center"
                    else:
                        if max_b <= 2: contact_label = "Extreme Toe"
                        elif max_b == 3: contact_label = "Toe"
                        elif min_b >= 5: contact_label = "Far Heel"
                        elif min_b == 4: contact_label = "Heel"
                        else:            contact_label = "Center"

                    # Derive shot shape from spin axis
                    # For LH: positive spin axis curves left (hook), negative curves right (slice)
                    axis = ball.spin_axis
                    eff_axis = -axis if left_handed else axis
                    if eff_axis > 10:    shape_label = "Slice"
                    elif eff_axis > 3:   shape_label = "Fade"
                    elif eff_axis > -3:  shape_label = "Straight"
                    elif eff_axis > -10: shape_label = "Draw"
                    else:                shape_label = "Hook"

                    source = 'SIMULATED' if simulation_mode else 'OptiShot'
                    hand_label = 'LH' if left_handed else 'RH'
                    W = 38
                    print("\n" + "=" * W)
                    print(f"  CLUB: {user_club}  [{source}] [{hand_label}]")
                    print("=" * W)
                    print(f"  {'CLUB METRICS':}")
                    print(f"    Club Speed  : {metrics['speed']:.1f} mph")
                    print(f"    Face Angle  : {face_label}")
                    print(f"    Swing Path  : {eff_path:+.1f}°")
                    print(f"    Face Contact: {contact_label}")
                    real_smash = (ball.ball_speed / metrics['speed']) if metrics['speed'] > 0 else 0.0
                    print(f"    Smash Factor: {real_smash:.2f}")
                    print("-" * W)
                    print(f"  {'BALL FLIGHT':}")
                    print(f"    Ball Speed  : {ball.ball_speed:.1f} mph")
                    print(f"    Launch (V)  : {ball.launch_angle:.1f}°")
                    print(f"    Launch (H)  : {ball.launch_direction:+.1f}°")
                    print(f"    Total Spin  : {ball.total_spin:.0f} rpm")
                    print(f"    Spin Axis   : {ball.spin_axis:+.1f}°")
                    print(f"    Shot Shape  : {shape_label}")
                    print("=" * W + "\n")

                    overlay.push_state({
                        "using_ball":   using_ball,
                        "left_handed":  left_handed,
                        "club":         user_club,
                        "source":       source,
                        "hand_label":   hand_label,
                        "club_speed":   f"{metrics['speed']:.1f}",
                        "face_angle":   face_label,
                        "swing_path":   f"{eff_path:+.1f}°",
                        "face_contact": contact_label,
                        "smash_factor": f"{real_smash:.2f}",
                        "ball_speed":   f"{ball.ball_speed:.1f}",
                        "launch_v":     f"{ball.launch_angle:.1f}",
                        "launch_h":     f"{ball.launch_direction:+.1f}",
                        "total_spin":   f"{ball.total_spin:.0f}",
                        "spin_axis":    f"{ball.spin_axis:+.1f}",
                        "shot_shape":   shape_label,
                    })
                    
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
                        time.sleep(2.5)
                        reader.set_led_green()
                        last_keep_alive_time = time.time()
                        print("\nReady for a swing. Waiting for data...")
                    except Exception:
                        print("[DEVICE] Communication lost during LED feedback.")
                        reader.is_connected = False
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