# -*- coding: utf-8 -*-
import appdaemon.plugins.hass.hassapi as hass
from sun_lib import Sun
import datetime

class Sun(hass.Hass, Sun):

  def initialize(self):
    self.log("Initializing Sun data collector...")
    self.listen_state(self.lux, entity_id=self.args["brightness_sensor"])
    self.listen_state(self.lux, entity_id=self.args["brightness_at_dawn_sensor"])
    self.lux_values = []
    time = datetime.time(0, 0, 30)
    self.run_minutely(self.lux, time)

  def lux(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
    # self.log("lux values: %s" % self.lux_values)
    _, average = self.get_lux(
        self.get_state(self.args["brightness_sensor"]),
        self.get_state(self.args["brightness_at_dawn_sensor"]))

    if average is None:
      self.log('KNX lux values are unknown. Doing nothing.', level="ERROR")
      return

    self.call_service("input_number/set_value", 
        entity_id="input_number.sun_lux_10_minute_average", value=average) 
