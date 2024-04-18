import appdaemon.plugins.hass.hassapi as hass
import time
import datetime

class Wind(hass.Hass):
    DEFAULT_MAX_SPEED=40 # Default max speed if not otherwise specified 
    ALARM_TIMEOUT = 30 # Reset alarm if after 30 min wind has calm down


    def initialize(self):
        self.log("Initializing Wind Alarm system...")
        self.wind_alarm_bool = False
        self.wind_alarm_timeout = 0
        self.listen_state(self.wind_update, entity_id=self.args["wind_speed_sensor"])
        self.max_speed = self.get_max_speed()
        
        time = datetime.time(0, 0, 20)
        self.run_minutely(self.unarm_wind_alarm, time)

    def wind_update(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        if float(self.get_state(self.args["wind_speed_sensor"])) >= self.max_speed:
            self.wind_alarm_bool = True
            self.wind_alarm_timeout = int(time.time()) + self.ALARM_TIMEOUT * 60
            self.call_service("input_boolean/turn_on",
                entity_id=self.args["wind_alarm"])
        else:
            self.unarm_wind_alarm()

    def unarm_wind_alarm(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        if self.wind_alarm_timeout < int(time.time()) and self.wind_alarm_bool:
            self.wind_alarm_bool = False
            self.log("Wind has slowed down, wind alarm is now off")
            self.call_service("input_boolean/turn_off",
                entity_id=self.args["wind_alarm"])


    def get_max_speed(self):
        max_speed = self.DEFAULT_MAX_SPEED
        try: 
            max_speed=float(self.args["wind_resistance"])
        except ValueError:
            resistance_class = str(self.args["wind_resistance"]).partition('class')[2]

            if resistance_class=='0':
                max_speed=10
            elif resistance_class=='1':
                max_speed=20
            elif resistance_class=='2':
                max_speed=40
            elif resistance_class=='3':
                max_speed=60
            elif resistance_class=='4':
                max_speed=80
            elif resistance_class=='5':
                max_speed=100
            elif resistance_class=='5':
                max_speed=120
            else:
                self.log(f"Wrong wind_resistance argument passed, max speed will defaut to {max_speed}")
                return max_speed
            max_speed*=0.8
        
        self.log(f"Max wind speed set to {max_speed}")

        return max_speed
        
