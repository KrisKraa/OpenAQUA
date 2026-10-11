# OpenAQUA R2 in the Wokwi simulator

Runs the real bring-up firmware (`firmware/openaqua-main-r2/`) on a simulated ESP32-S3 wired
exactly like the R2 board (same GPIOs). `sketch.ino` is that firmware with `SIMULATION 1`.

## Load it (wokwi.com, free, no install)

1. Open https://wokwi.com/projects/new/esp32-s3
2. **sketch.ino** tab: replace everything with this folder's `sketch.ino`.
3. **diagram.json** tab: replace everything with this folder's `diagram.json`.
4. Click the small ▾ next to the file tabs → **New file…** → `libraries.txt`, paste this folder's `libraries.txt`.
5. Same way, add `ads1115.chip.json` and `ads1115.chip.c` (a simulated ADS1115 ADC; Wokwi doesn't have one built in).
6. Press ▶ (first run takes a minute while the libraries compile). Log in to Wokwi if you want to save the project.

## What to try

| Control | Stands in for | What you should see |
|---|---|---|
| **pH probe** knob vs **VOCM** knob | pH electrode signal (ADS1115 AIN1 − AIN3) | same position = pH 7.00; ~59 mV difference = 1 pH unit |
| **TDS** knob | TDS front end (AIN0) | raw volts on screen (TDS isn't calibrated yet) |
| **DS18B20** (click it) | water temperature | temperature on screen; also sets pH temperature compensation |
| **Leak 1 / Leak 2** switches | leak probes in water | "Leak" turns red, button flashes red; long-press (>1 s) the button to acknowledge |
| **Front button** short press | maintenance mode | button turns blue |
| **Port1 / Port2 CC1** sliders | what is plugged into a module port | 61–76 % (2.0–2.5 V) = OpenAQUA module → after 0.5 s the orange **VBUS** LED turns on; 24–48 % (0.8–1.6 V) = phone/USB device → port refused, its red LED blinks; anything else = empty, VBUS off at once |

The screen shows every reading plus the raw CC voltages; the serial monitor shows what was found on I2C.

## Not simulated

USB-PD (STUSB4500 shows as "--"), the CAN bus, the buck converter and the real analog circuits
(probe impedance, noise). Those can only be checked on the real board.
