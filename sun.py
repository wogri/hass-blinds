# -*- coding: utf-8 -*-
import appdaemon.plugins.hass.hassapi as hass
from sun_lib import Sun
import datetime

class Sun(hass.Hass, Sun):
  # Value taken from: https://www.extrica.com/article/21667/pdf IEEE A conversion guide: solar irradiance and lux illuminance
  RADIATION_LUX_CONV_RATE = 122 # Value taken to convert radiation to lux 

  def initialize(self):
    self.log("Initializing Sun data collector...")

    # Get brightness or radiation, brigntness is taken in priority over radiation to prevent conversion when possible 
    if "brightness_sensor" in self.args and "brightness_at_dawn_sensor" in self.args:
      self.listen_state(self.lux, entity_id=self.args["brightness_sensor"])
      self.listen_state(self.lux, entity_id=self.args["brightness_at_dawn_sensor"])
      self.sensor_conf = 'brightness_and_brightness_dawn'
      
    elif "brightness_sensor" in self.args and "radiation_at_dawn_sensor" in self.args:
      self.listen_state(self.lux, entity_id=self.args["brightness_sensor"])
      self.listen_state(self.lux, entity_id=self.args["radiation_at_dawn_sensor"])
      self.sensor_conf = 'brightness_and_radiation_dawn'

    elif "brightness_sensor" in self.args:
      self.listen_state(self.lux, entity_id=self.args["brightness_sensor"])
      self.sensor_conf = 'brightness_only'

    elif "radiation_sensor" in self.args and "brightness_at_dawn_sensor" in self.args:
      self.listen_state(self.lux, entity_id=self.args["radiation_sensor"])
      self.listen_state(self.lux, entity_id=self.args["brightness_at_dawn_sensor"])
      self.sensor_conf = 'radiation_and_brightness_dawn'

    elif "radiation_sensor" in self.args and "radiation_at_dawn_sensor" in self.args:
      self.listen_state(self.lux, entity_id=self.args["radiation_sensor"])
      self.listen_state(self.lux, entity_id=self.args["radiation_at_dawn_sensor"])
      self.sensor_conf = 'radiation_and_radiation_dawn'

    elif "radiation_sensor" in self.args:
      self.listen_state(self.lux, entity_id=self.args["radiation_sensor"])
      self.sensor_conf = 'radiation_only'

    else:
      self.log('No brightness or radiation_sensor provided', level="ERROR")

    self.log(f"Sun collector using {self.sensor_conf}")
    
    self.lux_values = []
    time = datetime.time(0, 0, 30)
    self.run_minutely(self.lux, time)

  def lux(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
    # self.log("lux values: %s" % self.lux_values)

    # Retrieve value from sensor based on sun captor configuration
    if self.sensor_conf == 'brightness_and_brightness_dawn':
      val_day = float(self.get_state(self.args["brightness_sensor"]))
      val_night = float(self.get_state(self.args["brightness_at_dawn_sensor"]))

    elif self.sensor_conf == 'brightness_and_radiation_dawn':
      val_day = float(self.get_state(self.args["brightness_sensor"]))
      val_night = float(self.get_state(self.args["radiation_at_dawn_sensor"])) * self.RADIATION_LUX_CONV_RATE 
    
    elif self.sensor_conf == 'brightness_only':
      val_day = float(self.get_state(self.args["brightness_sensor"]))
      val_night = val_day

    elif self.sensor_conf == 'radiation_and_brightness_dawn':
      val_day = self.get_state(self.args["radiation_sensor"]) * self.RADIATION_LUX_CONV_RATE 
      val_night = float(self.get_state(self.args["brightness_at_dawn_sensor"]))

    elif self.sensor_conf == 'radiation_and_radiation_dawn':
      val_day = float(self.get_state(self.args["radiation_sensor"])) * self.RADIATION_LUX_CONV_RATE 
      val_night = float(self.get_state(self.args["radiation_at_dawn_sensor"])) * self.RADIATION_LUX_CONV_RATE 

    elif self.sensor_conf == 'radiation_only':
      val_day = float(self.get_state(self.args["radiation_sensor"])) * self.RADIATION_LUX_CONV_RATE 
      val_night = val_day
    
    else:
      self.log('No valid configuration detected for sun captor', level="ERROR")

    _, average = self.get_lux(val_day, val_night)

    if average is None:
      self.log('KNX lux values are unknown. Doing nothing.', level="ERROR")
      return

    self.call_service("input_number/set_value", 
        entity_id="input_number.sun_lux_10_minute_average", value=average) 
