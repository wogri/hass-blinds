import appdaemon.plugins.hass.hassapi as hass

class TestAsyncGate(hass.Hass):
    def initialize(self):
        self.log("Initializing TestAsyncGate...")
        self.entity = "cover.volet_salon_porte_fenetre"

        # Reset internal timestamp
        self.last_call = 0
        self.call_interval = 2   # every 2s
        self.run_every(self._test_gate, "now", self.call_interval)

    def _safe_call_service(self, domain, service, **kwargs):
        import time
        now = time.time()
        if now - getattr(self, "last_call", 0) < 5:
            self.log("[GATE] Skipping service call (rate-limit).", level="WARNING")
            return
        self.last_call = now
        self.log(f"[GATE] Executing {domain}/{service} with {kwargs}", level="INFO")
        self.run_in(lambda _: self.call_service(f"{domain}/{service}", **kwargs), 0)

    def _test_gate(self, kwargs):
        self.log("Triggering test call ...")
        self._safe_call_service("cover", "set_cover_position", entity_id=self.entity, position=50)
