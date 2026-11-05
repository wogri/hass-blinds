import datetime

from blinds import Blinds


class MockApp:
    """Minimal fake AppDaemon context for unit testing."""
    def __init__(self):
        self.logs = []

    def log(self, msg, level="INFO"):
        print(f"{level}: {msg}")
        self.logs.append((level, msg))

    def run_in(self, callback, delay, **kwargs):
        """Simulate asynchronous scheduling (execute immediately)."""
        callback(kwargs)


class TestManualOverride:
    """Unit test for _move_blind manual override behavior."""

    def __init__(self):
        # Initialize fake AppDaemon app + Blinds object
        self.app = MockApp()
        self.blind = Blinds()
        self.blind.blinds_app = self.app
        self.blind.blind = "cover.volet_salon_porte_fenetre"
        self.blind.blind_tilt = "cover.volet_salon_porte_fenetre"
        self.blind.kill_switch_hold_time = 0.001  # ≈ 3.6 seconds cooldown for test
        self.blind.last_command_pos = 30
        self.blind.last_command_angle = 15

        # Inject our new helper and safe call service mocks
        self.blind._safe_call_service = self._mock_service_call
        self.calls = []

    def _mock_service_call(self, domain_service, **kwargs):
        """Capture all service calls for later assertions."""
        self.calls.append((domain_service, kwargs))
        self.app.log(f"[SAFE] Called {domain_service} with {kwargs}")

    def run(self):
        print("\n===== Running TestManualOverride =====")

        # Step 1: Normal move (should trigger service calls)
        self.blind._move_blind(current_pos=60, current_angle=80)
        assert self.calls, "Expected a movement call on first tick"

        # Step 2: Manual override detected (large deviation)
        self.calls.clear()
        self.blind._move_blind(current_pos=80, current_angle=100)
        assert not self.calls, "Manual override should not move blind"
        assert hasattr(self.blind, "last_manual_override"), "Should record timestamp"

        # Step 3: Immediate retry (within cooldown)
        self.calls.clear()
        self.blind._move_blind(current_pos=80, current_angle=100)
        assert not self.calls, "Should skip due to active cooldown"

        # Step 4: Simulate cooldown expiry
        self.blind.last_manual_override -= datetime.timedelta(seconds=10)
        self.blind._move_blind(current_pos=80, current_angle=100)
        assert self.calls, "After cooldown, automation should resume"

        print("✅ TestManualOverride passed successfully.")


if __name__ == "__main__":
    TestManualOverride().run()
