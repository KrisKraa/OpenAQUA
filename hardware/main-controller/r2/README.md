# OpenAQUA main controller — R2 (EasyEDA Standard)

| File | What it is |
|---|---|
| `SCH_OpenAQUA_R2.json` | Schematic, all R2 fixes applied (EasyEDA Std source) |
| `PCB_OpenAQUA_R2.json` | 2-layer PCB, placed and routed, GND pours on both layers |
| `sch_preview/` | PNG previews of the schematic |

Why everything changed: see [`docs/r2-design-review.md`](../../../docs/r2-design-review.md).
Pin map: [`docs/gpio-map.md`](../../../docs/gpio-map.md). Module port rules: [`docs/module-port-spec.md`](../../../docs/module-port-spec.md).

## Import into EasyEDA (Standard edition)

1. Open https://easyeda.com/editor (Standard, not Pro).
2. **File → Open → EasyEDA Source…** and pick `SCH_OpenAQUA_R2.json`. Save it into your project (**File → Save As**, choose your OpenAQUA project).
3. Do the same for `PCB_OpenAQUA_R2.json` and save it into the **same** project.
4. In the PCB: **Tools → Copper Area → Rebuild All Copper Areas** (shortcut **Shift+B**). The pour outlines are in the file but their fill is computed by EasyEDA.
5. Run **Design → Design Rule Check**. Rules used for routing: 0.2 mm clearance, 0.25 mm default track, 0.6/0.3 mm vias (JLCPCB standard 2-layer is fine with this).
6. Optional: open the 3D view and check against `mechanical/Main Controller.step`.

If you later change the schematic, use **Design → Update PCB** from the schematic with both documents in the same project.

## Board summary

- 154 × 67 mm, 2 layers, 1.6 mm. Outline, mounting holes, USB-C ports and edge LEDs are unchanged from the original (they match the case).
- Bottom layer: solid GND plane (only short crossings on the bottom). Top: GND pour between tracks, stitching vias every ~5 mm.
- No copper under the ESP32 antenna (top edge, both layers).
- Buck converter: switch node is one short wide trace (U13 → D8 → L2), input caps sit directly on VIN/GND.
- pH input: short trace from the U.FL to the LMP91200 with guard traces on both sides and a guard copper patch on the bottom layer (TI SNAS571E §10). For best results leave the solder mask off this area and clean the board after soldering.
- 20 V feed to the module ports is hand-routed between the ESP32 and the analog section, away from the pH/TDS circuits.

## Regenerating

Everything here is generated — don't hand-edit the JSON, change the scripts and rebuild:

```bash
python3 tools/build_r2_pcb.py        # parts, nets, placement
python3 tools/route_r2.py --passes 30 # Freerouting (needs Java 25 + freerouting-2.5.0.jar, see FREEROUTING_DIR)
python3 tools/finalize_r2.py         # pours, keep-outs, stitching (needs numpy + scipy)
python3 tools/check_r2_final.py      # connectivity / clearance / edge / antenna checks
python3 tools/build_r2_sch.py --png  # schematic from the same change list
```

Footprints and symbols for new parts come from the JLCEDA/EasyEDA official library (https://easyeda.com, https://lceda.cn).
