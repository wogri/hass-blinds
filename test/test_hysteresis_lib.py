# -*- coding: utf-8
import unittest
from hysteresis_lib import Hysteresis

def lower_function(x, value, _unused_old_value):
  print("lower: ", value)
  if value < 5000:
    return True
  if value > 60000:
    return False
  y = 5000 * x - 75000
  print("y: ", y)
  if value < y:
    return True
  return False

def upper_function(x, value, _unused_old_value):
  print("upper: ", value)
  if value < 5000:
    return False
  y = 5000 * x - 55000
  print("y: ", y)
  if value > y:
    return True
  return False


class TestSun(unittest.TestCase):

  def setUp(self):
    self.hysteresis = Hysteresis(5, 10)

  def tearDown(self):
    pass
 
  def test_enter(self):
    self.assertEqual(False, self.hysteresis.status_update(4))
    self.assertEqual(False, self.hysteresis.status_update(7))
    self.assertEqual(True, self.hysteresis.status_update(11))
    self.assertEqual(True, self.hysteresis.status_update(7))
    self.assertEqual(True, self.hysteresis.status_update(6))
    self.assertEqual(False, self.hysteresis.status_update(4))
    self.assertEqual(False, self.hysteresis.status_update(7))

  def test_upper_and_lower_bound_function(self):
    self.hysteresis = Hysteresis(None, None, lower_function, upper_function)
    self.assertEqual(True, self.hysteresis.status_update(10000, 10))
    self.assertEqual(False, self.hysteresis.status_update(3000, 20))
    self.assertEqual(False, self.hysteresis.status_update(3000, 10))
    self.assertEqual(False, self.hysteresis.status_update(10000, 15))
    self.assertEqual(True, self.hysteresis.status_update(30000, 15))
    self.assertEqual(True, self.hysteresis.status_update(10000, 15))
    self.assertEqual(False, self.hysteresis.status_update(20000, 20))
