# -*- coding: utf-8 -*-
import sys
import types
import unittest
import datetime


appdaemon_module = types.ModuleType("appdaemon")
plugins_module = types.ModuleType("appdaemon.plugins")
hass_module = types.ModuleType("appdaemon.plugins.hass")
hassapi_module = types.ModuleType("appdaemon.plugins.hass.hassapi")
yaml_module = types.ModuleType("yaml")


class FakeHass:
    pass


hassapi_module.Hass = FakeHass
yaml_module.safe_load = lambda _stream: {}
sys.modules.setdefault("appdaemon", appdaemon_module)
sys.modules.setdefault("appdaemon.plugins", plugins_module)
sys.modules.setdefault("appdaemon.plugins.hass", hass_module)
sys.modules.setdefault("appdaemon.plugins.hass.hassapi", hassapi_module)
sys.modules.setdefault("yaml", yaml_module)

from blinds import Blinds
from lib.blinds_lib import Blind


class FakeBlind:
    DOWN = 0

    def __init__(self, position, angle):
        self.position = position
        self.angle = angle
        self.master_lock_unset = False
        self.last_state_updates = 0

    def GetDesiredPosition(self):
        return self.position

    def GetDesiredAngle(self):
        return self.angle

    def UnsetMasterLock(self):
        self.master_lock_unset = True

    def UpdateLastStateFromDesiredState(self):
        self.last_state_updates += 1

    def GetKillSwitchHoldTime(self):
        return 1

    def GetMasterLock(self):
        raise AssertionError("tick should return before checking master lock")


class FakeBlindsApp:
    def __init__(self):
        self.logs = []

    def log(self, message, **kwargs):
        self.logs.append((message, kwargs))

    def run_in(self, callback, delay, **kwargs):
        return None


class TestBlinds(unittest.TestCase):
    def setUp(self):
        self.app = Blinds.__new__(Blinds)
        self.app.args = {
            "blind": "cover.salle_manger",
            "tilt_mode": "immediate"
        }
        self.app.blind = "cover.salle_manger"
        self.app.blind_tilt = "cover.salle_manger"
        self.app.b = FakeBlind(position=0, angle=0)
        self.app.knx_current_angle = 100
        self.service_calls = []
        self.scheduled_calls = []
        self.logs = []

        self.app._safe_call_service = self._safe_call_service
        self.app.call_service = self._call_service
        self.app.run_in = self._run_in
        self.app.log = self._log
        self.app.sleep = self._sleep

    def _call_service(self, service, **kwargs):
        self.service_calls.append((service, kwargs))

    def _safe_call_service(self, domain, service, **kwargs):
        self.service_calls.append((domain, service, kwargs))

    def _run_in(self, callback, delay, **kwargs):
        self.scheduled_calls.append((callback, delay, kwargs))

    def _log(self, message, **kwargs):
        self.logs.append((message, kwargs))

    def _sleep(self, _seconds):
        raise AssertionError("sleep must not be called from _safe_call_service")

    def test_immediate_tilt_sends_position_and_tilt_without_delay(self):
        self.app._move_blind(current_pos=100, current_angle=100)

        self.assertEqual([
            (
                "cover",
                "set_cover_position",
                {
                    "entity_id": "cover.salle_manger",
                    "position": 0
                }
            ),
            (
                "cover",
                "set_cover_tilt_position",
                {
                    "entity_id": "cover.salle_manger",
                    "tilt_position": 0
                }
            )
        ], self.service_calls)
        self.assertEqual([], [
            call for call in self.scheduled_calls
            if call[0] == self.app.set_tilt
        ])
        self.assertTrue(self.app.b.master_lock_unset)
        self.assertEqual(0, self.app.pending_command["position"])
        self.assertEqual(0, self.app.pending_command["angle"])
        self.assertEqual(1, self.app.b.last_state_updates)

    def test_safe_call_service_does_not_wait_for_async_fallback(self):
        self.app._safe_call_service = Blinds._safe_call_service.__get__(self.app, Blinds)
        self.app._safe_call_service("cover", "set_cover_position", entity_id="cover.salle_manger", position=0)

        self.assertEqual([
            (
                "cover/set_cover_position",
                {
                    "entity_id": "cover.salle_manger",
                    "position": 0
                }
            )
        ], self.service_calls)

    def test_manual_override_releases_master_lock(self):
        self.app.last_manual_override = datetime.datetime.now()

        self.app._move_blind(current_pos=100, current_angle=100)

        self.assertEqual([], self.service_calls)
        self.assertTrue(self.app.b.master_lock_unset)
        self.assertEqual(0, self.app.b.last_state_updates)

    def test_target_change_is_not_detected_as_manual_override(self):
        self.app.last_command_pos = 100
        self.app.last_command_angle = 10
        self.app.b.position = 0
        self.app.b.angle = 60

        self.app._move_blind(current_pos=100, current_angle=10)

        self.assertEqual([
            (
                "cover",
                "set_cover_position",
                {
                    "entity_id": "cover.salle_manger",
                    "position": 0
                }
            ),
            (
                "cover",
                "set_cover_tilt_position",
                {
                    "entity_id": "cover.salle_manger",
                    "tilt_position": 60
                }
            )
        ], self.service_calls)
        self.assertTrue(self.app.b.master_lock_unset)
        self.assertEqual(1, self.app.b.last_state_updates)

    def test_manual_override_still_detected_when_target_did_not_change(self):
        self.app.last_command_pos = 0
        self.app.last_command_angle = 60
        self.app.b.position = 0
        self.app.b.angle = 60

        self.app._move_blind(current_pos=100, current_angle=10)

        self.assertEqual([], self.service_calls)
        self.assertTrue(self.app.b.master_lock_unset)
        self.assertEqual(0, self.app.b.last_state_updates)

    def test_tick_skips_evaluation_while_command_is_pending(self):
        self.app.pending_command = {
            "position": 100,
            "angle": 100,
            "until": datetime.datetime.now() + datetime.timedelta(seconds=30)
        }

        self.app.tick(None)

        self.assertEqual([
            (
                "input_text/set_value",
                {
                    "entity_id": "input_text.salle_manger_status",
                    "value": "Movement in progress. Waiting for KNX feedback."
                }
            )
        ], self.service_calls)
        self.assertTrue(self.app.b.master_lock_unset)

    def test_evaluate_keeps_last_state_when_movement_is_needed(self):
        blind = Blind(
            blinds_app=FakeBlindsApp(),
            azimuth_entry=0,
            azimuth_exit=360,
        )
        blind.SetKNXPositions(0, 0)
        blind.last_position = 0
        blind.last_angle = 0

        def control():
            blind.SetDesiredPositions(100, 100, "test movement")
            return "test movement"

        blind.Control = control

        self.assertEqual(blind.BLIND_NEEDS_MOVING, blind.Evaluate())
        self.assertEqual(0, blind.last_position)
        self.assertEqual(0, blind.last_angle)

    def test_evaluate_syncs_last_state_when_positions_match(self):
        blind = Blind(
            blinds_app=FakeBlindsApp(),
            azimuth_entry=0,
            azimuth_exit=360,
        )
        blind.SetKNXPositions(100, 100)
        blind.last_position = 100
        blind.last_angle = 100

        def control():
            blind.SetDesiredPositions(100, 100, "already there")
            return "already there"

        blind.Control = control

        self.assertEqual(blind.NO_CHANGE, blind.Evaluate())
        self.assertEqual(100, blind.last_position)
        self.assertEqual(100, blind.last_angle)


if __name__ == "__main__":
    unittest.main()
