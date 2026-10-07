# What changed from the original board to R2, and why

This is a design review of the OpenAQUA main controller, comparing the original board
(schematic dated 2026-05-27, PCB dated 2026-10-08) against R2. Every change listed here is
implemented in `tools/r2_changes.py`, which is the source of truth for the actual part
removals, swaps, and net reassignments — this doc explains the reasoning behind each one.
Several of the original issues would have stopped the first assembled board from powering up
at all.

## Power input (USB-C PD, STUSB4500)

- **VDD powered from +3V3.** 3V3 only exists *after* the PD chip has already turned the power
  switch on — a chicken-and-egg problem that meant the board could never start from cold.
  **R2:** VDD (pin 24) is now fed from raw VBUS instead, matching ST's own reference design, so
  the chip can power up before any downstream rail exists.
- **CC1DB/CC2DB floating.** These are the dead-battery pull-down pins; left floating, the chip
  never presents a load on CC, so a charger never sees a sink and never turns VBUS on in the
  first place. **R2:** CC1DB/CC2DB are now tied to CC1/CC2.
- **RESET pulled the wrong way.** RESET is active-HIGH on this chip, but it was pulled up to
  3V3 — holding the chip in permanent reset. **R2:** RESET is now pulled to GND.
- **No decoupling on VREG_1V2/VREG_2V7.** The datasheet calls for 1 µF caps on both internal
  regulator outputs; neither was fitted, risking unstable internal supplies. **R2:** added
  (C46 on VREG_1V2, C47 on VREG_2V7).
- **Exposed pad not grounded.** **R2:** tied to GND.
- **I2C not connected.** With no I2C, firmware has no way to talk to the chip, so it's stuck on
  the factory default PDOs: 5V/1.5A, 15V/1.5A, 20V/1.0A — never 20 V at useful current. **R2:**
  SCL/SDA wired onto the same I2C bus as the ADS1115, so firmware can program PDO2/PDO3 for
  20 V.
- **Q1 (P-FET power switch) gate tied to GND.** This held the FET permanently on with Vgs at
  -20 V — right at the AO3407's absolute ±20 V Vgs rating, with zero margin. **R2:** added a
  100 kΩ gate-source resistor plus a 22 kΩ series resistor to VBUS_EN_SNK, as in ST's reference
  design. Vgs is now around -16 V, inside the part's rated margin.
- **USB data lines not connected to the ESP32.** There was no way to flash firmware over the
  USB-C input port at all. **R2:** D+/D− now routed to the ESP32 (IO20/IO19) through the
  existing 22 Ω series resistors, with a USBLC6-2SC6 ESD protector (U16) added.
- **USB-C shells not grounded.** **R2:** all three USB-C connector shells tied to GND.

## Buck converter (MP1584)

- **Catch diode (D8) reversed.** Installed backwards, it would short the switch node straight
  to ground the moment the regulator started switching — likely damaging the diode or the IC
  on first power-up. **R2:** reoriented, cathode to the switch node, anode to GND.
- **FREQ pin floating.** The datasheet requires a resistor here to set the switching frequency;
  left floating, frequency (and regulation) is undefined. **R2:** 100 kΩ to GND, giving
  roughly 900 kHz.
- **COMP had only a single capacitor.** The datasheet's loop compensation table calls for a
  series R+C network on COMP for a 5 V output, not a lone cap. **R2:** 100 kΩ in series with a
  150 pF cap, per the datasheet's 5 V table.
- **EN tied straight to the 20 V rail.** Worked, but with no resistor in the path. **R2:**
  routed through a 100 kΩ pull-up from +20V_BUS instead, as the datasheet recommends.
- Output (4.8 V, from the 100 kΩ/20 kΩ feedback divider against the 0.8 V reference) was
  already fine for feeding the downstream 3.3 V LDO — unchanged.

## Module ports (USB-C, used for CAN + switched power, not USB)

- **20 V was always present on VBUS.** Plugging in a phone, USB stick, or an ordinary charger
  would have applied 20 V where the device expects 5 V — likely destroying it. **R2:** each
  port gets a high-side P-FET switch (AO3407, Q2 on port 1 / Q4 on port 2) driven by a 2N7002
  (Q3/Q5) from an ESP32 GPIO, with a pull-down resistor so the port defaults to **off** at
  power-up.
- **Charge-only cables would silently break CAN.** These cables have no D+/D− wires, so CAN
  would simply not work with no obvious indication why. **R2:** added CC sensing on both ports
  — each CC pin gets a 10 kΩ pull-up to 3.3 V plus a 1 kΩ series resistor into an ESP32 ADC
  pin, so firmware can check what's actually plugged in before switching VBUS on at all (see
  `docs/module-port-spec.md` for the full identification logic).
- Port mapping (current, after the layout-driven GPIO replan — see the ESP32 section below):
  **Port 1 = USBC2** (silk "CAN1"): CC1 → IO1, CC2 → IO2, power enable → IO42.
  **Port 2 = USBC3** (silk "CAN2"): CC1 → IO9, CC2 → IO10, power enable → IO14.
- Each port is protected by a 0.3 A-hold PTC fuse (F2 on port 1, F1 on port 2), giving roughly
  6 W of budget per port at 20 V.

## ESP32

- **GPIO remap to make room for CC sensing.** CC sensing needs ADC1, which only exists on
  GPIO1–10. An initial remap freed GPIO1/2/3/7 for the four CC-sense inputs by moving the
  button RGB LED and the display DC line elsewhere.
- **GPIO remap, round two — driven by layout.** Once the physical layout started, with the
  ESP32 placed antenna-up at the board's top edge, almost the entire map was reassigned again
  so that each function's pins sit on the side of the module facing what it connects to
  (display connector on the left, sensors/CAN/port 2 below, port 1 and the button on the
  right) — this minimises trace crossings on a 2-layer board. The two module-port CC-sense
  inputs that were fixed in the first pass (GPIO1/2 for port 1) stayed put; port 2's CC sense
  moved to GPIO9/10, and the two port power-enable lines, the display pins, I2C SDA, TDS
  excitation, the leak inputs, the temperature input, the status LEDs, the button LED, and CAN
  TX/RX all moved. The current, authoritative map is in `docs/gpio-map.md` — it's taken
  directly from `tools/r2_changes.py`, which is the actual source of truth; if this document
  and that file ever disagree, trust the file.
- **EN (CHIP_PU) had no RC cap.** **R2:** added a 1 µF cap, per Espressif's own reference
  design recommendation, for more reliable power-on reset timing.
- **LED4 was mounted backwards.** The part's footprint had it wired with reversed polarity, so
  it would never light. **R2:** footprint orientation corrected. LED4 (along with LED5 and
  LED6) is now also driven through its own series resistor (R27/R29/R28 respectively) as part
  of the GPIO replan, rather than straight off the GPIO pin.

## pH front end (LMP91200)

- **Two chip outputs were wired as if they were inputs.** VCM (pin 8) and VCMHI (pin 7) are
  *outputs* of the LMP91200, but the original board tied VCM to a resistor divider and VCMHI
  straight to 3.3 V — and VREF, which actually is an input, shared the same node as these
  outputs. Driving an output pin from an external source like that is invalid and would have
  produced unreliable pH readings at best. **R2:**
  - **VREF** (true input) is now fed from 3.3 V through a 100 Ω / 100 nF RC filter.
  - **VCM** (output) now drives the pH probe's own reference line, routed via U.FL to a BNC
    bulkhead in the case.
  - **VCMHI** (output) is left open, unconnected.
  - **VOCM** (output) now goes to the ADS1115's AIN3 input, so firmware reads pH
    *differentially* as AIN1 − AIN3, which cancels drift in the mid-point voltage instead of
    measuring against a fixed reference that can wander.
  - Layout adds a guard ring (GUARD1/GUARD2) around the high-impedance input traces.

## CAN bus

- **R4/R5 did nothing.** These were meant to be 10 Ω series resistors on CAN_H/CAN_L, but both
  pads of each were wired to the same net — zero volts across them, no effect. **R2:** removed.
- **120 Ω termination is now a jumper (R55, 0 Ω).** Fit it when the controller sits at one end
  of the CAN bus. Remove it when modules are connected to **both** module ports (controller in
  the middle of the bus) and terminate instead at the two far-end modules.

## Parts & voltage ratings

Several capacitors were rated below the voltage they actually see:

- **C10** (47 µF, on the 20 V bus) was a 10 V part → replaced with a 50 V-rated part.
- **C6** (on USB VBUS) was a 10 V part → replaced with a 50 V-rated part.
- **C5** was a 16 V part but sits on VBUS (up to 20 V) → replaced.
- **C29** was 47 µF, 0603, 6.3 V → replaced with 22 µF, 1206, 25 V.
- **C26** → replaced with a 50 V-rated part.

Running capacitors above, or too close to, their rated voltage risks dielectric breakdown and
capacitance derating over time and temperature — this is exactly the kind of fault that doesn't
show up on day one but causes field failures later.

## Layout

The board layout is still in progress (by the lead), but the plan is a 2-layer, 154 × 67 mm
board with a solid GND plane on the bottom layer, split into zones: power (USB-C PD input +
buck) top-left; ESP32 top-middle, with its antenna at the board's top edge and no copper
underneath it (on the original layout the antenna pointed into the middle of the board, partly
under the display — bad for WiFi range); analog front-end (pH/TDS/ADC) bottom-left/middle, kept
away from the buck's switching noise; CAN and the module port switches on the right.

Connector, LED, and mounting-hole positions are unchanged, because they have to line up with
the 3D-printed case — this was checked against the case's STEP model (board outline, 4 mounting
holes, 3 USB-C openings, and 3 LED slots, all within 0.25 mm). The button is a low-profile
16 mm RGB button mounted above the board.

## Still open

- **TDS front end needs a measurement-strategy rework.** The ADS1115 is too slow to properly
  sample the AC excitation waveform used for TDS. Worth considering synchronous sampling using
  the ESP32's own built-in ADC instead.
- **pH probe isn't galvanically isolated** from the other probes sharing the same water. An
  isolated pH front end would be the robust fix, but that's a later-revision change, not R2.
- **Status LEDs LED4/5/6** are top-emitting 0603 parts sitting next to 1 mm side slots in the
  case — side-emitting LEDs, or light pipes, would work better.
- **The PCB layout itself isn't finished yet** — the plan above is a work in progress.
- **Firmware** still needs to actually drive all of this (see below) — none of the board fixes
  do anything on their own without firmware support.

## Firmware to-do for R2 bring-up

- Program the STUSB4500's PDO2/PDO3 for 20 V over I2C (address 0x28) — without this, the chip
  stays on its factory-default PDOs and the board never gets more than 1 A at 20 V (or 1.5 A at
  15 V).
- Implement module port detection and VBUS enable logic: watch the CC-sense ADC readings,
  require the voltage to sit in the module window (not the sink window) with some hysteresis,
  and apply a timeout so a port doesn't flip on and off on a noisy or marginal reading.
- Read pH differentially: ADS1115 AIN1 − AIN3, not AIN1 against a fixed reference.
- Implement the new GPIO map end to end (see `docs/gpio-map.md`) — in particular, the four new
  ADC1 CC-sense inputs and the two new port power-enable outputs.

## Bring-up checklist (first assembled board)

1. **Before applying any power**, inspect the board and check for shorts on the 20 V, 5 V, and
   3.3 V rails to GND with a multimeter (continuity / low-ohms) — catch any solder bridge or
   assembly fault before it has a chance to do damage.
2. **Power from a USB-C PD charger**, not a plain 5 V-only source — the STUSB4500 needs a real
   PD source to negotiate with, and the board depends on that negotiation to reach 20 V.
3. **Measure the rails in order**: VBUS_RAW first, then +20V_BUS after Q1, then the buck output
   (~4.8 V), then the 3.3 V LDO output. Confirm each stage before trusting the next one.
4. **Check STUSB4500 status over I2C** (address 0x28) to confirm PD negotiation actually
   succeeded and see the attach state.
5. **Flash firmware over USB-C** now that D+/D− are wired — confirm the ESP32 enumerates, and
   that holding the button (IO0) while powering up enters download mode as expected.
6. **Leave the module ports disabled** (they default off) and verify the CC-sense ADC readings
   match the expected voltage table in `docs/module-port-spec.md` before enabling either port.
7. Only then, **connect an actual module** and confirm the port switches on within the module
   CC window and CAN traffic appears on the bus.

## Credits

Footprints and symbols for parts come from the JLCEDA/EasyEDA official library
(https://easyeda.com, https://lceda.cn) and are used within EasyEDA.
