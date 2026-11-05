# -*- coding: utf-8 -*-
import appdaemon.plugins.hass.hassapi as hass
import datetime

class MaxTemp(hass.Hass):

    def initialize(self):
        self.is_ready = False
        self.outside_temp = None  # initialize cache
        self.log("Initializing Maximum Temperature system...")
        
        self.read_temp_captor() 

        self.listen_state(self.temperature_update, entity_id=self.args["outside_temp_sensor"])
        time = datetime.time(0, 0, 0)
        self.run_daily(self.reset, time)
        self.is_ready = True

    def safe_float(self, val):
        try:
            return float(val)
        except (TypeError, ValueError):
            return None
        
    def read_temp_captor(self):
        """Read the current value of the outside temperature sensor from HA."""
        sensor = self.args.get("outside_temp_sensor")
        if not sensor:
            self.log("read_temp_captor(): no outside_temp_sensor defined", level="ERROR")
            return None

        try:
            val = self.get_state(sensor)
            if val is None:
                self.log(f"Outside temp sensor '{sensor}' returned None", level="WARNING")
                return None

            self.outside_temp = self.safe_float(val)
            self.log(f"Outside temperature initialized to {self.outside_temp}C", level="INFO")
            return self.outside_temp

        except Exception as e:
            self.log(f"Error reading outside temp sensor {sensor}: {e}", level="ERROR")
            return None

    def temperature_update(self, entity, attribute, old, new, kwargs):
        new_temp = self.safe_float(new)
        if new_temp is None:
            return
        
        # Store last valid temperature for reuse
        self.outside_temp = new_temp 

        max_temp = self.safe_float(self.get_state(self.args["max_temp_sensor"]))
        min_temp = self.safe_float(self.get_state(self.args["min_temp_sensor"]))

        if max_temp is None or min_temp is None:
            self.log("Stored max/min temperature is unavailable.", level="WARNING")
            return

        if new_temp > max_temp:
            self.call_service("input_number/set_value", entity_id=self.args["max_temp_sensor"], value=new_temp)
            self.log(f"New daily max temperature: {new_temp:.1f}C", level='DEBUG')

        if new_temp < min_temp:
            self.call_service("input_number/set_value", entity_id=self.args["min_temp_sensor"], value=new_temp)
            self.log(f"New daily min temperature: {new_temp:.1f}C", level='DEBUG')


    def reset(self, _unused):
        # reset this and store the old value somewhere
        self.call_service("input_number/set_value",
            entity_id=self.args["max_temp_sensor_yesterday"],
            value=self.get_state(self.args["max_temp_sensor"]))

        self.call_service("input_number/set_value",
            entity_id=self.args["max_temp_sensor"],
            value=self.get_state(self.args["outside_temp_sensor"]))
        
        self.call_service("input_number/set_value",
            entity_id=self.args["min_temp_sensor_yesterday"],
            value=self.get_state(self.args["min_temp_sensor"]))

        self.call_service("input_number/set_value",
            entity_id=self.args["min_temp_sensor"],
            value=self.get_state(self.args["outside_temp_sensor"]))
    

    def get_yesterday_extremes(self):
        """Return yesterday's (max, min) outside temperatures as floats."""
        try:
            max_entity = self.args["max_temp_sensor_yesterday"]
            min_entity = self.args["min_temp_sensor_yesterday"]

            max_val = self.get_state(max_entity)
            min_val = self.get_state(min_entity)

            # Defaulting if the input_numbers were not initilised on a fresh install
            if max_val is None or min_val is None:
                self.log("MaxTemp app not ready — using default startup values 24/21°C", level="WARNING")
                max_val, min_val = 24, 21

            return float(max_val), float(min_val)
        except Exception as e:
            self.log(f"Error getting yesterday extremes: {e}", level="ERROR")
            return None, None

    def get_outside_temperature(self):
        """Return the last cached outside temperature value."""
        if self.outside_temp is None:
            self.log("Outside temperature not initialized yet or captor incorrectly set", level="WARNING")
        return self.outside_temp
    
    def ready(self):
        return getattr(self, "is_ready", False)