# -*- coding: utf-8
import time
import datetime
import math
import yaml
from sun_lib import Sun
from hysteresis_lib import Hysteresis

def lower_function(x, lux, old_x):
  if lux < 8000:
    return True
  # Return false fast if the light is too intense.
  if lux > Sun.LUX_BLIND_DOWN_THRESHOLD:
    return False
  # This is the case when the sun is falling, no more linear formulars.
  if datetime.datetime.now().hour > 15:
    if lux < Sun.LUX_BLIND_UP_THRESHOLD:
      return True
    else:
      return False
  # only if the elevation is high enough, introduce a fixed threshold.
  if (x > 30):
    if lux < Sun.LUX_BLIND_UP_THRESHOLD:
      return True
    else:
      return False
  y = 3000 * x - 50000
  if lux < y:
    return True
  return False

def upper_function(x, value, old_x):
  if value < 12000:
    return False
  if value > Sun.LUX_BLIND_DOWN_THRESHOLD:
    return True
  # When the sun is falling, don't do linear comparisons anymore, this really only makese sense in the morning.
  if datetime.datetime.now().hour > 15:
    return False
  y = 5000 * x - 55000
  if value > y:
    return True
  return False


class Blind:
  """Entscheidet über die Rolladen-Situation"""

  UP = 100
  DOWN = 0

  NO_CHANGE = False
  BLIND_NEEDS_MOVING = True

  KILL_SWITCH_ON = 1
  KILL_SWITCH_OFF_NO_CHANGE = 2
  KILL_SWITCH_OFF_CHANGE_NEEDED = 3

  def __init__(self, azimuth_entry, azimuth_exit, elevation=None, azimuth=None,
               wind_lock=False, lux_last_10_minutes=None,
               outside_temperature=None, inside_temperature=None,
               manual_night_control=False,
               manual_day_control=False, ledge=None,
               window_azimuth_position=None, window_type='window',
               window_open=False, alarm_lock=False,
               # max inside temperatur is when the blinds go down on cold days (< 21 degree maximum)
               max_inside_temperature_cold_day=25.0,
               # min inside temperatur is when the blinds go down on warm days (> 21 degree maximum)
               max_inside_temperature_warm_day=21.0,
               lux_blind_up_threshold=Sun.LUX_BLIND_UP_THRESHOLD,
               lux_blind_down_threshold=Sun.LUX_BLIND_DOWN_THRESHOLD,
               lux_dark=Sun.LUX_DARK,
               kill_switch_hold_time=8,
               disable_tilt=False,
               window_height=240):
    # master lock prevents any further changes in blinds until released.
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
    # self.kill_switch = kill_switch
    self.outside_temperature = outside_temperature
    self.inside_temperature = inside_temperature
    # when the blind should never go down in the nigh set this to true.
    self.manual_night_control = manual_night_control
    self.manual_day_control = manual_day_control
    self.window_type = window_type
    self.alarm_lock = alarm_lock
    self.last_position = None
    self.last_angle = None
    self.desired_position = None
    self.desired_angle = None
    self.desired_position_reason = None
    self.kill_switch_timeout = None
    self.max_inside_temperature_cold_day = max_inside_temperature_cold_day
    self.max_inside_temperature_warm_day = max_inside_temperature_warm_day
    # a parameter that determines how long to hold the kill switch.
    # can be configured per blind. Unit is hours.
    self.kill_switch_hold_time = kill_switch_hold_time
    self.window_height = window_height
    self.blind_hysteresis = Hysteresis(None,
                                       None,
                                       lower_function,
                                       upper_function)
    self.temperature_hysteresis = Hysteresis(max_inside_temperature_cold_day - 0.5,
                                             max_inside_temperature_cold_day)
    self.previous_elevation = self.elevation
    self.logmsg = []
    self.disable_tilt = disable_tilt
    self.lux_dark = lux_dark

  def __str__(self):
    return yaml.dump(self.__dict__, default_flow_style=False)

  def log(self, msg):
    self.logmsg.append(msg)

  def SetWindowClosed(self):
    if self.window_type == 'door':
      self.SetKillSwitch(30)

  def FlushLog(self):
    log = self.logmsg
    self.logmsg = []
    return log

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

  def SetMaxOutsideTemperature(self, max_value, min_value):
    # Actually, we don't care about the maximum outside temperature (it is
    # calculated for the last day). What we do care about is if we should
    # assume it is generally warm outside or if it is generally cold outside.
    # We adapt the maximum inside temperature when we think it is a cold day,
    # same for a warm day. People have different feelings when blinds should go
    # down for cold and warm days. At least my wife has.
    # 24 outside - 21 inside
    # 22 outside - 22 inside
    # 20 outside - 23 inside
    # 18 outside - 24 inside
    # 16 outside - 25 inside

    avg = (self.max_inside_temperature_cold_day + self.max_inside_temperature_warm_day)/2.0
    if max_value > 24:
      self.temperature_hysteresis = Hysteresis(self.max_inside_temperature_warm_day - 0.5,
                                               self.max_inside_temperature_warm_day)
      return "Minimum temperature to get down blinds is: %sC (seems like warm season)" % self.max_inside_temperature_warm_day
    elif max_value < 16:
      self.temperature_hysteresis = Hysteresis(self.max_inside_temperature_cold_day - 0.5,
                                               self.max_inside_temperature_cold_day)
      return "Minimum temperature to get down blinds is: %sC (seems like cold season)" % self.max_inside_temperature_cold_day
    else:
      if min_value < 10:
        self.temperature_hysteresis = Hysteresis(self.max_inside_temperature_cold_day - 0.5,
                                                 self.max_inside_temperature_cold_day)
        return "Mornings are cold, we heat the building up to %sC." % self.max_inside_temperature_cold_day 
      offset = (max_value - 16) * 0.5
      threshold = 25 - offset
      self.temperature_hysteresis = Hysteresis(threshold - 0.5, threshold)
      return "Minimum temperature to get down blinds is: %sC (seems like transitional season)" % threshold

  def SetLux(self, average_value):
    self.lux_last_10_minutes = average_value

  def SetAlarm(self, alarm):
    self.alarm_lock = alarm

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
    # desired position is None -> do nothing.
    # last position is None -> copy knx current position if kill switch is not set.
    # knx position and last position differ -> kill switch, do nothing until dusk.
    kill_switch_status = self.GetKillSwitch()
    if kill_switch_status == self.KILL_SWITCH_ON:
      self.desired_position_reason = 'Kill Switch is on, release at %s' % datetime.datetime.utcfromtimestamp(self.kill_switch_timeout).strftime('%Y-%m-%d %H:%M:%S')
      return self.NO_CHANGE

    self.Control()

    if kill_switch_status == self.KILL_SWITCH_OFF_CHANGE_NEEDED:
      #self.Control()
      #self.UpdateLastStateFromDesiredState()
      #if self.desired_position is None and self.desired_angle is None:
      #  self.UpdateLastPositionFromKNX()
      #  return self.NO_CHANGE
      #return self.BLIND_NEEDS_MOVING
      self.log('Kill Switch was just turned off.')
      self.log('Desired Position: %s, Last Position: %s, KNX Position: %s' % (
          self.desired_position, self.last_position, self.knx_current_position))

    # this is a situation where we just booted the application.
    if self.last_position is None:
      self.UpdateLastPositionFromKNX()
    # This makes sure that positions can be overridden when the system has no
    # opinion on blind positions without activating the kill switch.
    if self.desired_position is None and self.desired_angle is None:
      self.UpdateLastPositionFromKNX()
      return self.NO_CHANGE

    # This is when the engine doesn't have enough data and doesn't know what to
    # do next.
    if self.desired_position is False and self.desired_angle is False:
      return self.NO_CHANGE

    # this is when the system has an opinion and the user overrode the
    # situation manually. it means, we're not doing anything anymore. However,
    # we are also graceful and permit 10% difference.
    position_diff = abs(self.last_position - self.knx_current_position)
    if not self.disable_tilt:
      if self.last_angle is None or self.knx_current_angle is None:
        return self.NO_CHANGE
    angle_diff = abs(self.last_angle - self.knx_current_angle)
    if (position_diff > 10) and (
        kill_switch_status != self.KILL_SWITCH_OFF_CHANGE_NEEDED):
      self.log("Turning Kill switch on due to position mismatch: last_postion: %s, knx_current_position: %s, last_angle: %s, knx_current_angle: %s" % (self.last_position, self.knx_current_position, self.last_angle, self.knx_current_angle))
      self.SetKillSwitch(self.kill_switch_hold_time * 60)
      return self.NO_CHANGE
    if not self.disable_tilt and (angle_diff > 10) and (
        kill_switch_status != self.KILL_SWITCH_OFF_CHANGE_NEEDED):
      self.log("Turning Kill switch on due to angle mismatch: last_postion: %s, knx_current_position: %s, last_angle: %s, knx_current_angle: %s" % (self.last_position, self.knx_current_position, self.last_angle, self.knx_current_angle))
      self.SetKillSwitch(30)
      return self.NO_CHANGE
    self.UpdateLastStateFromDesiredState()
    # this is when the system has an opinion and reality agrees.
    if (self.desired_position == self.knx_current_position) and ((
      self.desired_angle == self.knx_current_angle) or self.disable_tilt):
      return self.NO_CHANGE
    # otherwise: we need to move to the desired position.
    return self.BLIND_NEEDS_MOVING

  def SetKillSwitch(self, timeout):
    """ Timeout for kill switch in minutes. """
    self.desired_position_reason = "Kill Switch is ON"
    # self.kill_switch = True
    self.kill_switch_timeout = int(time.time()) + timeout * 60

  def ReleaseKillSwitch(self):
    self.kill_switch_timeout = None # int(time.time())

  def GetKillSwitch(self):
    if self.kill_switch_timeout and self.kill_switch_timeout < int(time.time()):
      self.ReleaseKillSwitch()
      return self.KILL_SWITCH_OFF_CHANGE_NEEDED
    if self.kill_switch_timeout:
      return self.KILL_SWITCH_ON
    return self.KILL_SWITCH_OFF_NO_CHANGE

  def SunUnderLedge(self):
    # beschreibt wie hoch die Sonne in das Fenster eintritt (Wert ist vom
    # Dachvorsprung abwärts gemessen). Muss zwischen Abstand Dachvorsprung zur
    # oberen Fensterkante und Abstand Dachvorsprung Boden liegen. Ist der Wert
    # z.b. 3m bedeutet das, dass die Sonne quasi unterm Fenster, also auf der
    # Terasse auftrifft.

		# Die Berechnung unten hat 2 rechtwinklige Dreiecke zugrunde. 1. Dreieck
    # ist in Abhängigkeit Azimuth und wird auf den Dachvorsprung projiziert. 2.
		# Dreieck ist die errechnete Länge auf dem Dachvorsprung mit der Höhe des
		# Vorsprungs. Der Winkel ist die elevation.
    return (self.ledge * math.tan(math.radians(self.elevation)) / (
        math.cos(math.radians(self.window_azimuth_position - self.azimuth))) <
        self.window_height)

  def GetBlindSunAngle(self):
    # elevation = 0: angle = 0
    # elevation = 90: angle: 100
    # 90*x = 100
    # x = 100/90 = 1.11
    # /10 * 10 um 10er Schritte zu erreichen.
    #angle = int(round((1.111111 * self.elevation) / 10) * 10)

    # Default to closed.
    angle = self.DOWN
    if 0 < self.elevation < 23:
      angle = 50
    elif 23 <= self.elevation < 33:
      angle = 70
    elif 33 <= self.elevation < 43:
      angle = 80
    elif self.elevation >= 43:
      angle = 100
    return angle

  def ManualDayControl(self):
    if self.manual_day_control:
      if datetime.datetime.now().hour > 12:
        return False
      return True
    return False

  def SunHitsWindow(self):
    return (self.azimuth > self.azimuth_entry and
            self.azimuth < self.azimuth_exit)

  def DayLight(self):
    return self.lux_last_10_minutes > Sun.LUX_DAYLIGHT

  def IntenseSun(self):
    return self.blind_hysteresis.status_update(self.lux_last_10_minutes, self.elevation, self.previous_elevation)

  def Darkness(self):
    return self.lux_last_10_minutes < self.lux_dark

  def Dawn(self):
    return (self.lux_last_10_minutes >= Sun.LUX_DARK and
            self.lux_last_10_minutes <= Sun.LUX_DAYLIGHT)

  def DownBecauseOfDarkness(self):
    if self.manual_night_control:
      return self.DoNothing('it is dark, but this blind is controlled manually')
    # self.ReleaseKillSwitch()
    return self.Down(self.DOWN, self.DOWN, 'Down because of darkness')

  def DownBecauseOfSun(self):
    if self.ledge:
      if self.SunUnderLedge():
        return self.Down(self.DOWN, self.GetBlindSunAngle(),
               'Blind goes down, Sun is reaching under the ledge')
      else:
        return self.DoNothing('doing nothing, ledge protects us from sun')
    else:
      # no ledge.
      return self.Down(self.DOWN, self.GetBlindSunAngle(),
             'Sun hits the window, closing blind') # (%s lux, %s elevation, %s azimuth)' % (self.lux_last_10_minutes, self.elevation, self.azimuth))

  def DoNothing(self, reason):
    return self.SetDesiredPositions(None, None, reason)

  def Down(self, pos=DOWN, angle=DOWN, message='Blinds are down'):
    if self.window_open == True and self.window_type == 'door':
      return self.DoNothing('Blinds do not change on an open door')
    #if self.GetKillSwitch() == True:
      #return self.DoNothing('Raffstore Kill Switch is on, release at %s' % datetime.datetime.utcfromtimestamp(self.kill_switch_timeout).strftime('%Y-%m-%d %H:%M:%S'))
    return self.SetDesiredPositions(pos, angle, message)

  def Up(self, message):
    #if self.GetKillSwitch():
      #return self.DoNothing('Raffstore Kill Switch is on')

    if self.ManualDayControl():
      return self.DoNothing('Blinds are controlled manually')
    else:
      return self.SetDesiredPositions(self.UP, self.UP, message)

  def Control(self):
    if self.alarm_lock == True and self.wind_lock != True:
      pass
      # return self.Down(self.DOWN, self.DOWN, 'Alarm lock is on. Nobody is home. Blinds down')
    if self.wind_lock == True:
      return self.DoNothing('Wind lock is on')
    if self.Darkness():
      # this avoids the case where the blinds go up again when the light was already turned on but it gets a little bit brigher (if a cloud vanishes). This is a poor-mans hysteresis implementation.
      if self.lux_dark == Sun.LUX_DARK_WITH_LIGHT_INSIDE:
        self.lux_dark += 200
      return self.DownBecauseOfDarkness()

    if self.Dawn():
      if datetime.datetime.now().hour > 15:
        return self.Up('It dawns in the evening, blinds go up')
      else:
        return self.DoNothing('Not enough sun, doing nothing')

    if not self.SunHitsWindow():
      if self.DayLight():
        return self.Up('Sun has not reached the blind yet')
    # Sun hits the window!
    else:
      if not self.IntenseSun():
        return self.Up('Blinds go up, there is not enough sun') # (%s lux, %s elevation, %s azimuth)' % (self.lux_last_10_minutes, self.elevation, self.azimuth))

      # intense sun right into the window.
      else:
        if self.temperature_hysteresis.status_update(self.inside_temperature):
          return self.DownBecauseOfSun()
        else:
          return self.DoNothing('Doing nothing because max_inside_temperature_cold_day is not reached.')

    return self.SetDesiredPositions(False, False, 'Unclear what to do')
