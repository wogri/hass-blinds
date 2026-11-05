# -*- coding: utf-8 -*-
import appdaemon.plugins.hass.hassapi as hass
from lib.sun_lib import Sun as SunLib
import datetime
import time

class Sun(hass.Hass, SunLib):
    """
    Collecte les données lumineuses depuis les capteurs Home Assistant,
    convertit le rayonnement en lux (si nécessaire), et calcule une moyenne
    glissante sur plusieurs minutes.
    """

    # Conversion issue de la littérature (IEEE - solar irradiance → lux)
    RADIATION_LUX_CONV_RATE = 126

    def initialize(self):
        self.is_ready = False
        self.log("Initializing Sun data collector...")
        SunLib.__init__(self)
        # Sélection dynamique des capteurs selon la config utilisateur
        self.sensor_conf = None
        self._setup_sensors()

        self.last_sent_value = None  # pour éviter les logs inutiles
        self.last_valid_lux = 0.0    # fallback si un capteur tombe

        # Run every minute on the 30s 
        self.run_minutely(self.lux, datetime.time(0, 0, 30))

        # Optional: kick an immediate first compute so you don't wait for :30
        self.run_in(self.lux, 1)

        # Start a non-blocking readiness probe
        self.run_in(self._await_first_value, 1)

    def _await_first_value(self, kwargs):
        """Poll until first valid value arrives; never blocks initialize()."""
        if self.last_sent_value is not None:
            self.is_ready = True
            self.log(f"Sun ready")
            return
        # try again in 1 second
        self.run_in(self._await_first_value, 1)

    def _setup_sensors(self):
        """Détecte automatiquement la configuration des capteurs."""
        s = self.args

        def ls(key):
            if key in s:
                self.listen_state(self.lux, entity_id=s[key])

        if "brightness_sensor" in s and "brightness_at_dawn_sensor" in s:
            ls("brightness_sensor"); ls("brightness_at_dawn_sensor")
            self.sensor_conf = "brightness_and_brightness_dawn"

        elif "brightness_sensor" in s and "radiation_at_dawn_sensor" in s:
            ls("brightness_sensor"); ls("radiation_at_dawn_sensor")
            self.sensor_conf = "brightness_and_radiation_dawn"

        elif "brightness_sensor" in s:
            ls("brightness_sensor")
            self.sensor_conf = "brightness_only"

        elif "radiation_sensor" in s and "brightness_at_dawn_sensor" in s:
            ls("radiation_sensor"); ls("brightness_at_dawn_sensor")
            self.sensor_conf = "radiation_and_brightness_dawn"

        elif "radiation_sensor" in s and "radiation_at_dawn_sensor" in s:
            ls("radiation_sensor"); ls("radiation_at_dawn_sensor")
            self.sensor_conf = "radiation_and_radiation_dawn"

        elif "radiation_sensor" in s:
            ls("radiation_sensor")
            self.sensor_conf = "radiation_only"

        else:
            self.sensor_conf = None
            self.log("No valid sun sensors found!", level="ERROR")

        if self.sensor_conf:
            self.log(f"***** Sun collector configured as: {self.sensor_conf}")

    # --- Utilitaires ---
    def safe_float(self, val):
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    # --- Fonction principale ---
    def lux(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        """Récupère les mesures, convertit et calcule la moyenne."""
        s = self.args

        def gf(key):
            return self.safe_float(self.get_state(s.get(key)))

        conf = self.sensor_conf
        if not conf:
            return

        val_day = val_night = None

        # Récupération selon la configuration
        try:
            if conf == 'brightness_and_brightness_dawn':
                val_day, val_night = gf("brightness_sensor"), gf("brightness_at_dawn_sensor")

            elif conf == 'brightness_and_radiation_dawn':
                val_day, val_night = gf("brightness_sensor"), gf("radiation_at_dawn_sensor")
                val_night = None if val_night is None else val_night * self.RADIATION_LUX_CONV_RATE

            elif conf == 'brightness_only':
                val_day = gf("brightness_sensor")
                val_night = val_day

            elif conf == 'radiation_and_brightness_dawn':
                val_day = gf("radiation_sensor")
                val_day = None if val_day is None else val_day * self.RADIATION_LUX_CONV_RATE
                val_night = gf("brightness_at_dawn_sensor")

            elif conf == 'radiation_and_radiation_dawn':
                val_day = gf("radiation_sensor")
                val_night = gf("radiation_at_dawn_sensor")
                val_day = None if val_day is None else val_day * self.RADIATION_LUX_CONV_RATE
                val_night = None if val_night is None else val_night * self.RADIATION_LUX_CONV_RATE

            elif conf == 'radiation_only':
                val_day = gf("radiation_sensor")
                val_day = None if val_day is None else val_day * self.RADIATION_LUX_CONV_RATE
                val_night = val_day

        except Exception as e:
            self.log(f"***** Sensor read error: {e}", level="WARNING")
            return

        if val_day is None or val_night is None:
            self.log("***** Sensor values are None — using last valid average", level="WARNING")
            val_day = val_night = self.last_valid_lux

        # Calcul du lux instantané et moyen
        lux, average = self.get_lux(val_day, val_night)

        if average is None:
            return  # pas de donnée stable

        # Mémorise la dernière valeur stable
        self.last_valid_lux = average

        # --- Correctif nocturne ---
        if float(self.get_state("sun.sun", attribute="elevation")) < -5:
            average = 0.0

        self.call_service(
            "input_number/set_value",
            entity_id="input_number.sun_lux_10_minute_average",
            value=average,
        )
        self.log(f"***** Sun average lux updated : {average:.0f}", level='DEBUG')
        self.last_sent_value = average

            
    def get_lux_last_10_minutes(self):
        # return your computed rolling average; if you already track it, just return it
        return self.last_sent_value
    
    def ready(self):
        return getattr(self, "is_ready", False)