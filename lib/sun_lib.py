# -*- coding: utf-8 -*-
import time
import statistics

class LuxEntry:
    """Represents a single lux reading with timestamp."""
    def __init__(self, value: float):
        self.timestamp = time.time()
        self._value = float(value)

    def expired(self, minutes: int) -> bool:
        """Return True if this entry is older than 'minutes'."""
        return (time.time() - self.timestamp) > minutes * 60

    def get_value(self) -> float:
        return self._value

    def __repr__(self):
        return f"{int(self.timestamp)}: {self._value}"


class Sun:
    """Handles the smoothing and logic thresholds for sunlight detection."""

    # ---- Thresholds ----
    LUX_BLIND_DOWN_THRESHOLD = 30000    # Sun too strong → blinds down
    LUX_BLIND_UP_THRESHOLD = 10000      # Sun weak enough → blinds up
    LUX_BLIND_UP_THRESHOLD_EVENING = 20000
    LUX_DAYLIGHT = 500                  # Daytime threshold
    MINUTES_AVERAGE = 15                # Rolling window for smoothing
    LUX_DARK = 100                      # Below this → night
    LUX_DARK_WITH_LIGHT_INSIDE = 250    # Night if lights are on

    def __init__(self):
        self.lux_values = []
        self.last_valid_average = None  # new: keep last stable lux

    # --- Validation helpers ---
    def is_not_a_number(self, value):
        return value in ('unknown', 'unavailable', None)

    # --- Main processing ---
    def get_lux(self, day_light: float, dawn_light: float):
        """
        Takes lux values already converted from radiation if necessary.
        Returns [instant_lux, averaged_lux].
        """

        if self.is_not_a_number(day_light) or self.is_not_a_number(dawn_light):
            # If both sensors are unavailable, keep last valid average
            return [None, self.last_valid_average]

        light = float(day_light)
        dusk = float(dawn_light)

        # Combine direct + diffuse sunlight (both in lux)
        lux = max(light, dusk)

        # Add to buffer and prune old entries
        self.lux_values.append(LuxEntry(lux))
        self.lux_values = [l for l in self.lux_values if not l.expired(self.MINUTES_AVERAGE)]

        # Compute rolling average
        if not self.lux_values:
            return [lux, lux]

        values = [l.get_value() for l in self.lux_values]
        avg = statistics.mean(values)

        # Optional: reject isolated spikes (protects hysteresis)
        if len(values) > 4:
            median_val = statistics.median(values)
            if abs(avg - median_val) / (median_val + 1) > 0.4:
                avg = median_val

        # Store for stability recovery
        self.last_valid_average = avg

        # --- NIGHT FALL PROTECTION ---
        # If both sensors read near-zero, clear old values and reset average
        if lux < self.LUX_DARK/2:  # almost dark
            # purge all old lux values to avoid holding high averages overnight
            self.lux_values = [LuxEntry(lux)]
            lux_avg = lux
            self.last_valid_average = lux

        return [lux, avg]


    def get_lux_dark(self):
        return self.LUX_DARK
    
    def get_Lux_dark_with_light_inside(self):
        return self.LUX_DARK_WITH_LIGHT_INSIDE