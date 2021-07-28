# -*- coding: utf-8 -*-
import appdaemon.plugins.hass.hassapi as hass
import datetime
import blinds_lib
import time
from sun_lib import Sun

class Blinds(hass.Hass, Sun):

  def initialize(self):
    self.log("Initializing blinds...")
    self.b = blinds_lib.Blind(
        **self.args["blind_config"])
    time = datetime.time(1, 1, 3)
    self.tick(None)
    ticker = datetime.datetime.now() + datetime.timedelta(seconds=60)
    self.run_every(self.tick, ticker, 60)
    # self.run_at_sunset(self.release_kill_switch)
    self.run_daily(self.set_max_outside_temp, time)
    if "min_temp_sensor_value_yesterday" not in self.args:
      self.args["min_temp_sensor_value_yesterday"] = "input_number.yesterdays_min_outside_temp_over_24_hours"
    self.set_max_outside_temp(None)
    if "contact" in self.args:
      self.listen_state(self.window_closed, entity=self.args["contact"], new="off", old="on")

    if "wind_alarm" in self.args:
      self.listen_state(self.wind_alarm_off, entity=self.args["wind_alarm"], new="off", old="on")

    if "dawn_lights" in self.args:
      for light in self.args["dawn_lights"]:
        self.listen_state(self.light_on, entity=light, new="on", old="off")
        self.listen_state(self.light_off, entity=light, new="off", old="on")

  def window_closed(self, entity, attribute, old, new, kwargs):
    if "window_type" in self.args["blind_config"] and self.args["blind_config"]["window_type"] == "door":
      self.log("Window %s has been closed. Activating kill switch for 30 minutes." % self.args["contact"])
      self.b.SetWindowClosed()

  def wind_alarm_off(self, entity, attribute, old, new, kwargs):
    self.log("Wind alarm is off, releasing kill switch.")
    self.release_kill_switch(None)

  def light_on(self, entity, attribute, old, new, kwargs):
    self.log("raising lux threshold to %s" % Sun.LUX_DARK_WITH_LIGHT_INSIDE)
    self.b.SetLuxDark(Sun.LUX_DARK_WITH_LIGHT_INSIDE)

  def light_off(self, entity, attribute, old, new, kwargs):
    # We need to check if all lights are off, only then we can reset the lux for darkness.
    for light in self.args["dawn_lights"]:
      if self.get_state(light) == "on":
        return
    # If all lights are off, reset the darkness threshold to DARK.
    self.log("resetting the lux threshold to %s" % Sun.LUX_DARK)
    self.b.SetLuxDark(Sun.LUX_DARK)
    # if someone turns the last light off and this is after 3pm AND the blinds are down then don't let them go up anymore for 30 minutes. the reason for this is that by setting the LuxDark threshold to a lower value it could go up again, and that is totally unnecessary.
    if datetime.datetime.now().hour > 15:
      pos = self.get_state(self.args["blind"], attribute="current_position") 
      if pos is None:
        return
      if int(pos) == 0:
        self.b.SetKillSwitch(30)

  def evaluate(self):
    """Check if we need to do something with the blinds. """
    knx_current_position = self.get_state(self.args["blind"], attribute="current_position")
    knx_current_angle = self.get_state(self.args["blind"], attribute="current_tilt_position")
    if knx_current_position is None:
      self.set_state_reason("unknown real-life knx position. Doing nothing.")
      return
    # because blind positions can vary when changing the tilt (!) we round on 10 percent precision.
    if knx_current_angle is not None:
      knx_current_angle = int(knx_current_angle / 10) * 10
    knx_current_position = int(knx_current_position / 10) * 10
    self.knx_current_angle = knx_current_angle
    self.b.SetKNXPositions(knx_current_position, knx_current_angle)
    we_have_work = self.b.Evaluate()
    for l in self.b.FlushLog():
      self.log(l)
    self.set_state_reason(self.b.GetDesiredPositionReason())
    if we_have_work: 
      self.b.SetMasterLock()
      position = self.b.GetDesiredPosition()
      tilt_delay = 0
      if position != knx_current_position:
        self.log("Changing position of blind %s from %s to %s because: %s" % (self.args["blind"], knx_current_position, position, self.b.GetDesiredPositionReason()))
        self.call_service("cover/set_cover_position", entity_id=self.args["blind"], position=position)
        tilt_delay = 85 
        if tilt_delay in self.args:
          tilt_delay = self.args["tilt_delay"]
      tilt_position = self.b.GetDesiredAngle()
      if tilt_position is None:
        self.log("Not setting the tilt as these blinds don't have that feature.")
        self.b.UnsetMasterLock()
        return
      # if we know how long the cover runs and they go down, then set the parameters so that the blinds can stop and set the angle faster.
      if "blind_runtime" in self.args and position == 0:
        self.run_in(self.set_tilt, self.args["blind_runtime"], tilt_position=tilt_position,
                    position=position, knx_current_angle=knx_current_angle, stop=True)
      else:
        self.run_in(self.set_tilt, tilt_delay, tilt_position=tilt_position,
                    position=position, knx_current_angle=knx_current_angle)

  def set_tilt(self, kwargs):
    # if we were told to stop then stop the cover.
    if kwargs.get('stop'):
      self.log("stopping the blind to move the angle faster.")
      self.call_service("cover/stop_cover", entity_id=self.args["blind"])
      # wait half a second for the system to report back the current position.
      time.sleep(1.0)
    # there is no need to change the tilt position when we send the blinds up.
    # However, we have to unset the MasterLock.
    #if kwargs.get('position') == 100 and kwargs.get('knx_current_angle') is not  None:
      #self.b.UnsetMasterLock()
      #return
    tilt_position = kwargs.get('tilt_position')
    self.log("Changing angle/tilt of blind %s from %s to %s" % (self.args["blind"], self.knx_current_angle, tilt_position))
    self.call_service("cover/set_cover_tilt_position", entity_id=self.args["blind"], tilt_position=tilt_position)
    self.b.UnsetMasterLock()

  def release_kill_switch(self, _unused):
    self.log("releasing kill switch because why not")
    self.b.ReleaseKillSwitch()

  def set_state_reason(self, reason):
    # self.log(reason)
    obj = "input_text.%s_status" % self.args["blind"].replace("cover.", "")
    self.call_service("input_text/set_value", entity_id=obj, value=reason) 

  def set_max_outside_temp(self, _unused):
    max_outside_temp = self.get_state(self.args["max_temp_sensor_value_yesterday"])
    if self.is_not_a_number(max_outside_temp):
      max_outside_temp = 24

    min_outside_temp = self.get_state(self.args["min_temp_sensor_value_yesterday"])
    if self.is_not_a_number(min_outside_temp):
      min_outside_temp = 21

    self.log(self.b.SetMaxOutsideTemperature(float(max_outside_temp), float(min_outside_temp)))
  
  def tick(self, _unused_): # , entity, attribute, old, new, kwargs):
    # this prevents concurrency issues where blinds run longer than 60 seconds.
    if self.b.GetMasterLock():
      self.set_state_reason("Masterlock is on for blind %s" % self.args["blind"])
      return
    global_kill_switch = self.get_state("switch.raffstore_kill_switch")
    if global_kill_switch == 'on':
      self.set_state_reason("Global Kill switch is on. All blinds are controlled manually.")
      return
    outside_temp = self.get_state(self.args["outside_temperature_sensor"])
    if self.is_not_a_number(outside_temp):
      self.set_state_reason('unknown outside temperature. doing nothing.')
      return
    self.b.SetOutsideTemperature(float(outside_temp))
    inside_temp = 'unknown'
    if 'inside_temperature_is_no_thermostat' in self.args and self.args['inside_temperature_is_no_thermostat']:
      inside_temp = self.get_state(self.args["inside_temperature"])
    else:
      inside_temp = self.get_state(self.args["inside_temperature"], attribute="current_temperature")
    
    if self.is_not_a_number(inside_temp):
      self.set_state_reason('unknown inside temperature. doing nothing.')
      return
    self.b.SetInsideTemperature(float(inside_temp))
        
    self.b.SetLux(float(self.get_state("input_number.sun_lux_10_minute_average")))

    self.b.SetAzimuth(float(self.get_state("sun.sun", attribute="azimuth")))
    self.b.SetElevation(float(self.get_state("sun.sun", attribute="elevation")))

    if "contact" in self.args:
      self.b.SetReedContact(self.get_state(self.args["contact"]) == "on")

    alarm = self.get_state("input_boolean.alarmanlage_scharf") == "on"
    self.b.SetAlarm(alarm)

    wind_lock = self.get_state(self.args["wind_alarm"]) == "on"
    self.b.SetWindLock(wind_lock)

    self.evaluate()
