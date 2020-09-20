# -*- coding: utf-8
import time

class LuxEntry:

  def __init__(self, value):
    self.timestamp = time.time()
    self.value = value

  def expired(self, minutes):
    return self.timestamp + minutes * 60 < time.time()

  def value(self):
    return self.value

  def __str__(self):
    return "%d: %s" % (self.timestamp, self.value)

  def __repr__(self):
    return "%d: %s" % (self.timestamp, self.value)

class Sun:
  LUX_DARK = 30 # Lux when we consider things to be dark.
  LUX_DARK_WITH_LIGHT_INSIDE = 140 # Lux when we think it's dark outside because we turned the light on.
  LUX_BLIND_DOWN_THRESHOLD = 60000 # Lux when blinds should go down.
  LUX_BLIND_UP_THRESHOLD = 20000 # Lux when hysteresis decides to go up again.
  LUX_BLIND_UP_THRESHOLD_EVENING = 20000 # Lux when the evening has started and there is no point in having the blinds down anymore.
  LUX_DAYLIGHT = 110 # Lux when I think the day has started.
  MINUTES_AVERAGE = 7 # The time it takes to calculate the average of the current sun.

  def __init__(self):
    self.lux_values = []

  def is_not_a_number(self, value):
    return value == 'unknown' or value == 'unavailable' or value is None

  def get_lux(self, light, dusk):
    lux = None
    if self.is_not_a_number(light) or self.is_not_a_number(dusk):
      return [None, None]
    light = float(light)
    dusk = float(dusk)
    if dusk < 895:
      lux = dusk
    else:
      lux = max(light, dusk)
    self.lux_values.append(LuxEntry(lux))
    self.lux_values = [l for l in self.lux_values if not l.expired(self.MINUTES_AVERAGE)]
    lux_sum = 0
    lux_length = 0
    for l in self.lux_values:
      lux_sum += l.value
      lux_length += 1

    average = lux_sum / float(lux_length)
    return [lux, average]
