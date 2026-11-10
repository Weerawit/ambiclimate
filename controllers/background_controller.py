#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ambi Climate Background Services & Daemons Controller
-----------------------------------------------------
Handles background listeners: DNS server, Cloud Mock TCP (8866/8867), AMX Beacon UDP (9131),
Auto-tuning Comfort AI, periodic hardware sensor polling, and interactive CLI.
"""

import sys
import os
import time
import socket
import ssl
import struct
import threading
import select
import ambi_db
from test_daikin import save_ambi_ip, is_valid_ambi, get_live_sensors

from models.config import (
    DIR, CERT_FILE, KEY_FILE, HOST_IP, ROUTER_GATEWAY_IP, ROUTER_WAN_IP,
    DNS_REDIRECT_IP, AMBI_READY_EVENT, hub_log, refresh_network_settings
)
import models.ac_state as ac_mod
from models.ac_state import (
    AC_STATE, get_ambi_ip, get_cached_ambi_ip, set_ambi_ip
)
from models.comfort import (
    COMFORT_PROFILE, save_comfort_profile, evaluate_comfort
)
from controllers.hardware_controller import (
    update_ambi_ip, check_and_flush_pending_ir, set_ambi_led_green,
    set_ambi_led_brightness, query_live_sensors, send_daikin_ir,
    send_ambi_cmd, get_cloud_server_setting, change_cloud_server,
    fetch_ambi_system_log
)
from controllers.api_controller import ThreadedHTTPServer, AmbiAPIHandler

AMBI_SPECIFIC_DOMAINS = [
    'ambiclimate.com',
    'smartambi.com',
    'ambiapis.com',
    'tryambi.com',
    'tryambiapis.com',
    'globalcache.com',
]

AMBI_SHARED_DOMAINS = [
    'amazonaws.com',
    'cloudfront.net',
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
    """Runs DNS interceptor on UDP 53 to redirect Ambi cloud domains to local hub."""
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

            is_ambi_domain = any(domain.endswith(t) for t in ("smartambi.com", "ambiclimate.com", "tryambi.com", "ambiapis.com", "tryambiapis.com"))

            if is_ambi_domain and client_ip not in (HOST_IP, ROUTER_GATEWAY_IP, "127.0.0.1"):
                curr_ambi = get_ambi_ip()
                if curr_ambi != client_ip:
                    set_ambi_ip(client_ip)
                    save_ambi_ip(client_ip)
                    hub_log(f"\n{'='*70}")
                    hub_log(f"🎯 [STEP 1: CAPTURED AMBI IP FROM DNS]")
                    hub_log(f"   Received Query : '{domain}' (qtype={qtype})")
                    hub_log(f"   Device IP      : {client_ip}")
                    hub_log(f"   -> Locked Ambi IP into memory: {client_ip}")
                    hub_log(f"{'='*70}\n")
                    threading.Thread(target=set_ambi_led_green, args=(client_ip,), daemon=True).start()

                resp = make_dns_redirect_response(data, DNS_REDIRECT_IP)
                if resp:
                    hub_log(f"[DNS REDIRECT 🎯] {domain} (qtype={qtype}) from Ambi ({client_ip}) -> {DNS_REDIRECT_IP}")
                    sock.sendto(resp, addr)

                check_and_flush_pending_ir(client_ip)

                def auto_set_cloud_worker(target_ip):
                    time.sleep(0.6)
                    set_ambi_led_green(target_ip)
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
                    set_ambi_led_green(target_ip)
                    AMBI_READY_EVENT.set()

                if not ac_mod.AMBI_AUTO_RETARGETED:
                    ac_mod.AMBI_AUTO_RETARGETED = True
                    threading.Thread(target=auto_set_cloud_worker, args=(client_ip,), daemon=True).start()
                continue

            ambi_current = get_ambi_ip()
            is_from_ambi = (client_ip == ambi_current and ambi_current is not None)

            is_ambi_exclusive = any(domain.endswith(t) for t in AMBI_SPECIFIC_DOMAINS)
            is_ambi_shared = any(domain.endswith(t) for t in AMBI_SHARED_DOMAINS)

            if is_from_ambi:
                if is_ambi_exclusive or is_ambi_shared:
                    resp = make_dns_redirect_response(data, DNS_REDIRECT_IP)
                    if resp:
                        hub_log(f"[DNS REDIRECT 🎯] {domain} (qtype={qtype}) from Ambi ({client_ip}) -> {DNS_REDIRECT_IP}")
                        sock.sendto(resp, addr)
                else:
                    hub_log(f"[DNS FORWARD 🌐] {domain} (qtype={qtype}) from Ambi ({client_ip}) -> Forwarded to 8.8.8.8")
                    forward_dns_upstream(sock, data, addr)
            else:
                forward_dns_upstream(sock, data, addr)

        except Exception:
            pass

def run_https(port):
    """Runs an HTTPS server instance on specified port."""
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
    """Runs a plain HTTP server instance on specified port."""
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
            check_and_flush_pending_ir(addr[0])

            def handle_client(c, a, p, ctx):
                c.settimeout(180.0)
                active_sock = c
                try:
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

                        if data and data[0] == 0x07 and len(data) >= 3:
                            seq = data[1:3]
                            cmd = data[3:6].decode('latin1', errors='ignore') if len(data) >= 6 else ""
                            seq_str = seq.decode('latin1', errors='ignore')
                            hub_log(f"  [Cloud :{p}] ⚙️ Ambi Native Frame: Seq={seq_str} Cmd={cmd}")

                            proto_resp = b"\x07" + seq + b"0" + cmd.encode('ascii') + b"0\r\n"
                            active_sock.sendall(proto_resp)
                            proto_asc = ''.join(chr(b) if 32 <= b <= 126 else f'\\x{b:02x}' for b in proto_resp)
                            hub_log(f"  [📡 AMBI TRAFFIC :{p}] 📤 SEND ({len(proto_resp)}B) ASCII: {proto_asc}")

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
                                        t_calib = float(COMFORT_PROFILE.get("temp_calibration_offset", -3.0))
                                        AC_STATE["room_temp_raw"] = val
                                        AC_STATE["room_temp"] = round(val + t_calib, 2)
                                        AC_STATE["temp_calibration_offset"] = t_calib
                                        AC_STATE["sensor_status"] = f"Cloud Push (:{p})"
                                        AC_STATE["sensor_time"] = time.strftime('%H:%M:%S')
                                        if AC_STATE.get("room_temp") is not None and AC_STATE.get("room_humidity") is not None:
                                            c = evaluate_comfort(AC_STATE["room_temp"], AC_STATE["room_humidity"])
                                            AC_STATE["humidex"] = c["humidex"]
                                            AC_STATE["comfort_score"] = c["score"]
                                            AC_STATE["comfort_label"] = c["label"]
                                            AC_STATE["comfort_badge_color"] = c["badge_color"]
                                            ambi_db.record_sensor(
                                                temperature=AC_STATE["room_temp"],
                                                humidity=AC_STATE["room_humidity"],
                                                luminosity=AC_STATE.get("luminosity", 0),
                                                humidex=c.get("humidex"),
                                                comfort_score=c.get("score"),
                                                comfort_label=c.get("label"),
                                                source=f"cloud_{p}"
                                            )
                                        hub_log(f"  [📡 AMBI SENSOR PUSH] 🌡️ Temperature: {AC_STATE['room_temp']}°C (Raw: {val}°C, {t_calib:+}°C) (Port {p})")
                            elif cmd == "NHM":
                                payload = data[6:].decode('latin1', errors='ignore').strip('\r\n') if len(data) > 6 else ""
                                if payload:
                                    from test_daikin import parse_sensor_value
                                    val, _ = parse_sensor_value(payload)
                                    if val is not None:
                                        h_calib = float(COMFORT_PROFILE.get("humidity_calibration_offset", 4.0))
                                        AC_STATE["room_humidity_raw"] = val
                                        AC_STATE["room_humidity"] = round(min(100.0, max(0.0, val + h_calib)), 2)
                                        AC_STATE["humidity_calibration_offset"] = h_calib
                                        AC_STATE["sensor_status"] = f"Cloud Push (:{p})"
                                        AC_STATE["sensor_time"] = time.strftime('%H:%M:%S')
                                        if AC_STATE.get("room_temp") is not None and AC_STATE.get("room_humidity") is not None:
                                            c = evaluate_comfort(AC_STATE["room_temp"], AC_STATE["room_humidity"])
                                            AC_STATE["humidex"] = c["humidex"]
                                            AC_STATE["comfort_score"] = c["score"]
                                            AC_STATE["comfort_label"] = c["label"]
                                            AC_STATE["comfort_badge_color"] = c["badge_color"]
                                            ambi_db.record_sensor(
                                                temperature=AC_STATE["room_temp"],
                                                humidity=AC_STATE["room_humidity"],
                                                luminosity=AC_STATE.get("luminosity", 0),
                                                humidex=c.get("humidex"),
                                                comfort_score=c.get("score"),
                                                comfort_label=c.get("label"),
                                                source=f"cloud_{p}"
                                            )
                                        hub_log(f"  [📡 AMBI SENSOR PUSH] 💧 Humidity: {AC_STATE['room_humidity']}% (Raw: {val}%, {h_calib:+}%) (Port {p})")

                            check_and_flush_pending_ir(a[0])
                        else:
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
        hub_log(f"[-] CLOUD MOCK SERVER port {port} bind error: {e}")

def led_keepalive_worker(interval_sec=120):
    """
    Periodically reaffirms Solid Green LED every interval_sec (default 120s)
    to ensure the internal 1NCO slave watchdog never reverts the LED to amber.
    """
    while True:
        try:
            time.sleep(interval_sec)
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
            if "GlobalCache" in text or "ITACH" in text.upper():
                update_ambi_ip(addr[0], source="GlobalCache AMX Beacon UDP 9131")
            elif "AMXB" in text and is_valid_ambi(addr[0], timeout=0.4):
                update_ambi_ip(addr[0], source="Ambi AMX Beacon UDP 9131")
    except Exception:
        pass

def auto_tuning_worker():
    """
    Background worker that monitors room climate and tunes Daikin AC automatically.
    Safety controls:
      - Deadband: -0.7 to +0.7 -> No action
      - Noise filter: requires 2 consecutive cycles outside deadband
      - Cooldown timer: default 10 minutes between IR transmissions
      - Min / Max temperature clamps
    """
    time.sleep(10)
    hub_log("[+] AUTO-TUNING COMFORT AI Worker Active.")

    while True:
        try:
            time.sleep(30)
            if not COMFORT_PROFILE.get("auto_tune_enabled", True):
                continue

            power_status = str(AC_STATE.get("power", "Off")).lower()
            if power_status != "on":
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

            if -0.8 <= score <= 0.8:
                ac_mod.CONSECUTIVE_OUT_OF_BOUNDS = 0
                continue

            ac_mod.CONSECUTIVE_OUT_OF_BOUNDS += 1
            if ac_mod.CONSECUTIVE_OUT_OF_BOUNDS < 2:
                continue

            if time_since_tune < cooldown_sec:
                continue

            min_t = COMFORT_PROFILE.get("min_temp", 22)
            max_t = COMFORT_PROFILE.get("max_temp", 27)
            curr_ac_t = AC_STATE.get("temperature", 24)

            if score <= -1.2:
                new_t = curr_ac_t
                new_fan = AC_STATE.get("fan", "Auto")
                if curr_ac_t < max_t:
                    new_t = curr_ac_t + 1
                elif new_fan in ("High", "5", "med", "3"):
                    new_fan = "Low"
                elif new_fan in ("Low", "1", "Auto"):
                    new_fan = "Quiet"

                if new_t != curr_ac_t or new_fan != AC_STATE.get("fan"):
                    target_hx = comfort.get("target_humidex", 26.0)
                    reason = f"AI Adjust: รู้สึกหนาวเกินไป (Humidex {comfort['humidex']}°C, เป้าหมาย {target_hx}°C) -> ปรับเพิ่มเป็น {new_t}°C ({new_fan})"
                    send_daikin_ir(temp=new_t, fan=new_fan, reason=reason)
                    COMFORT_PROFILE["last_tune_time"] = now
                    COMFORT_PROFILE["last_tune_action"] = f"AI Adjust: Warmed to {new_t}°C ({new_fan})"
                    save_comfort_profile(COMFORT_PROFILE)
                    ac_mod.CONSECUTIVE_OUT_OF_BOUNDS = 0

            elif score >= 1.2:
                new_t = curr_ac_t
                new_fan = AC_STATE.get("fan", "Auto")
                if curr_ac_t > min_t:
                    new_t = curr_ac_t - 1
                elif new_fan in ("Quiet", "silent", "Low", "1"):
                    new_fan = "med"
                elif new_fan in ("med", "3"):
                    new_fan = "High"

                if new_t != curr_ac_t or new_fan != AC_STATE.get("fan"):
                    target_hx = comfort.get("target_humidex", 26.0)
                    reason = f"AI Adjust: รู้สึกร้อนเกินไป (Humidex {comfort['humidex']}°C, เป้าหมาย {target_hx}°C) -> ปรับลดเป็น {new_t}°C ({new_fan})"
                    send_daikin_ir(temp=new_t, fan=new_fan, reason=reason)
                    COMFORT_PROFILE["last_tune_time"] = now
                    COMFORT_PROFILE["last_tune_action"] = f"AI Adjust: Cooled to {new_t}°C ({new_fan})"
                    save_comfort_profile(COMFORT_PROFILE)
                    ac_mod.CONSECUTIVE_OUT_OF_BOUNDS = 0

        except Exception as e:
            hub_log(f"[-] Auto-Tuning worker exception: {e}")

def poll_live_sensors(interval=20):
    """Periodically queries Port 8070 on Ambi Climate to retrieve real-time live sensor data."""
    hub_log(f"[+] Live Hardware Sensor Poller (Pull Query :8070) worker started (every {interval}s).")

    if get_ambi_ip() or get_cached_ambi_ip():
        AMBI_READY_EVENT.set()

    while True:
        try:
            if not ac_mod.POLL_SENSORS_ENABLED:
                time.sleep(5)
                continue

            target_ip = get_ambi_ip() or get_cached_ambi_ip() or "192.168.1.191"
            if not target_ip:
                time.sleep(4)
                continue

            t_calib = float(COMFORT_PROFILE.get("temp_calibration_offset", -3.0))
            h_calib = float(COMFORT_PROFILE.get("humidity_calibration_offset", 4.0))

            live = get_live_sensors(target_ip, port=8070, timeout=3.5, temp_offset=t_calib, hum_offset=h_calib)
            if live and (live.get("temperature") is not None or live.get("humidity") is not None):
                raw_t = live.get("raw_temperature", live.get("temperature"))
                raw_h = live.get("raw_humidity", live.get("humidity"))
                if live.get("temperature") is not None:
                    AC_STATE["room_temp_raw"] = raw_t
                    AC_STATE["room_temp"] = live["temperature"]
                if live.get("humidity") is not None:
                    AC_STATE["room_humidity_raw"] = raw_h
                    AC_STATE["room_humidity"] = live["humidity"]
                AC_STATE["temp_calibration_offset"] = t_calib
                AC_STATE["humidity_calibration_offset"] = h_calib
                if live.get("luminosity"):
                    AC_STATE["luminosity"] = live["luminosity"]

                c = evaluate_comfort(AC_STATE.get("room_temp"), AC_STATE.get("room_humidity"))
                AC_STATE["humidex"] = c["humidex"]
                AC_STATE["comfort_score"] = c["score"]
                AC_STATE["comfort_label"] = c["label"]
                AC_STATE["comfort_badge_color"] = c["badge_color"]
                AC_STATE["sensor_status"] = f"Auto Pull Active (:{target_ip})"
                AC_STATE["sensor_time"] = time.strftime('%H:%M:%S')

                ambi_db.record_sensor(
                    temperature=AC_STATE["room_temp"],
                    humidity=AC_STATE["room_humidity"],
                    luminosity=AC_STATE.get("luminosity", 0),
                    humidex=c.get("humidex"),
                    comfort_score=c.get("score"),
                    comfort_label=c.get("label"),
                    source="poller"
                )
                hub_log(f"[POLL SENSOR] 🌡️ Temp: {AC_STATE['room_temp']}°C (Raw: {raw_t}°C, {t_calib:+}°C) | 💧 Hum: {AC_STATE['room_humidity']}% (Raw: {raw_h}%, {h_calib:+}%) | Humidex: {c['humidex']}°C")

            time.sleep(interval)
        except Exception as e:
            hub_log(f"[-] Live sensor polling error: {e}")
            time.sleep(interval)

def interactive_cli():
    """Interactive command-line interface for manual hardware diagnostics and controls."""
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
                ac_mod.POLL_SENSORS_ENABLED = not ac_mod.POLL_SENSORS_ENABLED
                state_txt = "ENABLED (ดึงทุก 20 วิ)" if ac_mod.POLL_SENSORS_ENABLED else "DISABLED (ปิด)"
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

