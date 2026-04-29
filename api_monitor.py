import socket
import json
import select
import time

API_IP = "127.0.0.1"
API_PORT = 3111
IDLE_TIMEOUT = 30.0


def display_player_event(msg):
    club = msg.get("club", {})
    pos  = msg.get("currentPosition", {})
    print("  >>> PLAYER / CLUB UPDATE <<<")
    print(f"  Player ID : {msg.get('playerId')}")
    print(f"  Club      : {club.get('name')}  (id={club.get('id')}, dist={club.get('distance')}m)")
    if pos:
        print(f"  Position  : x={pos.get('x')}  y={pos.get('y')}  z={pos.get('z')}")


def display_shot_result(msg):
    print("  >>> SHOT RESULT <<<")
    print(f"  Carry    : {msg.get('carry')} m")
    print(f"  Total    : {msg.get('total')} m")
    print(f"  Roll     : {msg.get('roll')} m")
    print(f"  Height   : {msg.get('height')} m")
    print(f"  Lateral  : {msg.get('lateral')} m")
    club = msg.get("club", {})
    if club:
        print(f"  Club     : {club.get('name')}")
    session = msg.get("sessionId")
    if session:
        print(f"  Session  : {session}")


def display_device_status(msg):
    print("  >>> DEVICE STATUS <<<")
    print(f"  Status   : {msg.get('status')}")
    device = msg.get("device") or msg.get("deviceId")
    if device:
        print(f"  Device   : {device}")


def display_message(msg):
    ts  = time.strftime('%H:%M:%S')
    typ = msg.get("type", "unknown")
    print(f"\n[{ts}] {typ.upper()}")
    if typ == "player":
        display_player_event(msg)
    elif typ == "shot result":
        display_shot_result(msg)
    elif typ == "device status":
        display_device_status(msg)
    else:
        print(json.dumps(msg, indent=2))
    print("-" * 40)


def connect():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5.0)
        s.connect((API_IP, API_PORT))
        s.settimeout(None)
        print(f"\nConnected to {API_IP}:{API_PORT}")
        return s
    except (socket.error, ConnectionRefusedError) as e:
        print(f"Connection failed: {e}. Retrying in 5s...")
        return None


def main():
    print("--- API Monitor ---")
    print(f"Listening on {API_IP}:{API_PORT}  (Ctrl+C to quit)")

    sock = None
    buf  = ""

    while True:
        try:
            if sock is None:
                sock = connect()
                if sock is None:
                    time.sleep(5)
                    continue
                buf = ""

            readable, _, _ = select.select([sock], [], [], IDLE_TIMEOUT)

            if not readable:
                continue

            chunk = sock.recv(4096).decode('utf-8')
            if not chunk:
                print("Server closed connection. Reconnecting...")
                sock.close()
                sock = None
                time.sleep(2)
                continue

            buf += chunk

            while buf:
                buf = buf.lstrip()
                if not buf:
                    break
                try:
                    decoder = json.JSONDecoder()
                    msg, end = decoder.raw_decode(buf)
                    display_message(msg)
                    buf = buf[end:]
                except json.JSONDecodeError:
                    break

        except KeyboardInterrupt:
            print("\nExiting.")
            if sock:
                sock.close()
            break
        except Exception as e:
            print(f"Error: {e}. Reconnecting...")
            if sock:
                sock.close()
            sock = None
            time.sleep(5)


if __name__ == '__main__':
    main()
