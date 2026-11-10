#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ambi Climate Comfort AI Model
-----------------------------
Calculates Canadian Humidex, user comfort evaluation, and manages comfort profile persistence.
"""

import math
import ambi_db
from models.config import hub_log

DEFAULT_COMFORT_PROFILE = {
    "auto_tune_enabled": True,
    "target_base_humidex": 26.0,
    "user_offset": 0.0,
    "temp_calibration_offset": -3.0,
    "humidity_calibration_offset": 4.0,
    "min_temp": 22,
    "max_temp": 27,
    "cooldown_minutes": 10,
    "last_tune_time": 0,
    "last_tune_action": "System Initialized",
    "history": []
}

def load_comfort_profile():
    """Loads comfort profile from SQLite database with fallback defaults."""
    try:
        prof = ambi_db.load_comfort_profile()
        res = DEFAULT_COMFORT_PROFILE.copy()
        res.update(prof)
        return res
    except Exception as e:
        hub_log(f"[-] Error loading comfort profile from DB: {e}")
        return DEFAULT_COMFORT_PROFILE.copy()

def save_comfort_profile(profile):
    """Saves comfort profile to SQLite database."""
    try:
        return ambi_db.save_comfort_profile(profile)
    except Exception as e:
        hub_log(f"[-] Error saving comfort profile to DB: {e}")
        return False

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
    """Evaluates thermal comfort on a 7-tier scale compared against personalized Humidex target."""
    if user_offset is None:
        user_offset = COMFORT_PROFILE.get("user_offset", 0.0)
    base_target = COMFORT_PROFILE.get("target_base_humidex", 26.0)
    target = base_target + user_offset

    if temp_c is None or humidity_rh is None:
        return {
            "humidex": None,
            "target_humidex": round(target, 1),
            "score": 0.0,
            "label": "กำลังอ่านค่าเซนเซอร์...",
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

