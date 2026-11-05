import appdaemon.plugins.hass.hassapi as hass
import time
import datetime

class Wind(hass.Hass):
    DEFAULT_MAX_SPEED=30 # Default max speed if not otherwise specified 
    ALARM_TIMEOUT = 30 # Reset alarm if after 30 min wind has calm down


    def initialize(self):
        self.log("Initializing Wind Alarm system...")
        self.wind_alarm_bool = False
        self.wind_alarm_timeout = 0

        self.listen_state(self.wind_update, entity_id=self.args["wind_speed_sensor"])
        self.max_speed = self.get_max_speed()

        self.wind_update() 
        
        trigger_time = datetime.time(0, 0, 20)
        self.run_minutely(self.unarm_wind_alarm, trigger_time)

    def wind_update(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        try:
            wind_speed = float(self.get_state(self.args["wind_speed_sensor"]))
        except (TypeError, ValueError):
            self.log("Invalid wind sensor reading. Skipping update.", level="WARNING")
            return
        
        if wind_speed >= self.max_speed:
            self.wind_alarm_bool = True
            self.wind_alarm_timeout = int(time.time()) + self.ALARM_TIMEOUT * 60
            self.call_service("input_boolean/turn_on",
                entity_id=self.args["wind_alarm"])
            self.log(f"Wind alarm triggered. Wind speed: {wind_speed} km/h")
            

    def unarm_wind_alarm(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        if self.wind_alarm_timeout < int(time.time()) and self.wind_alarm_bool:
            self.wind_alarm_bool = False
            self.log("Wind has calmed down, wind alarm is now off")
            self.call_service("input_boolean/turn_off",
                entity_id=self.args["wind_alarm"])


    def get_max_speed(self):
        try:
            speed = float(self.args["wind_resistance"])
            self.log(f"Max wind speed set to {speed}")
            return speed
        except (ValueError, TypeError, KeyError):
            self.log(f"Wind resistance value could not be read. Defaulting to {self.DEFAULT_MAX_SPEED}", level="WARNING")
            return self.DEFAULT_MAX_SPEED
        
