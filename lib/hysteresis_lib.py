# -*- coding: utf-8
class Hysteresis():

  def __init__(self, lower_bound, upper_bound, lower_function=None, upper_function=None):
    # function must be a function that accepts a value (x axis) and returns the value on the (y axis).
    self._hysteresis_enabled = False
    self._upper_function = upper_function
    self._lower_function = lower_function
    self._hysteresis_upper_bound = upper_bound
    self._hysteresis_lower_bound = lower_bound
  
  def above_upper_bound(self, x, value, old_x):
    if self._upper_function:
      f = self._upper_function
      return f(x, value, old_x)
    return value > self._hysteresis_upper_bound

  def under_lower_bound(self, x, value, old_x):
    if self._lower_function:
      f = self._lower_function
      return f(x, value, old_x)
    return value <  self._hysteresis_lower_bound 
    
  def status_update(self, value, x=None, old_x=None):
    if self._hysteresis_enabled:
      if self.under_lower_bound(x, value, old_x):
        self._hysteresis_enabled = False
        return False
      return True
    else:
      if self.above_upper_bound(x, value, old_x):
        self._hysteresis_enabled = True
        return True
      return False
