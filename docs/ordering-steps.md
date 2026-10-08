# From the R2 files to a JLCPCB order (EasyEDA Standard)

1. Log in at https://easyeda.com/editor (Standard edition). File → New → Project, name it "OpenAQUA R2".
2. File → Open → EasyEDA Source → `hardware/main-controller/r2/SCH_OpenAQUA_R2.json`. File → Save As → into "OpenAQUA R2".
3. Same for `hardware/main-controller/r2/PCB_OpenAQUA_R2.json`, same project.
4. In the PCB: Tools → Copper Area → Rebuild All (Shift+B).
5. Design → Design Rule Check; open Design Manager → DRC Errors. Expect 0.
6. View → 3D View: compare with the case (connectors at the edges, nothing tall under the display/button).
7. Fabrication → PCB Fabrication File (Gerber) → Order at JLCPCB.
   2 layers, 1.6 mm, 1 oz, **ENIG** (fine-pitch QFN/X2QFN parts), any colour.
8. PCB Assembly: top side. Export Fabrication → BOM and Fabrication → Pick and Place File if they aren't passed automatically.
   - Fix any "out of stock" line with an equivalent part (same value, package, voltage).
   - Through-hole connectors (CN2, CN3, U7, U8, U10, U11): JLC THT assembly or hand-solder.
   - **Check every rotation in JLC's placement preview**: ICs (pin 1), D8 (cathode band towards L2/U13), LEDs, USB-C, ESP32.
9. Buy separately: display module (8-pin cable to CN2), low-profile RGB button (CN3), U.FL→BNC bulkhead pigtail, GX12 (or similar) sensor connectors, probes.
10. Don't use "Convert to PCB" or "Update PCB" from the schematic unless you mean to — the PCB file is the routed source.
