#!/usr/bin/env python3
"""
Ambi Climate MVC Automated Test Suite
-------------------------------------
Verifies Model-View-Controller architecture integrity, Humidex math,
AC state management, HomeKit/Homebridge endpoints, and Web Dashboard rendering.
"""

import sys
import os
import json
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ambi_hub
import models
import views
import controllers
from models.comfort import calculate_humidex, evaluate_comfort
from controllers.api_controller import AmbiAPIHandler


class DummyServer:
    server_port = 9090


class MockHTTPHandler:
    def __init__(self, path):
        self.path = path
        self.server = DummyServer()
        self.wfile_data = b''
        self.status_code = None
        self.headers = {}

    def send_response(self, code):
        self.status_code = code

    def send_header(self, k, v):
        self.headers[k] = v

    def end_headers(self):
        pass

    @property
    def wfile(self):
        class W:
            def __init__(self, outer):
                self.outer = outer
            def write(self, data):
                self.outer.wfile_data += data
        return W(self)


class TestAmbiMVC(unittest.TestCase):
    def test_01_models_loaded(self):
        """Verify models package and state initialization."""
        self.assertIsNotNone(models.AC_STATE)
        self.assertIn("temperature", models.AC_STATE)
        self.assertIn("power", models.AC_STATE)
        self.assertIsNotNone(models.COMFORT_PROFILE)
        self.assertIsNotNone(models.get_ambi_ip())

    def test_02_comfort_math(self):
        """Verify Canadian Humidex formula & comfort categorization."""
        # 28°C and 60% RH -> approx 35.0°C Humidex
        hx = calculate_humidex(28.0, 60.0)
        self.assertAlmostEqual(hx, 35.0, delta=0.5)

        # Evaluate comfort at 28°C / 60% RH (Hot)
        c = evaluate_comfort(28.0, 60.0)
        self.assertEqual(c["status_key"], "hot")
        self.assertIn("ร้อนมาก", c["label"])

        # Comfortable range
        c_comfy = evaluate_comfort(25.0, 50.0)
        self.assertEqual(c_comfy["status_key"], "comfortable")

    def test_03_view_dashboard(self):
        """Verify dashboard HTML view loads with valid structure."""
        html = views.get_dashboard_html()
        self.assertTrue(len(html) > 1000)
        self.assertIn("Ambi Climate", html)
        self.assertIn("<!DOCTYPE html>", html)

    def test_04_homebridge_status_endpoint(self):
        """Verify Homebridge /status & /api/homebridge/status endpoints."""
        for path in ('/status', '/api/homebridge/status'):
            mock = MockHTTPHandler(path)
            AmbiAPIHandler.handle_web_ui(mock)
            self.assertEqual(mock.status_code, 200)
            data = json.loads(mock.wfile_data.decode('utf-8'))
            self.assertIn("targetHeatingCoolingState", data)
            self.assertIn("targetTemperature", data)
            self.assertIn("currentHeatingCoolingState", data)
            self.assertIn("currentTemperature", data)
            self.assertIn("currentRelativeHumidity", data)

    def test_05_homebridge_target_controls(self):
        """Verify setting Target Temperature & HeatingCoolingState."""
        # Mock send_daikin_ir
        saved_send = controllers.hardware_controller.send_daikin_ir
        mock_calls = []
        def mock_send(temp=None, mode=None, fan=None, power=None, reason=""):
            mock_calls.append({"temp": temp, "mode": mode, "power": power})
            if temp is not None: models.AC_STATE['temperature'] = int(temp)
            if power is not None: models.AC_STATE['power'] = str(power)
            return "OK"

        controllers.hardware_controller.send_daikin_ir = mock_send
        controllers.api_controller.send_daikin_ir = mock_send

        try:
            # Set target temperature to 25
            m1 = MockHTTPHandler('/targetTemperature?value=25.0')
            AmbiAPIHandler.handle_web_ui(m1)
            self.assertEqual(m1.status_code, 200)
            self.assertEqual(models.AC_STATE['temperature'], 25)

            # Set HeatingCoolingState to Cool (2)
            m2 = MockHTTPHandler('/targetHeatingCoolingState?value=2')
            AmbiAPIHandler.handle_web_ui(m2)
            self.assertEqual(m2.status_code, 200)
            self.assertEqual(models.AC_STATE['power'], 'on')
        finally:
            controllers.hardware_controller.send_daikin_ir = saved_send
            controllers.api_controller.send_daikin_ir = saved_send

    def test_06_state_api(self):
        """Verify /api/state returns full JSON payload."""
        mock = MockHTTPHandler('/api/state')
        AmbiAPIHandler.handle_web_ui(mock)
        self.assertEqual(mock.status_code, 200)
        data = json.loads(mock.wfile_data.decode('utf-8'))
        self.assertEqual(data["status"], "OK")
        self.assertIn("ac_state", data)
        self.assertIn("comfort", data)
        self.assertIn("network", data)

    def test_07_feedback_api(self):
        """Verify /api/feedback adjusts comfort profile and offset."""
        saved_send = controllers.hardware_controller.send_daikin_ir
        def mock_send(**kwargs): return "OK"
        controllers.hardware_controller.send_daikin_ir = mock_send
        controllers.api_controller.send_daikin_ir = mock_send

        try:
            curr_offset = models.COMFORT_PROFILE.get("user_offset", 0.0)
            mock = MockHTTPHandler('/api/feedback?choice=cold')
            AmbiAPIHandler.handle_web_ui(mock)
            self.assertEqual(mock.status_code, 200)
            new_offset = models.COMFORT_PROFILE.get("user_offset", 0.0)
            self.assertAlmostEqual(new_offset, curr_offset + 0.5, delta=0.01)
        finally:
            controllers.hardware_controller.send_daikin_ir = saved_send
            controllers.api_controller.send_daikin_ir = saved_send

    def test_08_backward_compatibility_reexports(self):
        """Verify ambi_hub entry point re-exports all essential symbols."""
        self.assertTrue(hasattr(ambi_hub, "AC_STATE"))
        self.assertTrue(hasattr(ambi_hub, "send_daikin_ir"))
        self.assertTrue(hasattr(ambi_hub, "get_ambi_ip"))
        self.assertTrue(hasattr(ambi_hub, "update_ambi_ip"))
        self.assertTrue(hasattr(ambi_hub, "AmbiAPIHandler"))
        self.assertTrue(hasattr(ambi_hub, "calculate_humidex"))
        self.assertTrue(hasattr(ambi_hub, "evaluate_comfort"))
        self.assertTrue(hasattr(ambi_hub, "get_dashboard_html"))


if __name__ == '__main__':
    unittest.main()
