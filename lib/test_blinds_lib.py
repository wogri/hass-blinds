# -*- coding: utf-8
import unittest
import time
import datetime
import math
from mock import patch, Mock
from blinds_lib import Blind

class TestBlind(unittest.TestCase):

  def setUp(self):
    pass

  def tearDown(self):
    pass
        
  def compare(self, b, desired_position, desired_angle, desired_position_reason):
    self.assertEqual(b.desired_position_reason, desired_position_reason)
    self.assertEqual(b.desired_position, desired_position)
    self.assertEqual(b.desired_angle, desired_angle)

  def test_automatic_night_control(self):
    blind = Blind(elevation=-2,
                  azimuth=340,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=12,
                  outside_temperature=10,
                  inside_temperature=21,
                  manual_night_control=False
                 )
    blind.Control()
    self.compare(blind, Blind.DOWN, Blind.DOWN, 'Blinds are down')

  def test_automatic_night_control(self):
    blind = Blind(elevation=-2,
                  azimuth=340,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=12,
                  outside_temperature=10,
                  inside_temperature=21,
                  manual_night_control=False
                 )
    blind.Control()
    self.compare(blind, blind.DOWN, blind.DOWN, 'Down because of darkness')


  def test_manual_night_control(self):
    blind = Blind(elevation=-2,
                  azimuth=340,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=12,
                  outside_temperature=10,
                  inside_temperature=21,
                  manual_night_control=True
                 )
    blind.Control()
    self.compare(blind, None, None, 'it is dark, but this blind is controlled manually')

  @patch('blinds_lib.datetime')
  def test_dawn_in_evening(self, datetime_mock):
    datetime_mock.datetime.now = Mock(return_value=datetime.datetime.strptime(
        'Aug 26 2017 17:34', '%b %d %Y %H:%M'))
    blind = Blind(elevation=5,
                  azimuth=176,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=90,
                  outside_temperature=10,
                  inside_temperature=21,
                 )
    blind.Control()
    self.compare(blind, Blind.UP, Blind.UP, 'It dawns in the evening, blinds go up')

  @patch('blinds_lib.datetime')
  def test_dawn_in_morning(self, datetime_mock):
    datetime_mock.datetime.now = Mock(return_value=datetime.datetime.strptime(
        'Aug 26 2017 06:34', '%b %d %Y %H:%M'))
    blind = Blind(elevation=5,
                  azimuth=176,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=90,
                  outside_temperature=10,
                  inside_temperature=21,
                 )
    blind.Control()
    self.compare(blind, None, None, 'Not enough sun, doing nothing')

  def test_much_sun_on_window_too_warm_inside(self):
    blind = Blind(elevation=40,
                  azimuth=176,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=70000,
                  outside_temperature=30,
                  inside_temperature=27,
                 )
    blind.Control()
    self.compare(blind, Blind.DOWN, 80, 'Sun hits the window, closing blind')

  def test_hysteresis(self):
    blind = Blind(elevation=40,
                  azimuth=176,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=70000,
                  outside_temperature=30,
                  inside_temperature=27,
                 )
    blind.Control()
    self.compare(blind, Blind.DOWN, 80, 'Sun hits the window, closing blind')

    # Hysteresis should detect that this is still too much sun, should still be down.
    blind.SetLux(30000)
    blind.Control()
    self.compare(blind, Blind.DOWN, 80, 'Sun hits the window, closing blind')

    # hysteresis should detect that this is still too warm, although the limit is 24 degrees.
    blind.SetInsideTemperature(24.6)
    print(blind.inside_temperature)
    print(blind.temperature_hysteresis.status_update(blind.inside_temperature))
    blind.Control()
    self.compare(blind, Blind.DOWN, 80, 'Sun hits the window, closing blind')

    # now this is not enough sun anymore.
    blind.SetLux(10000)
    blind.Control()
    self.compare(blind, Blind.UP, Blind.UP, 'Blinds go up, there is not enough sun')
    blind.SetElevation(13)
    blind.SetLux(29498)
    blind.Control()
#    self.compare(blind, Blind.DOWN, 50, 'Sun hits the window, closing blind')
#    blind.SetElevation(29)
#    blind.SetLux(59369)
#    blind.Control()
#    self.compare(blind, Blind.DOWN, 70, 'Sun hits the window, closing blind')

  def test_much_sun_on_window_not_so_warm_inside(self):
    blind = Blind(elevation=40,
                  azimuth=176,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=70000,
                  outside_temperature=30,
                  inside_temperature=21,
                 )
    blind.Control()
    self.compare(blind, None, None, 'Doing nothing because max_inside_temperature_cold_day is not reached.')

  def test_not_much_sun_on_window(self):
    blind = Blind(elevation=40,
                  azimuth=176,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=40000,
                  outside_temperature=30,
                  inside_temperature=27,
                 )
    blind.Control()
    self.compare(blind, Blind.UP, Blind.UP, 'Blinds go up, there is not enough sun')

  @patch('blinds_lib.datetime')
  def test_dusk_with_manual_day_control_before_12(self, datetime_mock):
    datetime_mock.datetime.now = Mock(return_value=datetime.datetime.strptime(
        'Aug 26 2017 06:34', '%b %d %Y %H:%M'))
    blind = Blind(elevation=40,
                  azimuth=0,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=260,
                  outside_temperature=30,
                  inside_temperature=21,
                  manual_day_control=True,
                 )
    blind.Control()
    self.compare(blind, None, None, 'Blinds are controlled manually')

  @patch('blinds_lib.datetime')
  def test_dusk_with_manual_day_control_after_12(self, datetime_mock):
    datetime_mock.datetime.now = Mock(return_value=datetime.datetime.strptime(
        'Aug 26 2017 16:34', '%b %d %Y %H:%M'))
    blind = Blind(elevation=40,
                  azimuth=0,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=260,
                  outside_temperature=30,
                  inside_temperature=21,
                  manual_day_control=True,
                 )
    blind.Control()
    self.compare(blind, Blind.UP, Blind.UP, 'Sun has not reached the blind yet')

  def test_warm_day_where_sun_does_not_reach_the_window(self):
    blind = Blind(elevation=40,
                  azimuth=172,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=70000,
                  outside_temperature=30,
                  inside_temperature=21,
                 )
    blind.Control()
    self.compare(blind, Blind.UP, Blind.UP, 'Sun has not reached the blind yet')
        
  def test_warm_day_where_sun_does_not_reach_the_window_under_a_ledge(self):
    blind = Blind(elevation=57.50,
                  azimuth=207.72,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=70000,
                  outside_temperature=30,
                  inside_temperature=25.1,
                  ledge=175,
                  window_azimuth_position=263.0,
                  window_type='door',
                 )
    blind.Control()
    self.compare(blind, None, None, 'doing nothing, ledge protects us from sun')

  def test_wind_lock(self):
    blind = Blind(elevation=44.15,
                  azimuth=244.81,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=True,
                  window_open=False,
                  lux_last_10_minutes=70000,
                  outside_temperature=30,
                  inside_temperature=21,
                  ledge=175,
                  window_azimuth_position=263.0,
                  window_type='door',
                 )
    blind.Control()
    self.compare(blind, None, None, 'Wind lock is on')

  def test_open_door(self):
    blind = Blind(elevation=44.15,
                  azimuth=244.81,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=True,
                  lux_last_10_minutes=70000,
                  outside_temperature=30,
                  inside_temperature=25.1,
                  ledge=175,
                  window_azimuth_position=263.0,
                  window_type='door',
                 )
    blind.Control()
    self.compare(blind, None, None, 'Blinds do not change on an open door')

  def test_warm_day_where_sun_reaches_the_window(self):
    blind = Blind(elevation=44.15,
                  azimuth=244.81,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=70000,
                  outside_temperature=30,
                  inside_temperature=25.1,
                  window_azimuth_position=263.0,
                 )
    r = blind.Control()
    self.compare(blind, Blind.DOWN, 100, 'Sun hits the window, closing blind')

#  def test_kill_switch(self):
#    blind = Blind(elevation=44.15,
#                  azimuth=244.81,
#                  azimuth_entry=173,
#                  azimuth_exit=270,
#                  wind_lock=False,
#                  window_open=False,
#                  lux_last_10_minutes=70000,
#                  outside_temperature=30,
#                  inside_temperature=25.1,
#                  window_azimuth_position=263.0,
#                 )
#    blind.SetKNXPositions(15, 20)
#    blind.Control()
#    blind.SetKNXPositions(85, 40)
#    blind.Control()
#    self.compare(blind, None, None, 'Kill Switch is ON')

  def test_warm_day_where_sun_does_reach_the_window_under_a_ledge(self):
    blind = Blind(elevation=30.15,
                  azimuth=244.81,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=70000,
                  outside_temperature=30,
                  inside_temperature=25.1,
                  ledge=175,
                  window_azimuth_position=263.0,
                  window_type='door',
                 )
    r = blind.Control()
    self.compare(blind, Blind.DOWN, 70, 'Blind goes down, Sun is reaching under the ledge')
#		# just another case, to be sure.
    blind.azimuth = 261.61
    blind.elevation = 29.75
    r = blind.Control()
    self.compare(blind, Blind.DOWN, 70, 'Blind goes down, Sun is reaching under the ledge')

#  def test_alarm_lock(self):
#    blind = Blind(elevation=40,
#                  azimuth=172,
#                  azimuth_entry=173,
#                  azimuth_exit=270,
#                  wind_lock=False,
#                  window_open=False,
#                  lux_last_10_minutes=70000,
#                  outside_temperature=30,
#                  inside_temperature=21,
#                  alarm_lock=True,
#                 )
#    blind.Control()
#    self.compare(blind, blind.DOWN, blind.DOWN, 'Alarm lock is on. Nobody is home. Blinds down')

  def test_blind_angle(self):
    blind = Blind(elevation=60.1,
                  azimuth=172,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=70000,
                  outside_temperature=30,
                  inside_temperature=21,
                  alarm_lock=True,
                 )
    self.assertEqual(blind.GetBlindSunAngle(), 100)

  def test_temperature_curve(self):
    blind = Blind(elevation=60.1,
                  azimuth=172,
                  azimuth_entry=173,
                  azimuth_exit=270,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=70000,
                  outside_temperature=30,
                  inside_temperature=21,
                  alarm_lock=True,
                 )
    self.assertEqual(blind.SetMaxOutsideTemperature(15),
            "Minimum temperature to get down blinds is: 25.0C (seems like cold season)")
    self.assertEqual(blind.SetMaxOutsideTemperature(18),
            "Minimum temperature to get down blinds is: 24.0C (seems like transitional season)")
    self.assertEqual(blind.SetMaxOutsideTemperature(20),
            "Minimum temperature to get down blinds is: 23.0C (seems like transitional season)")
    self.assertEqual(blind.SetMaxOutsideTemperature(22),
            "Minimum temperature to get down blinds is: 22.0C (seems like transitional season)")
    self.assertEqual(blind.SetMaxOutsideTemperature(23),
            "Minimum temperature to get down blinds is: 21.5C (seems like transitional season)")
    self.assertEqual(blind.SetMaxOutsideTemperature(24),
            "Minimum temperature to get down blinds is: 21.0C (seems like transitional season)")
    self.assertEqual(blind.SetMaxOutsideTemperature(26),
            "Minimum temperature to get down blinds is: 21.0C (seems like warm season)")

  @patch('blinds_lib.datetime')
  def test_blind_situation(self, datetime_mock):
    datetime_mock.datetime.now = Mock(return_value=datetime.datetime.strptime(
        'Aug 26 2017 19:54', '%b %d %Y %H:%M'))
    blind = Blind(elevation=11,
                  azimuth=290,
                  azimuth_entry=256,
                  azimuth_exit=359,
                  wind_lock=False,
                  window_open=False,
                  lux_last_10_minutes=61000,
                  outside_temperature=30,
                  inside_temperature=25.2,
                 )
    s = blind.blind_hysteresis.status_update(61421, 10, 11)
    self.assertEqual(s, True)
    s = blind.blind_hysteresis.status_update(23421, 10, 11)
    self.assertEqual(s, True)
    s = blind.blind_hysteresis.status_update(20148, 9, 8)
    self.assertEqual(s, True)
    s = blind.blind_hysteresis.status_update(14300, 10, 11)
    self.assertEqual(s, False)

    blind.Control()
    self.assertEqual(blind.desired_position_reason, "Sun hits the window, closing blind")
    blind.SetLux(23421)
    blind.SetElevation(10)
    r = blind.Control()
    datetime_mock.datetime.now = Mock(return_value=datetime.datetime.strptime(
        'Aug 26 2017 19:58', '%b %d %Y %H:%M'))
    self.assertEqual(blind.desired_position_reason, "Sun hits the window, closing blind")
    blind.SetLux(23421)
    blind.SetLux(20148)
    blind.SetElevation(9)
    r = blind.Control()
    datetime_mock.datetime.now = Mock(return_value=datetime.datetime.strptime(
        'Aug 26 2017 20:00', '%b %d %Y %H:%M'))
    self.assertEqual(blind.desired_position_reason, "Sun hits the window, closing blind")
    blind.SetLux(14300)
    blind.SetElevation(8)
    r = blind.Control()
    self.assertEqual(blind.desired_position_reason, "Blinds go up, there is not enough sun")

if __name__ == '__main__':
  unittest.main()
