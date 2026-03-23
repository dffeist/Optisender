import socket
import json
import select
import time

API_IP = "127.0.0.1"
API_PORT = 3111

def main():
    """
    A simple, standalone tool to monitor all messages from the OpenGolfSim API.
    """
    print("--- API Monitor ---")
    print(f"Continuously listening for messages from {API_IP}:{API_PORT}...")

    api_socket = None
    api_buffer = ""
    last_heartbeat_time = time.time()

    while True:
        try:
            # --- Connection Logic ---
            if api_socket is None:
                try:
                    # Create and connect the socket
                    api_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    api_socket.settimeout(3.0) # Timeout for the connection attempt
                    api_socket.connect((API_IP, API_PORT))
                    print(f"\nSUCCESS: Connected to API at {API_IP}:{API_PORT}")
                    # Set to non-blocking for the listening loop
                    api_socket.setblocking(False)
                    api_buffer = "" # Clear buffer on new connection
                except (socket.error, ConnectionRefusedError) as e:
                    # If connection fails, reset and wait before retrying
                    print(f"\rConnection failed: {e}. Retrying in 5 seconds...", end="")
                    api_socket = None
                    time.sleep(5)
                    continue # Retry connection

            # --- Heartbeat / Null Message Logic ---
            if api_socket and (time.time() - last_heartbeat_time > 5.0):
                try:
                    # Sending a zero-speed shot to try and trigger a response
                    print("Z", end="", flush=True) 
                    payload = {
                        "type": "shot",
                        "shot": {
                            "ballSpeed": 100.0,
                            "verticalLaunchAngle": 30.0,
                            "horizontalLaunchAngle": 0.0,
                            "spinSpeed": 0.0,
                            "spinAxis": 0.0
                        }
                    }
                    api_socket.sendall(json.dumps(payload).encode('utf-8'))
                    last_heartbeat_time = time.time()
                except Exception:
                    # If send fails, let the receive logic or next loop handle closure
                    pass

            # --- Message Receiving Logic ---
            readable, _, _ = select.select([api_socket], [], [], 0.1)

            if readable:
                new_data = api_socket.recv(4096).decode('utf-8')
                if new_data:
                    api_buffer += new_data
                    while api_buffer:
                        api_buffer = api_buffer.lstrip()
                        if not api_buffer:
                            break
                        try:
                            decoder = json.JSONDecoder()
                            msg_json, end_index = decoder.raw_decode(api_buffer)
                            
                            # Filter out generic Heartbeat/Status 200 messages to reduce noise
                            if msg_json.get("status") == 200 or msg_json.get("code") == 200:
                                print(".", end="", flush=True)
                            else:
                                print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] API MESSAGE RECEIVED:")
                                print(json.dumps(msg_json, indent=2))
                                
                                if msg_json.get("type") == "player":
                                    p_data = msg_json.get("data", {})
                                    p_club = p_data.get("club", {})
                                    print("\n  >>> PLAYER / CLUB UPDATE DETECTED <<<")
                                    print(f"  Player ID: {p_data.get('playerId')}")
                                    print(f"  Club Name: {p_club.get('name')}")
                                    print(f"  Club ID:   {p_club.get('id')}")
                                    print(f"  Distance:  {p_club.get('distance')}")
                                    print("  " + "="*35)

                                print("-" * 40)

                            api_buffer = api_buffer[end_index:]
                        except json.JSONDecodeError:
                            break # Incomplete message, wait for more data
                else:
                    print("\nAPI Connection Closed by Server. Reconnecting...")
                    api_socket.close()
                    api_socket = None
                    time.sleep(2)

        except KeyboardInterrupt:
            print("\nExiting monitor.")
            if api_socket:
                api_socket.close()
            break
        except Exception as e:
            print(f"\nAn unexpected error occurred: {e}. Reconnecting...")
            if api_socket:
                api_socket.close()
            api_socket = None
            time.sleep(5)

if __name__ == '__main__':
    main()
