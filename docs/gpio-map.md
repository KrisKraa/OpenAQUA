# ESP32-S3 GPIO map (R2)

Every ESP32-S3-WROOM-1 pin used on the OpenAQUA main controller, as of the current R2 design
(`tools/r2_changes.py`). The GPIO map was re-planned partway through R2 for layout reasons: the
ESP32 sits antenna-up at the board's top edge, so pins were assigned to the side of the module
facing their destination (display connector on the left, sensors/CAN/port 2 below, port 1 and
the button on the right) to minimise trace crossings on a 2-layer board. The ESP32-S3's GPIO
matrix allows almost any function on almost any pin, with two hard constraints: CC sensing
needs **ADC1**, which only exists on GPIO1–10, and USB is fixed to GPIO19/20 in hardware.

"Module pin #" is the physical WROOM-1 module pin number, where it's explicitly tracked in
`tools/r2_changes.py`; a dash means that pin isn't called out there (either it didn't change, or
its physical pin number isn't tracked in that file).

| GPIO | Module pin # | Net name | Function | Notes |
|---|---|---|---|---|
| EN (CHIP_PU) | 3 | ESP_EN | Chip enable / reset | R2 adds a 1 µF RC cap (Espressif-recommended), improves power-on reset timing |
| GPIO0 | 27 | BTN_SW | Button switch input | Also the BOOT strap pin — hold the button while powering up to enter download mode |
| GPIO1 | 39 | P1_CC1_SENSE | Module port 1, CC1 sense | ADC1_CH0 |
| GPIO2 | 38 | P1_CC2_SENSE | Module port 1, CC2 sense | ADC1_CH1 |
| GPIO3 | 15 | TDS_EXCITE | TDS probe excitation | Moved here in the layout replan |
| GPIO4 | 4 | DISP_SCLK | Display SPI clock | Moved here in the layout replan |
| GPIO5 | 5 | DISP_MOSI | Display SPI MOSI | Moved here in the layout replan |
| GPIO6 | 6 | DISP_CS | Display SPI chip select | Moved here in the layout replan |
| GPIO7 | 7 | DISP_DC | Display data/command | Moved here in the layout replan |
| GPIO8 | 12 | I2C_SCL | I2C clock (ADS1115, STUSB4500) | Unchanged |
| GPIO9 | 17 | P2_CC1_SENSE | Module port 2, CC1 sense | ADC1_CH8. Moved here in the layout replan (was IO3) |
| GPIO10 | 18 | P2_CC2_SENSE | Module port 2, CC2 sense | ADC1_CH9. Moved here in the layout replan (was IO7) |
| GPIO11 | 19 | TEMP_DATA | Temperature sensor (1-wire, DS18B20-style) | Moved here in the layout replan |
| GPIO12 | 20 | LEAK1_SIG | Leak sensor 1 input | Moved here in the layout replan |
| GPIO13 | 21 | LEAK2_SIG | Leak sensor 2 input | Moved here in the layout replan |
| GPIO14 | 22 | P2_PWR_EN | Module port 2 VBUS switch enable | Moved here in the layout replan (was IO42) |
| GPIO15 | 8 | DISP_RST | Display reset | Unchanged |
| GPIO16 | 9 | DISP_BL | Display backlight | Moved here in the layout replan |
| GPIO17 | 10 | LED4_DRV | Status LED, left edge (LED4), via series resistor R27 | Moved here in the layout replan (was IO40) |
| GPIO18 | 11 | I2C_SDA | I2C data | Moved here in the layout replan (was IO9) |
| GPIO19 | 13 | USB_D− | USB 2.0 D− from the USB-C PD input | Via existing 22 Ω series resistor R12 + USBLC6-2SC6 ESD protector (U16); wired to the ESP32 for the first time in R2 |
| GPIO20 | 14 | USB_D+ | USB 2.0 D+ from the USB-C PD input | Via existing 22 Ω series resistor R13 + ESD protector; wired to the ESP32 for the first time in R2 |
| GPIO21 | 23 | LED6_DRV | Status LED, port 2 side (LED6), via series resistor R28 | Moved here in the layout replan (was IO39) |
| GPIO38 | 31 | BTN_LED_R | Button RGB LED, red | Moved here in the layout replan |
| GPIO39 | 32 | BTN_LED_G | Button RGB LED, green | Moved here in the layout replan |
| GPIO40 | 33 | BTN_LED_B | Button RGB LED, blue | Moved here in the layout replan |
| GPIO41 | 34 | LED5_DRV | Status LED, port 1 side (LED5), via series resistor R29 | Same GPIO as before; now explicitly through R29 |
| GPIO42 | 35 | P1_PWR_EN | Module port 1 VBUS switch enable | Moved here in the layout replan (was IO38) |
| GPIO47 | 24 | CAN_TX | CAN transceiver TX | Moved here in the layout replan |
| GPIO48 | 25 | CAN_RX | CAN transceiver RX | Moved here in the layout replan |

## Reserved / not used

These pins are intentionally left alone — don't repurpose them:

| GPIO | Why it's off-limits |
|---|---|
| GPIO45, GPIO46 | Strapping pins — avoid using for anything else |
| GPIO35, GPIO36, GPIO37 | Used internally by the octal PSRAM on the N16R8 module variant — never use |
| RXD0, TXD0 | Reserved for the debug UART |

## Module port pin summary

| | Port 1 (USBC2, silk "CAN1") | Port 2 (USBC3, silk "CAN2") |
|---|---|---|
| CC1 sense | GPIO1 (ADC1_CH0) | GPIO9 (ADC1_CH8) |
| CC2 sense | GPIO2 (ADC1_CH1) | GPIO10 (ADC1_CH9) |
| VBUS switch enable | GPIO42 | GPIO14 |

## Why this map keeps changing

This is the *second* GPIO plan for R2 — almost every pin except the two module-port CC-sense
inputs (GPIO1/2, which were fixed early since ADC1 only covers GPIO1–10) was reassigned again
once the physical layout started, to put each function's pins on the side of the ESP32 module
facing what it connects to. If you're implementing firmware against this table, check the date
of your checkout of `tools/r2_changes.py` — that file, not this page, is the source of truth if
the two ever disagree.

See `docs/r2-design-review.md` for why each of the underlying electrical changes was made.
