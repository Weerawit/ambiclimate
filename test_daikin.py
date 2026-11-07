"""
Daikin AC Controller & Ambi Climate Diagnostics (All-in-One)
============================================================
Remote Model: Daikin ARC480A46 / ARC433A59
Verified Protocol: Protocol B (2-Frame, C5 Header, 38kHz)
Target: Ambi Climate 2 (192.168.1.151)
"""

import sys
import os
import time
import socket
import ssl
import re
import select
import subprocess
from daikin_ir import build_daikin_command, frames_to_sendir

DIR = os.path.dirname(os.path.abspath(__file__))
IP_CACHE_FILE = os.path.join(DIR, "ambi_ip.txt")
FALLBACK_IP = "192.168.1.191"
AMBI_IP = FALLBACK_IP
AMBI_PORT = 4998

def is_valid_ambi(ip, timeout=0.8):
    """Verifies whether an IP is an active, responsive Ambi Climate device."""
    if not ip:
        return False
    # Check Port 8070 (Native Ambi Sensors)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, 8070))
        s.sendall(b"\x0700NTP\r")
        r = s.recv(64)
        s.close()
        if len(r) >= 7 and (r[0] == 7 or b"NTP" in r):
            return True
    except Exception:
        pass

    # Check Port 4998 (Global Cache IR Engine)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, 4998))
        s.sendall(b"getdevices\r")
        r = s.recv(64)
        s.close()
        if b"device" in r or b"WIFI" in r or b"IR" in r:
            return True
    except Exception:
        pass

    return False

def save_ambi_ip(ip):
    try:
        with open(IP_CACHE_FILE, "w", encoding="utf-8") as f:
            f.write(ip.strip())
    except Exception:
        pass

def discover_ambi_ip():
    """
    Auto-discovers the current IP address of Ambi Climate 2:
    1. Checks cached IP from ambi_ip.txt
    2. Inspects ARP table for MAC dc-e5-33-13-02-bd
    3. Fast-probes known recent IP candidates
    """
    # 1. Check cached IP
    if os.path.exists(IP_CACHE_FILE):
        try:
            with open(IP_CACHE_FILE, "r", encoding="utf-8") as f:
                cached = f.read().strip()
                if is_valid_ambi(cached, timeout=0.4):
                    return cached
        except Exception:
            pass

    # 2. Inspect ARP table
    arp_commands = []
    if os.name == 'nt':
        arp_commands.append(["arp", "-a"])
    else:
        # Linux / WSL - avoid running Windows .exe if it could block
        arp_commands.extend([["arp", "-a"], ["ip", "neigh"]])

    for cmd in arp_commands:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.0)
            for line in res.stdout.splitlines():
                if "dc-e5-33-13-02-bd" in line.lower() or "dce5331302bd" in line.lower():
                    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
                    if m and is_valid_ambi(m.group(1), timeout=0.4):
                        found_ip = m.group(1)
                        save_ambi_ip(found_ip)
                        return found_ip
        except Exception:
            pass

    # 3. Check known recent IP candidates
    for candidate in ["192.168.1.191", "192.168.1.156", "192.168.1.163", "192.168.1.152", "192.168.1.151", "192.168.1.121", "192.168.1.181"]:
        if is_valid_ambi(candidate, timeout=0.8):
            save_ambi_ip(candidate)
            return candidate

    return FALLBACK_IP

def get_ambi_ip():
    """Returns the verified, live Ambi Climate IP address (auto-discovering if changed)."""
    global AMBI_IP
    if not is_valid_ambi(AMBI_IP, timeout=0.8):
        discovered = discover_ambi_ip()
        if discovered:
            AMBI_IP = discovered
    return AMBI_IP

# Initialize current IP
AMBI_IP = get_ambi_ip()

def send_to_ambi(sendir_cmd, timeout=4.0):
    """
    Connects to Ambi Climate port 4998, sends sendir command, and waits for response.
    Reliable socket handling with guaranteed close and auto-discovery.
    """
    target_ip = get_ambi_ip()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((target_ip, AMBI_PORT))
        s.sendall(sendir_cmd.encode("ascii"))
        time.sleep(0.3)
        try:
            resp = s.recv(1024).decode("ascii", errors="replace").strip()
        except socket.timeout:
            resp = "No response (Command sent)"
        return resp
    finally:
        try:
            s.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        s.close()

def send_daikin(temp=24, mode="cool", fan="auto", swing="off", power=True, protocol_type="B", connector="1:1"):
    f1, f2 = build_daikin_command(temp=temp, mode=mode, fan=fan, swing=swing, power=power, protocol_type=protocol_type)
    sendir_cmd = frames_to_sendir(f1, f2, connector=connector)

    p_status = "ON" if power else "OFF"
    f1_hex = ' '.join(f'{b:02X}' for b in f1) if f1 else "(None)"
    f2_hex = ' '.join(f'{b:02X}' for b in f2)

    print(f"\n[*] Sending Daikin IR [Protocol {protocol_type}] -> {mode.upper()} {temp}C Fan:{fan} Power:{p_status}")
    print(f"    Port: {connector}")
    print(f"    Frame 1: {f1_hex}")
    print(f"    Frame 2: {f2_hex}")
    print(f"    Payload: {sendir_cmd[:45]}... ({len(sendir_cmd)} chars)")

    try:
        resp = send_to_ambi(sendir_cmd)
        print(f"    [<] Ambi Response: {resp}")
        if "completeir" in resp or "OK" in resp:
            print("    [+] SUCCESS! IR signal was transmitted by Ambi Climate hardware!")
        else:
            print(f"    [!] Note: Ambi returned: {resp}")
        return True
    except socket.timeout:
        print("    [-] ERROR: Timeout waiting for Ambi Climate. Ensure no other connection is open on port 4998.")
        return False
    except ConnectionRefusedError:
        print(f"    [-] ERROR: Connection refused at {AMBI_IP}:{AMBI_PORT}. Is Ambi Climate powered on?")
        return False
    except Exception as e:
        print(f"    [-] ERROR: {e}")
        return False

def check_status():
    target_ip = get_ambi_ip()
    print(f"\n[*] Connecting to {target_ip}:{AMBI_PORT} to query device info...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect((target_ip, AMBI_PORT))
        s.sendall(b"getversion\r")
        time.sleep(0.3)
        ver = s.recv(1024).decode("ascii", errors="replace").strip()
        s.sendall(b"getdevices\r")
        time.sleep(0.3)
        dev = s.recv(1024).decode("ascii", errors="replace").strip().replace("\r", " | ")
        s.close()
        print(f"[+] Version: {ver}")
        print(f"[+] Devices: {dev}")
    except Exception as e:
        print(f"[-] Error: {e}")

def parse_sensor_value(raw_val: str):
    """
    Parses Ambi Climate raw sensor string format:
    e.g. '+2913C2' -> (29.13, '°C')
    e.g. '+5012%2' -> (50.12, '%')
    """
    import re
    m = re.match(r'([+-]?\d+)([C%])(\d+)?', raw_val)
    if m:
        val_str, unit, dec_str = m.groups()
        dec = int(dec_str) if dec_str else 2
        float_val = int(val_str) / (10 ** dec)
        unit_display = "°C" if unit == "C" else "%"
        return float_val, unit_display
    return None, raw_val

def get_live_sensors(ip=None, port=8070, timeout=2.5, temp_offset=-3.0, hum_offset=4.0):
    """
    Directly queries real-time temperature, humidity, luminosity, and hardware info
    from Ambi Climate 2 over TCP Port 8070 using the native Ambi Protocol.
    Applies hardware sensor calibration offsets (-3.0°C / +4%).
    Returns a dict with live calibrated readings and raw sensor values.
    """
    target_ip = ip or get_ambi_ip()
    sensors = {
        "temperature": None,
        "humidity": None,
        "raw_temperature": None,
        "raw_humidity": None,
        "temp_calibration_offset": temp_offset,
        "humidity_calibration_offset": hum_offset,
        "luminosity": None,
        "device_id": None,
        "firmware": None,
        "uptime": None,
        "wifi_quality": None,
        "ip": target_ip,
        "raw": {}
    }
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((target_ip, port))

        def send_and_recv(cmd_str):
            pkt = b"\x0700" + cmd_str.encode("ascii") + b"\r"
            s.sendall(pkt)
            time.sleep(0.2)
            data = s.recv(512)
            # Response format: \x07 + "000" + 'N' + code(2) + payload + \r\n
            if data and len(data) >= 7 and data[0] == 7:
                payload = data[7:].decode("ascii", errors="replace").strip("\r\n")
                return payload
            return None

        # Query Temperature
        t_raw = send_and_recv("NTP")
        if t_raw:
            sensors["raw"]["NTP"] = t_raw
            val, _ = parse_sensor_value(t_raw)
            sensors["raw_temperature"] = val
            sensors["temperature"] = round(val + temp_offset, 2) if (val is not None and temp_offset is not None) else val

        # Query Humidity
        h_raw = send_and_recv("NHM")
        if h_raw:
            sensors["raw"]["NHM"] = h_raw
            val, _ = parse_sensor_value(h_raw)
            sensors["raw_humidity"] = val
            sensors["humidity"] = round(min(100.0, max(0.0, val + hum_offset)), 2) if (val is not None and hum_offset is not None) else val

        # Query Luminosity
        l_raw = send_and_recv("NLU")
        if l_raw:
            sensors["raw"]["NLU"] = l_raw
            sensors["luminosity"] = l_raw

        # Query Unique ID
        id_raw = send_and_recv("NID")
        if id_raw:
            sensors["raw"]["NID"] = id_raw
            sensors["device_id"] = id_raw

        # Query Firmware Version
        fv_raw = send_and_recv("NFV")
        if fv_raw:
            sensors["raw"]["NFV"] = fv_raw
            sensors["firmware"] = fv_raw

        # Query Uptime
        ut_raw = send_and_recv("NUT")
        if ut_raw:
            sensors["raw"]["NUT"] = ut_raw
            try:
                sensors["uptime"] = int(ut_raw)
            except ValueError:
                sensors["uptime"] = ut_raw

        # Query Wifi Quality
        wq_raw = send_and_recv("NWQ")
        if wq_raw:
            sensors["raw"]["NWQ"] = wq_raw
            try:
                sensors["wifi_quality"] = int(wq_raw)
            except ValueError:
                sensors["wifi_quality"] = wq_raw
    except Exception as e:
        sensors["error"] = str(e)
    finally:
        try:
            s.close()
        except Exception:
            pass

    return sensors

COLOR_MAP = {
    "green": (0, 9, 0),
    "teal": (0, 9, 9),
    "cyan": (0, 9, 9),
    "blue": (0, 0, 9),
    "yellow": (9, 5, 0),
    "amber": (9, 3, 0),
    "orange": (9, 2, 0),
    "red": (9, 0, 0),
    "purple": (9, 0, 9),
    "magenta": (9, 0, 9),
    "white": (9, 9, 9),
    "off": (0, 0, 0)
}

def set_led_color(color_name: str, brightness=5730, ip=None, port=8070, timeout=2.5):
    """
    Sets persistent LED color via hardware RGB channels (NLD0, NLD1, NLD2).
    """
    target_ip = ip or get_ambi_ip()
    c = color_name.lower().strip()
    if c not in COLOR_MAP:
        print(f"    [-] Unknown color '{color_name}'. Available: {list(COLOR_MAP.keys())}")
        return False
    r, g, b = COLOR_MAP[c]
    print(f"\n[*] Setting Ambi Climate LED color to '{c.upper()}' (R={r}, G={g}, B={b}) on {target_ip}...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((target_ip, port))
        
        # 1. Stop offline error blink loop
        s.sendall(b"\x0700NSD\r")
        time.sleep(0.15)
        s.recv(256)
        s.sendall(b"\x0700NCD1\r")
        time.sleep(0.15)
        s.recv(256)

        # 2. Ensure brightness is enabled
        s.sendall(b"\x0700NLL1 " + str(brightness).encode("ascii") + b"\r")
        time.sleep(0.2)
        s.recv(256)
        
        # 3. Set individual RGB channels
        s.sendall(b"\x0700NLD0" + str(r).encode("ascii") + b"\r")
        time.sleep(0.15)
        s.recv(256)
        s.sendall(b"\x0700NLD1" + str(g).encode("ascii") + b"\r")
        time.sleep(0.15)
        s.recv(256)
        s.sendall(b"\x0700NLD2" + str(b).encode("ascii") + b"\r")
        time.sleep(0.15)
        resp = s.recv(256)
        s.close()
        print(f"    [+] SUCCESS! LED color set to '{c.upper()}'.")
        return True
    except Exception as e:
        print(f"    [-] Error setting LED color: {e}")
        return False

def set_led_visual_response(pattern_id: int, ip=None, port=8070, timeout=2.5):
    """
    Triggers Ambi Climate hardware Visual Response (LED color animations).
    pattern_id: 1 to 24 (presets for cooling cyan, heating amber, comfort green, etc.)
    """
    target_ip = ip or get_ambi_ip()
    print(f"\n[*] Sending Visual Response NVR{pattern_id} to Ambi Climate on {target_ip}...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((target_ip, port))
        # Ensure brightness is enabled first! Otherwise animation is invisible
        s.sendall(b"\x0700NLL1 5730\r")
        time.sleep(0.1)
        s.recv(256)

        pkt = b"\x0700NVR" + str(pattern_id).encode("ascii") + b"\r"
        s.sendall(pkt)
        time.sleep(0.2)
        resp = s.recv(512)
        s.close()
        ack = chr(resp[3]) if len(resp) > 3 else '?'
        if ack == '0':
            print(f"    [+] SUCCESS! Visual Response NVR{pattern_id} accepted (ACK_OK).")
            return True
        else:
            print(f"    [!] Device returned ACK code: {ack} (raw: {resp})")
            return False
    except Exception as e:
        print(f"    [-] Error sending LED command: {e}")
        return False

def set_led_brightness(level: int, ip=None, port=8070, timeout=2.5):
    """
    Sets Ambi Climate LED brightness level via PWM (0 to 10000).
    level = 0 completely DISABLES the LED (NLL0 + channels off).
    level > 0 ENABLES the LED and sets PWM level (NLL1 <level>).
    """
    target_ip = ip or get_ambi_ip()
    print(f"\n[*] Setting Ambi Climate LED brightness level to {level} on {target_ip}...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((target_ip, port))
        if level <= 0:
            # 1. Inform firmware that setup is done and disconnect from cloud to stop error blink loop
            s.sendall(b"\x0700NSD\r")
            time.sleep(0.1)
            s.recv(256)
            s.sendall(b"\x0700NCD1\r")
            time.sleep(0.1)
            s.recv(256)
            # 2. Completely disable LED state
            s.sendall(b"\x0700NLL0\r")
            time.sleep(0.1)
            s.recv(256)
            # 3. Explicitly turn off individual RGB channels
            for ch in ["NLD00", "NLD10", "NLD20"]:
                s.sendall(b"\x0700" + ch.encode("ascii") + b"\r")
                time.sleep(0.1)
                resp = s.recv(256)
            print(f"    [+] SUCCESS! LED is completely DISABLED and turned OFF.")
        else:
            cmd_str = f"NLL1 {level}"
            pkt = b"\x0700" + cmd_str.encode("ascii") + b"\r"
            s.sendall(pkt)
            time.sleep(0.2)
            resp = s.recv(512)
            print(f"    [+] SUCCESS! LED brightness set to {level}: {resp}")
        s.close()
        return True
    except Exception as e:
        print(f"    [-] Error setting LED brightness: {e}")
        return False

def dump_system_log(ip=None, port=8070, timeout=3.5):
    """
    Retrieves full internal system log from Ambi Climate using the NSL command.
    """
    target_ip = ip or get_ambi_ip()
    print(f"\n[*] Fetching System Log from Ambi Climate ({target_ip}:{port})...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((target_ip, port))
        s.sendall(b"\x0701NSL\r")
        chunks = []
        while True:
            try:
                data = s.recv(4096)
                if not data:
                    break
                chunks.append(data)
                time.sleep(0.15)
                r, _, _ = select.select([s], [], [], 0.3)
                if not r:
                    break
            except socket.timeout:
                break
        s.close()
        raw = b"".join(chunks)
        if raw:
            text = raw.decode("utf-8", errors="replace")
            print(f"[+] Received {len(raw)} bytes of System Log!\n")
            print("=" * 65)
            print(text.strip())
            print("=" * 65)
            log_file = os.path.join(DIR, "ambi_system_dump.log")
            with open(log_file, "wb") as f:
                f.write(raw)
            print(f"\n[+] System Log saved to: {log_file}")
            return text
        else:
            print("[-] No log data returned from device.")
    except Exception as e:
        print(f"[-] Error fetching system log: {e}")
    return None

def probe_sensors_and_ports():
    """
    Probes Ambi Climate ports and queries real-time sensors via native protocol (Port 8070).
    """
    print("\n" + "=" * 65)
    print("   Probing Ambi Climate Services & Real-time Sensors")
    print("=" * 65)

    # 1. Check Active Ports
    current_ip = get_ambi_ip()
    target_ports = [4998, 8070]
    print(f"\n[1/3] Checking active Ambi ports on {current_ip} (Auto-Discovered)...")
    open_ports = []
    for p in target_ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.5)
        res = s.connect_ex((current_ip, p))
        s.close()
        if res == 0:
            open_ports.append(p)
            print(f"    [+] Port {p:5d} is OPEN!")
        else:
            print(f"    [-] Port {p:5d} not responding (error code: {res})")
        time.sleep(0.3)

    # 2. Query Real-Time Sensors on Port 8070 (Native Framed Ambi Protocol)
    print(f"\n[2/3] Querying Real-time Sensors via Native Ambi Protocol (Port 8070)...")
    if 8070 in open_ports:
        live = get_live_sensors(current_ip, 8070)
        if "error" in live:
            print(f"    [-] Error querying sensors: {live['error']}")
        else:
            print("    [+] SENSOR READINGS RECEIVED SUCCESSFULLY:")
            print(f"        * Temperature   : {live['temperature']} °C (raw: {live.get('raw_temperature')} °C, offset: {live.get('temp_calibration_offset'):+}°C)")
            print(f"        * Humidity      : {live['humidity']} % (raw: {live.get('raw_humidity')} %, offset: {live.get('humidity_calibration_offset'):+}%)")
            print(f"        * Luminosity    : {live['luminosity']} (raw: {live['raw'].get('NLU')})")
            print(f"        * Device ID     : {live['device_id']}")
            print(f"        * Firmware Ver  : {live['firmware']}")
            print(f"        * Uptime        : {live['uptime']} seconds")
            print(f"        * Wi-Fi Quality : {live['wifi_quality']}%")
    else:
        print("    [-] Port 8070 is not open, skipping sensor query.")

    # 3. Global Cache Status on Port 4998
    print(f"\n[3/3] Checking Global Cache IR Engine on Port 4998...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect((current_ip, 4998))
        test_cmds = [
            "getversion\r",
            "getdevices\r",
        ]
        for cmd in test_cmds:
            s.sendall(cmd.encode("ascii"))
            time.sleep(0.3)
            try:
                resp = s.recv(512).decode("ascii", errors="replace").strip()
                print(f"    CMD: {repr(cmd.strip())} -> Response: {repr(resp)}")
            except socket.timeout:
                print(f"    CMD: {repr(cmd.strip())} -> (No response)")
        s.close()
    except Exception as e:
        print(f"    [-] Port 4998 error: {e}")

    print("\n" + "=" * 65)
    print("   Probe complete!")
    print("=" * 65)

def main():
    print("=" * 65)
    print("   Ambi Climate 2 - Daikin AC IR Controller (ARC480A46)")
    print(f"   Ambi IP: {AMBI_IP}:{AMBI_PORT} (Verified: Protocol B)")
    print("=" * 65)

    while True:
        print("\nChoose an option:")
        print("  [1] Turn ON  - Cool 24C (Verified Working Protocol B)")
        print("  [2] Turn OFF AC")
        print("  [3] Set Custom Temperature (18-30C)")
        print("  [4] Probe Ambi Climate (Find Real-time Sensors & Web API)")
        print("  [5] Check Connection & Status")
        print("  [6] Set LED Color (Green, Teal, Blue, Orange, Red, Purple, White, Animations)")
        print("  [7] Set LED Brightness / OFF (0-10000)")
        print("  [8] Dump System Log (ดึง Raw Syslog ล่าสุดเป็น Snapshot)")
        print("  [9] Real-time Log Monitor (tail -f เฝ้าดู Syslog สดตลอดเวลา)")
        print("  [0] Exit")

        try:
            choice = input("\nEnter choice [0-9]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            break

        if choice == "1":
            send_daikin(temp=24, mode="cool", fan="auto", power=True, protocol_type="B")
        elif choice == "2":
            print("\nSending Power OFF...")
            send_daikin(temp=24, mode="cool", fan="auto", power=False, protocol_type="B")
        elif choice == "3":
            try:
                t = int(input("Enter temperature (18-30): ").strip())
                send_daikin(temp=t, mode="cool", fan="auto", power=True, protocol_type="B")
            except ValueError:
                print("Invalid temperature!")
        elif choice == "4":
            probe_sensors_and_ports()
        elif choice == "5":
            check_status()
        elif choice == "6":
            print("\nSelect LED Color:")
            print("  [1] Green (เขียวสด)")
            print("  [2] Teal / Cyan (ฟ้าอมเขียว - สี Cloud ปกติ)")
            print("  [3] Blue (น้ำเงิน)")
            print("  [4] Orange / Amber (ส้ม/เหลือง)")
            print("  [5] Red (แดง)")
            print("  [6] Purple (ม่วง)")
            print("  [7] White (ขาว)")
            print("  [8] Visual Response Animation Preset (1-24)")
            c_choice = input("Enter choice [1-8]: ").strip().lower()
            c_map = {
                "1": "green", "green": "green",
                "2": "teal", "teal": "teal", "cyan": "cyan",
                "3": "blue", "blue": "blue",
                "4": "orange", "orange": "orange", "amber": "amber",
                "5": "red", "red": "red",
                "6": "purple", "purple": "purple",
                "7": "white", "white": "white"
            }
            if c_choice in c_map:
                set_led_color(c_map[c_choice])
            elif c_choice == "8":
                try:
                    pat = int(input("Enter Visual Response code (1-24): ").strip())
                    set_led_visual_response(pat)
                except ValueError:
                    print("Invalid number!")
            else:
                print("Invalid choice.")
        elif choice == "7":
            try:
                lvl = int(input("Enter LED Brightness (0=OFF, 1000-10000=Brightness): ").strip())
                set_led_brightness(lvl)
            except ValueError:
                print("Invalid brightness! Please enter 0-10000.")
        elif choice == "8":
            dump_system_log()
        elif choice == "9":
            from tail_ambi_log import stream_logs
            stream_logs()
        elif choice == "0":
            print("Bye!")
            break
        else:
            print("Invalid choice, please enter 0-9.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd in ["tail", "stream", "live", "9", "-f", "--tail"]:
            from tail_ambi_log import stream_logs
            stream_logs()
        elif cmd in ["log", "syslog", "8", "--log"]:
            dump_system_log()
        elif cmd in ["probe", "sensors", "sensor", "4", "-p", "--probe"]:
            probe_sensors_and_ports()
        elif cmd in ["on", "1"]:
            send_daikin(temp=24, mode="cool", fan="auto", power=True, protocol_type="B")
        elif cmd in ["off", "2"]:
            send_daikin(temp=24, mode="cool", fan="auto", power=False, protocol_type="B")
        elif cmd in ["status", "5"]:
            check_status()
        elif cmd in ["color", "colour"]:
            col = sys.argv[2] if len(sys.argv) > 2 else "teal"
            set_led_color(col)
        elif cmd in ["led", "vr"]:
            val = int(sys.argv[2]) if len(sys.argv) > 2 else 1
            set_led_visual_response(val)
        elif cmd in ["brightness", "bright"]:
            lvl = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
            set_led_brightness(lvl)
        elif cmd in ["led_off", "off_led"]:
            set_led_brightness(0)
        else:
            print(f"Unknown command: {cmd}. Usage: python3 test_daikin.py [probe|on|off|status|color <green|teal|blue|orange|red|purple|white>|led <1-24>|brightness <0-10000>|led_off]")
    else:
        main()
