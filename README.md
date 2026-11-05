# hass-blinds

## A Home Assistant blind library

Hass-blinds is a Python library to control your blinds. The Python library itself is independent of the home automation software, however it also contains a glue layer to make it very easy to run with [AppDaemon](https://appdaemon.readthedocs.io/en/latest/#), hence [Home Assistant](https://www.home-assistant.io).
Hass-blinds is rather powerful and does many things, but was also written in an opinionated way for a single house in Europe (Austria).
The code is independent of the technology (KNX, zigbee, etc) how you control your blinds. Your covers must report their position and support position commands. For blinds with adjustable slats, they must also report and support tilt; use `disable_tilt` for covers without slats.

The code has been tested and fine-tuned over two years and should work fine if your opinions how blinds should work also match with the strategy below.

## Strategy

Hass-blinds tries to optimize on either heating or cooling a building depending on the outside temperature. It also makes sure the maximum amount of light floods the house, so it defaults to "blinds are up".

A Blind will go down if the sun angle (also known as azimuth) positions itself in a way where we know the sun goes through the window, a certain temperature threshold inside the room has been reached, the sun is intense enough and no human has overridden the blind position previously.
If a window is underneath an overhang, one can configure the height of the window and the length of the ledge. The code will then do the geometry to only close the blinds when the sun actually reaches the room. If the ledge still throws shadow into the window, the blinds will not go down.

If it gets dark one can configure if the blinds go down automatically or not. The same thing is configurable when the sun rises - blinds can go up at a lux threshold or stay down.

It is also sensitive to what's happening inside of rooms. If lights are turned on inside a room it is possible to change the lux thresholds so that blinds go down earlier at dusk.

The angle of the fins will be auto-adjusted according to the height of the sun to again allow maximum light into the room. However to not make adjustments all the time this is done in ~10% steps.

Brightness thresholds adapt to the sun's elevation, the time of day, and the previous day's maximum outside temperature. Hysteresis helps prevent repeated opening and closing when brightness fluctuates.

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
  `git clone https://github.com/wogri/hass-blinds.git`
- If you do not have git installed:
  Copy `blinds.py`, `sun.py`, `max_temp.py`, `wind.py`, and the complete `lib/` directory into `appdaemon/apps/hass-blinds/`, preserving the repository layout.

## Configuration

### Configuring appdaemon.yaml

To do sun math correctly, Home Assistant and appdaemon need to know where you live. So please be sure to configure the latitude and longitude in `appdaemon.yaml` and your `secrets.yaml`:

```yaml
secrets: /homeassistant/secrets.yaml # Adjust this path for your installation.
appdaemon:
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

### Configure Home Assistant

In Home Assistant's `configuration.yaml` you want to add the required input numbers so the apps can do some cross communication through Home Assistant. Please ensure also in your setting that your HA location is correctly set.

```yaml
input_boolean:
  wind_alarm:
    name: Strong Wind Alarm
  raffstore_kill_switch:
    name: Blinds automation kill switch

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
    name: Minimum outside temperature
    min: -60
    max: 65
    step: 0.1
    mode: box
  yesterdays_min_outside_temp_over_24_hours:
    name: Yesterdays Minimum outside temperature
    min: -60
    max: 65
    step: 0.1
    mode: box

```

### Configuring AppDaemon's apps.yaml

This library is configured through the "normal" appdaemon configuration file `apps.yaml`.

The blinds app requires helpers named `sun` and `max_temp`. Add the `wind` helper if you use a wind sensor. Replace the example sensor entity IDs with your own:

```yaml
sun:
  class: Sun
  module: sun
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
|`outside_temp_sensor`| The outside temperature measured by your weather station expressed in °C|

In the wind library you need to configure
| yaml key | meaning |
|----------|---------|
|`wind_speed_sensor`| The wind speed measured by your weather station expressed in km/h|

These helpers update the Home Assistant helpers defined above:

- the rolling average brightness (currently a 15-minute window, despite the `sun_lux_10_minute_average` entity name)
- the maximum/minimum temperature of each day to understand if we are in a cold or in a warm season.
- the wind alarm to prevent blind damage in case of strong wind

## Automate a cover in AppDaemon's apps.yaml file

Every window gets its own yaml dict that you need to append to AppDaemon's `apps.yaml` file

This library is configured through the "normal" appdaemon configuration file . Here's a (more complicated) example of a single window the `blind_wohnzimmer_west` :

```yaml
blind_wohnzimmer_west:
  class: Blinds
  module: blinds
  dependencies:
    - sun
    - max_temp
    - wind
  blind: cover.raffstore_erdgeschoss_wohnzimmer_west
  tilt_mode: immediate
  inside_temperature: climate.thermostat_erdgeschoss_wohnzimmer
  contact: binary_sensor.kontakt_erdgeschoss_wohnzimmer_hebe_schiebetuer
  blind_config:
    azimuth_entry: 173
    azimuth_exit: 290
    manual_day_control: "10:00"
    max_inside_temperature_cold_day: 24
    ledge: 135
    window_azimuth_position: 173
    window_height: 180
    kill_switch_hold_time: 4
  dawn_lights:
  - light.dimmer_erdgeschoss_essbereich
```

The table below lists required and optional parameters. Indented keys belong inside `blind_config`; all other keys belong at the app level. If you omit the `wind` helper, remove `wind` from `dependencies`.

See the [AppDaemon app guide](https://appdaemon.readthedocs.io/en/latest/APPGUIDE.html#app-dependencies) for dependency configuration.

| yaml key | meaning |
|----------|---------|
| `class` | Appdaemon config parameter that hints the Python class. Required. |
| `module` | Python module name without the `.py` extension; use `blinds`. Required. |
| `dependencies` | AppDaemon app dependencies. List `sun` and `max_temp`, plus `wind` if configured, so helpers initialize before the blind app. |
| `blind` | Home Assistant name of the blind. Must report and support position, plus tilt unless `disable_tilt` is enabled. Required. |
| `blind_tilt_position` | Home Assistant name of the blind that controls the tilt but reports the tilt as a position. This is the case for some z-wave controller (ex. Fibaro roller shutter). Optional parameter, only use if your blind has this setup ([here](https://community.home-assistant.io/t/fibaro-roller-shutter-3-fgr-223-cannot-get-it-to-work-properly/97577/158) for a detailed conversation). |
| `tilt_mode` | Optional parameter for covers that support tilt on the same Home Assistant entity. Set to `immediate` to send position and tilt commands without the default delay. Omit it to keep the delayed behavior. Configure this next to `blind`, not inside `blind_config`. |
| `inside_temperature` | the thermostat that gives you the inside temperature (it grabs automatically the state or the `current_temperature` attribute of the sensor). Use a room close by if you don't have thermostats in every room. Required parameter. |
| `contact` | Home Assistant binary sensor that knows if the window is open or not. If used, the blinds will not go down if the window is open. Once you close the door the blind control will sleep for 30 minutes and then position itself. This waiting time is useful if you want to go out, close your door in the summer to avoid heat coming in, and therefore avoid locking yourself out. |
| `blind_config` | A hash that configures the Blind class in the constructor of lib/blinds_lib.py. This allows you to override defaults. Required. |
| &emsp;`azimuth_entry` | This is the angle of the sun when it starts hitting the window. You can find this out if you position your house on a map. North is an azimuth angle of zero. The `azimuth_entry` is the angle from the north axis when the sun starts hitting your window. You can also look at the azimuth in Home Assistant, and when the sun hits your window you can just write down this number. This parameter is required. |
| &emsp;`azimuth_exit` | This is the angle when the sun no longer shines into your window. This parameter is required. |
| &emsp;`manual_night_control` | Set to `true` to prevent automatic closing because of darkness. Defaults to `false`. |
| &emsp;`manual_day_control` | Set to `true` to suppress automatic morning opening until noon, or use a quoted time such as `"10:00"` to suppress opening until that time. Sun protection can still close the blinds. Defaults to `false`. |
|&emsp; `max_inside_temperature_cold_day` | Maximum inside temperature before the blinds go down on a cold day. A day is considered cold if the maximum temperature of the previous day is below 16 degrees Celsius. |
|&emsp; `kill_switch_hold_time` | Hours for which automation pauses after detecting a manual override. Default is 4 hours. Omit to keep the default. |
| &emsp;`ledge` | If the window is under a ledge, this is the ledge length in centimeters. If the window is not under a ledge, omit. |
| &emsp;`window_azimuth_position` | In order to do the math with a window being under a ledge we need to know the exact position of the window so we know how the ledge throws shadow. This angle describes the azimuth of the sun when the window is positioned in an exact right angle to the sun. If the window is not under a ledge, omit. |
| &emsp;`window_height` | The height of the window in cm. If the window is not under a ledge, omit. |
| &emsp;`disable_tilt` | Optional parameter that you would need to set to `true` in case your blinds don't have the option to set a tilt (like with roller shutters). |
| `dawn_lights` | A list of Home Assistant lights that change the lux threshold when the lights in a room are turned on. If the lights get turned on the blinds will go down sooner at dusk. The reason why you might want to use this is because turning on the lights in a room changes the subjective feeling for how dark it is outside and how "watched" you feel. |
| `blind_runtime` | Optional Home Assistant entity ID whose state gives the full travel time in seconds. When closing, this sets the delay before stopping the cover and adjusting tilt. Default delay is 85 seconds; `tilt_mode: immediate` bypasses it. |
| `use_10_percent_precision` | Optional flag that rounds reported position and tilt down to multiples of 10. Useful for covers with imprecise position feedback. |

For every Home Assistant cover (I call them blinds) that you configure you need to add an `input_text` variable. Set `max: 255` to allow longer status messages. This variable is extremely useful for understanding why hass-blinds did or did not do something with blinds. So if your cover in Home Assistant is called `cover.raffstore_erdgeschoss_kueche_fixteil_west` you need to create an `input_text` in your Home Assistant config called `input_text.raffstore_erdgeschoss_kueche_fixteil_west_status` (note the `_status` suffix). In the Home Assistant `configuration.yaml` this looks like this:

```yaml
input_text:
  raffstore_erdgeschoss_kueche_fixteil_west_status:
    name: Kitchen west blind status
    max: 255
```

#### Kill Switch

There are times (for example when it snows and freezes overnight) where you want to disable your blind automation and want to go full manual.
Therefore, you need to implement a kill switch in Home Assistant. That entity is expected to be called `input_boolean.raffstore_kill_switch` in Home Assistant.

## Contributing

Contributions are welcome, especially improvements that simplify the code or setup. This project started as an automation for a single house running on KNX, so preserving existing behavior is important.

When submitting a pull request:

- Describe the problem and explain how your changes address it.
- Add or update unit tests for code changes to demonstrate the expected behavior, and make sure existing tests still pass.
- Keep the current API and default behavior compatible. Introduce optional configuration to support new behavior without disrupting existing installations.
- Keep changes focused and document any new configuration options.

## Contributors

- [wogri](https://github.com/wogri) — original author.
- [carmanber](https://github.com/carmanber) — improvements to blind control, tilt timing, kill switch handling, and robustness.
