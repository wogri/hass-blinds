import time
import datetime
import math
import yaml
from lib.sun_lib import Sun
from lib.hysteresis_lib import Hysteresis

EVENING_HOUR_THRESHOLD = 15
DEFAULT_EVENT_KILL_SWITCH_DURATION = 30

class Blind:
  """Entscheidet über die Rolladen-Situation"""

  UP = 100
  DOWN = 0

  NO_CHANGE = False
  BLIND_NEEDS_MOVING = True

  KILL_SWITCH_ON = 1
  KILL_SWITCH_OFF_NO_CHANGE = 2
  KILL_SWITCH_OFF_CHANGE_NEEDED = 3

  def __init__(self, blinds_app, azimuth_entry, azimuth_exit, elevation=None, azimuth=None,
               wind_lock=False, lux_last_10_minutes=None,
               outside_temperature=None, inside_temperature=None,
               manual_night_control=False,
               manual_day_control=False, ledge=None,
               window_azimuth_position=None, window_type='window',
               window_open=False,
               # max inside temperatur is when the blinds go down on cold days (< 21 degree maximum)
               max_inside_temperature_cold_day=25.0,
               # min inside temperatur is when the blinds go down on warm days (> 21 degree maximum)
               max_inside_temperature_warm_day=21.0,
               lux_blind_up_threshold=Sun.LUX_BLIND_UP_THRESHOLD,
               lux_blind_down_threshold=Sun.LUX_BLIND_DOWN_THRESHOLD,
               lux_dark=Sun.LUX_DARK,
               kill_switch_hold_time=4,
               disable_tilt=False,
               window_height=240):

    # master lock prevents any further changes in blinds until released.
    self.blinds_app = blinds_app
    self.master_lock = False
    self.elevation = elevation
    self.azimuth = azimuth
    self.azimuth_entry = azimuth_entry
    self.azimuth_exit = azimuth_exit
    self.lux_last_10_minutes = lux_last_10_minutes
    self.wind_lock = wind_lock
    self.ledge = ledge
    self.window_open = window_open
    # relative position of the window due to azimuth 0.
    self.window_azimuth_position = window_azimuth_position

    self.outside_temperature = outside_temperature
    self.inside_temperature = inside_temperature
    self.manual_night_control = manual_night_control
    self.manual_day_control = manual_day_control
    self.window_type = window_type
    self.last_position = None
    self.last_angle = None
    self.desired_position = None
    self.desired_angle = None
    self.desired_position_reason = None
    self.kill_switch_timeout = None

    self.max_inside_temperature_cold_day = max_inside_temperature_cold_day
    self.max_inside_temperature_warm_day = max_inside_temperature_warm_day

    # a parameter that determines how long to hold the kill switch. Unit is hours.
    self.kill_switch_hold_time = kill_switch_hold_time
    self.window_height = window_height

    # ---- Thresholds (base + current/adaptive) ----
    self.base_lux_blind_up_threshold = int(lux_blind_up_threshold)
    self.base_lux_blind_down_threshold = int(lux_blind_down_threshold)
    # Current thresholds actually used by logic (start with base)
    self.lux_blind_up_threshold = int(lux_blind_up_threshold)
    self.lux_blind_down_threshold = int(lux_blind_down_threshold)

    # Smoothing / hysteresis helpers
    self.previous_elevation = self.elevation
    self.logmsg = []
    self.disable_tilt = disable_tilt
    self.lux_dark = lux_dark
    self.log = self.blinds_app.log

    # Instance-bound lower/upper so they can read adaptive thresholds
    def _lower_fn(x, lux, old_x):
      """Return True if we should OPEN (lux low enough)."""
      hour = datetime.datetime.now().hour
      # Open quickly if clearly under up-threshold
      if lux < self.lux_blind_up_threshold:
        return True
      # Keep closed if clearly over down-threshold
      if lux > self.lux_blind_down_threshold:
        return False
      # Evening: allow reopening a bit above up_threshold to avoid staying shut
      if hour > EVENING_HOUR_THRESHOLD:
        return lux < int(self.lux_blind_up_threshold * 1.2)
      # Morning/mid-day: soften based on elevation
      if x is not None and x > 20:
        return lux < (self.lux_blind_up_threshold + int(x * 200))
      return lux < int(self.lux_blind_up_threshold * 1.5)

    def _upper_fn(x, lux, old_x):
      """Return True if we should CLOSE (lux high enough)."""
      hour = datetime.datetime.now().hour
      if lux > self.lux_blind_down_threshold:
        return True
      if lux < self.lux_blind_up_threshold:
        return False
      # After evening threshold we generally avoid new closures
      if hour > EVENING_HOUR_THRESHOLD:
        return False
      # If sun is already high, be a bit more aggressive
      if x is not None and x > 25:
        return lux > int(self.lux_blind_down_threshold * 0.8)
      return lux > int(self.lux_blind_down_threshold * 0.6)

    self._lower_fn = _lower_fn
    self._upper_fn = _upper_fn

    self.blind_hysteresis = Hysteresis(None, None, self._lower_fn, self._upper_fn)
    self.temperature_hysteresis = Hysteresis(max_inside_temperature_cold_day - 0.5,
                                             max_inside_temperature_cold_day)

  def __str__(self):
    return yaml.dump(self.__dict__, default_flow_style=False)

  def SetDoorType(self):
    self.window_type='door'
    self.log('Blind treated as door')

  def SetWindowClosed(self):
    if self.window_type == 'door':
      self.SetKillSwitch(DEFAULT_EVENT_KILL_SWITCH_DURATION)

  def FlushLog(self, force: bool = False):
      """
      Smart log flush: only emit new or changed messages since the last tick.
      Set self.debug_logs = True or call FlushLog(force=True) to print everything.

      Features:
      - Suppresses duplicates across ticks.
      - Detects cleared/removed messages.
      - Adds "(changed after X min YY s)" on message changes.
      - Keeps an internal history for timing context.
      """

      # --- Allow forcing all logs (debug mode) ---
      debug_mode = getattr(self, "debug_logs", False) or force

      # --- init buffers on first run ---
      if not hasattr(self, "_prev_log_snapshot"):
          self._prev_log_snapshot = []
      if not hasattr(self, "_log_history"):
          self._log_history = {}  # {msg: last_change_timestamp}

      # --- capture current tick messages ---
      unique_current = list(dict.fromkeys(self.logmsg))
      self.logmsg = []  # clear buffer immediately

      # --- if debug mode, just return them all ---
      if debug_mode:
          self._prev_log_snapshot = unique_current
          now = time.time()
          for msg in unique_current:
              self._log_history[msg] = now
          return unique_current

      # --- main change detection ---
      now = time.time()
      new_lines = []

      for msg in unique_current:
          if msg not in self._prev_log_snapshot:
              # New or changed message
              delta_str = ""
              if msg in self._log_history:
                  delta_t = now - self._log_history[msg]
                  mins, secs = divmod(int(delta_t), 60)
                  if mins or secs:
                      delta_str = f" (changed after {mins}m{secs:02d}s)"
              new_lines.append(msg + delta_str)
              self._log_history[msg] = now

      # --- detect cleared lines ---
      cleared = [m for m in self._prev_log_snapshot if m not in unique_current]
      for msg in cleared:
          last_seen = now - self._log_history.get(msg, now)
          mins, secs = divmod(int(last_seen), 60)
          new_lines.append(f"[Cleared] {msg} (after {mins}m{secs:02d}s)")
          self._log_history.pop(msg, None)

      # --- snapshot maintenance ---
      self._prev_log_snapshot = unique_current[-200:]
      if len(self._log_history) > 500:
          cutoff = now - 3600
          self._log_history = {m: t for m, t in self._log_history.items() if t > cutoff}

      return new_lines


  def SetAzimuth(self, value):
    self.azimuth = value

  def SetElevation(self, value):
    self.previous_elevation = self.elevation
    self.elevation = value

  def SetReedContact(self, value):
    self.window_open = value

  def SetOutsideTemperature(self, value):
    self.outside_temperature = value

  def SetInsideTemperature(self, value):
    self.inside_temperature = value

  def GetKillSwitchHoldTime(self):
    return self.kill_switch_hold_time

  # ---------------- Adaptive thresholds ----------------
  def _apply_adaptive_thresholds(self, max_out_temp: float):
    """
    Ajuste dynamiquement les seuils de luminosité selon la température max extérieure.
    
    - Par temps froid  (≤ 15°C) → on laisse entrer plus de soleil :
        → seuils plus élevés (fermeture plus tardive)
    - Par temps chaud (≥ 35°C) → on protège du soleil :
        → seuils plus bas (fermeture plus précoce)
    """
    try:
        t = float(max_out_temp)
    except Exception:
        t = 24.0  # Valeur par défaut tempérée

    # Clamp le facteur entre 0 (froid) et 1 (chaud)
    factor = min(1.0, max(0.0, (t - 15.0) / 20.0))

    # Échelles d’adaptation :
    #  15°C → +30 % (plus de soleil)
    #  35°C → -40 % (fermeture plus tôt)
    COLD_SCALE = 1.3
    HOT_SCALE = 0.6
    scale = COLD_SCALE - (COLD_SCALE - HOT_SCALE) * factor

    # Applique le facteur aux seuils de base
    self.lux_blind_down_threshold = int(self.base_lux_blind_down_threshold * scale)
    self.lux_blind_up_threshold   = int(self.base_lux_blind_up_threshold * scale)

    adaptive_line = f"[Adaptive] MaxTemp={t:.1f}C | scale={scale:.2f} | Down={self.lux_blind_down_threshold} | Up={self.lux_blind_up_threshold}"
    self.log(adaptive_line, level='DEBUG')

  def SetMaxOutsideTemperature(self, max_value, min_value):
    """
    Decides seasonal inside-temp hysteresis (existing behavior) AND
    applies adaptive lux thresholds based on max outside temperature (new).
    """
    # ---- existing seasonal logic for inside temperature hysteresis ----
    avg = (self.max_inside_temperature_cold_day + self.max_inside_temperature_warm_day)/2.0
    if max_value > 24:
      self.temperature_hysteresis = Hysteresis(self.max_inside_temperature_warm_day - 0.5,
                                               self.max_inside_temperature_warm_day)
      msg = "Minimum temperature to get down blinds is: %sC (seems like warm season)" % self.max_inside_temperature_warm_day
    elif max_value < 16:
      self.temperature_hysteresis = Hysteresis(self.max_inside_temperature_cold_day - 0.5,
                                               self.max_inside_temperature_cold_day)
      msg = "Minimum temperature to get down blinds is: %sC (seems like cold season)" % self.max_inside_temperature_cold_day
    else:
      if min_value < 10:
        self.temperature_hysteresis = Hysteresis(self.max_inside_temperature_cold_day - 0.5,
                                                 self.max_inside_temperature_cold_day)
        msg = "Mornings are cold, we heat the building up to %sC." % self.max_inside_temperature_cold_day
      else:
        offset = (max_value - 16) * 0.5
        threshold = 25 - offset
        self.temperature_hysteresis = Hysteresis(threshold - 0.5, threshold)
        msg = "Minimum temperature to get down blinds is: %sC (seems like transitional season)" % threshold

    # ---- NEW: adapt lux thresholds according to outside max temperature ----
    self._apply_adaptive_thresholds(max_value)

    return msg

  def SetWindLock(self, wind_lock):
    self.wind_lock = wind_lock

  def SetKNXPositions(self, position, angle):
    self.knx_current_position = int(position)
    if angle is None:
      self.knx_current_angle = None
    else:
      self.knx_current_angle = int(angle)

  def SetDesiredPositions(self, position, angle, reason):
    self.desired_position = position
    if self.disable_tilt:
      self.desired_angle = None
    else:
      self.desired_angle = angle
    self.desired_position_reason = reason

  def SetLuxDark(self, threshold):
    self.lux_dark = threshold

  def SetLux(self, average_value):
    self.lux_last_10_minutes = average_value

  def SetMasterLock(self):
    self.master_lock = True

  def UnsetMasterLock(self):
    self.master_lock = False

  def GetMasterLock(self):
    return self.master_lock

  def GetDesiredPosition(self):
    return self.desired_position

  def GetDesiredAngle(self):
    if self.disable_tilt:
      return None
    return self.desired_angle

  def GetDesiredPositionReason(self):
    return self.desired_position_reason

  def UpdateLastPositionFromKNX(self):
    self.last_position = self.knx_current_position
    self.last_angle = self.knx_current_angle

  def UpdateLastStateFromDesiredState(self):
      self.last_position = self.desired_position
      self.last_angle = self.desired_angle

  def Evaluate(self):
    kill_switch_status = self.GetKillSwitch()

    if kill_switch_status == self.KILL_SWITCH_ON:
      return self._handle_kill_switch_on()

    reason = self.Control()
    self.desired_position_reason = reason
    self.log(f"Raison: {reason}")

    if kill_switch_status == self.KILL_SWITCH_OFF_CHANGE_NEEDED:
      self._log_kill_switch_off()

    if self.last_position is None:
      self.UpdateLastPositionFromKNX()

    if self.desired_position is None and self.desired_angle is None:
      self.UpdateLastPositionFromKNX()
      return self.NO_CHANGE

    if self.desired_position is False and self.desired_angle is False:
      return self.NO_CHANGE

    if self._position_changed_by_user(kill_switch_status):
      return self.NO_CHANGE

    if self._positions_match():
      self.UpdateLastStateFromDesiredState()
      return self.NO_CHANGE

    return self.BLIND_NEEDS_MOVING

  def _handle_kill_switch_on(self):
    ts = datetime.datetime.fromtimestamp(self.kill_switch_timeout).strftime('%Y-%m-%d %H:%M:%S')
    reason = f"Kill Switch is on, release at {ts}"
    self.desired_position_reason = reason
    return self.NO_CHANGE

  def _log_kill_switch_off(self):
    self.log('Kill Switch was just turned off.')
    self.log(f"Desired Position: {self.desired_position}, Last Position: {self.last_position}, KNX Position: {self.knx_current_position}")

  def _position_changed_by_user(self, kill_switch_status):
    position_diff = abs(self.last_position - self.knx_current_position) > 10
    position_target_changed = self.desired_position != self.last_position

    if self.last_angle is not None and self.knx_current_angle is not None and not self.disable_tilt:
      angle_diff = abs(self.last_angle - self.knx_current_angle) > 10 
      angle_target_changed = self.desired_angle != self.last_angle
    else:
      angle_diff = False
      angle_target_changed = False

    if not self.disable_tilt:
      if self.last_angle is None or self.knx_current_angle is None:
        return True

    if position_diff and not position_target_changed and kill_switch_status != self.KILL_SWITCH_OFF_CHANGE_NEEDED:
      self.log(f"Turning Kill switch on due to position mismatch: last_postion: {self.last_position}, knx_current_position: {self.knx_current_position}, last_angle: {self.last_angle}, knx_current_angle: {self.knx_current_angle}")
      self.SetKillSwitch(self.kill_switch_hold_time * 60)
      return True

    if angle_diff and not angle_target_changed and kill_switch_status != self.KILL_SWITCH_OFF_CHANGE_NEEDED:
      self.log(f"Turning Kill switch on due to angle mismatch: last_postion: {self.last_position}, knx_current_position: {self.knx_current_position}, last_angle: {self.last_angle}, knx_current_angle: {self.knx_current_angle}")
      self.SetKillSwitch(DEFAULT_EVENT_KILL_SWITCH_DURATION)
      return True

    return False

  def _positions_match(self):
    return self.desired_position == self.knx_current_position and (
      self.desired_angle == self.knx_current_angle or self.disable_tilt)

  def SetKillSwitch(self, timeout):
      """
      Safely (re)arm the Kill Switch timer.

      This prevents the blind from being moved by automation for a defined duration
      (timeout in minutes). If the blind is currently moving, the Kill Switch
      activation will be delayed until movement finishes.

      Args:
          timeout (int or float): Duration in minutes for the kill switch.
      """

      now = int(time.time())

      # --- 1️⃣ Guard: prevent kill switch while moving ---
      if getattr(self, "moving", False):
          self.blinds_app.log(
              f"[KILL] Skipped activation — blind still moving, retrying in 5s (timeout={timeout} min)",
              level="WARNING",
          )
          # Schedule retry after short delay
          self.blinds_app.run_in(lambda _: self.SetKillSwitch(timeout), 5)
          return

      # --- 2️⃣ If already active, don't extend timer ---
      if getattr(self, "kill_switch_timeout", None) and self.kill_switch_timeout > now:
          remaining = int((self.kill_switch_timeout - now) / 60)
          self.desired_position_reason = "Kill Switch is ON"
          self.blinds_app.log(
              f"[KILL] Already active, {remaining} min remaining (no extension).",
              level="DEBUG",
          )
          return

      # --- 3️⃣ Parse and validate timeout value ---
      try:
          timeout_minutes = float(timeout)
      except Exception:
          timeout_minutes = getattr(self, "DEFAULT_EVENT_KILL_SWITCH_DURATION", 10)  # fallback
          self.blinds_app.log(
              f"[KILL] Invalid timeout provided, fallback to {timeout_minutes} min",
              level="WARNING",
          )

      # --- 4️⃣ Arm new Kill Switch timer ---
      self.kill_switch_timeout = now + int(timeout_minutes * 60)
      self.desired_position_reason = "Kill Switch is ON"
      self.blinds_app.log(
          f"[KILL] Activated for {timeout_minutes:.1f} min "
          f"(until {datetime.datetime.fromtimestamp(self.kill_switch_timeout).strftime('%H:%M:%S')})",
          level="INFO",
      )

      # --- 5️⃣ Schedule automatic reset ---
      def _auto_reset(_):
          # Only clear if the timer actually expired (avoid race with re-arm)
          if time.time() >= self.kill_switch_timeout:
              self.kill_switch_timeout = None
              self.blinds_app.log("[KILL] Timer expired — automation re-enabled.", level="INFO")

      self.blinds_app.run_in(_auto_reset, timeout_minutes * 60)


  def ReleaseKillSwitch(self):
    self.kill_switch_timeout = None
    self.UpdateLastStateFromDesiredState()

  def GetKillSwitch(self):
    if self.kill_switch_timeout and self.kill_switch_timeout < int(time.time()):
      self.ReleaseKillSwitch()
      return self.KILL_SWITCH_OFF_CHANGE_NEEDED
    if self.kill_switch_timeout:
      return self.KILL_SWITCH_ON
    return self.KILL_SWITCH_OFF_NO_CHANGE

  def SunUnderLedge(self):
    return (self.ledge * math.tan(math.radians(self.elevation)) / (
        math.cos(math.radians(self.window_azimuth_position - self.azimuth))) <
        self.window_height)

  def GetBlindSunAngle(self):
    angle = self.DOWN
    angle = int(round((10.0/9.0 * self.elevation) / 10) * 10) 
    return angle

  def ManualDayControl(self):
    day = False
    if self.manual_day_control:
      if isinstance(self.manual_day_control, str):
        try:
          day = datetime.datetime.strptime(self.manual_day_control, "%H:%M").time() > datetime.datetime.now().time()
        except ValueError:
          self.log("The manual day control time is not in the correct format and will default to 12:00, please use the format HH:MM", level="WARNING")
          day = datetime.datetime.now().hour < 12
      elif isinstance(self.manual_day_control, bool):
        if self.manual_day_control:
          day = datetime.datetime.now().hour < 12
      else:
        self.log("The manual day control time is not in the correct format and will default to 12:00, please use the format HH:MM", level="WARNING")
        day = datetime.datetime.now().hour < 12
    return day

  def ManualNightControl(self):
    night = False
    if self.manual_night_control:
      if isinstance(self.manual_night_control, str):
        try:
          night = datetime.datetime.strptime(self.manual_night_control, "%H:%M").time() < datetime.datetime.now().time()
        except ValueError:
          self.log("The manual day control time is not in the correct format and will default to 22:00, please use the format HH:MM", level="WARNING")
          night = datetime.datetime.now().hour > 22
      elif isinstance(self.manual_night_control, bool):
        if self.manual_night_control:
          night = datetime.datetime.now().hour > 22
      else:
        self.log("The manual day control time is not in the correct format and will default to 22:00, please use the format HH:MM", level="WARNING")
        night = datetime.datetime.now().hour > 22
    return night

  def SunHitsWindow(self):
    if self.azimuth_entry < self.azimuth_exit:
      return (self.azimuth > self.azimuth_entry and
              self.azimuth < self.azimuth_exit)
    else:
      return (self.azimuth > self.azimuth_entry or
              self.azimuth < self.azimuth_exit)

  def DayLight(self):
    return self.lux_last_10_minutes > Sun.LUX_DAYLIGHT

  def IntenseSun(self):
    # Uses adaptive lower/upper via hysteresis callbacks bound to self
    return self.blind_hysteresis.status_update(self.lux_last_10_minutes, self.elevation, self.previous_elevation)

  def Darkness(self):
    return self.lux_last_10_minutes < self.lux_dark

  def Dawn(self):
    return (self.lux_last_10_minutes >= Sun.LUX_DARK and
            self.lux_last_10_minutes <= Sun.LUX_DAYLIGHT)

  def DownBecauseOfDarkness(self):
    if self.manual_night_control:
      reason = 'it is dark, but this blind is controlled manually'
      self.DoNothing(reason)
    else:
      reason = 'Down because of darkness'
      self.Down(self.DOWN, self.DOWN, 'Down because of darkness')
    return reason

  def DownBecauseOfSun(self):
    if self.ledge:
      if self.SunUnderLedge():
        return self.Down(self.DOWN, self.GetBlindSunAngle(),
               'Blind goes down, Sun is reaching under the ledge')
      else:
        return self.DoNothing('doing nothing, ledge protects us from sun')
    else:
      return self.Down(self.DOWN, self.GetBlindSunAngle(),
             'Sun hits the window, closing blind')

  def DoNothing(self, reason):
    return self.SetDesiredPositions(None, None, reason)

  def Down(self, pos=DOWN, angle=DOWN, message='Blinds are down'):
    if self.window_open == True and self.window_type == 'door':
      return self.DoNothing('Blinds do not change on an open door')
    return self.SetDesiredPositions(pos, angle, message)

  def Up(self, message):
    if self.ManualDayControl() or self.ManualNightControl():
      return self.DoNothing('Blinds are controlled manually')
    else:
      return self.SetDesiredPositions(self.UP, self.UP, message)

  def Control(self):
    if self.wind_lock:
      return self._handle_wind_lock()

    if self.Darkness():
      return self._handle_darkness()
    
    if self.ManualNightControl():
      return self._handle_manual_night()

    if self.Dawn():
      return self._handle_dawn()

    if not self.SunHitsWindow():
      return self._handle_no_direct_sun()

    return self._handle_direct_sun()

  def _handle_wind_lock(self):
    reason = 'Wind Alarm: blinds go up to prevent damage'
    self.SetDesiredPositions(self.UP, self.UP, reason)
    return reason

  def _handle_darkness(self):
    if self.lux_dark == Sun.LUX_DARK_WITH_LIGHT_INSIDE:
      self.lux_dark += 200
    reason = self.DownBecauseOfDarkness()
    return reason

  def _handle_manual_night(self):
    reason = 'Manual night control active'
    self.Down(self.DOWN, self.DOWN, reason)
    return reason

  def _handle_dawn(self):
    if datetime.datetime.now().hour > EVENING_HOUR_THRESHOLD:
      reason = 'It dawns in the evening, blinds go up'
      self.Up(reason)
    else:
      reason = 'Not enough sun'
    return reason

  def _handle_no_direct_sun(self):
      """Handle case where sun does not directly hit the window."""
      if self.DayLight():
          extreme_heat = self._extreme_heat_test()
          if extreme_heat:
              reason = extreme_heat
              return reason

          reason = 'Sun has not reached the blind yet'
          self.Up(reason)
          return reason

      reason = 'Not enough daylight and sun does not hit window'
      self.DoNothing(reason)
      return reason

  def _handle_direct_sun(self):
      """Handle case where sun directly hits the window."""
      extreme_heat = self._extreme_heat_test()
      if extreme_heat:
          reason = extreme_heat
          return reason

      # If the sun is low in the morning (azimuth between 5° and 40°)
      if not self.IntenseSun() and 5 <= self.azimuth < 40:
          if self.temperature_hysteresis.status_update(self.inside_temperature):
              reason = 'Low sun but hot morning, blinds go down'
              self.DownBecauseOfSun()
              return reason
          else:
              reason = 'Morning sun not strong enough'
              self.Up(reason)
              return reason
      else:
          if self.temperature_hysteresis.status_update(self.inside_temperature):
              reason = 'Intense sun + inside temp high -> blinds go down'
              self.DownBecauseOfSun()
              return reason
          else:
              # S'il fait jour et que la luminosité est élevée mais la température est OK,
              # on doit vérifier si les stores sont encore fermés depuis la nuit.
              if self.knx_current_position == self.DOWN and self.DayLight() and not self.Darkness():
                  reason = 'Morning sun, inside temp OK -> blinds go up'
                  self.Up(reason)
                  return reason
              else:
                  reason = 'Intense sun but inside temp OK -> keep current position'
                  self.DoNothing(reason)
                  return reason

  def _extreme_heat_test(self):
      """
      Detect extreme heat conditions that force all blinds down.

      Conditions:
        - Activates if outside temperature ≥ 30°C and lux ≥ 12 000 lx,
          provided sun elevation is within a realistic range (5°–75°).
        - Ignores inside temperature (proactive cooling).
        - Deactivates only when temp < 28.5°C, lux < 8000 lx, or sun elevation < 5°.
        - Ensures blinds stay down for at least 30 minutes once triggered.
      """

      # --- Thresholds & hysteresis ---
      HEAT_ON  = 30.0
      HEAT_OFF = 28.5
      LUX_ON   = 12000
      LUX_OFF  = 8000
      ELEV_MIN = 5
      ELEV_MAX = 75
      MIN_DURATION_MIN = 30  # minimum time blinds stay down after activation

      # --- Access your existing state variables ---
      outside_temp = self.outside_temperature
      lux_avg = self.lux_last_10_minutes
      sun_elev = self.elevation

      # Initialize persistent attributes
      if not hasattr(self, "extreme_heat_active"):
          self.extreme_heat_active = False
          self.extreme_heat_timestamp = None

      # --- Activation logic ---
      if (
          not self.extreme_heat_active
          and outside_temp >= HEAT_ON
          and lux_avg >= LUX_ON
          and ELEV_MIN <= sun_elev <= ELEV_MAX
      ):
          self.extreme_heat_active = True
          self.extreme_heat_timestamp = datetime.datetime.now()  # record start time
          reason = f"Extreme heat ON ({outside_temp:.1f}°C, {lux_avg:.0f} lx, elev {sun_elev:.1f}°)"
          self.log(f"[ExtremeHeat] {reason}")
          self.Down(self.DOWN, self.DOWN, reason)
          return reason

      # --- Deactivation logic ---
      elif self.extreme_heat_active:
          # Time since activation
          elapsed = (datetime.datetime.now() - self.extreme_heat_timestamp).total_seconds() / 60.0

          # Only release after minimum duration and favorable conditions
          if (
              elapsed >= MIN_DURATION_MIN
              and (
                  outside_temp <= HEAT_OFF
                  or lux_avg <= LUX_OFF
                  or sun_elev < ELEV_MIN
              )
          ):
              self.extreme_heat_active = False
              reason = (
                  f"Extreme heat OFF after {elapsed:.0f} min "
                  f"({outside_temp:.1f}°C, {lux_avg:.0f} lx, elev {sun_elev:.1f}°)"
              )
              self.log(f"[ExtremeHeat] {reason}")
              return False
          
          reason = (
              f"Extreme heat ACTIVE, hold blinds down "
              f"({elapsed:.0f}/{MIN_DURATION_MIN} min, "
              f"{outside_temp:.1f}°C, {lux_avg:.0f} lx, elev {sun_elev:.1f}°)"
          )
          self.Down(self.DOWN, self.DOWN, reason)
          return reason

      # --- No change ---
      return False
