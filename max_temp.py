# -*- coding: utf-8 -*-
import appdaemon.plugins.hass.hassapi as hass
import datetime

class MaxTemp(hass.Hass):

  def initialize(self):
    self.log("Initializing Maximum Temperature system...")
    self.listen_state(self.temperature_update, entity=self.args["outside_temp_sensor"])
    time = datetime.time(0, 0, 0)
    self.run_daily(self.reset, time)

  def temperature_update(self, _m, _n, _o, new, kwargs):
    if new == None:
      return
    max_temp_so_far = float(self.get_state(self.args["max_temp_sensor"]))
    if float(new) > max_temp_so_far:
      self.call_service("input_number/set_value",
          entity_id=self.args["max_temp_sensor"], value=new)
      # self.log("New daily record for maximum temperatur. Was: %s, new temp is: %s" %  (max_temp_so_far, new))

  def reset(self, _unused):
    # reset this and store the old value somewhere.
    self.call_service("input_number/set_value",
        entity_id=self.args["max_temp_sensor_yesterday"],
        value=self.get_state(self.args["max_temp_sensor"]))

    self.call_service("input_number/set_value",
        entity_id=self.args["max_temp_sensor"],
        value=self.get_state(self.args["outside_temp_sensor"]))
