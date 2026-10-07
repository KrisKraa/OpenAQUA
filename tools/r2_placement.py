"""R2 placement: ref -> (x_mm, y_mm, rotation) of the footprint bbox centre,
board coordinates with origin at the outline's top-left corner, y down
(same orientation as the EasyEDA canvas). Board is 154 x 67 mm.

Parts not listed keep their original position: connectors, edge LEDs and
anything that lines up with the enclosure (USBC1-3, LED4-6, RF1, U7, U8, U10, U11).

Zones: power top-left, ESP32 top-middle (antenna at the top edge, copper
keep-out), analog bottom-left, sensors bottom-middle, CAN + module ports right.
"""

PLACEMENT = {
    # ---------------- ESP32 + local parts
    'U15': (70.0, 13.0, 0),       # antenna up, flush with the top edge
    'C38': (57.0, 9.3, 0),        # 100nF at 3V3 pin
    'C37': (53.2, 7.4, 0),        # 10uF 0805
    'R11': (57.0, 11.1, 0),       # EN pull-up
    'C48': (57.0, 12.8, 0),      # EN cap
    'R12': (57.3, 22.7, 0),       # USB D- 22R
    'R13': (57.3, 24.4, 0),       # USB D+ 22R
    'R6': (57.0, 16.2, 0),        # display MOSI 22R
    'R7': (57.0, 14.5, 0),        # display SCLK 22R
    'CN2': (51.5, 24.5, 270),     # display cable

    # ---------------- USB-C PD input
    'U1': (17.0, 24.5, 0),
    'C4': (11.6, 27.8, 90),
    'C5': (9.7, 27.8, 90),
    'C46': (11.6, 23.6, 90),
    'C47': (12.3, 20.9, 0),
    'R2': (19.5, 28.6, 0),
    'U16': (12.5, 32.2, 0),       # USBLC6 ESD next to the receptacle
    'C6': (11.0, 18.6, 0),        # VBUS input bulk 10uF 50V
    'C7': (11.0, 16.4, 0),
    'Q1': (16.0, 15.2, 0),
    'R1': (19.4, 14.8, 90),
    'R37': (21.0, 17.6, 0),

    # ---------------- MP1584 buck 20V -> 5V (hot loop: C10/C26 - U13 - D8)
    'C10': (25.9, 15.1, 180),        # input 10uF 50V
    'C26': (25.9, 12.75, 0),        # input 100nF
    'U13': (26.5, 7.5, 180),
    'D8': (33.4, 6.0, 270),
    'L2': (42.0, 8.5, 90),
    'C27': (30.4, 7.5, 270),       # bootstrap
    'C29': (42.0, 17.8, 0),       # output 22uF
    'C30': (45.6, 18.0, 90),
    'R9': (21.6, 5.0, 90),       # FB top
    'R10': (19.8, 5.0, 90),      # FB bottom
    'R38': (28.4, 1.4, 0),      # EN pull-up
    'R39': (25.9, 18.2, 270),      # FREQ
    'R40': (22.0, 1.6, 0),      # COMP R
    'C28': (18.6, 1.6, 0),      # COMP C
    # LDO 5V -> 3V3
    'U14': (44.5, 24.4, 0),
    'C35': (47.5, 19.0, 90),
    'C36': (44.5, 29.4, 180),
    # power LEDs
    'LED1': (34.0, 22.5, 0), 'R25': (37.6, 22.5, 0),
    'LED2': (34.0, 24.6, 0), 'R24': (37.6, 24.6, 0),
    'LED3': (34.0, 26.7, 0), 'R26': (37.6, 26.7, 0),
    'R27': (5.0, 38.5, 0),         # LED4 resistor (LED4 fixed at left edge)

    # ---------------- analog: pH (RF1 fixed) + ADC + TDS
    'U6': (31.0, 55.5, 270),
    'C1': (36.2, 59.5, 90), 'C2': (38.1, 59.5, 90), 'C3': (40.3, 59.5, 90),
    'R31': (35.5, 51.0, 0), 'C11': (35.5, 49.0, 0),     # VREF filter
    'R19': (38.6, 54.0, 0), 'C43': (41.4, 54.0, 90),    # VOUT filter
    'R56': (38.6, 56.0, 0), 'C49': (43.4, 56.2, 90),    # VOCM filter
    'U4': (46.0, 51.5, 0),                               # ADS1115
    'C39': (46.0, 48.0, 0), 'C40': (49.4, 48.0, 90),
    'R16': (44.0, 44.0, 0), 'R17': (44.0, 45.7, 0),      # I2C pull-ups
    'R18': (49.0, 54.5, 0), 'C16': (49.0, 56.6, 0),      # TDS ADC filter
    'U3': (56.0, 48.5, 0),                               # MCP6002
    'C14': (60.6, 44.5, 90), 'C15': (62.5, 44.5, 90),
    'R32': (52.0, 43.0, 90), 'R33': (53.7, 43.0, 90), 'C12': (56.6, 42.0, 0),
    'R34': (61.8, 51.0, 90), 'C13': (63.6, 51.0, 90), 'R36': (61.0, 54.2, 0),
    'R35': (55.5, 53.8, 0),

    # ---------------- temp / leak inputs (connectors fixed at the bottom edge)
    'R21': (74.5, 51.5, 0), 'C45': (78.0, 51.5, 90),
    'R20': (91.5, 51.5, 0), 'C42': (95.0, 51.5, 90),
    'R22': (108.8, 51.5, 0), 'C44': (112.3, 51.5, 90),

    # ---------------- button connector + LED resistors (right of ESP32)
    'CN3': (90.0, 22.0, 270),
    'R23': (84.0, 16.4, 0), 'R15': (84.0, 18.2, 0), 'R14': (84.0, 20.0, 0),
    'R8': (84.0, 25.4, 0),

    # ---------------- module port 1 (USBC2 at right edge, y 32)
    'F2': (129.0, 12.0, 0),
    'Q2': (136.0, 14.0, 0),
    'R41': (135.5, 10.5, 0), 'R42': (139.5, 12.0, 90),
    'Q3': (142.0, 16.0, 0), 'R43': (142.0, 19.5, 0),
    'R44': (140.0, 24.0, 90), 'R45': (138.3, 24.0, 90),
    'R46': (140.0, 38.5, 90), 'R47': (138.3, 38.5, 90),
    'R29': (148.5, 20.9, 90),

    # ---------------- CAN transceiver between the ports
    'U2': (133.0, 41.0, 0),
    'C8': (127.5, 41.0, 90), 'C9': (128.5, 37.0, 0),
    'D1': (142.5, 44.0, 0), 'R3': (138.0, 45.0, 90), 'R55': (139.8, 45.0, 90),

    # ---------------- module port 2 (USBC3 at right edge, y 56)
    'F1': (122.0, 59.0, 0),
    'Q4': (129.0, 58.5, 0),
    'R48': (129.0, 62.0, 0), 'R49': (132.5, 61.0, 90),
    'Q5': (134.5, 57.0, 0), 'R50': (134.5, 53.5, 0),
    'R51': (140.0, 50.0, 90), 'R52': (138.3, 50.0, 90),
    'R53': (144.0, 63.0, 0), 'R54': (144.0, 61.3, 0),
    'R28': (148.5, 48.0, 90),

    # ---------------- added after the independent review
    'R57': (17.0, 20.2, 0),        # VBUS_VS_DISCH series R (1206)
    'C50': (24.5, 21.0, 0),        # +20V bulk after Q1
    'C51': (124.5, 12.0, 90),      # +20V bulk at the port feed
    'C52': (133.2, 16.8, 90),      # port 1 soft-start
    'C53': (126.0, 55.5, 90),      # port 2 soft-start
    'SW2': (58.4, 31.0, 0),        # RESET (reachable with the faceplate off)
    'SW1': (84.5, 34.5, 0),        # BOOT
}
