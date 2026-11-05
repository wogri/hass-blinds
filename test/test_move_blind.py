import appdaemon.plugins.hass.hassapi as hass
from datetime import datetime

class TestMoveBlind(hass.Hass):
    def initialize(self):
        self.log("Initializing TestMoveBlind...")
        self.entity = "cover.volet_salon_porte_fenetre"
        self.tilt_entity = "cover.volet_salon_porte_fenetre"
        self.moving = False
        self.last_command_pos = 0
        self.last_command_angle = 100

        # Simulate one tick every 30s
        self.run_every(self._test_move, "now", 30)

    def _safe_call_service(self, domain, service, **kwargs):
        self.log(f"[SAFE] Calling {domain}/{service} {kwargs}", level="INFO")
        self.run_in(lambda _: self.call_service(f"{domain}/{service}", **kwargs), 0)

    def _move_blind(self):
        if self.moving:
            self.log("[MOVE] Skipped: already moving", level="DEBUG")
            return

        self.moving = True
        target_pos = 30
        target_tilt = 15

        self.log(f"[MOVE] Moving to {target_pos}% | tilt → {target_tilt}°", level="INFO")

        self._safe_call_service("cover", "set_cover_position", entity_id=self.entity, position=target_pos)
        self._safe_call_service("cover", "set_cover_tilt_position", entity_id=self.tilt_entity, tilt_position=target_tilt)

        self.run_in(lambda _: setattr(self, "moving", False), 35)

    def _test_move(self, kwargs):
        self.log("Simulating tick at " + datetime.now().strftime("%H:%M:%S"))
        self._move_blind()
