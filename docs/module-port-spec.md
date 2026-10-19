# OpenAQUA module port v1

This is the spec for anyone designing an expansion module for OpenAQUA (power strip, fleece
roller, dosing pump, sensor module, whatever). It describes what the controller puts on each
module port, how a module should identify itself, and the safety limits you need to design
around. If you're building a module, read this whole page before you wire anything to the
connector.

Note: this is v1. Pin usage and the identification thresholds below may be refined as the first
real modules get built — if you're reading this months later, check for a newer revision.

## Connector

Each module port on the controller is a normal **USB-C receptacle**. You connect a module to it
with a **normal USB-C cable** — nothing proprietary. The cable needs its USB 2.0 data wires
(D+/D-) connected, because the controller uses them for CAN.

**Charge-only USB-C cables will not work.** Cheap "charging only" USB-C cables leave out the
D+/D- wires entirely (they're wired straight through for power only). If you use one of these,
power may appear to work but CAN will silently not connect — there is no signal on the bus and
no obvious error. Always use a full-featured USB-C data cable between the controller and a
module.

## Pin usage

| Pin | Function on the module port | Notes |
|---|---|---|
| VBUS | Power, 20 V nominal, switched by the controller | May be lower than 20 V depending on what the controller's own USB-C PD input negotiated — 5 V from a plain USB port or non-PD source, or 15 V if a PD charger can't do 20 V. Design your module's input stage to accept the full 5–20 V range. VBUS is OFF by default and is only switched on after the controller identifies a module (see below). |
| GND | Ground | — |
| D+ | CAN_H | Carried over the cable's USB D+ wire. Needs a real data-capable cable. |
| D− | CAN_L | Carried over the cable's USB D− wire. |
| CC | Module identification | See below. Present on both CC1 and CC2 of the controller's receptacle. |
| SBU1 / SBU2 | Unused | Not connected on the controller side. Leave unconnected on the module side too. |

## Module identification

The controller needs to tell the difference between "an OpenAQUA module is plugged in" and
"someone plugged in a phone / USB stick / charger by mistake" before it will turn VBUS on. It
does this purely through the CC pins, the same mechanism USB-C uses for power role detection —
no handshake, no firmware on the module required just to be recognized.

**What your module must do:** put a **22 kΩ resistor from CC to GND** on your module's
connector. If your module uses a receptacle (rather than a fixed cable), put this resistor on
**both CC1 and CC2**, so the module is recognized correctly no matter which way the cable is
plugged in.

**What the controller does:** each CC pin on the controller has a **10 kΩ pull-up (Rp) to
3.3 V**. With your 22 kΩ to GND on the other end, that forms a voltage divider the controller
reads on an ADC pin.

Expected voltage = 3.3 V × 22 kΩ / (22 kΩ + 10 kΩ) ≈ **2.27 V**.

(An earlier draft of this spec used 47 kΩ, for ~2.72 V. That was changed to 22 kΩ because the
controller's ADC pins run at 12 dB attenuation, which only reads reliably up to about 2.9 V —
2.72 V left almost no margin below that ceiling. 22 kΩ / 2.27 V sits comfortably inside the
ADC's usable range instead. If you built a module against the 47 kΩ version of this spec,
update it to 22 kΩ.)

### What the controller sees

| What's connected | Approx. CC voltage | Controller's response |
|---|---|---|
| Nothing plugged in | 3.3 V (pulled all the way up, no load) — above the ADC's ~2.9 V usable ceiling, so it reads as pinned/saturated | Port stays off |
| OpenAQUA module (22 kΩ CC→GND) | ~2.27 V | Port recognized as a module — VBUS enabled |
| Phone / USB device (5.1 kΩ Rd to GND, standard USB sink) | ~1.11 V | Port stays off — this is a USB power sink, not a module |
| Cable with an e-marker (Ra, 1 kΩ, visible on the other CC line) | ~0.3 V | Port stays off |
| Charger / power source (its own Rp pull-up facing the controller's Rp) | above 3.3 V, or an indeterminate Rp-vs-Rp condition | Port stays off |
| Legacy USB-A-to-C cable (56 kΩ pull-up to 5 V on the far CC pin, instead of a proper Rd) | Also pins the ADC high — reads the same as nothing plugged in | Port stays off |

The controller only turns VBUS on when a CC pin reads inside the **module window, suggested
2.0–2.5 V**, and it must **never** turn VBUS on when a CC pin reads inside the **sink window,
0.8–1.6 V** (that's the range a phone, USB stick, or other normal USB device will present — if
you see a reading there, something that is not an OpenAQUA module is plugged in). Anything
outside both windows, including anything pinned at or near the ADC's saturation ceiling, is
also treated as "not a module."

## Power budget

Each port is protected by a **0.3 A hold-current PTC fuse**. At 20 V that's about **6 W**
available per port, continuous. Don't design a module that needs more than that from the port
itself.

Modules should also limit their own inrush current at power-on — a big, uncontrolled input
capacitor will trip the PTC or sag the port voltage when the controller switches VBUS on.
Either add a soft-start to your input stage, or keep your module's input capacitance to
**10 µF or less** so inrush stays low enough for the PTC and the controller's switch FET.

## CAN bus

- Transceiver on the controller: **NXP TJA1051T/3** (3.3 V CAN, VIO side; powered from 5 V on
  VCC). An earlier draft of the controller used an SN65HVD230, which is only rated for
  −4…+16 V on its bus pins — not enough margin given that the module port connector and cable
  carry up to 20 V on the same connector as CAN_H/CAN_L. The TJA1051T/3 is rated for ±58 V bus
  faults, which is the right margin for a connector that also carries 20 V. If you're designing
  your own module, pick a similarly bus-fault-protected transceiver rather than a bare SN65HVD230
  — your CAN lines sit in the same cable as the port's power.
- Suggested bitrate: **125–250 kbit/s**. Match whatever the controller firmware uses for the
  bus — this isn't something a module can negotiate on its own.
- Termination: the CAN bus needs 120 Ω termination at each physical end, not at every node.
  - The controller has a termination resistor behind a jumper (**R55**, 0 Ω when fitted).
    - Fit R55 if the controller sits at **one end** of the bus (only one module port is used,
      or modules are only ever daisy-chained off one port).
    - Remove R55 if modules are connected to **both** of the controller's module ports (i.e.
      the controller sits in the **middle** of the bus) — in that case, terminate at the two
      far-end modules instead.
  - **Modules should have two CAN ports** (so they can be daisy-chained: cable in from the
    previous device, cable out to the next one) and their own **optional 120 Ω termination
    jumper**, fitted only on a module that is the last one at the end of a chain.

## Safety notes

- **These ports are not USB**, even though they use a USB-C connector and cable. VBUS can be up
  to 20 V, and D+/D− carry CAN signaling, not USB data. Label the ports on the case (e.g. "CAN1
  / CAN2 — not USB") so nobody plugs a phone or USB drive into them expecting it to charge or
  mount as a drive.
- The CC-based identification above is the controller's safeguard against applying 20 V to
  something that expects 5 V, but it is not a certified USB-C power-role negotiation — don't
  rely on these ports behaving like a standards-compliant USB-C port for anything other than
  OpenAQUA modules.
- Always use a genuine OpenAQUA module, or a module you've built to this spec, on these ports.
- **No reverse-current blocking on the controller side (yet).** The port's power switch is a
  P-FET, and a P-FET's body diode still conducts in reverse even when the switch is commanded
  off. If your module has its own power source and can put voltage back onto VBUS, it could
  back-feed the controller while the controller itself is unpowered or has that port disabled.
  Don't design a module that can source current onto VBUS.
- **Don't assume an instant power cut.** Firmware is expected to switch a port's VBUS off
  quickly (on the order of 1 ms) once it sees the CC line go open, but there will always be
  some delay between the cable coming loose and the port actually turning off. Don't design a
  module whose safety depends on VBUS disappearing the instant it's unplugged.
