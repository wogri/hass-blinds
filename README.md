# hass-blinds

## A Homessistant Blind library

Hass-blinds is a python library to control your blinds. The python library itself is independent of the home automation software, however it also contains a glue layer to make it very easy to run with [appdaemon](https://appdaemon.readthedocs.io/en/latest/#), hence [homeassistant](https://www.home-assistant.io). 
Hass-blinds is rather powerful and does many things, but was also written in an opinionated way for a single house in Europe (Austria).
The code is independent of the technology (KNX, zigbee, etc) how you control your blinds. It was not designed for this independence, however it is expected that your technology can position your blinds and set an angle of your fins.

The code has been tested and fine tunes over two years and should work fine if your opinions how blinds should work also match with the strategy below.

## Strategy

Hass-blinds tries to optimize on either heating or cooling a building depending on the outside temperature. It also makes sure the maximum amount of light floods the house, so it defaults to "blinds are up". 

A Blind will go down if the sun angle (also known as azimuth) positions itself in a way where we know the sun goes through the window, a certain temperature threshold inside the room has been reached, the sun is intense enough and no human has overridden the blind position previously.
If a window is underneath a ledge, one can configure the height of the window and the length of the ledge. The code will then do the geometric algebra to only close the blinds when the sun actually reaches the room. If the ledge still throws shadow into the window, the blinds will not go down. 

If it gets dark one can configure if the blinds go down automatically or not. The same thing is configureable when the sun rises - blinds can go up at a lux threshold or stay down.

It is also sensitive to what's happening inside of rooms. If lights are turned on inside a room it is possible to change the lux thresholds so that blinds go down earlier if it dawns. 

The angle of the fins will be auto-adjusted according to the height of the sun to again allow maximum light into the room. However to not make adjustments all the time this is done in ~10% steps. 

The mornings are tricky, because when the sun is intense in the morning it can already be disturbing, but the actual lux values might be low. Here we again apply a linear function of a threshold when the sun should go down in the morning depending on its height. So if the sun is still low the lux threshold is lower than if the sun reaches a higher point.

If you have binary sensors that know about the state of a window door (open or closed) the blinds will not go down if the door is open to avoid locking someone out.

The best (and most complicated) part about hass-blinds is that they tend to be friendly to humans. If a human overrides the position of a blind because "they know better than the code" then hass-blinds backs off for a configurable amount of time.

## Sensor requirements

You need the following sensors to make full use of this library 

- Outside temperature
- Room temperature
- Outside Lux 

## Configuration

This library is configured through the "normal" appdaemon configuration file `apps.yaml`. Here's a (more complicated) example of a single window:

```yaml
blind_wohnzimmer_west:
  class: Blinds
  module: blinds
  global_dependencies: 
  - blinds_lib
  - hysteresis_lib
  - sun_lib
  blind: cover.raffstore_erdgeschoss_wohnzimmer_west
  inside_temperature: climate.thermostat_erdgeschoss_wohnzimmer
  max_temp_sensor_value_yesterday: input_number.yesterdays_max_outside_temp_over_24_hours
  wind_alarm: binary_sensor.wetter_zentrale_funktionen_windalarm_jalousien
  contact: binary_sensor.kontakt_erdgeschoss_wohnzimmer_hebe_schiebetuer
  blind_config:
    azimuth_entry: 173
    azimuth_exit: 290
    manual_night_control: True
    window_type: door
    max_inside_temperature_cold_day: 24
    ledge: 135
    window_azimuth_position: 173
    kill_switch_hold_time: 4
  dawn_lights:
  - light.dimmer_erdgeschoss_essbereich
 ```

You need to configure these parameters for every window.

| yaml key | meaning |
|----------|---------|
| `class` | Appdaemon config parameter that hints the python class. |
| `module` | Filename of your appdaemon config |
| `global_dependencies` | appdaemon specific configuration that hints library dependencies |
| `blind` | homeassistant name of the blind. Needs to support angle setting and positioning of the blind |
| `inside_temperature` | the thermostat that gives you the inside temperature. Use a room closeby if you don't have thermostats in every room |
| `max_temp_sensor_value_yesterday` | homeassistant input_number that stores yesterday's maximum temperature |
| `wind_alarm` | homeassistant binary sensor that tells the system if a wind alarm put all blinds up |
| `contact` | homeassistant binary sensor that knows if the window is open or not. Is dependent on the window_type. If the window_type is not `door`, then this sensor is not used. |
| `blind_config` | A hash that configures the Blind class in the constructor of lib/blinds_lib.py. This allows you to override defaults. |
| `azimuth_entry` | This is the angle of the sun when it starts hitting the window. You can find this out if you position your house on a map. North is an azimuth angle of zero. The `azumuth_entry` is the angle from the north axis when the sun starts hitting your window. You can also look at the azimuth in homeassistant, and when the sun hits your window you can just write down this number. |
| `azimuth_exit` | This is the angle when the sun no longer shines into your window. |
| `manual_night_control` | Set to `True` if you don't want the blinds to go down in the evening. Default is to go down, so you could omit this configuration paramter. Omit otherwise. |
| `manual_day_control` | Set to `True` if you don't want the blinds to go up when the sun starts shining in the morning. Omit otherwise. |
| `window_type` | Only if this is set to `door` the blinds will not go down if the window is open. Once you close the door the blind control will sleep for 30 minutes and then position itself. This waiting time is useful if you want to go out, close your door in the summer to avoid heat coming in, and therefore avoid locking yourself out. |
| `max_inside_temperature_cold_day` | Maximum inside temperature before the blinds go down on a cold day. A day is considered cold if the maximum temperature of the previous day is below 16 degrees celsius. |
| `kill_switch_hold_time` | Hours until the systems pauses if it discovers a human overriding its decisions. Default is 8 hours. Omit to keep the default. |
| `ledge` | If the window is under a ledge, this is the ledge length in centimeters. If the window is not under a ledge, omit. |
| `window_azimuth_position` | In order to do the math with a window being under a ledge we need to know the exact position of the window so we know how the ledge throws shadow. This angle describes the azimuth of the sun when the window is positioned in an exact right angle to the sun. If the window is not under a ledge, omit. |
| `dawn_lights` | A list of homeassistant lights that change the lux threshold when the lights in a room are turned on. If the lights get turned on the blinds will go down sooner when it dawns. The reason why you might want to use this is because turning on the lights in a room changes the subjective feeling for how dark it is outside and how "watched" you feel. |

## Installation

- Copy the python files in this into your appdaemon apps/ directory. The files in the `lib/` directory land in the `apps/lib` directory as well. 
- Configure your apps.yaml file. Every window gets its own yaml dict.

In addition to configuring every window the engine needs two helper apps. So please don't forget to add those: 

```yaml
sun:
  class: Sun
  module: sun
  global_dependencies: 
  - sun_lib

max_temp:
  class: MaxTemp
  module: max_temp
  outside_temp_sensor: sensor.wetter_zentrale_funktionen_aussentemperatur
  max_temp_sensor: input_number.max_outside_temp_over_24_hours
  max_temp_sensor_yesterday: input_number.yesterdays_max_outside_temp_over_24_hours

```

Both of these help to fill `input_number` variables inside of homeassistant. That is the current average of sunshine as well as the maximum temperature of each day to understand if we are in a cold or in a warm season.

### Configuring appdaemon

To do sun math correctly homeassistant and appdaemon need to know where you live. So please be sure to configure the latitude and longitude in `appdaemon.yaml`: 

```yaml
appdaemon:
  threads: 30
  # Location required to calculate the time the sun rises and sets                                                          
  latitude: 123.456
  longitude: 78.90
  # Impacts weather/sunrise data (altitude above sea level in meters)                                                       
  elevation: 303
  time_zone: Europe/Vienna
  plugins:
    HASS:
      type: hass
      ha_url: https://my.homeassistant
      token: <PUT YOUR TOKEN HERE>
```

### Configure homeassistant

In homeassistant's configuration.yaml you want to add the required input numbers so the apps can do some cross communication through homeassistant. You also need to add longitude / latitude and the sun module.

```yaml
homeassistant:                                                                      
  # Name of the location where Home Assistant is running
  name: myhome
  # Location required to calculate the time the sun rises and sets
  latitude: 123.456
  longitude: 78.90
  # Impacts weather/sunrise data (altitude above sea level in meters)
  elevation: 303
  # metric for Metric, imperial for Imperial
  unit_system: metric
  # Pick yours from here: http://en.wikipedia.org/wiki/List_of_tz_database_time_zones
  time_zone: Europe/Vienna

input_number:
  sun_lux_10_minute_average:
    min: 0
    max: 1000000
    name: Sun Lux 10 minute average
    mode: box
    unit_of_measurement: Lux
  max_outside_temp_over_24_hours:
    name: Maximum outside temperature
    min: -60
    max: 65
    step: 0.1
    mode: box
  yesterdays_max_outside_temp_over_24_hours:
    name: Yesterdays Maximum outside temperature
    min: -60
    max: 65
    step: 0.1
    mode: box

sun:
```

For every home assistant cover (I call them blinds) that you configure you need to add an `input_text` variable. This variable is extremely useful for understanding why hass-blinds did or did not do something with blinds. So if your cover in homeassistant is called `cover.raffstore_erdgeschoss_kueche_fixteil_west` you need to create an `input_text` in your homeassistant config called `input_text.raffstore_erdgeschoss_kueche_fixteil_west_status` (note the `_status` suffix). In the homeassistant `configuration.yaml` this looks like this:

```yaml
input_text:
  raffstore_erdgeschoss_arbeitszimmer_erdgeschoss_status:
    name: arbeitszimmer erdgeschoss Status
  ...
```

## Contribute

This project was written for a single house that's running on KNX. I decided to share this with the community so you can improve it. However, I don't have much time to maintain this library if you send me your pull requests. If you add new code I require you to:

- add a unit test that passes and proofs the correctness of your code
- stay compatible with the current API. If the blinds in my house stop working I get nervous. That means you can't change defaults, you can only introduce ways to override them.
- I love contributions that simplify the code or setup. The code was written at night and over a few years, so I might not always have gone the most simple routes in my logic.
