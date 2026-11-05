# -*- coding: utf-8 -*-
import datetime
import time
import appdaemon.plugins.hass.hassapi as hass
import os, yaml, glob, hashlib

from lib.blinds_lib import Blind, EVENING_HOUR_THRESHOLD, DEFAULT_EVENT_KILL_SWITCH_DURATION

class Blinds(hass.Hass):
    DEFAULT_TILT_DELAY = 85

    def initialize(self):
        """Main AppDaemon entrypoint for blinds control."""
        self.log("Initializing blinds...")

        # --- Internal runtime state ---
        self.state = "IDLE"
        self.is_moving = False
        self.manual_override_until = None
        self.pending_kill = False
        self.last_cmd_ts = 0
        self.watchdog_handle = None
        self.error_count = 0
        self.last_error = None
        self.pending_intent = None   # (position, tilt)
        self.pending_command = None

        # ───────────────────────────────
        # External app instances (kept from your version)
        # ───────────────────────────────
        self.max_temp_app = self.get_app("max_temp")
        self.sun_app = self.get_app("sun")

        # Wait for dependencies to report ready()
        for _trials in range(60):  # wait up to 30 seconds
            max_ready = getattr(self.max_temp_app, "ready", lambda: False)()
            sun_ready = getattr(self.sun_app, "ready", lambda: False)()
            if max_ready and sun_ready:
                break
            self.log(f"Waiting for dependencies... max_temp={max_ready}, sun={sun_ready}", level="DEBUG")
            time.sleep(0.5)
        if _trials + 1 == 60:
            self.log(f"Dependency wait loop raised. Continuing initialization.", level="WARNING")

        # ───────────────────────────────
        # Instantiate logic core
        # ───────────────────────────────
        self.b = Blind(blinds_app=self, **self.args["blind_config"])
        self.blind = self.args["blind"]
        if 'blind_tilt_position' not in self.args:
            self.blind_tilt = self.blind
        else:
            self.blind_tilt = self.args["blind_tilt_position"]

        # ───────────────────────────────
        # Adaptive periodic evaluation setup
        # ───────────────────────────────
        self.TICK_INTERVAL = 180  # seconds between evaluations
        app_name = getattr(self, "name", "unknown")

        # ───────────────────────────────
        # Locate apps.yaml dynamically
        # ───────────────────────────────
        apps_yaml_paths = []

        # 1️⃣ Add-on install (hashed folder like /addon_configs/a0d7b954_appdaemon)
        addon_candidates = glob.glob("/addon_configs/*_appdaemon/apps.yaml")
        apps_yaml_paths.extend(addon_candidates)

        # 2️⃣ Typical Home Assistant Core or manual setup
        apps_yaml_paths += [
            "/config/appdaemon/apps.yaml",
            "/config/apps.yaml",
            "/config/apps/apps.yaml",
        ]

        # 3️⃣ Relative path (for developer/manual install)
        try:
            current_dir = os.path.dirname(__file__)
            parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
            rel_path = os.path.join(parent_dir, "apps.yaml")
            apps_yaml_paths.append(rel_path)
        except Exception:
            pass

        # ───────────────────────────────
        # Parse the first valid file found
        # ───────────────────────────────
        total_blinds = 0
        for path in apps_yaml_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        config = yaml.safe_load(f) or {}
                    for name, data in config.items():
                        if isinstance(data, dict) and data.get("module") == "blinds":
                            total_blinds += 1
                    self.log(f"[Init] Found {total_blinds} blinds in {path}")
                    break
                except Exception as e:
                    self.log(f"[WARN] Could not read {path}: {e}", level="WARNING")

        # ───────────────────────────────
        # Fallback if parsing failed
        # ───────────────────────────────
        if total_blinds == 0:
            total_blinds = int(self.args.get("total_blinds", 6))
            self.log(f"[WARN] Falling back to total_blinds={total_blinds}", level="WARNING")

        self.NUM_BLINDS = total_blinds

        # ───────────────────────────────
        # Evenly distribute tick offsets
        # ───────────────────────────────
        # Use SHA1 and take the last bytes directly as a number between 0 and 1
        h_bytes = hashlib.sha1(app_name.encode()).digest()
        h_val = int.from_bytes(h_bytes[:8], "big")  # use 8 bytes = 64 bits of entropy
        fraction = (h_val % 10**8) / 10**8          # normalized to [0, 1)

        offset = fraction * self.TICK_INTERVAL
        next_tick = datetime.datetime.now() + datetime.timedelta(seconds=offset)

        # First evaluation immediately
        self.tick(None)

        # Periodic evaluation every 3 min, staggered
        self.run_every(self.tick, next_tick, self.TICK_INTERVAL)

        # ───────────────────────────────
        # Nightly reset for max/min outside temp
        # ───────────────────────────────
        self.run_daily(self.set_max_outside_temp, datetime.time(1, 1, 3))

        # Ensure default sensor for yesterday's min temp
        if "min_temp_sensor_value_yesterday" not in self.args:
            self.args["min_temp_sensor_value_yesterday"] = (
                "input_number.yesterdays_min_outside_temp_over_24_hours"
            )

        # Initialize max/min outside temp now
        self.set_max_outside_temp(None)

        # ───────────────────────────────
        # Optional sensors & listeners
        # ───────────────────────────────
        if "contact" in self.args:
            try:
                self.b.SetDoorType()
            except Exception:
                pass
            self.listen_state(
                self.window_closed,
                entity_id=self.args["contact"],
                new="off",
                old="on",
            )

        if "wind_alarm" in self.args:
            self.listen_state(
                self.wind_alarm_off,
                entity_id=self.args["wind_alarm"],
                new="off",
                old="on",
            )

        if "dawn_lights" in self.args:
            for light in self.args["dawn_lights"]:
                self.listen_state(self.light_on, entity_id=light, new="on", old="off")
                self.listen_state(self.light_off, entity_id=light, new="off", old="on")

        self.log(
            f"[Init] {'app_name'} ready: "
            f"{self.NUM_BLINDS} blinds total | "
            f"tick={self.TICK_INTERVAL}s | offset={offset:.1f}s"
        )


    # ----------------------
    # Event callbacks
    # ----------------------
    def window_closed(self, entity, attribute, old, new, kwargs):
        if "contact" in self.args:
            self.log(
                f"Window {self.args['contact']} closed. "
                f"Kill switch for {DEFAULT_EVENT_KILL_SWITCH_DURATION} min activated."
            )
            self.b.SetWindowClosed()

    def wind_alarm_off(self, entity, attribute, old, new, kwargs):
        self.log("Wind alarm is off, releasing kill switch.")
        self.release_kill_switch(None)

    def light_on(self, entity, attribute, old, new, kwargs):
        # Keep Previous behavior: raise dark threshold when interior light is on
        self.log(f"Raising lux dark threshold to {self.sun_app.get_Lux_dark_with_light_inside()} (light ON).", level="DEBUG")
        try:
            self.b.SetLuxDark(self.sun_app.get_Lux_dark_with_light_inside())
        except Exception:
            pass

    def light_off(self, entity, attribute, old, new, kwargs):
        # Only reset when ALL dawn_lights are off (kept from Previous)
        for light in self.args.get("dawn_lights", []):
            if self.get_state(light) == "on":
                return

        self.log(f"Resetting lux dark threshold to {self.sun_app.get_lux_dark()} (all lights OFF).", level="DEBUG")
        try:
            self.b.SetLuxDark(self.sun_app.get_lux_dark())
        except Exception:
            pass

        # Evening safeguard from Previous: if after 15:00, blinds down (0%), hold them with kill switch
        if datetime.datetime.now().hour > EVENING_HOUR_THRESHOLD:
            pos = self.get_state(self.args["blind"], attribute="current_position")
            if pos is not None:
                try:
                    if int(pos) == 0:
                        self.b.SetKillSwitch(DEFAULT_EVENT_KILL_SWITCH_DURATION)
                except Exception:
                    pass

    # ----------------------
    # Helpers
    # ----------------------
    def is_not_a_number(self, value):
        return value == 'unknown' or value == 'unavailable' or value is None

    def evaluate_runtime(self):
        """Read optional per-blind runtime; default to tilt delay."""
        default_runtime = self.DEFAULT_TILT_DELAY
        if "blind_runtime" not in self.args:
            return default_runtime

        try:
            return float(self.get_state(self.args["blind_runtime"]))
        except (TypeError, ValueError):
            self.log("Invalid blind_runtime value, using default.")
            return default_runtime

    def _get_inside_temperature(self):
        """Best-effort inside temp read with/without thermostat attribute."""
        # If user set a flag saying the entity isn't a climate/thermostat
        if self.args.get('inside_temperature_is_no_thermostat'):
            t = self.get_state(self.args["inside_temperature"])
            if t is not None:
                return t

        # Try climate attribute first (classic setup)
        t = self.get_state(self.args.get('inside_temperature'), attribute='current_temperature')
        if t is not None:
            return t

        # Fallback: plain sensor value
        t = self.get_state(self.args.get("inside_temperature"))
        if t is not None:
            return t

        self.log("Cannot read inside temperature", level="ERROR")
        return "unknown"

    def get_valid_knx_position(self):
        """
        Safely retrieves the current KNX position for the blind.
        Handles unknown or missing states gracefully without blocking AppDaemon.
        Returns:
            int: Current position (0–100)
            None: If no valid position available yet
        """
        pos = self.get_state(self.args["blind"], attribute="current_position")

        if pos in [None, "unknown"]:
            if not hasattr(self, "knx_first_unknown_ts"):
                self.knx_first_unknown_ts = self.datetime()
                self.knx_last_valid_pos = None
                self.log("KNX position unknown (startup or bus delay). Will retry in 30s.", level="WARNING")
                self.run_in(self.retry_knx_sync, 30)
                return None

            delay = (self.datetime() - self.knx_first_unknown_ts).total_seconds()

            if delay < 300:  # tolerate 5 minutes
                self.log(f"KNX position still unknown after {int(delay)}s, retrying later.", level="WARNING")
                self.run_in(self.retry_knx_sync, 30)
                return None

            # Fallback after 5 minutes
            self.log("KNX feedback missing >5 min, using last known position or fallback=50.", level="WARNING")
            return getattr(self, "knx_last_valid_pos", None) or 50

        try:
            self.knx_last_valid_pos = int(pos)
            if hasattr(self, "knx_first_unknown_ts"):
                del self.knx_first_unknown_ts
            return self.knx_last_valid_pos
        except Exception as e:
            self.log(f"Error parsing KNX position ({pos}): {e}", level="ERROR")
            return getattr(self, "knx_last_valid_pos", None) or 50

    def retry_knx_sync(self, kwargs):
        pos = self.get_state(self.args["blind"], attribute="current_position")
        if pos not in [None, "unknown"]:
            try:
                self.knx_last_valid_pos = int(pos)
            except Exception:
                self.knx_last_valid_pos = 50
            self.log(f"KNX position restored: {pos}", level="INFO")
            # run a full evaluation
            self.evaluate()
        else:
            self.log("KNX still unknown after retry. Keeping current state.", level="WARNING")
    
    def set_state_reason(self, reason):
        self.log(reason)
        obj = "input_text.%s_status" % self.args["blind"].replace("cover.", "")
        self.call_service("input_text/set_value", entity_id=obj, value=reason) 



    def _safe_call_service(self, domain: str, service: str, **kwargs):
        """
        Safe service call with fine-grained rate limiting.

        Keep this synchronous and short. Waiting for an async callback from inside
        an AppDaemon callback can block the worker thread and leave master locks set.
        """

        COOLDOWN = 5              # seconds between identical calls
     
        # --- Build unique key for this call ---
        key_parts = [domain, service]
        if "entity_id" in kwargs:
            key_parts.append(str(kwargs["entity_id"]))
        for k, v in sorted(kwargs.items()):
            if k != "entity_id":
                key_parts.append(f"{k}:{v}")
        call_key = "|".join(key_parts)

        # --- Rate limiting ---
        now = time.time()
        if not hasattr(self, "_last_service_calls"):
            self._last_service_calls = {}
        last_call = self._last_service_calls.get(call_key, 0)
        if now - last_call < COOLDOWN:
            self.log(f"[GATE] Skipping duplicate within {COOLDOWN}s: {call_key}", level="WARNING")
            return
        self._last_service_calls[call_key] = now

        # --- Build service string ---
        domain_service = f"{domain}/{service}"

        try:
            self.call_service(domain_service, **kwargs)
            self.log(f"[SAFE] Executed {domain_service} {kwargs}", level="DEBUG")
        except Exception as e:
            self.log(f"[SAFE] FAILED {domain_service}: {e}", level="ERROR")


    def release_kill_switch(self, _unused):
        self.log("KillSwitch released")
        self.b.ReleaseKillSwitch()

    # ----------------------
    # Periodic tick & evaluation
    # ----------------------
    def tick(self, _unused):
        if self._movement_pending_active():
            self.b.UnsetMasterLock()
            self.set_state_reason("Movement in progress. Waiting for KNX feedback.")
            return

        # prevent concurrency while a movement scenario is running
        if self.b.GetMasterLock():
            self.log(f"Masterlock active for {self.args['blind']}")
            return

        # Global kill-switch (Previous behavior)
        try:
            global_kill_switch = self.get_state("input_boolean.raffstore_kill_switch")
            if global_kill_switch == 'on':
                self.set_state_reason("Global Kill switch is on. All blinds are controlled manually.")
                return
        except Exception:
            pass

        # Outside temperature via max_temp_app (New behavior)
        outside_temp = self.max_temp_app.get_outside_temperature()
        if self.is_not_a_number(outside_temp):
            self.set_state_reason('Unknown outside temperature. Doing nothing.')
            return
        self.b.SetOutsideTemperature(float(outside_temp))


        # Inside temperature (merged robust read)
        inside_temp = self._get_inside_temperature()
        if self.is_not_a_number(inside_temp):
            self.set_state_reason("Unknown inside temperature.")
            return
        self.b.SetInsideTemperature(float(inside_temp))

        # Lux + sun geometry (New behavior)
        try:
            self.b.SetLux(self.sun_app.get_lux_last_10_minutes())
        except Exception:
            # fallback to previous helper entity
            try:
                self.b.SetLux(float(self.get_state("input_number.sun_lux_10_minute_average")))
            except Exception:
                pass

        try:
            self.b.SetAzimuth(float(self.get_state("sun.sun", attribute="azimuth")))
            self.b.SetElevation(float(self.get_state("sun.sun", attribute="elevation")))
        except Exception:
            pass

        # Contact state every tick (Previous)
        if "contact" in self.args:
            try:
                self.b.SetReedContact(self.get_state(self.args["contact"]) == "on")
            except Exception:
                pass

        # Wind lock every tick (support both ways)
        wind_lock = False
        try:
            if "wind_alarm" in self.args:
                wind_lock = (self.get_state(self.args["wind_alarm"]) == "on")
            else:
                wind_lock = (self.get_state(self.app_config["wind"]["wind_alarm"]) == "on")
        except Exception:
            pass
        self.b.SetWindLock(wind_lock)

        # Do the full evaluation & act (Previous behavior)
        self.evaluate()

    def evaluate(self):
        """Check if we need to do something with the blinds, then act."""
        pos = self.get_valid_knx_position()
        if pos is None:
            self.set_state_reason("Unknown real-life KNX position. Waiting for KNX feedback.")
            return

        # Tilt position: either same entity as blind (tilt attr) or a dedicated 'blind_tilt_position'
        if 'blind_tilt_position' not in self.args:
            tilt = self.get_state(self.blind, attribute="current_tilt_position")
        else:
            tilt = self.get_state(self.blind_tilt, attribute="current_position")

        # Optional 10% precision mode
        if self.args.get("use_10_percent_precision"):
            pos = int(pos / 10) * 10
            if tilt is not None:
                try:
                    tilt = int(int(tilt) / 10) * 10
                except Exception:
                    pass

        self.knx_current_angle = tilt
        self.b.SetKNXPositions(pos, tilt)
        action_needed = self.b.Evaluate()

        for log_line in self.b.FlushLog():
            self.log(f"[Evaluate] {log_line}")


        self.set_state_reason(self.b.GetDesiredPositionReason())

        if action_needed:
            self.b.SetMasterLock()
            self._move_blind(pos, tilt)

    # ----------------------
    # Move blind
    # ----------------------

    def _set_state(self, new_state):
        if new_state != self.state:
            self.log(f"[STATE] {self.state} → {new_state}")
            self.state = new_state

    def _move_blind(self, current_pos, current_angle):
        """Safely move blind and tilt to target positions, respecting manual override cooldown."""
        entity = self.blind
        tilt_entity = self.blind_tilt
        target_pos = self.b.GetDesiredPosition()
        target_angle = self.b.GetDesiredAngle()
        immediate_tilt = (
            self.args.get("tilt_mode") == "immediate"
            and "blind_tilt_position" not in self.args
        )

        # --- 1️⃣ Skip automation during manual override grace period ---
        if self.manual_override_active():
            hold_time = self.b.GetKillSwitchHoldTime()
            self.log(
                f"[MANUAL] Skipping automation (cooldown active, {hold_time}h remaining)",
                level="DEBUG",
            )
            self.b.UnsetMasterLock()
            return

        # --- 2️⃣ Detect manual movement only if automation target did not change ---
        last_command_pos = getattr(self, "last_command_pos", current_pos)
        last_command_angle = getattr(self, "last_command_angle", current_angle)
        position_target_changed = abs(target_pos - last_command_pos) > 5
        angle_target_changed = (
            target_angle is not None
            and last_command_angle is not None
            and abs(target_angle - last_command_angle) > 5
        )
        position_changed_unexpectedly = abs(current_pos - last_command_pos) > 5
        angle_changed_unexpectedly = (
            target_angle is not None
            and last_command_angle is not None
            and abs(current_angle - last_command_angle) > 5
        )

        if (
            (position_changed_unexpectedly or angle_changed_unexpectedly)
            and not (position_target_changed or angle_target_changed)
        ):
            self.last_manual_override = datetime.datetime.now()
            hold_time = self.b.GetKillSwitchHoldTime()
            self.log(
                f"[MANUAL] User override detected (pos={current_pos}, tilt={current_angle}). "
                f"Automation paused for {hold_time}h.",
                level="WARNING",
            )
            self.b.UnsetMasterLock()
            return

        # --- 3️⃣ If already moving, skip ---
        if getattr(self, "moving", False):
            self.log("[MOVE] Skipped: blind still moving", level="DEBUG")
            self.b.UnsetMasterLock()
            return

        # --- 4️⃣ Compute movement ---
        if abs(current_pos - target_pos) > 5 or abs(current_angle - target_angle) > 5:
            self.moving = True
            self.last_command_pos = target_pos
            self.last_command_angle = target_angle
            self.b.UpdateLastStateFromDesiredState()
            travel_time = getattr(self, "travel_time_s", 90)
            self._set_pending_command(target_pos, target_angle, travel_time + 5)

            self.log(
                f"[MOVE] Moving to {target_pos}% | tilt -> {target_angle}",
                level="INFO",
            )
            self.log(f"DEBUG : About to move blind {entity} to {target_pos} (tilt={target_angle})", level='INFO')

            # Run movement asynchronously (no blocking)
            if abs(current_pos - target_pos) > 5:
                self._safe_call_service("cover", "set_cover_position", entity_id=entity, position=target_pos)

            if target_angle is None:
                self.log("Blinds do not support tilt. Skipping tilt.")
                self.b.UnsetMasterLock()
            elif immediate_tilt:
                self._set_tilt_position(tilt_entity, target_angle)
                self.b.UnsetMasterLock()
            else:
                delay = self.DEFAULT_TILT_DELAY
                stop = False
                if "blind_runtime" in self.args and target_pos == self.b.DOWN:
                    delay = self.evaluate_runtime()
                    stop = True
                self.run_in(
                    self.set_tilt,
                    delay,
                    tilt_position=target_angle,
                    knx_current_angle=current_angle,
                    stop=stop
                )

            # Reset moving flag after travel time
            self.run_in(lambda _: setattr(self, "moving", False), travel_time)
            self.b.UnsetMasterLock()
        else:
            self.b.UnsetMasterLock()

    def _set_pending_command(self, position, angle, duration):
        self.pending_command = {
            "position": position,
            "angle": angle,
            "until": datetime.datetime.now() + datetime.timedelta(seconds=duration)
        }

    def _movement_pending_active(self):
        pending_command = getattr(self, "pending_command", None)
        if not pending_command:
            return False

        if datetime.datetime.now() < pending_command["until"]:
            self.log(
                f"[MOVE] Pending command active until {pending_command['until']:%H:%M:%S} "
                f"(pos={pending_command['position']}, tilt={pending_command['angle']})",
                level="DEBUG"
            )
            return True

        self.pending_command = None
        return False

    def _set_tilt_position(self, tilt_entity, tilt_position):
        if 'blind_tilt_position' not in self.args:
            self._safe_call_service(
                "cover", "set_cover_tilt_position", entity_id=tilt_entity, tilt_position=tilt_position
            )
        else:
            self._safe_call_service(
                "cover", "set_cover_position", entity_id=tilt_entity, position=tilt_position
            )

    def set_tilt(self, kwargs):
        if kwargs.get('stop'):
            self.log("Stopping blind for tilt adjustment.")
            self._safe_call_service("cover", "stop_cover", entity_id=self.blind)
            time.sleep(1.0)

        tilt_position = kwargs.get('tilt_position')
        self.log(f"Changing tilt for {self.blind} from {self.knx_current_angle} to {tilt_position}")
        self._set_tilt_position(self.blind_tilt, tilt_position)
        self.b.UnsetMasterLock()

    def manual_override_active(self):
        """Return True if a manual override cooldown is still active."""
        if not hasattr(self, "last_manual_override"):
            return False

        delta = datetime.datetime.now() - self.last_manual_override
        hold_time_sec = self.b.GetKillSwitchHoldTime() * 3600  # convert hours to seconds

        return delta.total_seconds() < hold_time_sec


    # ----------------------
    # Max/Min outside temperature
    # ----------------------
    def set_max_outside_temp(self, _unused):
        """
        Prefer data from max_temp app (New); fallback to Previous entities.
        """
        try:
            max_val, min_val = self.max_temp_app.get_yesterday_extremes()
            msg = self.b.SetMaxOutsideTemperature(max_val, min_val)
            self.log(msg)
            return
        except Exception as e:
            self.log(f"max_temp_app.get_yesterday_extremes failed: {e}. Falling back to entities.", level="WARNING")

        # Fallback to Previous behavior with entities
        try:
            max_temp = float(self.get_state(self.app_config["max_temp"]["max_temp_sensor_yesterday"]))
        except Exception:
            max_temp = 24
            self.log(f"Defaulting max temp to {max_temp}", level="WARNING")

        try:
            min_temp = float(self.get_state(self.args["min_temp_sensor_value_yesterday"]))
        except Exception:
            min_temp = 21
            self.log(f"Defaulting min temp to {min_temp}", level="WARNING")

        msg = self.b.SetMaxOutsideTemperature(max_temp, min_temp)
        self.log(msg)

    # ----------------------
    # Watchdog
    # ----------------------
    def _start_watchdog(self, timeout_s=30):
        """Placeholder for movement watchdog (Step 3)."""
        if self.watchdog_handle:
            self.cancel_timer(self.watchdog_handle)
        self.watchdog_handle = self.run_in(self._watchdog_expired, timeout_s)

    def _watchdog_expired(self, kwargs):
        self.log("[WATCHDOG] Movement timeout — resetting state.", level="WARNING")
        self.is_moving = False
        self._set_state("IDLE")
