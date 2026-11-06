#!/usr/bin/env python3
"""
Ambi Climate All-in-One Local Hub (Enhanced with Multi-Port Sniffer)
------------------------------------------------------------------
"""

import sys
import os
import re
import json
import time
import socket
import ssl
import struct
import threading
import subprocess
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import math
import select
from urllib.parse import urlparse, parse_qs

# -------------------------------------------------------------
# AUTO-NETWORK DETECTION & DASHBOARD CONFIG (Port 9090 default)
# -------------------------------------------------------------
DASHBOARD_PORT = int(os.environ.get("WEB_PORT") or os.environ.get("PORT") or 9090)

def detect_gateway_ip(fallback="192.168.1.1"):
    """Auto-detects the default router gateway IP address (Linux/Raspbian Buster & Windows)."""
    env_gw = os.environ.get("ROUTER_GATEWAY_IP")
    if env_gw and env_gw.strip():
        return env_gw.strip()

    # 1. Linux /proc/net/route (Standard on Raspbian Buster & Debian)
    if os.path.exists('/proc/net/route'):
        try:
            with open('/proc/net/route', 'r') as f:
                for line in f.readlines()[1:]:
                    parts = line.strip().split()
                    if len(parts) >= 3 and parts[1] == '00000000':
                        gw_hex = parts[2]
                        gw_bytes = bytes.fromhex(gw_hex)
                        gw_ip = socket.inet_ntoa(gw_bytes[::-1])
                        if gw_ip and gw_ip != '0.0.0.0':
                            return gw_ip
        except Exception:
            pass

    # 2. Linux ip route
    try:
        res = subprocess.run(['ip', 'route'], capture_output=True, text=True, timeout=1.5)
        m = re.search(r'default via (\d+\.\d+\.\d+\.\d+)', res.stdout)
        if m and m.group(1) != '0.0.0.0':
            return m.group(1)
    except Exception:
        pass

    # 3. Windows route print 0.0.0.0
    if os.name == 'nt':
        try:
            res = subprocess.run(['route', 'print', '0.0.0.0'], capture_output=True, text=True, timeout=1.5)
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and parts[0] == '0.0.0.0':
                    gw = parts[2]
                    if re.match(r'^\d+\.\d+\.\d+\.\d+$', gw) and gw != '0.0.0.0':
                        return gw
        except Exception:
            pass

    return fallback

def detect_local_ip(gateway_ip=None, fallback="192.168.1.138"):
    """Auto-detects the host's real primary LAN IP address (tested on Raspbian 10 Buster, Linux, and Windows)."""
    env_ip = os.environ.get("HOST_IP")
    # Only use env_ip if user explicitly specified a non-dummy value
    if env_ip and env_ip.strip() and env_ip.strip() != "192.168.1.138":
        return env_ip.strip()

    # 1. Linux ip -4 route get <target> (Rock-solid on Raspbian Buster)
    probe_target = gateway_ip if (gateway_ip and gateway_ip != "0.0.0.0") else "8.8.8.8"
    try:
        res = subprocess.run(['ip', '-4', 'route', 'get', probe_target], capture_output=True, text=True, timeout=1.5)
        m = re.search(r'src\s+(\d+\.\d+\.\d+\.\d+)', res.stdout)
        if m:
            cand = m.group(1)
            if not cand.startswith(('127.', '169.254.', '172.17.', '172.18.')):
                return cand
    except Exception:
        pass

    # 2. Linux hostname -I (Standard on Raspbian 10 Buster)
    try:
        res = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=1.5)
        for cand in res.stdout.strip().split():
            # Skip loopback, link-local, and default docker bridge networks
            if cand.startswith(('127.', '169.254.', '172.17.', '172.18.', '172.19.', '172.20.')):
                continue
            if re.match(r'^\d+\.\d+\.\d+\.\d+$', cand):
                return cand
    except Exception:
        pass

    # 3. Kernel UDP socket routing probe to gateway or 8.8.8.8
    for target in [gateway_ip, "8.8.8.8", "1.1.1.1"]:
        if not target or target == "0.0.0.0":
            continue
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1.0)
            s.connect((target, 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith(('127.', '169.254.', '172.17.', '172.18.')):
                return ip
        except Exception:
            pass

    # 4. Standard socket hostname resolution
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith(('127.', '169.254.', '172.17.', '172.18.')):
            return ip
    except Exception:
        pass

    # 5. Infer from gateway IP subnet if available
    if gateway_ip and '.' in gateway_ip:
        base = gateway_ip.rsplit('.', 1)[0]
        # Return fallback with matching subnet if feasible
        return f"{base}.138"

    return fallback

def detect_wan_ip(fallback="100.112.62.200"):
    """Auto-detects the router's public or CGNAT WAN IP via fast external probe."""
    env_wan = os.environ.get("ROUTER_WAN_IP")
    if env_wan and env_wan.strip():
        return env_wan.strip()

    urls = [
        'http://api.ipify.org',
        'https://api.ipify.org',
        'http://icanhazip.com',
        'https://icanhazip.com',
        'http://checkip.amazonaws.com',
        'https://ifconfig.me/ip'
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.88.1'})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                wan = resp.read().decode('utf-8', errors='ignore').strip()
                if re.match(r'^\d+\.\d+\.\d+\.\d+$', wan):
                    return wan
        except Exception:
            continue

    return fallback

# Initial automatic network configuration (Gateway first, then Host LAN IP)
ROUTER_GATEWAY_IP = detect_gateway_ip(fallback="192.168.1.1")
HOST_IP = detect_local_ip(gateway_ip=ROUTER_GATEWAY_IP, fallback="192.168.1.138")
ROUTER_WAN_IP = detect_wan_ip(fallback="100.112.62.200")
# DNS Redirect target: Uses ROUTER_WAN_IP (CGNAT 100.64.0.0/10) to bypass dnsmasq --stop-dns-rebind
DNS_REDIRECT_IP = os.environ.get("DNS_REDIRECT_IP") or ROUTER_WAN_IP

def refresh_network_settings():
    """Refreshes all auto-detected network settings."""
    global HOST_IP, ROUTER_GATEWAY_IP, ROUTER_WAN_IP, DNS_REDIRECT_IP
    ROUTER_GATEWAY_IP = detect_gateway_ip(fallback=ROUTER_GATEWAY_IP)
    HOST_IP = detect_local_ip(gateway_ip=ROUTER_GATEWAY_IP, fallback=HOST_IP)
    detected_wan = detect_wan_ip(fallback=ROUTER_WAN_IP)
    if detected_wan:
        ROUTER_WAN_IP = detected_wan
        if not os.environ.get("DNS_REDIRECT_IP"):
            DNS_REDIRECT_IP = ROUTER_WAN_IP
    hub_log(f"[AUTO-NET 🌐] Host IP: {HOST_IP} | Gateway: {ROUTER_GATEWAY_IP} | WAN IP: {ROUTER_WAN_IP} | DNS Redirect: {DNS_REDIRECT_IP} | Web Port: {DASHBOARD_PORT}")

DIR = os.path.dirname(os.path.abspath(__file__))
CERT_FILE = os.path.join(DIR, "server_cert.pem")
KEY_FILE = os.path.join(DIR, "server_key.pem")
PROFILE_FILE = os.path.join(DIR, "decompiled_analysis", "user_device_profile.json")

from test_daikin import save_ambi_ip, is_valid_ambi

# In-Memory Ambi IP State (Requirement 1: Locked strictly upon connect query)
AMBI_IP = None
AMBI_READY_EVENT = threading.Event()
AMBI_AUTO_RETARGETED = False
AMBI_PORT_8070_LOCK = threading.Lock()

def get_ambi_ip():
    global AMBI_IP
    return AMBI_IP

def update_ambi_ip(new_ip, source=""):
    global AMBI_IP
    if not new_ip or new_ip in (HOST_IP, ROUTER_WAN_IP, ROUTER_GATEWAY_IP, "127.0.0.1"):
        return
    if new_ip != AMBI_IP and new_ip.startswith("192.168."):
        old_ip = AMBI_IP
        AMBI_IP = new_ip
        save_ambi_ip(new_ip)
        src_tag = f" via {source}" if source else ""
        hub_log(f"\n{'='*65}\n🎯 [STEP 1: CAPTURED AMBI IP] Detected {AMBI_IP}{src_tag} (was {old_ip})\n{'='*65}\n")
        # Trigger Green LED immediately in background
        threading.Thread(target=set_ambi_led_green, args=(new_ip,), daemon=True).start()

def send_ambi_cmd(cmd_text, target_ip=None, port=8070, timeout=3.0):
    """Sends framed command to Ambi on Port 8070 and returns the raw response."""
    ip = target_ip or get_ambi_ip()
    if not ip:
        hub_log(f"[-] Command to Ambi ({cmd_text}) skipped: Ambi IP not yet acquired (waiting for DNS connect query).")
        return None
    seq = "01"
    packet = b"\x07" + seq.encode('ascii') + cmd_text.encode('latin1') + b"\r"
    with AMBI_PORT_8070_LOCK:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((ip, port))
            s.sendall(packet)
            time.sleep(0.15)
            resp = s.recv(2048)
            s.close()
            return resp
        except Exception as e:
            hub_log(f"[-] Command to Ambi ({cmd_text} -> {ip}:{port}) failed: {e}")
            return None

def get_cloud_server_setting(target_ip=None):
    """Queries current configured Cloud Server (NCA) from Ambi Port 8070."""
    ip = target_ip or get_ambi_ip()
    if not ip:
        return "Waiting for Ambi connect..."
    resp = send_ambi_cmd("NCA", ip)
    if resp and len(resp) >= 7 and resp[0] == 7:
        val = resp[7:].decode('latin1', errors='ignore').strip('\r\n ')
        return val if val else "Empty (Default Cloud)"
    elif resp:
        val = resp.decode('latin1', errors='ignore').strip()
        return val if val else "Empty (Default Cloud)"
    return "Unknown / No response"

def change_cloud_server(new_server_port, target_ip=None):
    """Sends NCA (Address Override), NCE (Environment), and NCD to force reconnect."""
    ip = target_ip or get_ambi_ip()
    if not ip:
        hub_log("[-] Cannot change cloud server: Ambi IP not yet acquired.")
        return {"status": "Error", "message": "Ambi IP not yet acquired"}
    hub_log(f"\n{'='*65}")
    hub_log(f"🚀 [STEP 3: CHANGING CLOUD SERVER] Target Ambi IP: {ip}")
    hub_log(f"   Target Server: {new_server_port}")
    hub_log(f"{'='*65}")

    # 1. Query current
    curr = get_cloud_server_setting(ip)
    hub_log(f"   1) Current Cloud Setting (NCA)     : '{curr}'")

    # 2. Send NCA (Cloud Server Address Override)
    resp_ca = send_ambi_cmd(f"NCA{new_server_port}", ip)
    ca_decoded = resp_ca.decode('latin1', errors='ignore').strip() if resp_ca else "None"
    hub_log(f"   2) Sent NCA (Address Override) ->  : '{ca_decoded}'")

    # 3. Send NCE (Cloud Environment)
    resp_ce = send_ambi_cmd(f"NCE{new_server_port}", ip)
    ce_decoded = resp_ce.decode('latin1', errors='ignore').strip() if resp_ce else "None"
    hub_log(f"   3) Sent NCE (Environment)      ->  : '{ce_decoded}'")

    # 4. Send NCD (Cloud Reconnect)
    resp_cd = send_ambi_cmd("NCD", ip)
    cd_decoded = resp_cd.decode('latin1', errors='ignore').strip() if resp_cd else "None"
    hub_log(f"   4) Sent NCD (Reconnect)        ->  : '{cd_decoded}'")
    hub_log(f"✅ Cloud Server re-target sent! Target: {new_server_port}\n")
    return {
        "status": "OK",
        "device_ip": ip,
        "previous_server": curr,
        "new_server": new_server_port,
        "response_ca": ca_decoded,
        "response_ce": ce_decoded,
        "response_cd": cd_decoded
    }

def fetch_ambi_system_log(target_ip=None, timeout=7.0):
    """Retrieves full internal system log from Ambi Climate using NSL command."""
    ip = target_ip or get_ambi_ip()
    if not ip:
        return "Ambi IP not yet acquired. Waiting for Ambi to send DNS connect query..."
    hub_log(f"[*] Fetching Ambi System Log from {ip}:8070 (NSL)...")
    with AMBI_PORT_8070_LOCK:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((ip, 8070))
            s.sendall(b"\x0701NSL\r")
            chunks = []
            start_t = time.time()
            while time.time() - start_t < timeout:
                try:
                    r, _, _ = select.select([s], [], [], 0.8)
                    if not r:
                        if chunks:
                            break
                        continue
                    data = s.recv(4096)
                    if not data:
                        break
                    chunks.append(data)
                except socket.timeout:
                    break
            s.close()
            raw = b"".join(chunks)
            if raw:
                text = raw.decode("utf-8", errors="replace")
                log_file = os.path.join(DIR, "ambi_system_dump.log")
                with open(log_file, "wb") as f:
                    f.write(raw)
                hub_log(f"[+] Received {len(raw)} bytes of Ambi System Log -> Saved to {log_file}")
                return text
            else:
                hub_log("[-] No log data returned from device.")
                return "No log data returned from device."
        except Exception as e:
            hub_log(f"[-] Error fetching system log from {ip}: {e}")
            return f"Error connecting to Ambi on {ip}:8070 -> {e}"

def get_cached_ambi_ip():
    cache_file = os.path.join(DIR, "ambi_ip.txt")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                ip = f.read().strip()
                if ip.startswith("192.168."):
                    return ip
        except Exception:
            pass
    return "192.168.1.156"

def set_ambi_led_green(target_ip=None, brightness=5730):
    """
    Directly sets Ambi Climate hardware LED to SOLID GREEN:
    1. Sends NSD (Setup Done) & NCD1 (Stop offline blink loop)
    2. Sends NLL1 (Enable brightness PWM)
    3. Sets RGB: Red=0 (NLD00), Green=9 (NLD19), Blue=0 (NLD20)
    """
    ip = target_ip or get_ambi_ip() or get_cached_ambi_ip()
    if not ip:
        hub_log("[-] Cannot set LED: Ambi IP not yet acquired.")
        return False
    hub_log(f"[*] Setting Ambi Climate LED to SOLID GREEN on {ip}:8070...")
    with AMBI_PORT_8070_LOCK:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect((ip, 8070))

            # 1. Stop offline blink loop
            s.sendall(b"\x0700NSD\r")
            time.sleep(0.12)
            try: s.recv(256)
            except Exception: pass

            s.sendall(b"\x0700NCD1\r")
            time.sleep(0.12)
            try: s.recv(256)
            except Exception: pass

            # 2. Enable brightness PWM
            s.sendall(b"\x0700NLL1 " + str(brightness).encode("ascii") + b"\r")
            time.sleep(0.15)
            try: s.recv(256)
            except Exception: pass

            # 3. Set Green: R=0, G=9, B=0
            s.sendall(b"\x0700NLD00\r")
            time.sleep(0.12)
            try: s.recv(256)
            except Exception: pass

            s.sendall(b"\x0700NLD19\r")
            time.sleep(0.12)
            try: s.recv(256)
            except Exception: pass

            s.sendall(b"\x0700NLD20\r")
            time.sleep(0.12)
            try: s.recv(256)
            except Exception: pass

            s.close()
            hub_log(f"✅ [🟢 LED ACTIVATED] Ambi Climate ({ip}) front LED is now SOLID GREEN!")
            return True
        except Exception as e:
            hub_log(f"[-] Error setting LED to Green on {ip}: {e}")
            return False

def set_ambi_led_brightness(level: int, target_ip=None):
    """
    Sets Ambi Climate LED brightness (0 = OFF, 1-10000 = PWM brightness).
    Maintains Green color when turned ON.
    """
    ip = target_ip or get_ambi_ip() or get_cached_ambi_ip()
    if not ip:
        hub_log("[-] Cannot set brightness: Ambi IP not yet acquired.")
        return False

    level = max(0, min(10000, int(level)))
    hub_log(f"[*] Setting Ambi Climate LED brightness to {level} on {ip}:8070...")
    with AMBI_PORT_8070_LOCK:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect((ip, 8070))

            if level <= 0:
                s.sendall(b"\x0700NSD\r")
                time.sleep(0.1)
                try: s.recv(256)
                except Exception: pass

                s.sendall(b"\x0700NCD1\r")
                time.sleep(0.1)
                try: s.recv(256)
                except Exception: pass

                s.sendall(b"\x0700NLL0\r")
                time.sleep(0.1)
                try: s.recv(256)
                except Exception: pass

                for ch in ["NLD00", "NLD10", "NLD20"]:
                    s.sendall(b"\x0700" + ch.encode("ascii") + b"\r")
                    time.sleep(0.08)
                    try: s.recv(256)
                    except Exception: pass
                s.close()
                hub_log(f"✅ [💡 LED OFF] Ambi Climate ({ip}) front LED is now turned OFF.")
            else:
                s.sendall(b"\x0700NSD\r")
                time.sleep(0.1)
                try: s.recv(256)
                except Exception: pass

                s.sendall(b"\x0700NCD1\r")
                time.sleep(0.1)
                try: s.recv(256)
                except Exception: pass

                s.sendall(b"\x0700NLL1 " + str(level).encode("ascii") + b"\r")
                time.sleep(0.15)
                try: s.recv(256)
                except Exception: pass

                # Maintain Green color (Red=0, Green=9, Blue=0)
                s.sendall(b"\x0700NLD00\r")
                time.sleep(0.1)
                try: s.recv(256)
                except Exception: pass

                s.sendall(b"\x0700NLD19\r")
                time.sleep(0.1)
                try: s.recv(256)
                except Exception: pass

                s.sendall(b"\x0700NLD20\r")
                time.sleep(0.1)
                try: s.recv(256)
                except Exception: pass

                s.close()
                pct = round(level / 100)
                hub_log(f"✅ [💡 LED BRIGHTNESS] Ambi Climate ({ip}) LED brightness set to {level} ({pct}%) Green.")
            return True
        except Exception as e:
            hub_log(f"[-] Error setting LED brightness on {ip}: {e}")
            return False

def query_live_sensors(target_ip=None):
    """
    On-demand query of real-time temperature, humidity, luminosity from Ambi Climate Port 8070.
    Updates AC_STATE and comfort evaluation immediately.
    """
    from test_daikin import get_live_sensors
    ip = target_ip or get_ambi_ip() or get_cached_ambi_ip()
    if not ip:
        hub_log("[-] Cannot query sensors: Ambi IP not yet acquired.")
        return {"status": "Error", "message": "Ambi IP not yet acquired"}

    hub_log(f"[*] Querying live sensors on-demand from {ip}:8070...")
    with AMBI_PORT_8070_LOCK:
        live = get_live_sensors(ip, port=8070, timeout=3.5)

    if live.get("temperature") is not None:
        AC_STATE["room_temp"] = live["temperature"]
    if live.get("humidity") is not None:
        AC_STATE["room_humidity"] = live["humidity"]
    if live.get("luminosity"):
        AC_STATE["luminosity"] = live["luminosity"]

    c = evaluate_comfort(AC_STATE["room_temp"], AC_STATE["room_humidity"])
    AC_STATE["humidex"] = c["humidex"]
    AC_STATE["comfort_score"] = c["score"]
    AC_STATE["comfort_label"] = c["label"]
    AC_STATE["comfort_badge_color"] = c["badge_color"]
    AC_STATE["sensor_status"] = f"Manual Query ({ip})"
    AC_STATE["sensor_time"] = time.strftime('%H:%M:%S')

    hub_log(f"[MANUAL SENSOR QUERY] Temp: {AC_STATE['room_temp']}°C | Hum: {AC_STATE['room_humidity']}% | Humidex: {c['humidex']}°C | Status: {c['label']}")
    return {
        "status": "OK",
        "room_temp": AC_STATE["room_temp"],
        "room_humidity": AC_STATE["room_humidity"],
        "luminosity": AC_STATE.get("luminosity"),
        "humidex": c["humidex"],
        "comfort_score": c["score"],
        "comfort_label": c["label"],
        "comfort_badge_color": c["badge_color"],
        "sensor_status": AC_STATE["sensor_status"],
        "sensor_time": AC_STATE["sensor_time"]
    }

def led_keepalive_worker(interval_sec=120):
    """
    Periodically reaffirms Solid Green LED every interval_sec (default 120s)
    to ensure the internal 1NCO slave watchdog never reverts the LED to amber.
    """
    while True:
        try:
            time.sleep(interval_sec)
            if AMBI_READY_EVENT.is_set():
                target = get_ambi_ip() or get_cached_ambi_ip()
                if target:
                    set_ambi_led_green(target)
        except Exception:
            pass

def run_beacon_listener():
    """Listens for AMX Beacon on UDP 9131 to auto-detect Ambi IP."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', 9131))
        mreq = struct.pack("4sl", socket.inet_aton("239.255.250.250"), socket.INADDR_ANY)
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except Exception:
            pass
        while True:
            data, addr = sock.recvfrom(2048)
            text = data.decode('latin1', errors='ignore')
            if "AMXB" in text or "GlobalCache" in text:
                update_ambi_ip(addr[0], source="AMX Beacon UDP 9131")
    except Exception:
        pass

LOG_FILE = os.path.join(DIR, "hub_activity.log")

def hub_log(msg):
    ts = time.strftime('%H:%M:%S')
    formatted = f"[{ts}] {msg}"
    print(formatted)
    sys.stdout.flush()
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
            f.flush()
    except Exception:
        pass

# Load device profile
with open(PROFILE_FILE, "r", encoding="utf-8") as f:
    PROFILE = json.load(f)

DEVICE = PROFILE["ZDEVICE"][0]
APPLIANCE = PROFILE["ZAPPLIANCE"][0]

REAL_DEVICE_ID = DEVICE["ZREAL_ID"]
DEVICE_UUID = DEVICE["ZID"]
MAC_ADDRESS = DEVICE["ZMAC_ADDRESS"]
IRP_ID = APPLIANCE["ZIRP_ID"]

AC_STATE = {
    "power": "Off",  # Requirement 3: System will not auto-tune until AC is explicitly turned ON
    "mode": "Cool",
    "ambi_mode": "Comfort",  # Comfort, Temperature, Manual, Away, Off (from Ambi User Guide)
    "temperature": 24,
    "fan": "Auto",
    "swing": "Auto",
    "last_seen": None,
    "room_temp": None,
    "room_humidity": None,
    "luminosity": None,
    "humidex": None,
    "comfort_score": 0.0,
    "comfort_label": "รอข้อมูล Push จาก Ambi...",
    "comfort_badge_color": "#64748b",
    "sensor_status": "รอข้อมูล Push จาก Ambi (Passive Push Mode)",
    "sensor_time": None
}

# -------------------------------------------------------------
# HYBRID LOCAL COMFORT AI - PROFILE & PREFERENCES
# -------------------------------------------------------------
COMFORT_PROFILE_FILE = os.path.join(DIR, "user_comfort_profile.json")

DEFAULT_COMFORT_PROFILE = {
    "auto_tune_enabled": True,
    "target_base_humidex": 26.0,
    "user_offset": 0.0,
    "min_temp": 22,
    "max_temp": 27,
    "cooldown_minutes": 10,
    "last_tune_time": 0,
    "last_tune_action": "System Initialized",
    "history": []
}

def load_comfort_profile():
    if os.path.exists(COMFORT_PROFILE_FILE):
        try:
            with open(COMFORT_PROFILE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                res = DEFAULT_COMFORT_PROFILE.copy()
                res.update(data)
                return res
        except Exception as e:
            hub_log(f"[-] Error loading comfort profile: {e}")
    return DEFAULT_COMFORT_PROFILE.copy()

def save_comfort_profile(profile):
    try:
        with open(COMFORT_PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
    except Exception as e:
        hub_log(f"[-] Error saving comfort profile: {e}")

COMFORT_PROFILE = load_comfort_profile()

def calculate_humidex(temp_c, humidity_rh):
    """
    Canadian Humidex Formula:
    v = 6.112 * (10 ** ((7.5 * T) / (237.7 + T))) * (RH / 100.0)
    Humidex = T + (5.0 / 9.0) * (v - 10.0)
    """
    if temp_c is None or humidity_rh is None:
        return None
    try:
        t = float(temp_c)
        rh = float(humidity_rh)
        v = 6.112 * (10.0 ** ((7.5 * t) / (237.7 + t))) * (rh / 100.0)
        humidex = t + (5.0 / 9.0) * (v - 10.0)
        return round(humidex, 1)
    except Exception:
        try:
            return round(float(temp_c), 1)
        except Exception:
            return None

def evaluate_comfort(temp_c, humidity_rh, user_offset=None):
    if user_offset is None:
        user_offset = COMFORT_PROFILE.get("user_offset", 0.0)
    base_target = COMFORT_PROFILE.get("target_base_humidex", 26.0)
    target = base_target + user_offset

    if temp_c is None or humidity_rh is None:
        return {
            "humidex": None,
            "target_humidex": round(target, 1),
            "score": 0.0,
            "label": "รอข้อมูล Push จาก Ambi...",
            "status_key": "waiting",
            "badge_color": "#64748b"
        }

    humidex = calculate_humidex(temp_c, humidity_rh)
    if humidex is None:
        humidex = round(float(temp_c), 1) if temp_c is not None else 25.0
    diff = humidex - target
    score = round(diff / 1.5, 1)
    score = max(-3.0, min(3.0, score))

    if score <= -2.2:
        label = "หนาวมาก (Freezing)"
        status_key = "freezing"
        badge_color = "#2563eb"
    elif score <= -1.2:
        label = "หนาวเกินไป (Too Cold)"
        status_key = "too_cold"
        badge_color = "#3b82f6"
    elif score <= -0.7:
        label = "เริ่มเย็นเล็กน้อย (Comfortably Cool)"
        status_key = "cool"
        badge_color = "#0284c7"
    elif score < 0.7:
        label = "กำลังสบาย (Comfortable)"
        status_key = "comfortable"
        badge_color = "#059669"
    elif score < 1.2:
        label = "เริ่มอุ่นเล็กน้อย (Comfortably Warm)"
        status_key = "warm"
        badge_color = "#d97706"
    elif score < 2.2:
        label = "ร้อนเกินไป (Too Warm)"
        status_key = "too_warm"
        badge_color = "#ea580c"
    else:
        label = "ร้อนมาก (Hot)"
        status_key = "hot"
        badge_color = "#dc2626"

    return {
        "humidex": humidex,
        "target_humidex": round(target, 1),
        "score": score,
        "label": label,
        "status_key": status_key,
        "badge_color": badge_color
    }

def send_daikin_ir(temp=None, mode=None, fan=None, power=None, reason="Manual"):
    """
    Sends IR signal to Daikin AC via Ambi Climate port 4998 and updates AC_STATE.
    """
    import daikin_ir
    if temp is not None:
        AC_STATE['temperature'] = max(18, min(30, int(temp)))
    if mode is not None:
        AC_STATE['mode'] = str(mode)
    if fan is not None:
        AC_STATE['fan'] = str(fan)
    if power is not None:
        AC_STATE['power'] = str(power)

    is_power = str(AC_STATE['power']).lower() != 'off'
    target_ip = get_ambi_ip()
    if not target_ip:
        hub_log(f"[IR TRANSMIT SKIPPED] ({reason}) Ambi IP not yet acquired.")
        return "Ambi IP not yet acquired"
    ir_resp = ""
    s = None
    try:
        f1, f2 = daikin_ir.build_daikin_command(
            temp=AC_STATE['temperature'],
            mode=AC_STATE['mode'],
            fan=AC_STATE['fan'],
            power=is_power,
            protocol_type="B"
        )
        cmd = daikin_ir.frames_to_sendir(f1, f2, connector="1:1")
        s = socket.create_connection((target_ip, 4998), timeout=3.0)
        s.sendall(cmd.encode('ascii'))
        ir_resp = s.recv(256).decode('ascii', errors='ignore').strip()
        hub_log(f"[IR TRANSMIT DAIKIN] ({reason}) Target={AC_STATE['temperature']}°C Fan={AC_STATE['fan']} Power={AC_STATE['power']} -> {ir_resp}")
    except Exception as e:
        ir_resp = f"Error: {e}"
        hub_log(f"[IR TRANSMIT ERROR] ({reason}) {e}")
    finally:
        if s:
            try:
                s.close()
            except Exception:
                pass

    # Record event in history
    entry = {
        "time": time.strftime('%H:%M:%S'),
        "action": reason,
        "temp": AC_STATE['temperature'],
        "fan": AC_STATE['fan'],
        "power": AC_STATE['power'],
        "room_temp": AC_STATE.get('room_temp'),
        "room_humidity": AC_STATE.get('room_humidity'),
        "result": ir_resp
    }
    history = COMFORT_PROFILE.get("history", [])
    history.insert(0, entry)
    COMFORT_PROFILE["history"] = history[:25]
    save_comfort_profile(COMFORT_PROFILE)

    return ir_resp

CONSECUTIVE_OUT_OF_BOUNDS = 0

def auto_tuning_worker():
    """
    Background worker that monitors room climate and tunes Daikin AC automatically.
    Safety controls:
      - Deadband: -0.7 to +0.7 -> No action
      - Noise filter: requires 2 consecutive cycles outside deadband
      - Cooldown timer: default 10 minutes between IR transmissions
      - Min / Max temperature clamps
    """
    global CONSECUTIVE_OUT_OF_BOUNDS
    time.sleep(10)
    hub_log("[+] AUTO-TUNING COMFORT AI Worker Active.")

    while True:
        try:
            time.sleep(30)
            if not COMFORT_PROFILE.get("auto_tune_enabled", True):
                continue

            # Requirement 3: MUST wait until AC is explicitly turned ON before auto-tuning!
            power_status = str(AC_STATE.get("power", "Off")).lower()
            if power_status != "on":
                continue

            if not AMBI_READY_EVENT.is_set():
                continue

            room_t = AC_STATE.get("room_temp")
            room_rh = AC_STATE.get("room_humidity")
            if room_t is None or room_rh is None:
                continue

            comfort = evaluate_comfort(room_t, room_rh)
            score = comfort["score"]

            now = time.time()
            cooldown_sec = COMFORT_PROFILE.get("cooldown_minutes", 10) * 60
            last_tune = COMFORT_PROFILE.get("last_tune_time", 0)
            time_since_tune = now - last_tune

            # Deadband check (-0.8 to +0.8)
            if -0.8 <= score <= 0.8:
                CONSECUTIVE_OUT_OF_BOUNDS = 0
                continue

            CONSECUTIVE_OUT_OF_BOUNDS += 1
            if CONSECUTIVE_OUT_OF_BOUNDS < 2:
                continue

            if time_since_tune < cooldown_sec:
                continue

            min_t = COMFORT_PROFILE.get("min_temp", 22)
            max_t = COMFORT_PROFILE.get("max_temp", 27)
            curr_ac_t = AC_STATE.get("temperature", 24)

            if score <= -1.2:
                # Too Cold: increase temp or reduce fan
                new_t = curr_ac_t
                new_fan = AC_STATE.get("fan", "Auto")
                if curr_ac_t < max_t:
                    new_t = curr_ac_t + 1
                elif new_fan in ("High", "5", "med", "3"):
                    new_fan = "Low"
                elif new_fan in ("Low", "1", "Auto"):
                    new_fan = "Quiet"

                if new_t != curr_ac_t or new_fan != AC_STATE.get("fan"):
                    reason = f"Auto-Tune (หนาวไป: Feels {comfort['humidex']}°C)"
                    send_daikin_ir(temp=new_t, fan=new_fan, reason=reason)
                    COMFORT_PROFILE["last_tune_time"] = now
                    COMFORT_PROFILE["last_tune_action"] = f"Warmed to {new_t}°C ({new_fan})"
                    save_comfort_profile(COMFORT_PROFILE)
                    CONSECUTIVE_OUT_OF_BOUNDS = 0

            elif score >= 1.2:
                # Too Warm: decrease temp or increase fan
                new_t = curr_ac_t
                new_fan = AC_STATE.get("fan", "Auto")
                if curr_ac_t > min_t:
                    new_t = curr_ac_t - 1
                elif new_fan in ("Quiet", "silent", "Low", "1"):
                    new_fan = "med"
                elif new_fan in ("med", "3"):
                    new_fan = "High"

                if new_t != curr_ac_t or new_fan != AC_STATE.get("fan"):
                    reason = f"Auto-Tune (ร้อนไป: Feels {comfort['humidex']}°C)"
                    send_daikin_ir(temp=new_t, fan=new_fan, reason=reason)
                    COMFORT_PROFILE["last_tune_time"] = now
                    COMFORT_PROFILE["last_tune_action"] = f"Cooled to {new_t}°C ({new_fan})"
                    save_comfort_profile(COMFORT_PROFILE)
                    CONSECUTIVE_OUT_OF_BOUNDS = 0

        except Exception as e:
            hub_log(f"[-] Auto-Tuning worker exception: {e}")

POLL_SENSORS_ENABLED = True

def poll_live_sensors(interval=20):
    """Periodically queries Port 8070 on Ambi Climate to retrieve real-time live sensor data."""
    from test_daikin import get_live_sensors
    hub_log(f"[+] Live Hardware Sensor Poller (Pull Query :8070) worker started (every {interval}s).")
    while True:
        try:
            if not POLL_SENSORS_ENABLED:
                time.sleep(5)
                continue

            if not AMBI_READY_EVENT.is_set():
                AC_STATE["sensor_status"] = "Waiting for Ambi connect.* DNS query..."
                time.sleep(2)
                continue

            target_ip = get_ambi_ip() or get_cached_ambi_ip()
            if not target_ip:
                time.sleep(2)
                continue

            with AMBI_PORT_8070_LOCK:
                live = get_live_sensors(target_ip, port=8070, timeout=3.5)
            if live.get("temperature") is not None:
                AC_STATE["room_temp"] = live["temperature"]
            if live.get("humidity") is not None:
                AC_STATE["room_humidity"] = live["humidity"]
            if live.get("luminosity"):
                AC_STATE["luminosity"] = live["luminosity"]

            # Update live comfort calculation
            c = evaluate_comfort(AC_STATE["room_temp"], AC_STATE["room_humidity"])
            AC_STATE["humidex"] = c["humidex"]
            AC_STATE["comfort_score"] = c["score"]
            AC_STATE["comfort_label"] = c["label"]
            AC_STATE["comfort_badge_color"] = c["badge_color"]

            AC_STATE["sensor_status"] = f"PULL LIVE ({target_ip})"
            AC_STATE["sensor_time"] = time.strftime('%H:%M:%S')
            hub_log(f"[SENSOR UPDATE PULL] Temp: {AC_STATE['room_temp']}°C | Hum: {AC_STATE['room_humidity']}% | Humidex: {c['humidex']}°C ({c['label']}) | IP: {target_ip}")
        except Exception as e:
            AC_STATE["sensor_status"] = f"Error: {e}"
        time.sleep(interval)

DASHBOARD_HTML_FILE = os.path.join(DIR, "web_dashboard.html")

def get_dashboard_html():
    """Returns the authentic Ambi Climate App UI matching user manual, fallback to embedded HTML."""
    if os.path.exists(DASHBOARD_HTML_FILE):
        try:
            with open(DASHBOARD_HTML_FILE, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return WEB_DASHBOARD_HTML

WEB_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ambi Climate Local Hub - Daikin Comfort AI</title>
    <style>
        :root {
            --bg: #0f172a;
            --card-bg: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --border: #334155;
            --blue: #3b82f6;
            --green: #10b981;
            --amber: #f59e0b;
            --red: #ef4444;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background: var(--bg); color: var(--text-main); padding: 16px; min-height: 100vh; display: flex; justify-content: center; }
        .container { width: 100%; max-width: 540px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }
        
        .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 16px; padding: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 14px; }
        .title { font-size: 18px; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 8px; }
        .badge { padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
        .badge-live { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }
        .badge-cooldown { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }
        
        /* Climate Grid */
        .metrics-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 16px 0; }
        .metric-box { background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 12px; padding: 12px 8px; text-align: center; }
        .metric-label { font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }
        .metric-val { font-size: 22px; font-weight: 700; color: #fff; }
        .metric-unit { font-size: 12px; color: var(--text-muted); font-weight: normal; }

        /* Comfort Banner */
        .comfort-banner { border-radius: 12px; padding: 14px; text-align: center; margin-bottom: 14px; transition: background 0.3s; }
        .comfort-score { font-size: 13px; font-weight: 600; margin-top: 4px; opacity: 0.9; }

        /* Auto-Tune Row */
        .autotune-row { display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.02); padding: 12px 14px; border-radius: 12px; border: 1px solid var(--border); }
        .switch { position: relative; display: inline-block; width: 44px; height: 24px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #475569; transition: .3s; border-radius: 24px; }
        .slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background-color: white; transition: .3s; border-radius: 50%; }
        input:checked + .slider { background-color: var(--green); }
        input:checked + .slider:before { transform: translateX(20px); }

        /* Feedback Section */
        .feedback-title { font-size: 13px; font-weight: 600; color: var(--text-muted); margin-bottom: 10px; text-align: center; }
        .feedback-btns { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
        .btn-feed { border: none; border-radius: 12px; padding: 14px 8px; cursor: pointer; font-size: 13px; font-weight: 700; display: flex; flex-direction: column; align-items: center; gap: 6px; transition: transform 0.1s, opacity 0.2s; color: white; }
        .btn-feed:active { transform: scale(0.96); }
        .btn-feed:hover { opacity: 0.9; }
        .btn-cold { background: linear-gradient(135deg, #2563eb, #3b82f6); }
        .btn-comfy { background: linear-gradient(135deg, #059669, #10b981); }
        .btn-warm { background: linear-gradient(135deg, #d97706, #f59e0b); }
        .btn-sub { font-size: 10px; font-weight: normal; opacity: 0.85; }

        /* AC Control Card */
        .temp-display { font-size: 54px; font-weight: 800; color: var(--blue); text-align: center; margin: 10px 0; }
        .fan-row { display: flex; justify-content: center; gap: 6px; margin: 12px 0; flex-wrap: wrap; }
        .btn-fan { background: rgba(255,255,255,0.06); border: 1px solid var(--border); color: var(--text-muted); padding: 6px 12px; border-radius: 8px; font-size: 12px; font-weight: 600; cursor: pointer; }
        .btn-fan.active { background: var(--blue); color: white; border-color: var(--blue); }
        .btn-action { background: #334155; color: white; border: none; padding: 12px 20px; border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer; }
        .btn-action:hover { background: #475569; }
        .btn-off { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }
        .btn-off:hover { background: var(--red); color: white; }

        /* History Table */
        .history-list { font-size: 11px; color: var(--text-muted); display: flex; flex-direction: column; gap: 8px; max-height: 180px; overflow-y: auto; }
        .history-item { display: flex; justify-content: space-between; padding: 8px; background: rgba(255,255,255,0.02); border-radius: 6px; border: 1px solid rgba(255,255,255,0.04); }
        
        .toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #1e293b; border: 1px solid #3b82f6; color: white; padding: 10px 20px; border-radius: 20px; font-size: 13px; font-weight: 600; opacity: 0; pointer-events: none; transition: opacity 0.3s; box-shadow: 0 4px 15px rgba(0,0,0,0.5); z-index: 99; }
        .toast.show { opacity: 1; }
    </style>
</head>
<body>
    <div class="container">
        <!-- Card 1: Header & Live Metrics -->
        <div class="card">
            <div class="header">
                <div class="title">
                    <span>❄️ Ambi Climate Local AI</span>
                </div>
                <span id="sensorBadge" class="badge badge-live">LIVE (Port 8070)</span>
            </div>

            <div class="metrics-grid">
                <div class="metric-box">
                    <div class="metric-label">อุณหภูมิห้อง</div>
                    <div class="metric-val"><span id="roomTemp">--</span><span class="metric-unit">°C</span></div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">ความชื้น</div>
                    <div class="metric-val"><span id="roomHum">--</span><span class="metric-unit">%</span></div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">ความรู้สึกจริง (Humidex)</div>
                    <div class="metric-val" style="color: #38bdf8;"><span id="roomFeels">--</span><span class="metric-unit">°C</span></div>
                </div>
            </div>

            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding: 0 4px;">
                <span id="sensorTimeText" style="font-size: 11px; color: var(--text-muted);">อัปเดตล่าสุด: --</span>
                <button class="btn-action" style="padding: 6px 14px; font-size: 12px; background: #0284c7; display: flex; align-items: center; gap: 4px;" onclick="querySensorsNow()">
                    🔄 อ่านค่าเซนเซอร์สด (Query)
                </button>
            </div>

            <!-- Comfort Badge -->
            <div id="comfortBanner" class="comfort-banner" style="background: rgba(16, 185, 129, 0.2); color: #34d399;">
                <div id="comfortLabel" style="font-size: 16px; font-weight: 700;">กำลังประมวลผล...</div>
                <div id="comfortScore" class="comfort-score">Comfort Index: 0.0</div>
            </div>

            <!-- Auto-Tune Row -->
            <div class="autotune-row">
                <div>
                    <div style="font-size: 13px; font-weight: 700;">🤖 Local AI Auto-Tuning</div>
                    <div id="cooldownText" style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">ตรวจเช็คทุก 30 วินาที</div>
                </div>
                <label class="switch">
                    <input type="checkbox" id="autotuneToggle" onchange="toggleAutoTune(this.checked)">
                    <span class="slider"></span>
                </label>
            </div>
        </div>

        <!-- Card 2: สอน AI (Interactive Feedback) -->
        <div class="card">
            <div class="feedback-title">🎯 ตอนนี้รู้สึกอย่างไร? (แตะเพื่อสอน AI ปรับจูนความชอบ)</div>
            <div class="feedback-btns">
                <button class="btn-feed btn-cold" onclick="sendFeedback('cold')">
                    <span>🥶 หนาวไป</span>
                    <span class="btn-sub">+1°C / ลมเบาลง</span>
                </button>
                <button class="btn-feed btn-comfy" onclick="sendFeedback('comfy')">
                    <span>😊 สบายดี</span>
                    <span class="btn-sub">จำสภาพนี้เป็นเป้าหมาย</span>
                </button>
                <button class="btn-feed btn-warm" onclick="sendFeedback('warm')">
                    <span>🥵 ร้อนไป</span>
                    <span class="btn-sub">-1°C / ลมแรงขึ้น</span>
                </button>
            </div>
            <div id="offsetDesc" style="text-align: center; font-size: 11px; color: var(--text-muted); margin-top: 10px;">
                ค่าชดเชยส่วนบุคคล: 0.0°C | เป้าหมาย Humidex: 26.0°C
            </div>
        </div>

        <!-- Card 3: Daikin Remote Control -->
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span style="font-size: 14px; font-weight: 700; color: #fff;">📡 แอร์ Daikin (ARC480A46)</span>
                <span id="powerBadge" class="badge" style="background: rgba(59, 130, 246, 0.2); color: #60a5fa;">COOL</span>
            </div>

            <div class="temp-display" id="targetTemp">24°C</div>

            <div style="display: flex; justify-content: center; gap: 10px; margin-bottom: 14px;">
                <button class="btn-action" style="padding: 10px 24px;" onclick="adjustTemp(-1)">- 1°C</button>
                <button class="btn-action" style="padding: 10px 24px;" onclick="adjustTemp(+1)">+ 1°C</button>
            </div>

            <!-- Fan Speeds -->
            <div class="fan-row">
                <button class="btn-fan" id="fan-auto" onclick="setFan('Auto')">Auto</button>
                <button class="btn-fan" id="fan-quiet" onclick="setFan('Quiet')">Quiet</button>
                <button class="btn-fan" id="fan-low" onclick="setFan('Low')">Low</button>
                <button class="btn-fan" id="fan-med" onclick="setFan('med')">Med</button>
                <button class="btn-fan" id="fan-high" onclick="setFan('High')">High</button>
            </div>

            <div style="display: flex; justify-content: center; gap: 10px; margin-top: 14px;">
                <button class="btn-action" style="background: #2563eb;" onclick="setAC({power:'On', temp:24, mode:'Cool'})">Cool 24°C</button>
                <button class="btn-action btn-off" onclick="setAC({power:'Off'})">ปิดแอร์ (OFF)</button>
            </div>
        </div>

        <!-- Card 4: Recent AI Tuning History -->
        <div class="card">
            <div style="font-size: 13px; font-weight: 700; color: var(--text-muted); margin-bottom: 10px;">📜 ประวัติการปรับจูน & Feedback ล่าสุด</div>
            <div id="historyList" class="history-list">
                <div style="text-align: center; padding: 12px; color: #64748b;">ยังไม่มีข้อมูลประวัติ</div>
            </div>
        </div>

        <!-- Card 5: Ambi Cloud Target Manager (NCA / NCE / NCD) -->
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span style="font-size: 14px; font-weight: 700; color: #fff;">☁️ จัดการ Cloud Server ในตัว Ambi (NCA / NCE)</span>
                <span id="cloudStatusBadge" class="badge" style="background: rgba(168, 85, 247, 0.2); color: #c084fc;">NCA / NCE</span>
            </div>
            <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">
                Cloud ปลายทางปัจจุบัน: <b id="currentCloudTarget" style="color: #38bdf8;">กำลังตรวจสอบ...</b>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px;">
                <button class="btn-action" style="flex: 1 1 45%; background: #059669; font-size: 12px; padding: 8px 12px;" onclick="changeCloud('192.168.1.138:8867')">
                    🔄 ชี้มาเครื่องนี้ (TLS :8867)
                </button>
                <button class="btn-action" style="flex: 1 1 45%; background: #0284c7; font-size: 12px; padding: 8px 12px;" onclick="changeCloud('192.168.1.138:8866')">
                    🔄 ชี้มาเครื่องนี้ (TCP :8866)
                </button>
                <button class="btn-action" style="flex: 1 1 45%; background: #d97706; font-size: 12px; padding: 8px 12px;" onclick="reconnectCloud()">
                    ⚡ สั่ง Reconnect (NCD)
                </button>
                <button class="btn-action" style="flex: 1 1 45%; background: #475569; font-size: 12px; padding: 8px 12px;" onclick="changeCloud('connect.smartambi.com:8867')">
                    ↩️ คืนค่า Cloud ฮ่องกง
                </button>
            </div>
            <div id="cloudActionOutput" style="font-size: 11px; color: #94a3b8; margin-top: 8px; font-family: monospace;"></div>
            <div style="margin-top: 10px; border-top: 1px solid #334155; padding-top: 10px; display: flex; flex-direction: column; gap: 8px;">
                <button class="btn-action" style="width: 100%; background: #10b981; font-size: 13px; font-weight: 700; padding: 10px;" onclick="setLedGreen()">
                    🟢 สั่งไฟหน้าเครื่องเป็นสีเขียว (Solid Green)
                </button>
                <button class="btn-action" style="width: 100%; background: #4f46e5; font-size: 12px; padding: 9px;" onclick="viewSystemLog()">
                    📋 ดึงดู System Dump Log ของ Ambi (NSL)
                </button>
                <pre id="syslogModal" style="display: none; background: #090d16; padding: 12px; border-radius: 8px; max-height: 250px; overflow-y: auto; font-size: 11px; color: #38bdf8; margin-top: 8px; border: 1px solid #1e293b; white-space: pre-wrap; font-family: monospace;"></pre>
            </div>
        </div>
    </div>

    <div id="toast" class="toast">ส่งสัญญาณเรียบร้อย</div>

    <script>
        let currentState = null;

        function showToast(msg) {
            const t = document.getElementById('toast');
            t.innerText = msg;
            t.classList.add('show');
            setTimeout(() => t.classList.remove('show'), 2500);
        }

        async function updateDashboard() {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                currentState = data;

                // 1. Live Metrics
                document.getElementById('roomTemp').innerText = data.ac_state.room_temp !== null ? data.ac_state.room_temp : '--';
                document.getElementById('roomHum').innerText = data.ac_state.room_humidity !== null ? data.ac_state.room_humidity : '--';
                document.getElementById('roomFeels').innerText = data.comfort.humidex !== null ? data.comfort.humidex : '--';

                // 2. Comfort Banner
                const banner = document.getElementById('comfortBanner');
                banner.style.background = data.comfort.badge_color + '25';
                banner.style.color = data.comfort.badge_color;
                banner.style.border = '1px solid ' + data.comfort.badge_color + '55';
                document.getElementById('comfortLabel').innerText = data.comfort.label;
                document.getElementById('comfortScore').innerText = 'Comfort Index: ' + (data.comfort.score > 0 ? '+' : '') + data.comfort.score + ' | เป้าหมาย: ' + data.comfort.target_humidex + '°C';

                // 3. Auto-Tune & Cooldown (Requirement 3: Wait until AC is turned ON)
                document.getElementById('autotuneToggle').checked = data.profile.auto_tune_enabled;
                const cdSec = data.cooldown_remaining_sec;
                const cdText = document.getElementById('cooldownText');
                const isACOn = (data.ac_state.power && data.ac_state.power.toLowerCase() === 'on');

                if (!data.profile.auto_tune_enabled) {
                    cdText.innerText = '⚪ ปิดใช้งาน Auto-Tuning';
                    cdText.style.color = '#94a3b8';
                } else if (!isACOn) {
                    cdText.innerText = '⏸️ แอร์ยังปิดอยู่ (รอเปิดแอร์ก่อนเริ่ม Auto-Tuning)';
                    cdText.style.color = '#f59e0b';
                } else {
                    if (cdSec > 0) {
                        const m = Math.floor(cdSec / 60);
                        const s = cdSec % 60;
                        cdText.innerText = '⏳ พักรออุณหภูมิกระจาย (อีก ' + (m > 0 ? m + ' น. ' : '') + s + ' วิ)';
                        cdText.style.color = '#fbbf24';
                    } else {
                        cdText.innerText = '🟢 พร้อมปรับอัตโนมัติ (แอร์เปิดอยู่ - ตรวจเช็คทุก 30 วินาที)';
                        cdText.style.color = '#34d399';
                    }
                }

                document.getElementById('offsetDesc').innerText = 'ค่าชดเชยส่วนบุคคล: ' + (data.profile.user_offset > 0 ? '+' : '') + data.profile.user_offset + '°C | เป้าหมาย Humidex: ' + data.comfort.target_humidex + '°C';

                // 4. AC Controls
                const pwr = data.ac_state.power;
                document.getElementById('targetTemp').innerText = data.ac_state.temperature + '°C';
                const pwrBadge = document.getElementById('powerBadge');
                if (pwr.toLowerCase() === 'off') {
                    pwrBadge.innerText = 'OFF';
                    pwrBadge.style.background = 'rgba(239, 68, 68, 0.2)';
                    pwrBadge.style.color = '#f87171';
                } else {
                    pwrBadge.innerText = data.ac_state.mode.toUpperCase();
                    pwrBadge.style.background = 'rgba(59, 130, 246, 0.2)';
                    pwrBadge.style.color = '#60a5fa';
                }

                // Fan active buttons
                const currFan = (data.ac_state.fan || 'Auto').toLowerCase();
                document.querySelectorAll('.btn-fan').forEach(b => b.classList.remove('active'));
                if (currFan === 'auto') document.getElementById('fan-auto')?.classList.add('active');
                else if (currFan === 'quiet' || currFan === 'silent') document.getElementById('fan-quiet')?.classList.add('active');
                else if (currFan === 'low' || currFan === '1') document.getElementById('fan-low')?.classList.add('active');
                else if (currFan === 'med' || currFan === '3') document.getElementById('fan-med')?.classList.add('active');
                else if (currFan === 'high' || currFan === '5') document.getElementById('fan-high')?.classList.add('active');

                // 5. History List
                const hist = data.profile.history || [];
                const histElem = document.getElementById('historyList');
                if (hist.length > 0) {
                    histElem.innerHTML = hist.slice(0, 7).map(item => `
                        <div class="history-item">
                            <div>
                                <span style="font-weight: 600; color: #fff;">${item.action}</span>
                                <div style="font-size: 10px; color: #64748b;">${item.temp}°C | ลม: ${item.fan} | แอร์: ${item.power} | ห้อง: ${item.room_temp || '--'}°C (${item.room_humidity || '--'}%)</div>
                            </div>
                            <div style="text-align: right;">
                                <span style="color: #38bdf8;">${item.time}</span>
                                <div style="font-size: 9px; color: ${item.result && item.result.includes('OK') ? '#34d399' : '#94a3b8'};">${item.result || ''}</div>
                            </div>
                        </div>
                    `).join('');
                }
            } catch (e) {
                console.error("Dashboard poll error:", e);
            }
        }

        async function sendFeedback(choice) {
            showToast('⏳ กำลังสอน AI & ปรับแอร์...');
            try {
                const res = await fetch('/api/feedback?choice=' + encodeURIComponent(choice));
                const json = await res.json();
                showToast('✅ ' + (json.action || 'บันทึกสำเร็จ'));
                updateDashboard();
            } catch (e) {
                showToast('❌ เกิดข้อผิดพลาด');
            }
        }

        async function toggleAutoTune(enabled) {
            try {
                await fetch('/api/autotune?enable=' + enabled);
                showToast(enabled ? '✅ เปิด Auto-Tuning' : '⚪ ปิด Auto-Tuning');
                updateDashboard();
            } catch (e) {}
        }

        async function adjustTemp(delta) {
            if (!currentState) return;
            const newT = currentState.ac_state.temperature + delta;
            await setAC({temp: newT});
        }

        async function setFan(fan) {
            await setAC({fan: fan});
        }

        async function setAC(params) {
            showToast('📡 กำลังยิงสัญญาณ IR...');
            const q = new URLSearchParams(params).toString();
            try {
                const res = await fetch('/api/control?' + q);
                const json = await res.json();
                showToast('✅ สั่งงาน Daikin สำเร็จ: ' + (json.ir_result || 'OK'));
                updateDashboard();
            } catch (e) {
                showToast('❌ ส่งสัญญาณไม่สำเร็จ');
            }
        }

        async function fetchCloudStatus() {
            try {
                const res = await fetch('/api/cloud/status');
                const json = await res.json();
                document.getElementById('currentCloudTarget').innerText = json.cloud_server || 'ไม่สามารถติดต่อได้';
            } catch (e) {
                document.getElementById('currentCloudTarget').innerText = 'Error';
            }
        }

        async function changeCloud(server) {
            showToast('🚀 กำลังยิงคำสั่งเปลี่ยน Cloud Server...');
            document.getElementById('cloudActionOutput').innerText = 'กำลังส่ง NCE' + server + ' และ NCD...';
            try {
                const res = await fetch('/api/cloud/change?server=' + encodeURIComponent(server));
                const json = await res.json();
                showToast('✅ สั่งเปลี่ยน Cloud เรียบร้อย: ' + server);
                document.getElementById('cloudActionOutput').innerText = 'ผลลัพธ์ NCE: ' + json.response_ce + ' | NCD: ' + json.response_cd;
                fetchCloudStatus();
            } catch (e) {
                showToast('❌ ไม่สามารถเปลี่ยน Cloud ได้');
                document.getElementById('cloudActionOutput').innerText = 'เกิดข้อผิดพลาดในการส่งคำสั่ง';
            }
        }

        async function reconnectCloud() {
            showToast('⚡ กำลังสั่ง Ambi ตัดและต่อใหม่ (NCD)...');
            try {
                const res = await fetch('/api/cloud/reconnect');
                const json = await res.json();
                showToast('✅ สั่ง NCD สำเร็จ');
                document.getElementById('cloudActionOutput').innerText = 'ผลลัพธ์ NCD: ' + json.response;
            } catch (e) {
                showToast('❌ ไม่สามารถส่ง NCD ได้');
            }
        }

        async function viewSystemLog() {
            showToast('⏳ กำลังดึง System Dump Log จาก Ambi...');
            const box = document.getElementById('syslogModal');
            box.style.display = 'block';
            box.innerText = 'กำลังส่งคำสั่ง NSL ไปที่ Ambi:8070... กรุณารอสักครู่';
            try {
                const res = await fetch('/api/system_log');
                const text = await res.text();
                box.innerText = text || 'ไม่มีข้อมูล Log ตอบกลับมา';
                showToast('✅ ดึง System Dump Log สำเร็จ');
            } catch (e) {
                box.innerText = 'เกิดข้อผิดพลาดในการดึง Log: ' + e;
                showToast('❌ ไม่สามารถดึง System Log ได้');
            }
        }

        async function setLedGreen() {
            showToast('🟢 กำลังส่งคำสั่งไฟสีเขียวไปที่ Ambi...');
            try {
                const res = await fetch('/api/led/green');
                const json = await res.json();
                if (json.status === 'OK') {
                    showToast('✅ สั่งไฟหน้าเครื่องเป็นสีเขียวแล้ว!');
                } else {
                    showToast('❌ ยังไม่ได้ IP หรือส่งคำสั่งไม่สำเร็จ');
                }
            } catch (e) {
                showToast('❌ เกิดข้อผิดพลาดในการเชื่อมต่อ');
            }
        }

        updateDashboard();
        fetchCloudStatus();
        setInterval(updateDashboard, 3000);
        setInterval(fetchCloudStatus, 15000);
    </script>
</body>
</html>
"""

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class AmbiAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        msg = format % args
        if "Bad request version" in msg or "code 400" in msg:
            return
        hub_log(f"[HTTP/S :{self.server.server_port}] {self.address_string()} - {msg}")

    def log_error(self, format, *args):
        msg = format % args
        if "Bad request version" in msg or "code 400" in msg:
            return
        hub_log(f"[-] HTTP Error :{self.server.server_port} - {msg}")

    def handle_one_request(self):
        try:
            peek = self.connection.recv(1, socket.MSG_PEEK)
            if peek and peek[0] == 0x16:
                self.close_connection = True
                return
        except Exception:
            pass
        super().handle_one_request()

    def do_GET(self):
        AC_STATE["last_seen"] = time.strftime('%H:%M:%S')
        hub_log(f"[GET :{self.server.server_port}] from {self.client_address[0]} Path: {self.path}")

        if (self.server.server_port in (DASHBOARD_PORT, 9090, 8080)) and (self.path == '/' or self.path.startswith('/api')):
            self.handle_web_ui()
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()

        response = {
            "status": "OK",
            "data": {
                "device_id": REAL_DEVICE_ID,
                "uuid": DEVICE_UUID,
                "mac": MAC_ADDRESS,
                "online": True,
                "room_name": DEVICE["ZROOM_NAME"],
                "appliance": {
                    "id": APPLIANCE["ZID"],
                    "manufacturer": APPLIANCE["ZMANUFACTURER"],
                    "irp_id": IRP_ID,
                    "type": APPLIANCE["ZTYPE"],
                    "state": AC_STATE
                }
            }
        }
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def do_POST(self):
        AC_STATE["last_seen"] = time.strftime('%H:%M:%S')
        if (self.server.server_port in (DASHBOARD_PORT, 9090, 8080)) and self.path.startswith('/api'):
            self.handle_web_ui()
            return
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8', errors='ignore') if length > 0 else ""
        hub_log(f"[POST :{self.server.server_port}] from {self.client_address[0]} Path: {self.path} Body: {body}")

        try:
            if body:
                data = json.loads(body)
                updated = False
                if "temperature" in data:
                    AC_STATE["room_temp"] = float(data["temperature"])
                    updated = True
                if "humidity" in data:
                    AC_STATE["room_humidity"] = float(data["humidity"])
                    updated = True
                if updated:
                    AC_STATE["sensor_status"] = f"PUSH (HTTP POST :{self.server.server_port})"
                    AC_STATE["sensor_time"] = time.strftime('%H:%M:%S')
                    c = evaluate_comfort(AC_STATE.get("room_temp", 25.0), AC_STATE.get("room_humidity", 50.0))
                    AC_STATE["humidex"] = c["humidex"]
                    AC_STATE["comfort_score"] = c["score"]
                    AC_STATE["comfort_label"] = c["label"]
                    AC_STATE["comfort_badge_color"] = c["badge_color"]
                    hub_log(f"[PUSH SENSOR HTTP] 📥 Temp: {AC_STATE['room_temp']}°C | Hum: {AC_STATE['room_humidity']}% | Humidex: {c['humidex']}°C")
        except Exception:
            pass

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()

        response = {"status": "OK", "message": "Success"}
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def do_PUT(self):
        self.do_POST()

    def handle_web_ui(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # 1. State API
        if path == '/api/state':
            room_t = AC_STATE.get("room_temp")
            room_rh = AC_STATE.get("room_humidity")
            comfort = evaluate_comfort(room_t, room_rh)

            now = time.time()
            cooldown_sec = COMFORT_PROFILE.get("cooldown_minutes", 10) * 60
            last_tune = COMFORT_PROFILE.get("last_tune_time", 0)
            remaining_cooldown = max(0, int(cooldown_sec - (now - last_tune)))

            data = {
                "status": "OK",
                "device_ip": get_ambi_ip(),
                "network": {
                    "host_ip": HOST_IP,
                    "gateway_ip": ROUTER_GATEWAY_IP,
                    "wan_ip": ROUTER_WAN_IP,
                    "dns_redirect_ip": DNS_REDIRECT_IP,
                    "ambi_ip": get_ambi_ip()
                },
                "ac_state": AC_STATE,
                "comfort": comfort,
                "profile": {
                    "auto_tune_enabled": COMFORT_PROFILE.get("auto_tune_enabled", True),
                    "target_base_humidex": COMFORT_PROFILE.get("target_base_humidex", 26.0),
                    "user_offset": COMFORT_PROFILE.get("user_offset", 0.0),
                    "min_temp": COMFORT_PROFILE.get("min_temp", 22),
                    "max_temp": COMFORT_PROFILE.get("max_temp", 27),
                    "cooldown_minutes": COMFORT_PROFILE.get("cooldown_minutes", 10),
                    "last_tune_action": COMFORT_PROFILE.get("last_tune_action", ""),
                    "history": COMFORT_PROFILE.get("history", [])[:10]
                },
                "cooldown_remaining_sec": remaining_cooldown
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode('utf-8'))
            return

        # 2. Control API
        if path == '/api/control':
            t = query.get('temp', [None])[0]
            f = query.get('fan', [None])[0]
            p = query.get('power', [None])[0]
            m = query.get('mode', [None])[0]
            resp = send_daikin_ir(temp=t, fan=f, power=p, mode=m, reason="Web UI Manual Control")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK", "ac_state": AC_STATE, "ir_result": resp}).encode('utf-8'))
            return

        # 3. Feedback API (User Teaching AI)
        if path == '/api/feedback':
            choice = query.get('choice', [''])[0].lower()
            curr_offset = COMFORT_PROFILE.get("user_offset", 0.0)
            action_desc = ""

            if choice == 'cold':
                new_offset = round(curr_offset + 0.5, 2)
                COMFORT_PROFILE["user_offset"] = new_offset
                curr_t = AC_STATE.get("temperature", 24)
                max_t = COMFORT_PROFILE.get("max_temp", 27)
                new_t = min(max_t, curr_t + 1)
                new_fan = "Low" if AC_STATE.get("fan") == "High" else AC_STATE.get("fan")
                action_desc = f"Feedback: หนาวไป -> ปรับ {new_t}°C (ชดเชย +{new_offset}°C)"
                send_daikin_ir(temp=new_t, fan=new_fan, reason=action_desc)
                COMFORT_PROFILE["last_tune_time"] = time.time()
                COMFORT_PROFILE["last_tune_action"] = action_desc
                save_comfort_profile(COMFORT_PROFILE)

            elif choice == 'warm':
                new_offset = round(curr_offset - 0.5, 2)
                COMFORT_PROFILE["user_offset"] = new_offset
                curr_t = AC_STATE.get("temperature", 24)
                min_t = COMFORT_PROFILE.get("min_temp", 22)
                new_t = max(min_t, curr_t - 1)
                new_fan = "High" if AC_STATE.get("fan") in ("Quiet", "Low") else AC_STATE.get("fan")
                action_desc = f"Feedback: ร้อนไป -> ปรับ {new_t}°C (ชดเชย {new_offset}°C)"
                send_daikin_ir(temp=new_t, fan=new_fan, reason=action_desc)
                COMFORT_PROFILE["last_tune_time"] = time.time()
                COMFORT_PROFILE["last_tune_action"] = action_desc
                save_comfort_profile(COMFORT_PROFILE)

            elif choice == 'comfy':
                room_t = AC_STATE.get("room_temp") or 25.0
                room_rh = AC_STATE.get("room_humidity") or 50.0
                curr_hx = calculate_humidex(room_t, room_rh) or 26.0
                base = COMFORT_PROFILE.get("target_base_humidex", 26.0)
                new_offset = round(curr_hx - base, 2)
                COMFORT_PROFILE["user_offset"] = new_offset
                action_desc = f"Feedback: บันทึกความสบายเป้าหมายที่ {curr_hx}°C (ชดเชย {new_offset}°C)"
                COMFORT_PROFILE["last_tune_time"] = time.time()
                COMFORT_PROFILE["last_tune_action"] = action_desc
                entry = {
                    "time": time.strftime('%H:%M:%S'),
                    "action": action_desc,
                    "temp": AC_STATE['temperature'],
                    "fan": AC_STATE['fan'],
                    "power": AC_STATE['power'],
                    "room_temp": room_t,
                    "room_humidity": room_rh,
                    "result": "Comfort Target Calibrated"
                }
                history = COMFORT_PROFILE.get("history", [])
                history.insert(0, entry)
                COMFORT_PROFILE["history"] = history[:25]
                save_comfort_profile(COMFORT_PROFILE)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "OK",
                "choice": choice,
                "action": action_desc,
                "user_offset": COMFORT_PROFILE.get("user_offset", 0.0),
                "ac_state": AC_STATE
            }).encode('utf-8'))
            return

        # 4. AutoTune Toggle API
        if path == '/api/autotune':
            en_val = query.get('enable', [''])[0].lower()
            if en_val in ('1', 'true', 'on'):
                COMFORT_PROFILE["auto_tune_enabled"] = True
            elif en_val in ('0', 'false', 'off'):
                COMFORT_PROFILE["auto_tune_enabled"] = False
            save_comfort_profile(COMFORT_PROFILE)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "OK",
                "auto_tune_enabled": COMFORT_PROFILE["auto_tune_enabled"]
            }).encode('utf-8'))
            return

        # 4.1 Mode Selection API (Comfort, Temperature, Manual, Away, Off - Ambi User Guide)
        if path == '/api/mode':
            m = query.get('mode', ['Comfort'])[0]
            m_cap = m.capitalize()
            if m_cap not in ('Comfort', 'Temperature', 'Manual', 'Away', 'Off'):
                m_cap = 'Comfort'
            AC_STATE['ambi_mode'] = m_cap
            if m_cap == 'Off':
                AC_STATE['power'] = 'Off'
                send_daikin_ir(power='Off', reason="Mode Change: OFF")
            elif m_cap == 'Comfort':
                AC_STATE['power'] = 'On'
                COMFORT_PROFILE["auto_tune_enabled"] = True
                save_comfort_profile(COMFORT_PROFILE)
                send_daikin_ir(power='On', reason="Mode Change: Comfort Mode")
            elif m_cap == 'Temperature':
                AC_STATE['power'] = 'On'
                COMFORT_PROFILE["auto_tune_enabled"] = False
                save_comfort_profile(COMFORT_PROFILE)
                send_daikin_ir(power='On', reason="Mode Change: Temperature Mode")
            elif m_cap == 'Manual':
                AC_STATE['power'] = 'On'
                COMFORT_PROFILE["auto_tune_enabled"] = False
                save_comfort_profile(COMFORT_PROFILE)
                send_daikin_ir(power='On', reason="Mode Change: Manual Mode")
            elif m_cap == 'Away':
                AC_STATE['power'] = 'Off'
                send_daikin_ir(power='Off', reason="Mode Change: Away Mode")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK", "ambi_mode": m_cap, "ac_state": AC_STATE}).encode('utf-8'))
            return

        # 5. Cloud Status API
        if path == '/api/cloud/status':
            curr = get_cloud_server_setting()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK", "device_ip": get_ambi_ip(), "cloud_server": curr}).encode('utf-8'))
            return

        # 6. Cloud Change API
        if path == '/api/cloud/change':
            srv = query.get('server', [f"{HOST_IP}:8867"])[0]
            res = change_cloud_server(srv)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(res).encode('utf-8'))
            return

        # 7. Cloud Reconnect API
        if path == '/api/cloud/reconnect':
            res = send_ambi_cmd("NCD")
            res_str = res.decode('latin1', errors='ignore').strip() if res else "None"
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK", "device_ip": get_ambi_ip(), "response": res_str}).encode('utf-8'))
            return

        # 8. Ambi System Dump Log API (NSL)
        if path == '/api/system_log':
            log_text = fetch_ambi_system_log()
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(log_text.encode('utf-8'))
            return

        # 9. Set LED Green API
        if path == '/api/led/green':
            ok = set_ambi_led_green()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK" if ok else "Error", "device_ip": get_ambi_ip()}).encode('utf-8'))
            return

        # 10. Manual Sensor Refresh / Query API (On-Demand)
        if path in ('/api/sensors/query', '/api/sensors/refresh'):
            res = query_live_sensors()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(res).encode('utf-8'))
            return

        # 10.1 Sensor Polling Status / Toggle API
        if path == '/api/sensors/polling':
            global POLL_SENSORS_ENABLED
            en = query.get('enable', [None])[0]
            if en is not None:
                POLL_SENSORS_ENABLED = str(en).lower() in ('1', 'true', 'on')
                hub_log(f"[*] Sensor Polling updated: enabled={POLL_SENSORS_ENABLED}")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "OK",
                "polling_enabled": POLL_SENSORS_ENABLED,
                "interval_sec": 20,
                "sensor_status": AC_STATE.get("sensor_status"),
                "sensor_time": AC_STATE.get("sensor_time")
            }).encode('utf-8'))
            return

        # 10.2 Auto Network Refresh / Detect API
        if path == '/api/network/detect':
            refresh_network_settings()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "OK",
                "network": {
                    "host_ip": HOST_IP,
                    "gateway_ip": ROUTER_GATEWAY_IP,
                    "wan_ip": ROUTER_WAN_IP,
                    "dns_redirect_ip": DNS_REDIRECT_IP,
                    "ambi_ip": get_ambi_ip()
                }
            }).encode('utf-8'))
            return

        # 11. Set LED Brightness API (0 = OFF, 1-10000 = PWM brightness)
        if path == '/api/led/brightness':
            try:
                lvl = int(query.get('level', ['5700'])[0])
            except (ValueError, TypeError):
                lvl = 5700
            ok = set_ambi_led_brightness(lvl)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK" if ok else "Error", "level": lvl, "device_ip": get_ambi_ip()}).encode('utf-8'))
            return

        # 12. Serve HTML Dashboard
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        html_page = get_dashboard_html()
        self.wfile.write(html_page.encode('utf-8'))

# DNS Server Domain Configuration
AMBI_SPECIFIC_DOMAINS = [
    'ambiclimate.com',     # connect.ambiclimate.com, api.ambiclimate.com, ota.ambiclimate.com
    'smartambi.com',       # connect.smartambi.com, api.smartambi.com
    'ambiapis.com',        # api.ambiapis.com
    'tryambi.com',         # tryambi.com
    'tryambiapis.com',     # tryambiapis.com
    'globalcache.com',     # iTach WF2IR
]

AMBI_SHARED_DOMAINS = [
    'amazonaws.com',       # AWS IoT, API Gateway (redirect ONLY for Ambi)
    'cloudfront.net',      # CloudFront CDN (redirect ONLY for Ambi)
]

def parse_dns_domain(data):
    """Parses domain name and query type from raw DNS packet."""
    if len(data) < 12:
        return None, None
    qdcount = struct.unpack('>H', data[4:6])[0]
    if qdcount == 0:
        return None, None
    pos = 12
    domain_parts = []
    while pos < len(data):
        length = data[pos]
        if length == 0:
            pos += 1
            break
        if (length & 0xc0) == 0xc0:
            pos += 2
            break
        pos += 1
        if pos + length > len(data):
            return None, None
        domain_parts.append(data[pos:pos+length].decode('latin1', errors='ignore'))
        pos += length
    domain = '.'.join(domain_parts).lower()
    if pos + 4 > len(data):
        return None, None
    qtype, _ = struct.unpack('>HH', data[pos:pos+4])
    return domain, qtype

def make_dns_redirect_response(data, redirect_ip):
    """Constructs RFC 1035 DNS response redirecting A queries to redirect_ip."""
    if len(data) < 12:
        return None
    tid = data[:2]
    flags_in = struct.unpack('>H', data[2:4])[0]
    qdcount = struct.unpack('>H', data[4:6])[0]
    arcount_in = struct.unpack('>H', data[10:12])[0]
    if qdcount == 0:
        return None

    pos = 12
    while pos < len(data):
        length = data[pos]
        if length == 0:
            pos += 1
            break
        if (length & 0xc0) == 0xc0:
            pos += 2
            break
        pos += 1
        pos += length

    if pos + 4 > len(data):
        return None

    qtype, _ = struct.unpack('>HH', data[pos:pos+4])
    pos += 4
    question_raw = data[12:pos]

    rd = flags_in & 0x0100
    resp_flags = 0x8400 | rd | 0x0080
    has_edns = (arcount_in > 0)
    resp_arcount = 1 if has_edns else 0

    if qtype in (1, 255):  # A (IPv4) or ANY
        header = tid + struct.pack('>HHHHH', resp_flags, 1, 1, 0, resp_arcount)
        ans = b'\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04' + socket.inet_aton(redirect_ip)
    else:  # AAAA (IPv6) or others -> NOERROR with 0 answer
        header = tid + struct.pack('>HHHHH', resp_flags, 1, 0, 0, resp_arcount)
        ans = b''

    opt_rr = b'\x00\x00\x29\x10\x00\x00\x00\x00\x00\x00\x00' if has_edns else b''
    return header + question_raw + ans + opt_rr

def forward_dns_upstream(sock, data, addr, timeout=2.0):
    """Silently forwards DNS packet to 8.8.8.8 without logging."""
    try:
        up = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        up.settimeout(timeout)
        up.sendto(data, ('8.8.8.8', 53))
        r, _ = up.recvfrom(2048)
        up.close()
        sock.sendto(r, addr)
    except Exception:
        pass

def run_dns():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass

    bound = False
    for bind_ip in [HOST_IP, '0.0.0.0']:
        try:
            sock.bind((bind_ip, 53))
            hub_log(f"[+] DNS SERVER running on UDP {bind_ip}:53 (Targeting Ambi Climate Only)")
            bound = True
            break
        except Exception:
            continue

    if not bound:
        hub_log("[-] DNS bind failed on port 53.")
        return

    while True:
        try:
            data, addr = sock.recvfrom(2048)
            client_ip = addr[0]

            domain, qtype = parse_dns_domain(data)
            if not domain:
                continue

            # Requirement 1: Check for Ambi domain queries (e.g. connect.smartambi.com, connect.ambiclimate.com)
            is_ambi_domain = any(domain.endswith(t) for t in ("smartambi.com", "ambiclimate.com", "tryambi.com", "ambiapis.com", "tryambiapis.com"))

            if is_ambi_domain and client_ip not in (HOST_IP, ROUTER_GATEWAY_IP, "127.0.0.1"):
                global AMBI_IP, AMBI_AUTO_RETARGETED
                if AMBI_IP != client_ip:
                    AMBI_IP = client_ip
                    save_ambi_ip(client_ip)
                    hub_log(f"\n{'='*70}")
                    hub_log(f"🎯 [STEP 1: CAPTURED AMBI IP FROM DNS]")
                    hub_log(f"   Received Query : '{domain}' (qtype={qtype})")
                    hub_log(f"   Device IP      : {client_ip}")
                    hub_log(f"   -> Locked Ambi IP into memory: {AMBI_IP}")
                    hub_log(f"{'='*70}\n")
                    # Turn Green LED immediately upon acquiring Ambi IP!
                    threading.Thread(target=set_ambi_led_green, args=(client_ip,), daemon=True).start()

                # Send DNS redirect to DNS_REDIRECT_IP (ROUTER_WAN_IP) to bypass OpenWrt DNS-Rebind protection
                resp = make_dns_redirect_response(data, DNS_REDIRECT_IP)
                if resp:
                    hub_log(f"[DNS REDIRECT 🎯] {domain} (qtype={qtype}) from Ambi ({client_ip}) -> {DNS_REDIRECT_IP}")
                    sock.sendto(resp, addr)

                # Requirement 2: Automatically shoot NCE to set Cloud Server to our IP & maintain Green LED
                def auto_set_cloud_worker(target_ip):
                    time.sleep(0.6)  # Allow DNS response to complete
                    set_ambi_led_green(target_ip)  # Ensure Solid Green
                    hub_log(f"\n{'='*70}")
                    hub_log(f"🚀 [STEP 2: AUTO-SET CLOUD SERVER TO LOCAL IP]")
                    hub_log(f"   Target Ambi IP : {target_ip}")
                    hub_log(f"   Target Server  : {HOST_IP}:8867")
                    hub_log(f"{'='*70}")
                    res = change_cloud_server(f"{HOST_IP}:8867", target_ip=target_ip)
                    hub_log(f"✅ Cloud URL configured on Ambi ({target_ip})!")
                    hub_log(f"   NCE Status: {res.get('response_ce')} | NCD Status: {res.get('response_cd')}")
                    hub_log(f"   Ambi will now reconnect to local server on port 8867.\n")
                    time.sleep(0.5)
                    set_ambi_led_green(target_ip)  # Re-affirm Green after NCD
                    AMBI_READY_EVENT.set()

                if not AMBI_AUTO_RETARGETED:
                    AMBI_AUTO_RETARGETED = True
                    threading.Thread(target=auto_set_cloud_worker, args=(client_ip,), daemon=True).start()
                continue

            # Check if query is from the locked Ambi IP
            ambi_current = get_ambi_ip()
            is_from_ambi = (client_ip == ambi_current and ambi_current is not None)

            # Check domain types
            is_ambi_exclusive = any(domain.endswith(t) for t in AMBI_SPECIFIC_DOMAINS)
            is_ambi_shared = any(domain.endswith(t) for t in AMBI_SHARED_DOMAINS)

            # Case A: Query comes from Ambi Climate device ONLY
            if is_from_ambi:
                if is_ambi_exclusive or is_ambi_shared:
                    resp = make_dns_redirect_response(data, DNS_REDIRECT_IP)
                    if resp:
                        hub_log(f"[DNS REDIRECT 🎯] {domain} (qtype={qtype}) from Ambi ({client_ip}) -> {DNS_REDIRECT_IP}")
                        sock.sendto(resp, addr)
                else:
                    # Ambi device asking for external domain (e.g. NTP pool.ntp.org)
                    hub_log(f"[DNS FORWARD 🌐] {domain} (qtype={qtype}) from Ambi ({client_ip}) -> Forwarded to 8.8.8.8")
                    forward_dns_upstream(sock, data, addr)

            # Case B: Query is from OTHER machines in the network (PC, Phone, Smart TV)
            else:
                # Silently forward to 8.8.8.8 without logging, intercepting, or polluting Ambi state
                forward_dns_upstream(sock, data, addr)

        except Exception:
            pass

def run_https(port):
    try:
        server = ThreadedHTTPServer(('0.0.0.0', port), AmbiAPIHandler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        print(f"[+] HTTPS Server running on port {port}")
        server.serve_forever()
    except Exception as e:
        print(f"[-] HTTPS port {port} error: {e}")

def run_http(port):
    try:
        server = ThreadedHTTPServer(('0.0.0.0', port), AmbiAPIHandler)
        print(f"[+] HTTP Server running on port {port}")
        server.serve_forever()
    except Exception as e:
        print(f"[-] HTTP port {port} error: {e}")

def run_cloud_mock(port):
    """
    Dedicated Cloud Mock Server on TCP (8866 & 8867) for Ambi Climate:
      - Port 8866: connect.ambiclimate.com (Plain TCP Native Framing)
      - Port 8867: connect.smartambi.com / connect.ambiclimate.com (TLS 1.2 Encrypted)
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', port))
        s.listen(5)
        hub_log(f"[+] CLOUD MOCK SERVER listening on TCP 0.0.0.0:{port}")

        ssl_ctx = None
        if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
            try:
                ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ssl_ctx.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
                hub_log(f"[+] Loaded SSL Certificate for Cloud Mock Port {port}")
            except Exception as e:
                hub_log(f"[-] Could not load SSL context for :{port}: {e}")

        while True:
            conn, addr = s.accept()
            update_ambi_ip(addr[0], source=f"Cloud TCP :{port}")
            hub_log(f"\n[🎉 AMBI CLIMATE CONNECTED TO CLOUD PORT {port}! from {addr[0]}:{addr[1]}]")

            def handle_client(c, a, p, ctx):
                c.settimeout(180.0)
                active_sock = c
                try:
                    # Peek to see if client initiates TLS handshake (0x16 0x03)
                    try:
                        peek = c.recv(16, socket.MSG_PEEK)
                        is_tls = len(peek) >= 3 and peek[0] == 0x16 and peek[1] == 0x03
                    except Exception:
                        is_tls = False

                    if is_tls and ctx:
                        hub_log(f"  [Cloud :{p}] 🔐 TLS Client Hello detected -> Handshaking...")
                        active_sock = ctx.wrap_socket(c, server_side=True)
                        cipher = active_sock.cipher()
                        hub_log(f"  [Cloud :{p}] ✅ TLS Handshake Established! Cipher: {cipher}")

                    while True:
                        data = active_sock.recv(4096)
                        if not data:
                            hub_log(f"  [Cloud :{p}] Connection closed by client {a[0]}")
                            break

                        # Detailed Ambi Traffic Monitor
                        hex_preview = data.hex()
                        printable = ''.join(chr(b) if 32 <= b <= 126 else f'\\x{b:02x}' for b in data)
                        if len(data) <= 300:
                            hub_log(f"  [📡 AMBI TRAFFIC :{p}] 📥 RECV ({len(data)}B) ASCII: {printable} | HEX: {hex_preview}")
                        else:
                            hub_log(f"  [📡 AMBI TRAFFIC :{p}] 📥 RECV Large Payload ({len(data)} bytes - Log/Telemetry dump)")
                            try:
                                dump_file = os.path.join(DIR, "cloud_dump.log")
                                with open(dump_file, "a", encoding="utf-8", errors="ignore") as df:
                                    df.write(f"\n--- [{time.strftime('%Y-%m-%d %H:%M:%S')}] Port {p} From {a[0]} ({len(data)} bytes) ---\n")
                                    df.write(data.decode('latin1', errors='ignore'))
                                    df.write("\n")
                            except Exception:
                                pass

                        # If Ambi framed protocol starting with \x07
                        if data and data[0] == 0x07 and len(data) >= 3:
                            seq = data[1:3]
                            cmd = data[3:6].decode('latin1', errors='ignore') if len(data) >= 6 else ""
                            seq_str = seq.decode('latin1', errors='ignore')
                            hub_log(f"  [Cloud :{p}] ⚙️ Ambi Native Frame: Seq={seq_str} Cmd={cmd}")

                            # Standard Ambi Protocol Response:
                            # Responses echo the command with Status Code '0' (OK) and optional payload
                            # Format: \x07 + [seq] + '0' + [cmd] + '0\r\n'
                            proto_resp = b"\x07" + seq + b"0" + cmd.encode('ascii') + b"0\r\n"
                            active_sock.sendall(proto_resp)
                            proto_asc = ''.join(chr(b) if 32 <= b <= 126 else f'\\x{b:02x}' for b in proto_resp)
                            hub_log(f"  [📡 AMBI TRAFFIC :{p}] 📤 SEND ({len(proto_resp)}B) ASCII: {proto_asc}")

                            # Command-specific extensions
                            if cmd == "NPS":
                                time.sleep(0.05)
                                nps_resp = b"\x07" + seq + b"0NPS1\r\n"
                                active_sock.sendall(nps_resp)
                                hub_log(f"  [📡 AMBI TRAFFIC :{p}] 📤 SEND NPS Paired (1)")
                            elif cmd == "NCO":
                                time.sleep(0.05)
                                nco_resp = b"\x07" + seq + b"0NCO0\r\n"
                                active_sock.sendall(nco_resp)
                                hub_log(f"  [📡 AMBI TRAFFIC :{p}] 📤 SEND NCO Connected (0)")
                            elif cmd == "NHS":
                                time.sleep(0.05)
                                nhs_resp = b"\x07" + seq + b"0NHS0\r\n"
                                active_sock.sendall(nhs_resp)
                                hub_log(f"  [📡 AMBI TRAFFIC :{p}] 📤 SEND NHS Handshake OK (0)")
                            elif cmd == "NID":
                                time.sleep(0.05)
                                nid_resp = b"\x07" + seq + b"0NID0\r\n"
                                active_sock.sendall(nid_resp)
                                hub_log(f"  [📡 AMBI TRAFFIC :{p}] 📤 SEND NID Response (0)")
                            elif cmd == "NSL":
                                time.sleep(0.05)
                                nsl_resp = b"\x07" + seq + b"0NSL0\r\n"
                                active_sock.sendall(nsl_resp)
                                hub_log(f"  [📡 AMBI TRAFFIC :{p}] 📤 SEND NSL ACK (0)")
                            elif cmd == "NTP":
                                payload = data[6:].decode('latin1', errors='ignore').strip('\r\n') if len(data) > 6 else ""
                                if payload:
                                    from test_daikin import parse_sensor_value
                                    val, _ = parse_sensor_value(payload)
                                    if val is not None:
                                        AC_STATE["room_temp"] = val
                                        AC_STATE["sensor_status"] = f"PUSH (Cloud :{p})"
                                        AC_STATE["sensor_time"] = time.strftime('%H:%M:%S')
                                        if AC_STATE.get("room_temp") is not None and AC_STATE.get("room_humidity") is not None:
                                            c = evaluate_comfort(AC_STATE["room_temp"], AC_STATE["room_humidity"])
                                            AC_STATE["humidex"] = c["humidex"]
                                            AC_STATE["comfort_score"] = c["score"]
                                            AC_STATE["comfort_label"] = c["label"]
                                            AC_STATE["comfort_badge_color"] = c["badge_color"]
                                        hub_log(f"  [📡 AMBI SENSOR PUSH] 🌡️ Temperature: {val}°C (Port {p})")
                            elif cmd == "NHM":
                                payload = data[6:].decode('latin1', errors='ignore').strip('\r\n') if len(data) > 6 else ""
                                if payload:
                                    from test_daikin import parse_sensor_value
                                    val, _ = parse_sensor_value(payload)
                                    if val is not None:
                                        AC_STATE["room_humidity"] = val
                                        AC_STATE["sensor_status"] = f"PUSH (Cloud :{p})"
                                        AC_STATE["sensor_time"] = time.strftime('%H:%M:%S')
                                        if AC_STATE.get("room_temp") is not None and AC_STATE.get("room_humidity") is not None:
                                            c = evaluate_comfort(AC_STATE["room_temp"], AC_STATE["room_humidity"])
                                            AC_STATE["humidex"] = c["humidex"]
                                            AC_STATE["comfort_score"] = c["score"]
                                            AC_STATE["comfort_label"] = c["label"]
                                            AC_STATE["comfort_badge_color"] = c["badge_color"]
                                        hub_log(f"  [📡 AMBI SENSOR PUSH] 💧 Humidity: {val}% (Port {p})")
                        else:
                            # Generic HTTP or raw response if needed
                            if b"HTTP" in data or b"GET" in data or b"POST" in data:
                                resp = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: keep-alive\r\nContent-Length: 15\r\n\r\n{\"status\":\"OK\"}"
                                active_sock.sendall(resp)
                                hub_log(f"  [Cloud :{p}] 📤 Sent HTTP 200 OK")
                except Exception as e:
                    hub_log(f"  [Cloud :{p}] Notice: {e}")
                finally:
                    try:
                        active_sock.close()
                    except Exception:
                        pass
            threading.Thread(target=handle_client, args=(conn, addr, port, ssl_ctx), daemon=True).start()
    except Exception as e:
        hub_log(f"[-] Cloud :{port} Server Error: {e}")

if __name__ == '__main__':
    refresh_network_settings()
    hub_log("=" * 68)
    hub_log("  Ambi Climate All-in-One Local Hub & Comfort AI")
    hub_log(f"  Auto-Detected Host IP    : {HOST_IP}")
    hub_log(f"  Auto-Detected Gateway IP : {ROUTER_GATEWAY_IP}")
    hub_log(f"  Auto-Detected Router WAN : {ROUTER_WAN_IP}")
    hub_log(f"  DNS Redirect Target IP   : {DNS_REDIRECT_IP}")
    hub_log(f"  Ambi Device IP (Locked)  : {AMBI_IP or 'Waiting for connect query...'}")
    hub_log(f"  Cloud Ports              : TCP 8866 (Plain) & TCP 8867 (TLS 1.2)")
    hub_log(f"  Dashboard Web            : http://localhost:{DASHBOARD_PORT} (or http://{HOST_IP}:{DASHBOARD_PORT})")
    hub_log("=" * 68)

    # 1. DNS Server (Port 53 UDP) - Targets & query monitors
    threading.Thread(target=run_dns, daemon=True).start()

    # 2. Dedicated Cloud Mock Servers (8866 & 8867)
    threading.Thread(target=run_cloud_mock, args=(8866,), daemon=True).start()
    threading.Thread(target=run_cloud_mock, args=(8867,), daemon=True).start()

    # 3. HTTP (80) & HTTPS (443) Servers
    threading.Thread(target=run_http, args=(80,), daemon=True).start()
    threading.Thread(target=run_https, args=(443,), daemon=True).start()

    # 4. Web UI Dashboard (:9090 default, fallback to :8080)
    threading.Thread(target=run_http, args=(DASHBOARD_PORT,), daemon=True).start()
    if DASHBOARD_PORT != 8080:
        try:
            threading.Thread(target=run_http, args=(8080,), daemon=True).start()
        except Exception:
            pass

    # 5. Live Hardware Sensor Poller (TCP 8070 to Ambi Climate) - ดึงข้อมูล Pull Query อัตโนมัติทุก 20 วินาที
    threading.Thread(target=poll_live_sensors, args=(20,), daemon=True).start()
    hub_log("[+] Live Hardware Sensor Poller (Pull Query :8070) is ENABLED (every 20s).")

    # 6. Hybrid Local Comfort AI Auto-Tuning Worker
    threading.Thread(target=auto_tuning_worker, daemon=True).start()

    # 7. AMX Beacon Listener (Port 9131 UDP)
    threading.Thread(target=run_beacon_listener, daemon=True).start()

    # 8. Solid Green LED Keep-Alive Watchdog (Reaffirms every 120s)
    threading.Thread(target=led_keepalive_worker, args=(120,), daemon=True).start()

    def interactive_cli():
        time.sleep(2.0)
        print("\n" + "=" * 65)
        print("  ⌨️  CONSOLE SHORTCUTS (Type number & press Enter):")
        print("     [1] ตรวจสอบ Cloud Server ปัจจุบัน (NCA)")
        print(f"     [2] ยิงเปลี่ยน Cloud มาที่เครื่องนี้ TLS -> {HOST_IP}:8867 (NCE + NCD)")
        print(f"     [3] ยิงเปลี่ยน Cloud มาที่เครื่องนี้ TCP -> {HOST_IP}:8866 (NCE + NCD)")
        print("     [4] สั่ง Ambi Reconnect (NCD)")
        print("     [5] อ่านค่าเซนเซอร์สดทันที (Manual Query NTP / NHM / NLU)")
        print("     [6] สั่งไฟ LED หน้าเครื่องเป็นสีเขียว (Solid Green)")
        print("     [7] ปรับความสว่างหลอดไฟ LED (0=OFF, 1000-10000)")
        print("     [P] สลับเปิด/ปิดการดึงเซนเซอร์อัตโนมัติ (Auto Pull Query ทุก 20 วิ)")
        print("     [N] ตรวจสอบและตรวจจับเน็ตเวิร์กใหม่ (Auto Detect Network)")
        print("     [M] สลับโหมด Ambi Climate (Comfort, Temperature, Manual, Away, Off)")
        print("     [L] ดึงและแสดง System Dump Log ของ Ambi (NSL)")
        print("     [R] Reset คืนค่า Cloud ฮ่องกง (connect.smartambi.com:8867)")
        print("=" * 65 + "\n")
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                cmd = line.strip().upper()
                if cmd == "1":
                    curr = get_cloud_server_setting()
                    print(f"\n[INFO] Target Ambi IP: {get_ambi_ip()} | Cloud Server (NCA): {curr}\n")
                elif cmd == "2":
                    if not get_ambi_ip():
                        print(f"\n[!] Ambi IP not yet detected. Waiting for connect DNS query...\n")
                    else:
                        change_cloud_server(f"{HOST_IP}:8867")
                elif cmd == "3":
                    if not get_ambi_ip():
                        print(f"\n[!] Ambi IP not yet detected. Waiting for connect DNS query...\n")
                    else:
                        change_cloud_server(f"{HOST_IP}:8866")
                elif cmd == "4":
                    if not get_ambi_ip():
                        print(f"\n[!] Ambi IP not yet detected. Waiting for connect DNS query...\n")
                    else:
                        res = send_ambi_cmd("NCD")
                        res_str = res.decode('latin1', errors='ignore').strip() if res else "None"
                        print(f"\n[INFO] Sent NCD -> {res_str}\n")
                elif cmd == "5":
                    target = get_ambi_ip() or get_cached_ambi_ip()
                    if not target:
                        print(f"\n[!] Ambi IP not yet detected. Waiting for connect DNS query...\n")
                    else:
                        print(f"\n[*] Querying live sensors on-demand from {target}:8070...")
                        res = query_live_sensors(target)
                        print(f"[INFO] Sensors -> Temp: {res.get('room_temp')} °C | Hum: {res.get('room_humidity')} % | Humidex: {res.get('humidex')} °C\n")
                elif cmd in ("6", "G"):
                    target = get_ambi_ip() or get_cached_ambi_ip()
                    print(f"\n[*] Sending Green LED command to Ambi ({target})...")
                    set_ambi_led_green(target)
                elif cmd == "7":
                    target = get_ambi_ip() or get_cached_ambi_ip()
                    if not target:
                        print(f"\n[!] Ambi IP not yet detected. Waiting for connect DNS query...\n")
                    else:
                        print("\nป้อนระดับความสว่าง LED (0 = ปิดไฟ, 1000-10000, ค่าเริ่มต้น 5700): ", end="", flush=True)
                        try:
                            lvl_str = sys.stdin.readline().strip()
                            lvl = int(lvl_str)
                            set_ambi_led_brightness(lvl, target)
                        except Exception as ex:
                            print(f"[!] Invalid brightness: {ex}")
                elif cmd == "P":
                    POLL_SENSORS_ENABLED = not POLL_SENSORS_ENABLED
                    state_txt = "ENABLED (ดึงทุก 20 วิ)" if POLL_SENSORS_ENABLED else "DISABLED (ปิด)"
                    print(f"\n[+] Auto Sensor Polling: {state_txt}\n")
                elif cmd == "N":
                    print("\n[*] Detecting and refreshing network settings...")
                    refresh_network_settings()
                    print(f"[+] Host IP: {HOST_IP} | Gateway: {ROUTER_GATEWAY_IP} | WAN: {ROUTER_WAN_IP} | DNS Redirect: {DNS_REDIRECT_IP}\n")
                elif cmd == "M":
                    print("\nเลือกโหมด Ambi [1=Comfort, 2=Temperature, 3=Manual, 4=Away, 0=Off]: ", end="", flush=True)
                    m_choice = sys.stdin.readline().strip()
                    m_map = {"1": "Comfort", "2": "Temperature", "3": "Manual", "4": "Away", "0": "Off"}
                    target_mode = m_map.get(m_choice)
                    if target_mode:
                        AC_STATE['ambi_mode'] = target_mode
                        if target_mode == 'Off':
                            send_daikin_ir(power='Off', reason="Console Mode: OFF")
                        else:
                            send_daikin_ir(power='On', reason=f"Console Mode: {target_mode}")
                        print(f"[+] Ambi Mode switched to: {target_mode}\n")
                    else:
                        print("[!] Invalid mode choice.\n")
                elif cmd == "L":
                    print(f"\n[*] Fetching Ambi System Dump Log (NSL) from {get_ambi_ip()}...")
                    log_content = fetch_ambi_system_log()
                    print("\n" + "=" * 70)
                    print(log_content)
                    print("=" * 70 + "\n")
                elif cmd == "R":
                    change_cloud_server("connect.smartambi.com:8867")
            except Exception:
                pass

    # 8. Interactive Console Command Worker
    threading.Thread(target=interactive_cli, daemon=True).start()

    print("\n[OK] Ready! Focused on Cloud Ports 8866 & 8867 and DNS queries...\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting...")
