# hass-blinds

## A Homessistant Blind library

Hass-blinds is a python library to control your blinds. The python library itself is independent of the home automation software, however it also contains a glue layer to make it very easy to run with [appdaemon](https://appdaemon.readthedocs.io/en/latest/#), hence [homeassistant](https://www.home-assistant.io). 
Hass-blinds is rather powerful and does many things, but was also written in an opinionated way for a single house in Europe (Austria).
The code is independent of the technology (KNX, zigbee, etc) how you control your blinds. It was not designed for this independence, however it is expected that your technology can position your blinds and set an angle of your fins.

The code has been tested and fine tuned over two years and should work fine if your opinions how blinds should work also match with the strategy below.

## Strategy

Hass-blinds tries to optimize on either heating or cooling a building depending on the outside temperature. It also makes sure the maximum amount of light floods the house, so it defaults to "blinds are up". 

A Blind will go down if the sun angle (also known as azimuth) positions itself in a way where we know the sun goes through the window, a certain temperature threshold inside the room has been reached, the sun is intense enough and no human has overridden the blind position previously.
If a window is underneath a ledge, one can configure the height of the window and the length of the ledge. The code will then do the geometric algebra to only close the blinds when the sun actually reaches the room. If the ledge still throws shadow into the window, the blinds will not go down. 

If it gets dark one can configure if the blinds go down automatically or not. The same thing is configureable when the sun rises - blinds can go up at a lux threshold or stay down.

It is also sensitive to what's happening inside of rooms. If lights are turned on inside a room it is possible to change the lux thresholds so that blinds go down earlier if it dawns. 

The angle of the fins will be auto-adjusted according to the height of the sun to again allow maximum light into the room. However to not make adjustments all the time this is done in ~10% steps.

The mornings are tricky, because when the sun is intense in the morning it can already be disturbing, but the actual lux values might be low. Here we again apply a linear function of a threshold when the sun should go down in the morning depending on its height. So if the sun is still low the lux threshold is lower than if the sun reaches a higher point.

If you have binary sensors that know about the state of a window door (open or closed) the blinds will not go down if the door is open to avoid locking someone out.

The best (and most complicated) part about hass-blinds is that they tend to be friendly to humans. If a human overrides the position of a blind because "they know better than the code" then hass-blinds backs off for a configurable amount of time. This method is called the kill switch. Whenever the code believes that a human overrode a blind position it will enable the kill switch. You can release the kill switch by reloading the appdaemon code - e. g. `touch blinds.py`. The kill switch time can be configured per blind and really depends on the ignorance of the people that live with you :)

## Sensor requirements

You need the following sensors to make full use of this library (ideally you own a weather station)

- Outside temperature (°C)
- Outside Lux (lux) or Radiance (W/m²)
- Wind Speed (km/h) (Optional)
- Room temperature (°C)

## Installation

- For Git users:
  Open the terminal and move to the appdaemon/apps directory and clone the git repository
  `cd /addon_configs/[XXXX]_appdaemon/apps` 
  `clone https://github.com/wogri/hass-blinds.git`
- If you do not have git installed:
  Copy the python files in this repository into your `appdaemon/apps/hass-blinds` directory. The files in the `lib/` directory land in the `apps/lib` directory as well. 

## Configuration

### Configuring appdaemon.yaml

To do sun math correctly, homeassistant and appdaemon need to know where you live. So please be sure to configure the latitude and longitude in `appdaemon.yaml` and your `secrets.yaml`: 

```yaml
appdaemon:
secrets: /homeassistant/secrets.yaml # for old version use of appdaemon use /config/secrets.yaml
  # Location required to calculate the time the sun rises and sets                                                          
  latitude: !secret latitude_home
  longitude: !secret longitude_home
  # Impacts weather/sunrise data (altitude above sea level in meters)                                                       
  elevation: !secret elevation_home
  time_zone: Europe/Vienna
  plugins:
    HASS:
      type: hass
http:
  url: http://127.0.0.1:5050 # Default
admin:
api:
hadashboard:
```

### Configure homeassistant

In homeassistant's configuration.yaml you want to add the required input numbers so the apps can do some cross communication through homeassistant. Please ensure also in your setting that your HA location is correctly set.

```yaml
input_boolean:
  wind_alarm:
    name: Strong Wind Alarm

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
  min_outside_temp_over_24_hours:
    name: Mimum outside temperature
    min: -60
    max: 65
    step: 0.1
    mode: box
  yesterdays_min_outside_temp_over_24_hours:
    name: Yesterdays Minimm outside temperature
    min: -60
    max: 65
    step: 0.1
    mode: box

```

### Configuring appdaemon's apps.yaml

This library is configured through the "normal" appdaemon configuration file `apps.yaml`.

Before being able to configure every window, the engine needs four helper apps. So please don't forget to add those: 

```yaml
blind_lib_global:
  module: blinds_lib
  global: true

hysteresis_lib_global:
  module: hysteresis_lib
  global: true

sun_lib_global:
  module: sun_lib
  global: true

sun:
  class: Sun
  module: sun
  dependencies:
    - sun_lib_global
  radiation_sensor: sensor.iwasse116_solar_radiation

max_temp:
  class: MaxTemp
  module: max_temp
  outside_temp_sensor: sensor.iwasse116_temperature
  max_temp_sensor: input_number.max_outside_temp_over_24_hours
  max_temp_sensor_yesterday: input_number.yesterdays_max_outside_temp_over_24_hours
  min_temp_sensor: input_number.min_outside_temp_over_24_hours
  min_temp_sensor_yesterday: input_number.yesterdays_min_outside_temp_over_24_hours

wind:
  class: Wind
  module: wind
  wind_speed_sensor: sensor.iwasse116_wind_gust
  wind_resistance: 40
  wind_alarm: input_boolean.wind_alarm

```

In the sun library you need to configure at least either the `brightness_sensor` or the `radiation_sensor`, other parameters are optional
| yaml key | meaning |
|----------|---------|
|`brightness_sensor`| The outside brightness measured by your weather station expressed in lux|
|`radiation_sensor`| The outside radiation measured by your weather station expressed in W/m²|
|`brightness_at_dawn_sensor`| The outside brightness if you have a specific captor for dawn light expressed in lux (optional)|
|`radiation_at_dawn_sensor`| The outside radiation if you have a specific captor for dawn light expressed in W/m² (optional)|

In the max_temp library you need to configure
| yaml key | meaning |
|----------|---------|
|`outside_temp_sensor`| The outside temperature measured by your weather station expressed in C°|

In the wind library you need to configure
| yaml key | meaning |
|----------|---------|
|`wind_speed_sensor`| The wind speed measured by your weather station expressed in km/h|

These helpers will fill the `input_number` variables inside homeassistant (defined previously). These are:
- the current average of sunshine 
- the maximum/minimum temperature of each day to understand if we are in a cold or in a warm season.
- the wind alarm to prevent blind damage in case of strong win

## Automate a cover in appdaemon's apps.yaml file

Every window gets its own yaml dict that you need to append to appdaemon's `apps.yaml` file

This library is configured through the "normal" appdaemon configuration file . Here's a (more complicated) example of a single window the `blind_wohnzimmer_west` :

```yaml
blind_wohnzimmer_west:
  class: Blinds
  module: blinds
  dependencies: 
  - blind_lib_global
  - hysteresis_lib_global
  - sun_lib_global
  blind: cover.raffstore_erdgeschoss_wohnzimmer_west
  inside_temperature: climate.thermostat_erdgeschoss_wohnzimmer
  contact: binary_sensor.kontakt_erdgeschoss_wohnzimmer_hebe_schiebetuer
  blind_config:
    azimuth_entry: 173
    azimuth_exit: 290
    manual_night_control: "10:00"
    contact: binary_sensor.capteur_ouverture_salon_window_door_is_open
    max_inside_temperature_cold_day: 24
    ledge: 135
    window_azimuth_position: 173
    window_height: 180
    kill_switch_hold_time: 4
  dawn_lights:
  - light.dimmer_erdgeschoss_essbereich
 ```

You need to configure these parameters for every window.

| yaml key | meaning |
|----------|---------|
| `class` | Appdaemon config parameter that hints the python class. Required. |
| `module` | Filename of your appdaemon config. Required. |
| `global_dependencies` | appdaemon specific configuration that hints library dependencies. Required. |
| `blind` | homeassistant name of the blind. Needs to support angle setting and positioning of the blind. Required. |
| `blind_tilt_position` | homeassistant name of the blind that controls the tilt but reports the tilt as a position. This is the case for some z-wave controller (ex. Fibaro roller shutter). Optional parameter, only use if your blind has this setup ([here](https://community.home-assistant.io/t/fibaro-roller-shutter-3-fgr-223-cannot-get-it-to-work-properly/97577/158) for a detailed conversation). |
| `inside_temperature` | the thermostat that gives you the inside temperature (it grabs automatically the state or the current_temperature` attribute of the captor). Use a room close by if you don't have thermostats in every room. Required parameter. |
| `contact` | homeassistant binary sensor that knows if the window is open or not. If used, the blinds will not go down if the window is open. Once you close the door the blind control will sleep for 30 minutes and then position itself. This waiting time is useful if you want to go out, close your door in the summer to avoid heat coming in, and therefore avoid locking yourself out. | 
| `blind_config` | A hash that configures the Blind class in the constructor of lib/blinds_lib.py. This allows you to override defaults. Required. |
| &emsp;`azimuth_entry` | This is the angle of the sun when it starts hitting the window. You can find this out if you position your house on a map. North is an azimuth angle of zero. The `azumuth_entry` is the angle from the north axis when the sun starts hitting your window. You can also look at the azimuth in homeassistant, and when the sun hits your window you can just write down this number. This parameter is required. |
| &emsp;`azimuth_exit` | This is the angle when the sun no longer shines into your window. This parameter is required. |
| &emsp;`manual_night_control` | Set to `True` if you don't want the blinds to go down in the evening. Default is to go down, so you could omit this configuration parameter. |
| &emsp;`manual_day_control` | Set to `True` if you don't want the blinds to go up when it dawns in the morning. You could also set it to a certain time in the format "HH:MM". Useful for rooms where you sleep for example if you like it staying dark in the morning. Once the sun becomes too bright the blinds will go down regardless of this parameter. Omit if you want the blinds to go up as soon as it's bright enough. |
|&emsp; `max_inside_temperature_cold_day` | Maximum inside temperature before the blinds go down on a cold day. A day is considered cold if the maximum temperature of the previous day is below 16 degrees Celsius. |
|&emsp; `kill_switch_hold_time` | Hours until the systems pauses if it discovers a human overriding its decisions. Default is 8 hours. Omit to keep the default. |
| &emsp;`ledge` | If the window is under a ledge, this is the ledge length in centimeters. If the window is not under a ledge, omit. |
| &emsp;`window_azimuth_position` | In order to do the math with a window being under a ledge we need to know the exact position of the window so we know how the ledge throws shadow. This angle describes the azimuth of the sun when the window is positioned in an exact right angle to the sun. If the window is not under a ledge, omit. |
| &emsp;`window_height` | The height of the window in cm. If the window is not under a ledge, omit. |
| &emsp;`disable_tilt` | Optional parameter that you would need to set to `true` in case your blinds don't have the option to set a tilt (like with roller shutters). |
| `dawn_lights` | A list of homeassistant lights that change the lux threshold when the lights in a room are turned on. If the lights get turned on the blinds will go down sooner when it dawns. The reason why you might want to use this is because turning on the lights in a room changes the subjective feeling for how dark it is outside and how "watched" you feel. |
| `blind_runtime` | Optional parameter that defines how long it will take the blind until it has moved from top to bottom. Used to set the angle faster (otherwise the blind will remain shut for a while) |
| `use_10_percent_precision` | Optional parameter that you would need to set to `true` when you want to setup 10% rounding errors on position and tilt. This is useful for blinds that do not have the ability to report 100% accurate values on position and tilt. |

For every home assistant cover (I call them blinds) that you configure you need to add an `input_text` variable. This variable is extremely useful for understanding why hass-blinds did or did not do something with blinds. So if your cover in homeassistant is called `cover.raffstore_erdgeschoss_kueche_fixteil_west` you need to create an `input_text` in your homeassistant config called `input_text.raffstore_erdgeschoss_kueche_fixteil_west_status` (note the `_status` suffix). In the homeassistant `configuration.yaml` this looks like this:

```yaml
input_text:
  raffstore_erdgeschoss_arbeitszimmer_erdgeschoss_status:
    name: arbeitszimmer erdgeschoss Status
  ...
```

#### Kill Switch

There are times (for example when it snows and freezes overnight) where you want to disable your blind automation and want to go full manual.
Therefore, you need to implement a kill switch in homeassistant. That entity is expected to be called `switch.raffstore_kill_switch` in homeasisstant.

## Contribute

This project was written for a single house that's running on KNX. I decided to share this with the community so you can improve it. However, I don't have much time to maintain this library if you send me your pull requests. If you add new code I require you to:

- add a unit test that passes and proofs the correctness of your code
- stay compatible with the current API. If the blinds in my house stop working I get nervous. That means you can't change defaults, you can only introduce ways to override them.
- I love contributions that simplify the code or setup. The code was written at night and over a few years, so I might not always have gone the most simple routes in my logic.
