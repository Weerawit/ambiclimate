#!/usr/bin/env python3
"""
Ambi Climate Hardware Controller
--------------------------------
Handles low-level hardware interactions with Ambi Climate (Port 8070)
and Daikin AC IR signal transmission (Port 4998).
"""

import os
import time
import socket
import struct
import select
import threading
import ambi_db
from test_daikin import save_ambi_ip, is_valid_ambi, get_live_sensors

from models.config import (
    DIR, HOST_IP, ROUTER_WAN_IP, ROUTER_GATEWAY_IP,
    AMBI_HW_LOCK, AMBI_PORT_8070_LOCK, PENDING_IR_LOCK, hub_log
)
from models.ac_state import (
    AC_STATE, get_cached_ambi_ip, get_ambi_ip, set_ambi_ip,
    queue_pending_ir, clear_pending_ir, get_pending_ir_status
)
from models.comfort import (
    COMFORT_PROFILE, save_comfort_profile, evaluate_comfort
)

_DISPATCHING_PENDING = False

def check_and_flush_pending_ir(client_ip=None):
    """Flushes any queued IR command when Ambi reconnects or shows cloud activity."""
    global _DISPATCHING_PENDING
    with PENDING_IR_LOCK:
        import models.ac_state as ac_mod
        if not ac_mod.PENDING_IR_COMMAND or _DISPATCHING_PENDING:
            return
        if client_ip and client_ip.startswith("192.168."):
            ac_mod.PENDING_IR_COMMAND["target_ip"] = client_ip
        _DISPATCHING_PENDING = True

    def dispatch_worker():
        global _DISPATCHING_PENDING
        try:
            time.sleep(0.4)
            with PENDING_IR_LOCK:
                import models.ac_state as ac_mod
                pending = dict(ac_mod.PENDING_IR_COMMAND) if ac_mod.PENDING_IR_COMMAND else None
            if not pending:
                return

            cmd = pending["cmd"]
            reason = pending["reason"]
            target_ip = pending.get("target_ip") or get_ambi_ip()
            power = pending.get("target_power")
            temp = pending.get("target_temp")
            fan = pending.get("target_fan")
            mode = pending.get("target_mode")

            hub_log(f"[🚀 AUTO-RETRY PENDING IR] Detected Ambi activity from {target_ip}. Flushing queued command ({reason})...")

            success = False
            ir_resp = ""
            with AMBI_HW_LOCK:
                for attempt in range(3):
                    s = None
                    try:
                        s = socket.create_connection((target_ip, 4998), timeout=3.5)
                        s.sendall(cmd.encode('ascii'))
                        ir_resp = s.recv(256).decode('ascii', errors='ignore').strip()
                        hub_log(f"[IR TRANSMIT DAIKIN (QUEUED RECOVERY)] ({reason}) [Target {target_ip}:4998] Target={temp}°C Fan={fan} Power={power} -> {ir_resp}")
                        success = True
                        break
                    except Exception as e:
                        ir_resp = f"Error: {e}"
                        hub_log(f"[IR QUEUED RETRY #{attempt+1}] Attempt failed: {e}")
                        time.sleep(0.4)
                    finally:
                        if s:
                            try:
                                s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                                s.close()
                            except Exception:
                                pass

            if success:
                clear_pending_ir()
                hub_log(f"[✅ PENDING IR RESOLVED] Successfully delivered queued command to Ambi Climate ({target_ip}:4998)!")
                entry = {
                    "time": time.strftime('%H:%M:%S'),
                    "action": f"Recovery: {reason}",
                    "temp": temp,
                    "fan": fan,
                    "power": power,
                    "room_temp": AC_STATE.get('room_temp'),
                    "room_humidity": AC_STATE.get('room_humidity'),
                    "result": ir_resp
                }
                history = COMFORT_PROFILE.get("history", [])
                history.insert(0, entry)
                COMFORT_PROFILE["history"] = history[:25]
                save_comfort_profile(COMFORT_PROFILE)

                ambi_db.record_action(
                    action_type="ir_recovery",
                    power=power,
                    temperature=temp,
                    fan=fan,
                    swing=AC_STATE.get('swing', 'Auto'),
                    mode=mode,
                    trigger_reason=f"Recovery after reconnect: {reason}",
                    room_temp=AC_STATE.get('room_temp'),
                    room_humidity=AC_STATE.get('room_humidity'),
                    humidex=AC_STATE.get('humidex'),
                    result=ir_resp
                )
            else:
                with PENDING_IR_LOCK:
                    import models.ac_state as ac_mod
                    if ac_mod.PENDING_IR_COMMAND:
                        ac_mod.PENDING_IR_COMMAND["attempts"] += 1
                        if ac_mod.PENDING_IR_COMMAND["attempts"] >= 5 or (time.time() - ac_mod.PENDING_IR_COMMAND["timestamp"] > 600):
                            hub_log(f"[❌ PENDING IR EXPIRED] Dropping queued IR command after {ac_mod.PENDING_IR_COMMAND['attempts']} attempts / timeout.")
                            ac_mod.PENDING_IR_COMMAND = None
        finally:
            with PENDING_IR_LOCK:
                _DISPATCHING_PENDING = False

    threading.Thread(target=dispatch_worker, daemon=True).start()

def update_ambi_ip(new_ip, source=""):
    """Validates and updates the Ambi IP address, auto-saving and triggering background notifications."""
    if not new_ip or new_ip in (HOST_IP, ROUTER_WAN_IP, ROUTER_GATEWAY_IP, "127.0.0.1"):
        return
    if "Cloud TCP" not in source and "Sensor Poller" not in source:
        if not is_valid_ambi(new_ip, timeout=0.8):
            hub_log(f"[-] Ignored non-Ambi IP {new_ip} from {source} (Ports 8070/4998 closed).")
            return

    curr_ip = get_ambi_ip()
    if new_ip != curr_ip and new_ip.startswith("192.168."):
        old_ip = curr_ip
        set_ambi_ip(new_ip)
        save_ambi_ip(new_ip)
        src_tag = f" via {source}" if source else ""
        hub_log(f"\n{'='*65}\n🎯 [STEP 1: CAPTURED AMBI IP] Detected {new_ip}{src_tag} (was {old_ip})\n{'='*65}\n")
        threading.Thread(target=set_ambi_led_green, args=(new_ip,), daemon=True).start()

    check_and_flush_pending_ir(new_ip)

def send_ambi_cmd(cmd_text, target_ip=None, port=8070, timeout=3.0):
    """Sends framed command to Ambi on Port 8070 and returns the raw response."""
    ip = target_ip or get_ambi_ip()
    if not ip:
        hub_log(f"[-] Command to Ambi ({cmd_text}) skipped: Ambi IP not yet acquired (waiting for DNS connect query).")
        return None
    seq = "01"
    packet = b"\x07" + seq.encode('ascii') + cmd_text.encode('latin1') + b"\r"
    with AMBI_PORT_8070_LOCK:
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((ip, port))
            s.sendall(packet)
            time.sleep(0.15)
            resp = s.recv(2048)
            return resp
        except Exception as e:
            hub_log(f"[-] Command to Ambi ({cmd_text} -> {ip}:{port}) failed: {e}")
            return None
        finally:
            if s:
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                    s.close()
                except Exception:
                    pass

_CLOUD_SETTING_CACHE = {"value": None, "timestamp": 0}

def get_cloud_server_setting(target_ip=None, max_age_sec=120):
    """Queries current configured Cloud Server (NCA) from Ambi Port 8070 with memory cache."""
    global _CLOUD_SETTING_CACHE
    now = time.time()
    if _CLOUD_SETTING_CACHE["value"] and (now - _CLOUD_SETTING_CACHE["timestamp"] < max_age_sec):
        return _CLOUD_SETTING_CACHE["value"]

    ip = target_ip or get_ambi_ip()
    if not ip:
        return "Waiting for Ambi connect..."
    resp = send_ambi_cmd("NCA", ip)
    if resp and len(resp) >= 7 and resp[0] == 7:
        val = resp[7:].decode('latin1', errors='ignore').strip('\r\n ')
        res = val if val else "Empty (Default Cloud)"
        _CLOUD_SETTING_CACHE = {"value": res, "timestamp": now}
        return res
    elif resp:
        val = resp.decode('latin1', errors='ignore').strip()
        res = val if val else "Empty (Default Cloud)"
        _CLOUD_SETTING_CACHE = {"value": res, "timestamp": now}
        return res
    if _CLOUD_SETTING_CACHE["value"]:
        return _CLOUD_SETTING_CACHE["value"]
    return "connect.smartambi.com:8867"

def change_cloud_server(new_server_port, target_ip=None):
    """Sends NCA (Address Override), NCE (Environment), and NCD to force reconnect."""
    global _CLOUD_SETTING_CACHE
    ip = target_ip or get_ambi_ip()
    if not ip:
        hub_log("[-] Cannot change cloud server: Ambi IP not yet acquired.")
        return {"status": "Error", "message": "Ambi IP not yet acquired"}
    hub_log(f"\n{'='*65}")
    hub_log(f"🚀 [STEP 3: CHANGING CLOUD SERVER] Target Ambi IP: {ip}")
    hub_log(f"   Target Server: {new_server_port}")
    hub_log(f"{'='*65}")

    _CLOUD_SETTING_CACHE = {"value": new_server_port, "timestamp": time.time()}

    curr = get_cloud_server_setting(ip)
    hub_log(f"   1) Current Cloud Setting (NCA)     : '{curr}'")

    resp_ca = send_ambi_cmd(f"NCA{new_server_port}", ip)
    ca_decoded = resp_ca.decode('latin1', errors='ignore').strip() if resp_ca else "None"
    hub_log(f"   2) Sent NCA (Address Override) ->  : '{ca_decoded}'")

    resp_ce = send_ambi_cmd(f"NCE{new_server_port}", ip)
    ce_decoded = resp_ce.decode('latin1', errors='ignore').strip() if resp_ce else "None"
    hub_log(f"   3) Sent NCE (Environment)      ->  : '{ce_decoded}'")

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
        s = None
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
        finally:
            if s:
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                    s.close()
                except Exception:
                    pass

def set_ambi_led_green(target_ip=None, brightness=None):
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
    b_val = brightness if brightness is not None else AC_STATE.get("led_brightness", 5700)
    hub_log(f"[*] Setting Ambi Climate LED to SOLID GREEN ({b_val} PWM) on {ip}:8070...")
    with AMBI_PORT_8070_LOCK:
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect((ip, 8070))

            s.sendall(b"\x0700NSD\r")
            time.sleep(0.12)
            try: s.recv(256)
            except Exception: pass

            s.sendall(b"\x0700NCD1\r")
            time.sleep(0.12)
            try: s.recv(256)
            except Exception: pass

            s.sendall(b"\x0700NLL1 " + str(b_val).encode("ascii") + b"\r")
            time.sleep(0.15)
            try: s.recv(256)
            except Exception: pass

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

            AC_STATE["led_status"] = "ON"
            hub_log(f"✅ [🟢 LED ACTIVATED] Ambi Climate ({ip}) front LED is now SOLID GREEN at {b_val} PWM!")
            return True
        except Exception as e:
            hub_log(f"[-] Error setting LED to Green on {ip}: {e}")
            return False
        finally:
            if s:
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                    s.close()
                except Exception:
                    pass

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
    AC_STATE["led_brightness"] = level
    hub_log(f"[*] Setting Ambi Climate LED brightness to {level} on {ip}:8070...")
    with AMBI_PORT_8070_LOCK:
        s = None
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

                pct = round(level / 100)
                hub_log(f"✅ [💡 LED BRIGHTNESS] Ambi Climate ({ip}) LED brightness set to {level} ({pct}%) Green.")
            return True
        except Exception as e:
            hub_log(f"[-] Error setting LED brightness on {ip}: {e}")
            return False
        finally:
            if s:
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                    s.close()
                except Exception:
                    pass

def query_live_sensors(target_ip=None):
    """
    On-demand query of real-time temperature, humidity, luminosity from Ambi Climate Port 8070.
    Updates AC_STATE and comfort evaluation immediately.
    """
    ip = target_ip or get_ambi_ip() or get_cached_ambi_ip()
    if not ip:
        hub_log("[-] Cannot query sensors: Ambi IP not yet acquired.")
        return {"status": "Error", "message": "Ambi IP not yet acquired"}

    t_calib = float(COMFORT_PROFILE.get("temp_calibration_offset", -3.0))
    h_calib = float(COMFORT_PROFILE.get("humidity_calibration_offset", 4.0))

    hub_log(f"[*] Querying live sensors on-demand from {ip}:8070...")
    with AMBI_PORT_8070_LOCK:
        live = get_live_sensors(ip, port=8070, timeout=3.5, temp_offset=t_calib, hum_offset=h_calib)

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

    c = evaluate_comfort(AC_STATE["room_temp"], AC_STATE["room_humidity"])
    AC_STATE["humidex"] = c["humidex"]
    AC_STATE["comfort_score"] = c["score"]
    AC_STATE["comfort_label"] = c["label"]
    AC_STATE["comfort_badge_color"] = c["badge_color"]
    AC_STATE["sensor_status"] = f"Manual Query ({ip})"
    AC_STATE["sensor_time"] = time.strftime('%H:%M:%S')

    ambi_db.record_sensor(
        temperature=AC_STATE["room_temp"],
        humidity=AC_STATE["room_humidity"],
        luminosity=AC_STATE.get("luminosity", 0),
        humidex=c.get("humidex"),
        comfort_score=c.get("score"),
        comfort_label=c.get("label"),
        source="query"
    )

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
    target_ip = get_ambi_ip() or get_cached_ambi_ip()
    if not target_ip:
        from test_daikin import discover_ambi_ip
        target_ip = discover_ambi_ip()
        if target_ip:
            update_ambi_ip(target_ip, source="Auto-Discovery")

    if not target_ip:
        hub_log(f"[IR TRANSMIT SKIPPED] ({reason}) Ambi IP not yet acquired.")
        return "Ambi IP not yet acquired"

    ir_resp = ""
    s = None
    f1, f2 = daikin_ir.build_daikin_command(
        temp=AC_STATE['temperature'],
        mode=AC_STATE['mode'],
        fan=AC_STATE['fan'],
        power=is_power,
        protocol_type="B"
    )
    cmd = daikin_ir.frames_to_sendir(f1, f2, connector="1:1")

    is_success = False
    with AMBI_HW_LOCK:
        for attempt in range(3):
            try:
                s = socket.create_connection((target_ip, 4998), timeout=3.0)
                s.sendall(cmd.encode('ascii'))
                ir_resp = s.recv(256).decode('ascii', errors='ignore').strip()
                hub_log(f"[IR TRANSMIT DAIKIN] ({reason}) [Target {target_ip}:4998] Target={AC_STATE['temperature']}°C Fan={AC_STATE['fan']} Power={AC_STATE['power']} -> {ir_resp}")
                is_success = True
                clear_pending_ir()
                break
            except Exception as e:
                ir_resp = f"Error: {e}"
                if s:
                    try:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                        s.close()
                    except Exception:
                        pass
                    s = None

                if attempt == 0:
                    hub_log(f"[IR RETRY] ({reason}) Connect to {target_ip}:4998 failed ({e}). Re-discovering Ambi IP...")
                    from test_daikin import discover_ambi_ip
                    fresh_ip = discover_ambi_ip()
                    if fresh_ip and fresh_ip != target_ip:
                        hub_log(f"[IR RETRY] Detected Ambi IP moved to: {fresh_ip} (was {target_ip})")
                        target_ip = fresh_ip
                        update_ambi_ip(fresh_ip, source="Re-Discovery on Refuse")
                    time.sleep(0.3)
                elif attempt == 1:
                    hub_log(f"[IR RETRY #2] ({reason}) Retrying target {target_ip}:4998 after wait...")
                    time.sleep(0.5)
                else:
                    hub_log(f"[IR TRANSMIT ERROR] ({reason}) Target {target_ip}:4998 -> {e}")
            finally:
                if s:
                    try:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                        s.close()
                    except Exception:
                        pass
                    s = None

    if not is_success:
        queue_pending_ir(
            cmd=cmd,
            reason=reason,
            target_power=AC_STATE['power'],
            target_temp=AC_STATE['temperature'],
            target_fan=AC_STATE['fan'],
            target_mode=AC_STATE['mode'],
            target_ip=target_ip
        )

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

    act_type = "manual_control"
    reason_lower = (reason or "").lower()
    if "feedback" in reason_lower:
        act_type = "user_feedback"
    elif any(k in reason_lower for k in ("ai", "auto-tune", "auto-tuning", "warmed", "cooled", "comfort ai")):
        act_type = "ai_tune"
    elif "mode" in reason_lower:
        act_type = "mode_change"
    elif power is not None or "power" in reason_lower:
        act_type = "power"

    ambi_db.record_action(
        action_type=act_type,
        power=AC_STATE['power'],
        temperature=AC_STATE['temperature'],
        fan=AC_STATE['fan'],
        swing=AC_STATE.get('swing', 'Auto'),
        mode=AC_STATE['mode'],
        trigger_reason=reason,
        room_temp=AC_STATE.get('room_temp'),
        room_humidity=AC_STATE.get('room_humidity'),
        humidex=AC_STATE.get('humidex'),
        result=ir_resp
    )

    return ir_resp

