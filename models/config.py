#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ambi Climate Configuration & Network Auto-Detection Model
---------------------------------------------------------
Handles networking environment, server paths, system locks, and logging.
"""

import sys
import os
import re
import socket
import subprocess
import urllib.request
import threading
import time
import ambi_db

CURRENT_TIMEZONE = ambi_db.init_timezone()

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

def detect_local_ip(gateway_ip=None, fallback="192.168.1.199"):
    """Auto-detects or sets the host's LAN IP address (Fixed Default IP: 192.168.1.199)."""
    env_ip = os.environ.get("HOST_IP")
    if env_ip and env_ip.strip():
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

# Paths
DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CERT_FILE = os.path.join(DIR, "server_cert.pem")
KEY_FILE = os.path.join(DIR, "server_key.pem")
PROFILE_FILE = os.path.join(DIR, "decompiled_analysis", "user_device_profile.json")
DASHBOARD_HTML_FILE = os.path.join(DIR, "web_dashboard.html")
LOG_FILE = os.path.join(DIR, "hub_activity.log")

# Initial automatic network configuration (Gateway first, then Host LAN IP)
ROUTER_GATEWAY_IP = detect_gateway_ip(fallback="192.168.1.1")
HOST_IP = detect_local_ip(gateway_ip=ROUTER_GATEWAY_IP, fallback="192.168.1.199")
ROUTER_WAN_IP = detect_wan_ip(fallback="100.112.62.200")
DNS_REDIRECT_IP = os.environ.get("DNS_REDIRECT_IP") or ROUTER_WAN_IP

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

# Locks & Synchronization Events
AMBI_HW_LOCK = threading.Lock()
AMBI_PORT_8070_LOCK = AMBI_HW_LOCK
AMBI_READY_EVENT = threading.Event()
PENDING_IR_LOCK = threading.Lock()

