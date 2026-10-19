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
  100 kΩ gate-source resistor plus a series resistor (R37) to VBUS_EN_SNK, as in ST's reference
  design. R37 was originally 22 kΩ; an independent review changed it to **33 kΩ**, giving
  Vgs ≈ -15 V at a 20 V input and ≈ -3.75 V at 5 V — more margin under the FET's ±20 V rating,
  across the whole input range the board can actually see.
- **USB data lines not connected to the ESP32.** There was no way to flash firmware over the
  USB-C input port at all. **R2:** D+/D− now routed to the ESP32 (IO20/IO19) through the
  existing 22 Ω series resistors, with a USBLC6-2SC6 ESD protector (U16) added.
- **USB-C shells not grounded.** **R2:** all three USB-C connector shells tied to GND.
- **STUSB4500's VBUS_VS_DISCH pin had no series resistor.** This pin discharges VBUS after a
  PD source is removed, and the datasheet requires a series resistor to keep that discharge
  current at or below 50 mA. **R2:** added R57, 1 kΩ, between VBUS_VS_DISCH and raw VBUS.

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
  routed through a 100 kΩ pull-up from +20V_BUS instead. This follows common practice — the
  MP1584's own datasheet reference design ties EN to VIN the same way — so this isn't a
  leftover shortcut, it's the intended way to wire this pin.
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
- **Module identification resistor revised: 47 kΩ → 22 kΩ.** The module-side CC resistor was
  originally spec'd at 47 kΩ (≈2.72 V with the controller's 10 kΩ pull-up). An independent
  review flagged that the ESP32-S3's ADC, at the 12 dB attenuation needed for this voltage
  range, only reads reliably up to about 2.9 V — 2.72 V left almost no margin, and an empty
  port (which pulls all the way to 3.3 V) would itself saturate the ADC input. **R2:** the
  module-side resistor is now spec'd at 22 kΩ (≈2.27 V), with a narrower suggested module
  window of 2.0–2.5 V, comfortably clear of both the sink window and the ADC's ceiling. Also
  worth knowing: a legacy USB-A-to-C cable's 56 kΩ-to-5V pull-up produces the same saturated
  reading as an empty port, so it correctly leaves the port off rather than being mistaken for
  a module. See `docs/module-port-spec.md` for the full table.
- Port mapping (current, after the layout-driven GPIO replan — see the ESP32 section below):
  **Port 1 = USBC2** (silk "CAN1"): CC1 → IO1, CC2 → IO2, power enable → IO42.
  **Port 2 = USBC3** (silk "CAN2"): CC1 → IO9, CC2 → IO10, power enable → IO14.
- Each port is protected by a 0.3 A-hold PTC fuse (F2 on port 1, F1 on port 2), giving roughly
  6 W of budget per port at 20 V.
- **Switching a port on could brown out the 20 V bus.** Enabling a port's FET into a module
  with any real input capacitance draws an inrush current that, without anything to soften it,
  could sag +20V_BUS enough to disturb everything else on it. **R2:** added bulk capacitance
  on the bus itself (C50/C51, 10 µF 50 V each) plus a gate-drain capacitor on each port switch
  (C52 on port 1, C53 on port 2, 22 nF) that gives each FET roughly a 0.5 ms soft-start ramp
  instead of slamming on instantly.

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
- **A 100 nF capacitor on the DS18B20 temperature sensor's 1-Wire data line.** This bug was
  present in the original board too, not just the first R2 draft. 1-Wire relies on fast edges
  on a single shared data line; with a 4.7 kΩ bus pull-up, 100 nF there gives a rise time of
  about 470 µs — far too slow for the bus timing, so the sensor would simply never answer.
  **R2:** C45 moved off the data line entirely; it's now a 3.3 V decoupling cap at the
  temperature connector (U8) instead.
- **Leak inputs read on the wrong kind of pin.** The leak sensor inputs land on GPIO12/13,
  which are ADC2 pins — and ADC2 can't be used reliably while Wi-Fi is active on the ESP32-S3,
  which this board needs. **R2:** firmware reads these digitally instead of as analog inputs,
  and the pull-ups (R20, R22) were changed from 10 kΩ to **1 MΩ** so that a resistive water
  path between the leak probe's pads — typically tens of kΩ for aquarium water, up to roughly
  330 kΩ — pulls the digital input low enough to register as "leak." The original 10 kΩ
  pull-up would have needed a water path under about 3.3 kΩ to register at all, which is far
  lower resistance than a real leak would actually present.
- **On-board bring-up buttons added.** **R2:** SW1 (wired to IO0 / BTN_SW_A) acts as a BOOT
  button, and SW2 (wired to EN / ESP_EN) acts as a RESET button — both directly on the board,
  so the enclosure's front-panel button isn't needed just to flash firmware or reset the chip
  during bring-up.

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

- **CAN transceiver wasn't rated for the voltage sharing its connector.** The board used an
  SN65HVD230, which is only rated for −4…+16 V on its bus pins. But CAN_H/CAN_L share the
  module port's USB-C connector and cable with the port's switched power, which can be up to
  20 V — above the transceiver's bus-fault rating. **R2:** swapped to an NXP **TJA1051T/3**
  (LCSC C38695), rated for ±58 V bus faults, with the same SOIC-8 pinout. It runs from VCC on
  the 5 V rail and VIO on 3.3 V.
- **R4/R5 did nothing.** These were meant to be 10 Ω series resistors on CAN_H/CAN_L, but both
  pads of each were wired to the same net — zero volts across them, no effect. **R2:** removed.
- **120 Ω termination is now a jumper (R55, 0 Ω).** Fit it when the controller sits at one end
  of the CAN bus. Remove it when modules are connected to **both** module ports (controller in
  the middle of the bus) and terminate instead at the two far-end modules.

## Parts & voltage ratings

- **3.3 V LDO was at its current limit.** The original TLV75533 is only rated for 500 mA, and
  at the currents this board actually draws it would end up dissipating around 0.6 W in a
  SOT-23-5 package — more than that small a package can comfortably shed. **R2:** swapped to
  an **AMS1117-3.3**, a 1 A LDO in a SOT-223 package with much more thermal headroom. Its
  output capacitor (C36) also needed to grow to meet the AMS1117's own minimum — now 22 µF.

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

The board is laid out and routed as a 2-layer, 154 × 67 mm board with a solid GND plane on the bottom layer, split into zones: power (USB-C PD input +
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
- **Firmware**: bring-up firmware exists (`firmware/openaqua-main-r2/`, tested in the Wokwi
  simulator), but STUSB4500 PDO programming and the CAN protocol are not written yet (see below).
- **No TVS protection on the USB-C input's VBUS/CC lines.** Considered low risk since PD
  sources always start by presenting 5 V before any higher voltage is negotiated, but a later
  revision could add an ESDA25P35 (or similar) at R3 on that input for extra margin.
- **Module ports have no reverse-current blocking.** The port switch FETs (AO3407) still
  conduct through their body diode in reverse even when switched off, so a self-powered module
  could in principle back-feed the controller while it's unpowered or that port is disabled.
  Worth an eFuse (e.g. a TPS25947) in a later revision at R3; see also the warning in
  `docs/module-port-spec.md` telling module designers not to source current onto VBUS.
- **Port shutoff speed matters.** Firmware needs to switch a port's VBUS off quickly — on the
  order of 1 ms — once its CC line reads open, so a module can't be left powered after it's
  unplugged for longer than that.
- **RGB button LED resistors (220 Ω) assume a common-cathode LED with no built-in resistors.**
  If the actual button part turns out to have different internal resistance, or isn't
  common-cathode, green and blue may end up visibly dimmer than red. Worth double-checking
  against the specific button's datasheet before finalizing.

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
- Check the STUSB4500's negotiated PD contract over I2C before enabling any module port — the
  bus voltage feeding the ports isn't always 20 V (a plain PC USB port behaves as 5 V, and a
  charger that can't do 20 V may fall back to 15 V), so firmware needs to know what's actually
  on the bus rather than assuming 20 V.
- Switch a port's VBUS off within about 1 ms of its CC line reading open. The bring-up firmware
  polls the ports from `loop()` (a few ms per pass, longer while the display redraws); a timer
  interrupt or comparator would be needed to guarantee 1 ms.
- Read the leak inputs (GPIO12/13) as plain digital inputs, not through the ADC — they're on
  ADC2, which doesn't work reliably with Wi-Fi active.

## Bring-up checklist (first assembled board)

1. **Before applying any power**, inspect the board and check for shorts on the 20 V, 5 V, and
   3.3 V rails to GND with a multimeter (continuity / low-ohms) — catch any solder bridge or
   assembly fault before it has a chance to do damage.
2. **Power from a USB-C PD charger**, not a plain 5 V-only source — the STUSB4500 needs a real
   PD source to negotiate with, and the board depends on that negotiation to reach 20 V.
3. **Measure the rails in order**: VBUS_RAW first, then +20V_BUS after Q1, then the buck output
   (~4.8 V), then the 3.3 V LDO output. Confirm each stage before trusting the next one.
4. **Check STUSB4500 status over I2C** (address 0x28) to confirm PD negotiation actually
   succeeded, see the attach state, and confirm which PDO was actually accepted — don't assume
   it's 20 V; a plain USB port or a charger that can't do 20 V will leave the bus at 5 V or
   15 V instead.
5. **Flash firmware over USB-C** now that D+/D− are wired — confirm the ESP32 enumerates, and
   that holding the button (IO0) while powering up enters download mode as expected. The board
   also has on-board BOOT (SW1) and RESET (SW2) buttons, so this doesn't depend on the
   enclosure's front-panel button being wired up yet.
6. **Leave the module ports disabled** (they default off) and verify the CC-sense ADC readings
   match the expected voltage table in `docs/module-port-spec.md` before enabling either port.
7. Only then, **connect an actual module** and confirm the port switches on within the module
   CC window and CAN traffic appears on the bus.

## Credits

Footprints and symbols for parts come from the JLCEDA/EasyEDA official library
(https://easyeda.com, https://lceda.cn) and are used within EasyEDA.
