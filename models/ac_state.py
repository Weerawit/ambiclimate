#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ambi Climate Device & AC State Model
------------------------------------
Tracks in-memory AC state, device identities, Ambi IP addressing, and pending IR commands.
"""

import os
import json
import time
from models.config import (
    DIR, PROFILE_FILE, PENDING_IR_LOCK, hub_log
)

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
    "room_temp_raw": None,
    "room_humidity": None,
    "room_humidity_raw": None,
    "luminosity": None,
    "humidex": None,
    "comfort_score": 0.0,
    "comfort_label": "สบายดี (Comfortable)",
    "comfort_badge_color": "#10b981",
    "sensor_status": "Auto Pull Active (TCP :8070)",
    "sensor_time": None,
    "temp_calibration_offset": -3.0,
    "humidity_calibration_offset": 4.0,
    "led_brightness": 10000,
    "led_status": "ON"
}

AMBI_IP = None
AMBI_AUTO_RETARGETED = False
POLL_SENSORS_ENABLED = True
CONSECUTIVE_OUT_OF_BOUNDS = 0

PENDING_IR_COMMAND = None
_DISPATCHING_PENDING = False

def get_cached_ambi_ip():
    """Reads cached Ambi IP from disk."""
    cache_file = os.path.join(DIR, "ambi_ip.txt")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                ip = f.read().strip()
                if ip and ip.startswith("192.168."):
                    return ip
        except Exception:
            pass
    return None

def get_ambi_ip():
    """Returns currently locked or discovered Ambi Climate IP."""
    global AMBI_IP
    if not AMBI_IP:
        cached = get_cached_ambi_ip()
        if cached:
            AMBI_IP = cached
        else:
            AMBI_IP = "192.168.1.191"
    return AMBI_IP

def set_ambi_ip(new_ip):
    """Sets in-memory Ambi IP directly."""
    global AMBI_IP
    AMBI_IP = new_ip

def queue_pending_ir(cmd, reason, target_power, target_temp, target_fan, target_mode, target_ip):
    """Queues an IR command for automatic re-dispatch upon Ambi activity."""
    global PENDING_IR_COMMAND
    with PENDING_IR_LOCK:
        PENDING_IR_COMMAND = {
            "cmd": cmd,
            "reason": reason,
            "target_power": target_power,
            "target_temp": target_temp,
            "target_fan": target_fan,
            "target_mode": target_mode,
            "target_ip": target_ip,
            "timestamp": time.time(),
            "attempts": 0
        }
        hub_log(f"[⏳ IR QUEUED] ({reason}) Target {target_ip}:4998 unreachable. Command queued for automatic re-dispatch on Cloud Traffic (:8867/8866).")

def clear_pending_ir():
    """Clears pending IR command."""
    global PENDING_IR_COMMAND
    with PENDING_IR_LOCK:
        if PENDING_IR_COMMAND:
            PENDING_IR_COMMAND = None

def get_pending_ir_status():
    """Returns a copy of the pending IR status dictionary."""
    with PENDING_IR_LOCK:
        if not PENDING_IR_COMMAND:
            return None
        return dict(PENDING_IR_COMMAND)

