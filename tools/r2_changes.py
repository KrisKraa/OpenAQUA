"""OpenAQUA main controller R2: every electrical change relative to the
2026-10-08 PCB / 2026-05-27 schematic, in one reviewable place.

Used by build_r2_pcb.py (PCB) and build_r2_sch.py (schematic).
Pin names in comments come from the datasheets (STUSB4500 DS12499, MP1584 r1.0,
LMP91200 SNAS571E, ESP32-S3-WROOM-1 v1.8).
"""

# ---------------------------------------------------------------- parts to delete
REMOVE = [
    'R4', 'R5',   # 10R "series" resistors had both pads on the same net (did nothing)
    'R30',        # old PH_VCM divider; VCM is an output of the LMP91200
]

# ---------------------------------------------------------------- value / part swaps
# ref: (LCSC part, value, footprint template ref or None to keep footprint)
SWAP = {
    'C5':  ('C15849', '1uF', None),        # was 16 V, now sits on VBUS (20 V)
    'C6':  ('C13585', '10uF', None),       # was 10 V on USB VBUS -> 50 V
    'C10': ('C13585', '10uF', None),       # was 47 uF 10 V on 20 V bus -> 50 V
    'C26': ('C14663', '100nF', None),      # was 25 V on 20 V bus -> 50 V
    'C28': ('C1645', '150pF', None),       # MP1584 COMP: series R+C (datasheet table 3)
    'C29': ('C12891', '22uF', 'C10'),      # was 47 uF 0603 6.3 V; 1206 25 V
    'R31': ('C22775', '100Ω', None),       # now VREF RC filter (with C11)
    'R1':  ('C25803', '100kΩ', None),      # Q1 gate pull-up to source (same value)
    # --- from the independent review ---
    'U2':  ('C38695', 'TJA1051T/3', None),  # CAN transceiver with ±58 V bus-fault protection
                                            # (20 V shares the module connector); same SOIC-8 pinout,
                                            # VCC 5 V on pin 3, VIO 3.3 V on pin 5, S (silent) pin 8 low
    'U14': ('C6186', 'AMS1117-3.3', 'lcsc:C6186'),  # 1 A LDO in SOT-223 (TLV75533 was at its 500 mA
                                                    # limit and ~0.6 W in SOT-23-5)
    'C36': ('C12891', '22uF', 'C10'),       # AMS1117 output needs >= 22 uF
    'R20': ('C22935', '1MΩ', None),         # leak inputs are digital (ADC2 unusable with Wi-Fi):
    'R22': ('C22935', '1MΩ', None),         # 1 M pull-up detects water paths up to ~330 kΩ
}

# ---------------------------------------------------------------- new parts
# ref: (template ref to clone footprint from | 'lcsc:<C#>', LCSC part, value)
NEW = {
    # STUSB4500 support
    'C46': ('C2', 'C15849', '1uF'),        # VREG_1V2 decoupling
    'C47': ('C2', 'C15849', '1uF'),        # VREG_2V7 decoupling
    'R37': ('R1', 'C4216', '33kΩ'),        # Q1 gate series resistor (Vgs -15 V at 20 V, -3.75 V at 5 V)
    'R57': ('lcsc:C4410', 'C4410', '1kΩ'), # VBUS_VS_DISCH series R (datasheet: required, <= 50 mA)
    # MP1584
    'R38': ('R1', 'C25803', '100kΩ'),      # EN pull-up from VIN
    'R39': ('R1', 'C25803', '100kΩ'),      # FREQ -> ~900 kHz
    'R40': ('R1', 'C25803', '100kΩ'),      # COMP series R
    # USB data ESD
    'U16': ('lcsc:C7519', 'C7519', 'USBLC6-2SC6'),
    # ESP32 EN RC
    'C48': ('C2', 'C15849', '1uF'),
    # Module port 1 (USBC2, silk "CAN1") switched VBUS + CC sense
    'Q2':  ('Q1', 'C181093', 'AO3407'),
    'Q3':  ('Q1', 'C8545', '2N7002'),
    'R41': ('R1', 'C25803', '100kΩ'),      # Q2 gate-source
    'R42': ('R1', 'C31850', '22kΩ'),       # Q2 gate series
    'R43': ('R1', 'C25803', '100kΩ'),      # Q3 gate pull-down: port OFF at boot
    'R44': ('R1', 'C25804', '10kΩ'),       # CC1 Rp to 3V3
    'R45': ('R1', 'C21190', '1kΩ'),        # CC1 -> ADC
    'R46': ('R1', 'C25804', '10kΩ'),       # CC2 Rp
    'R47': ('R1', 'C21190', '1kΩ'),        # CC2 -> ADC
    # Module port 2 (USBC3, silk "CAN2")
    'Q4':  ('Q1', 'C181093', 'AO3407'),
    'Q5':  ('Q1', 'C8545', '2N7002'),
    'R48': ('R1', 'C25803', '100kΩ'),
    'R49': ('R1', 'C31850', '22kΩ'),
    'R50': ('R1', 'C25803', '100kΩ'),
    'R51': ('R1', 'C25804', '10kΩ'),
    'R52': ('R1', 'C21190', '1kΩ'),
    'R53': ('R1', 'C25804', '10kΩ'),
    'R54': ('R1', 'C21190', '1kΩ'),
    # CAN termination jumper (remove when the controller is mid-bus)
    'R55': ('R1', 'C21189', '0Ω'),
    # +20V_BUS bulk after Q1 (port switch-on must not brown out the bus)
    'C50': ('C10', 'C13585', '10uF'),
    'C51': ('C10', 'C13585', '10uF'),
    # port switch soft-start: gate-drain caps -> ~0.5 ms VBUS ramp
    'C52': ('C2', 'C21122', '22nF'),
    'C53': ('C2', 'C21122', '22nF'),
    # on-board BOOT (IO0) and RESET (EN) buttons for bring-up
    'SW1': ('lcsc:C318884', 'C318884', 'BOOT'),
    'SW2': ('lcsc:C318884', 'C318884', 'RESET'),
    # LMP91200 VOCM -> ADS1115 AIN3 (differential pH measurement)
    'R56': ('R1', 'C21190', '1kΩ'),
    'C49': ('C2', 'C14663', '100nF'),
}

# ---------------------------------------------------------------- pin -> net
# Complete assignment for every pin that changes (existing or new parts).
NETS = {
    # --- STUSB4500 (U1) ---
    ('U1', '1'): 'USB_CC1',            # CC1DB -> CC1 (dead-battery mode)
    ('U1', '2'): 'USB_CC1',
    ('USBC1', 'A5'): 'USB_CC1',
    ('U1', '5'): 'USB_CC2',            # CC2DB -> CC2
    ('U1', '4'): 'USB_CC2',
    ('USBC1', 'B5'): 'USB_CC2',
    ('U1', '6'): 'PD_RESET',           # RESET is active HIGH -> pulled to GND
    ('R2', '1'): 'PD_RESET',
    ('R2', '2'): 'GND',
    ('U1', '7'): 'I2C_SCL',            # NVM/PDO config from the ESP32
    ('U1', '8'): 'I2C_SDA',
    ('U1', '21'): 'PD_VREG12', ('C46', '1'): 'PD_VREG12', ('C46', '2'): 'GND',
    ('U1', '23'): 'PD_VREG27', ('C47', '1'): 'PD_VREG27', ('C47', '2'): 'GND',
    ('U1', '22'): 'GND',               # VSYS unused -> GND (datasheet)
    ('U1', '24'): 'USB_VBUS_RAW',      # VDD from VBUS, not from 3V3 (chicken-and-egg)
    ('C4', '1'): 'USB_VBUS_RAW',
    ('C5', '1'): 'USB_VBUS_RAW',
    ('U1', '25'): 'GND',               # exposed pad
    ('U1', '16'): 'PD_EN_SNK',
    ('U1', '18'): 'PD_VBUS_VS', ('R57', '1'): 'PD_VBUS_VS', ('R57', '2'): 'USB_VBUS_RAW',
    # Q1 power path switch: gate pulled up to source, EN_SNK pulls it down via R37
    ('R1', '1'): 'Q1_GATE', ('R1', '2'): 'USB_VBUS_RAW',
    ('Q1', '1'): 'Q1_GATE',
    ('R37', '1'): 'Q1_GATE', ('R37', '2'): 'PD_EN_SNK',
    # USB-C receptacle shells to GND
    **{('USBC1', s): 'GND' for s in '1234'},
    **{('USBC2', s): 'GND' for s in '1234'},
    **{('USBC3', s): 'GND' for s in '1234'},
    # --- USB 2.0 data to ESP32 (IO19/IO20 via R12/R13) + ESD ---
    ('USBC1', 'A6'): 'USB_D+', ('USBC1', 'B6'): 'USB_D+',
    ('USBC1', 'A7'): 'USB_D-', ('USBC1', 'B7'): 'USB_D-',
    ('U16', '1'): 'USB_D+', ('U16', '6'): 'USB_D+',
    ('U16', '3'): 'USB_D-', ('U16', '4'): 'USB_D-',
    ('U16', '2'): 'GND', ('U16', '5'): '+3V3',
    # --- MP1584 buck (U13) ---
    ('U13', '2'): 'BUCK_EN', ('R38', '1'): '+20V_BUS', ('R38', '2'): 'BUCK_EN',
    ('U13', '6'): 'BUCK_FREQ', ('R39', '1'): 'BUCK_FREQ', ('R39', '2'): 'GND',
    ('U13', '3'): 'BUCK_COMP', ('R40', '1'): 'BUCK_COMP', ('R40', '2'): 'BUCK_COMP_RC',
    ('C28', '1'): 'BUCK_COMP_RC', ('C28', '2'): 'GND',
    ('D8', '1'): 'U13_1',              # cathode to SW (was reversed: shorted SW to GND)
    ('D8', '2'): 'GND',                # anode to GND
    # --- ESP32-S3 (U15) ---
    ('U15', '3'): 'ESP_EN', ('R11', '2'): 'ESP_EN', ('C48', '1'): 'ESP_EN', ('C48', '2'): 'GND',
    # GPIO map re-planned for layout: ESP32 sits antenna-up at the top edge, so
    # left-column pins serve the display connector (left of the module), bottom-row
    # pins serve sensors / CAN / port 2 (below and right), right-column pins serve
    # port 1 and the button. Port CC sensing needs ADC1 (GPIO1..10).
    ('U15', '4'): 'DISP_SCLK',         # IO4
    ('U15', '5'): 'DISP_MOSI',         # IO5
    ('U15', '6'): 'DISP_CS',           # IO6
    ('U15', '7'): 'DISP_DC',           # IO7
    ('U15', '8'): 'DISP_RST',          # IO15 (unchanged)
    ('U15', '9'): 'DISP_BL',           # IO16
    ('U15', '10'): 'LED4_DRV',         # IO17 -> R27 -> LED4 (left edge)
    ('R27', '1'): 'LED4_DRV',
    ('U15', '11'): 'I2C_SDA',          # IO18
    ('U15', '12'): 'I2C_SCL',          # IO8 (unchanged)
    ('U15', '15'): 'TDS_EXCITE',       # IO3
    ('U15', '17'): 'P2_CC1_SENSE',     # IO9  ADC1_CH8
    ('U15', '18'): 'P2_CC2_SENSE',     # IO10 ADC1_CH9
    ('U15', '19'): 'TEMP_DATA',        # IO11
    ('U15', '20'): 'LEAK1_SIG',        # IO12
    ('U15', '21'): 'LEAK2_SIG',        # IO13
    ('U15', '22'): 'P2_PWR_EN',        # IO14
    ('U15', '23'): 'LED6_DRV',         # IO21 -> R28 -> LED6 (port 2 side)
    ('R28', '1'): 'LED6_DRV',
    ('U15', '24'): 'CAN_TX',           # IO47
    ('U15', '25'): 'CAN_RX',           # IO48
    ('U15', '31'): 'BTN_LED_R',        # IO38
    ('U15', '32'): 'BTN_LED_G',        # IO39
    ('U15', '33'): 'BTN_LED_B',        # IO40
    ('U15', '34'): 'LED5_DRV',         # IO41 -> R29 -> LED5 (port 1 side)
    ('R29', '1'): 'LED5_DRV',
    ('U15', '35'): 'P1_PWR_EN',        # IO42
    ('U15', '38'): 'P1_CC2_SENSE',     # IO2  ADC1_CH1
    ('U15', '39'): 'P1_CC1_SENSE',     # IO1  ADC1_CH0
    # unchanged: IO0 BTN_SW_A (pin 27), IO19/IO20 USB via R12/R13 (pins 13/14)
    # LED4 was mounted backwards (anode on GND)
    ('LED4', '1'): 'GND', ('LED4', '2'): 'LED4_1',
    # --- Module port 1: USBC2 via F2 ---
    ('F2', '2'): 'P1_VFUSED',
    ('Q2', '2'): 'P1_VFUSED', ('Q2', '3'): 'P1_VBUS', ('Q2', '1'): 'P1_GATE',
    ('R41', '1'): 'P1_VFUSED', ('R41', '2'): 'P1_GATE',
    ('R42', '1'): 'P1_GATE', ('R42', '2'): 'P1_PULL',
    ('Q3', '3'): 'P1_PULL', ('Q3', '2'): 'GND', ('Q3', '1'): 'P1_PWR_EN',
    ('R43', '1'): 'P1_PWR_EN', ('R43', '2'): 'GND',
    ('USBC2', 'A4B9'): 'P1_VBUS', ('USBC2', 'B4A9'): 'P1_VBUS',
    ('USBC2', 'A5'): 'P1_CC1', ('R44', '1'): '+3V3', ('R44', '2'): 'P1_CC1',
    ('R45', '1'): 'P1_CC1', ('R45', '2'): 'P1_CC1_SENSE',
    ('USBC2', 'B5'): 'P1_CC2', ('R46', '1'): '+3V3', ('R46', '2'): 'P1_CC2',
    ('R47', '1'): 'P1_CC2', ('R47', '2'): 'P1_CC2_SENSE',
    # --- Module port 2: USBC3 via F1 ---
    ('F1', '2'): 'P2_VFUSED',
    ('Q4', '2'): 'P2_VFUSED', ('Q4', '3'): 'P2_VBUS', ('Q4', '1'): 'P2_GATE',
    ('R48', '1'): 'P2_VFUSED', ('R48', '2'): 'P2_GATE',
    ('R49', '1'): 'P2_GATE', ('R49', '2'): 'P2_PULL',
    ('Q5', '3'): 'P2_PULL', ('Q5', '2'): 'GND', ('Q5', '1'): 'P2_PWR_EN',
    ('R50', '1'): 'P2_PWR_EN', ('R50', '2'): 'GND',
    ('USBC3', 'A4B9'): 'P2_VBUS', ('USBC3', 'B4A9'): 'P2_VBUS',
    ('USBC3', 'A5'): 'P2_CC1', ('R51', '1'): '+3V3', ('R51', '2'): 'P2_CC1',
    ('R52', '1'): 'P2_CC1', ('R52', '2'): 'P2_CC1_SENSE',
    ('USBC3', 'B5'): 'P2_CC2', ('R53', '1'): '+3V3', ('R53', '2'): 'P2_CC2',
    ('R54', '1'): 'P2_CC2', ('R54', '2'): 'P2_CC2_SENSE',
    # --- CAN transceiver TJA1051T/3 (U2): VCC 5 V, VIO 3.3 V ---
    ('U2', '3'): '+5V_MAIN', ('C8', '2'): '+5V_MAIN',   # C8 now VCC decoupling
    ('U2', '5'): '+3V3', ('C9', '1'): '+3V3',           # C9 now VIO decoupling
    # --- LDO AMS1117-3.3 (U14): 1 GND, 2/4(tab) VOUT, 3 VIN ---
    ('U14', '1'): 'GND', ('U14', '2'): '+3V3', ('U14', '4'): '+3V3', ('U14', '3'): '+5V_MAIN',
    # --- +20V bulk, port soft-start ---
    ('C50', '1'): '+20V_BUS', ('C50', '2'): 'GND',
    ('C51', '1'): '+20V_BUS', ('C51', '2'): 'GND',
    ('C52', '1'): 'P1_GATE', ('C52', '2'): 'P1_VBUS',
    ('C53', '1'): 'P2_GATE', ('C53', '2'): 'P2_VBUS',
    # --- BOOT / RESET buttons (pins 1+2 one side, 3+4 other side) ---
    ('SW1', '1'): 'BTN_SW_A', ('SW1', '2'): 'BTN_SW_A', ('SW1', '3'): 'GND', ('SW1', '4'): 'GND',
    ('SW2', '1'): 'ESP_EN', ('SW2', '2'): 'ESP_EN', ('SW2', '3'): 'GND', ('SW2', '4'): 'GND',
    # --- DS18B20 1-Wire: C45 off the data line (100 nF killed the 1-Wire timing), now 3V3 decoupling at U8 ---
    ('C45', '1'): '+3V3', ('C45', '2'): 'GND',
    # --- CAN termination via jumper R55 ---
    ('R3', '2'): 'CAN_TERM', ('R55', '1'): 'CAN_TERM', ('R55', '2'): 'CAN_L',
    # --- LMP91200 pH front end (U6) ---
    ('U6', '7'): 'PH_VCMHI',           # output: leave unconnected (was shorted to 3V3)
    ('U6', '9'): 'PH_VREF',            # reference input from filtered 3V3
    ('R31', '1'): '+3V3', ('R31', '2'): 'PH_VREF',
    ('C11', '1'): 'PH_VREF', ('C11', '2'): 'GND',
    ('U6', '8'): 'PH_VCM',             # buffered common-mode output -> probe reference (RF1 shield)
    ('U6', '11'): 'PH_VOCM', ('R56', '1'): 'PH_VOCM', ('R56', '2'): 'PH_VOCM_FILT',
    ('C49', '1'): 'PH_VOCM_FILT', ('C49', '2'): 'GND',
    ('U4', '7'): 'PH_VOCM_FILT',       # ADS1115 AIN3: measure AIN1 - AIN3
}

# Port 2 VBUS used to be USBC3_A4B9 etc.; old single-pin nets disappear automatically.

LCSC_FIELDS = ('Supplier Part', 'Manufacturer Part', 'Manufacturer')
