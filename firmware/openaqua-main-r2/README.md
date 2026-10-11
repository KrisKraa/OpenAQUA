# OpenAQUA main controller R2 - bring-up firmware

Arduino sketch for the R2 board (ESP32-S3-WROOM-1-N16R8). Try it first in the simulator: `simulation/wokwi/`.

**Arduino IDE setup:** board package "esp32" by Espressif (v3.x), board **ESP32S3 Dev Module**,
USB CDC On Boot: Enabled, Flash Size 16MB, PSRAM: OPI PSRAM. Libraries: Adafruit GFX, Adafruit ILI9341,
Adafruit ADS1X15, OneWire, DallasTemperature.

**Flashing the real board:** plug the USB-C power port (left edge) into the PC. If it doesn't show up,
hold BOOT (SW1, or the front button), press RESET (SW2), release BOOT, then upload.

Not in this version yet: CAN bus, USB-PD voltage readout/programming, TDS measurement method,
Wi-Fi. Port detection thresholds follow `docs/module-port-spec.md`.
