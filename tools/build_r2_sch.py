"""Build the R2 schematic (EasyEDA Std JSON) from the 2026-05-27 original.

  python3 tools/build_r2_sch.py
      -> hardware/main-controller/r2/SCH_OpenAQUA_R2.json
      -> hardware/main-controller/r2/sch_preview/*.png (needs macOS qlmanage)

Everything electrical comes from r2_changes.py; the target connectivity is the
netlist of build_r2_pcb.build(). The script keeps the original drawing, cuts pins
loose where their net changes (pruning the wire branch that only served them),
renames flags of islands whose net was renamed, draws the new parts in free sheet
areas, and gives every remaining pin/island its net flag (searching a stub that
does not touch or overlap anything). It finishes with a pin-level comparison
against the PCB netlist and exits non-zero on any difference.
"""
import json, os, sys, re, collections, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r2_changes as CH
from schedit import (Sheet, Lib, Xf, fmt, new_gid, fresh_ids, make_flag, flag_info, auto_named,
                     verify, DIRV, R2, on_seg, rect_hit, flag_rects)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(ROOT, 'hardware/main-controller/original/SCH_Aquacontrol_2026-05-27.json')
OUT_DIR = os.path.join(ROOT, 'hardware/main-controller/r2')
OUT = os.path.join(OUT_DIR, 'SCH_OpenAQUA_R2.json')
LCSC_DIR = os.path.join(ROOT, 'tools/lcsc_cache')

# flags in the original that sit on a net with another name; kept as drawn
ALLOWED_EXTRA = ('BTN_SW_B', 'BT_LED_COM', 'TDS_SENSE')


# ------------------------------------------------------------------ library data

def lcsc(part):
    path = os.path.join(LCSC_DIR, part + '.json')
    if not os.path.exists(path):
        url = 'https://easyeda.com/api/products/%s/components?version=6.5.54' % part
        subprocess.run(['curl', '-s', '-m', '30', '-o', path, url], check=True)
    return json.load(open(path))['result']


def lcsc_attrs(part):
    cp = lcsc(part)['dataStr']['head'].get('c_para', {})
    a = {k: cp[k] for k in ('Supplier', 'Supplier Part', 'Manufacturer', 'Manufacturer Part', 'JLCPCB Part Class') if k in cp}
    if 'Manufacturer Part' in cp: a['spiceSymbolName'] = cp['Manufacturer Part']
    return a


def lcsc_symbol(part, ref, value):
    """Schematic symbol from the LCSC/EasyEDA library JSON, origin at the library's (x, y)."""
    ds = lcsc(part)['dataStr']; h = ds['head']; cp = h.get('c_para', {})
    attrs = {'package': cp.get('package', '')}
    for k in ('Supplier', 'Supplier Part', 'Manufacturer', 'Manufacturer Part', 'JLCPCB Part Class'):
        if k in cp: attrs[k] = cp[k]
    attrs['spicePre'] = cp.get('pre', 'U?').rstrip('?')
    attrs['spiceSymbolName'] = cp.get('name', '')
    head = ['LIB', fmt(h['x']), fmt(h['y']), '`'.join(k + '`' + v for k, v in attrs.items()) + '`',
            '', '0', new_gid(), h.get('puuid', ''), h.get('uuid', ''), '0', '', 'yes', 'yes', '', str(h.get('utime', '')), '']
    shapes = [s for s in ds['shape'] if not (s.startswith('T~P') or s.startswith('T~N'))]
    x, y = float(h['x']), float(h['y'])
    shapes.append('T~N~%s~%s~0~#000080~Arial~~~~~comment~%s~1~start~%s~0~pinpart' % (fmt(x), fmt(y - 25), value, new_gid()))
    shapes.append('T~P~%s~%s~0~#000080~Arial~~~~~comment~%s~1~start~%s~0~pinpart' % (fmt(x), fmt(y - 34), ref, new_gid()))
    lib = Lib(fresh_ids('~'.join(head) + ''.join('#@$' + s for s in shapes)))
    return lib


def place(lib, at, deg=0, mirror=False):
    """Move a symbol so its origin lands on `at`, rotated `deg` clockwise about it."""
    ox, oy = lib.xy()
    lib.transform(Xf(c=(ox, oy), deg=deg, mirror=mirror, d=(at[0] - ox, at[1] - oy)))
    return lib


def clone(sh, tmpl_ref, ref, value):
    _, src = sh.lib(tmpl_ref)
    lib = Lib(fresh_ids(src.raw()))
    lib.set_text('P', ref); lib.set_text('N', value)
    return lib


def labels(lib, where):
    """Place prefix/value texts next to a 2-terminal symbol: 'above', 'below', 'right', 'left'."""
    pins = list(lib.pins().values())
    xs = [p[0] for p in pins]; ys = [p[1] for p in pins]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    _, fp = lib.text('P'); _, fn = lib.text('N')
    wp, wn = 5 * len(fp[12]), 5 * len(fn[12])
    if where == 'above':
        P, N = (cx - wp / 2, cy - 17), (cx - wn / 2, cy - 8)
    elif where == 'below':
        P, N = (cx - wp / 2, cy + 16), (cx - wn / 2, cy + 25)
    elif where == 'right':
        P, N = (cx + 8, cy - 1), (cx + 8, cy + 8)
    elif where == 'left':
        P, N = (cx - 8 - wp, cy - 1), (cx - 8 - wn, cy + 8)
    else:
        P, N = where
    lib.set_text('P', xy=P); lib.set_text('N', xy=N)


# ------------------------------------------------------------------ reference netlist

def reference():
    from build_r2_pcb import build
    nl = build().netlist()
    return {n: sorted(set(l)) for n, l in nl.items()}


# ------------------------------------------------------------------ helpers on the sheet

class B:
    """Thin drawing helper bound to a sheet."""
    def __init__(s, sh):
        s.sh = sh

    def P(s, ref, num):
        x, y, d = s.sh.pin(ref, num); return (x, y)

    def wire(s, *pts):
        s.sh.add_wire([tuple(map(R2, p)) for p in pts])

    def flag(s, name, at, outward, stub=0):
        """flag at pin/wire point `at`, optionally after a straight stub."""
        dx, dy = DIRV[outward]
        end = (R2(at[0] + dx * stub), R2(at[1] + dy * stub))
        if stub: s.wire(at, end)
        s.sh.add_flag(name, end[0], end[1], outward)

    def pinflag(s, ref, num, name, stub=10):
        x, y, d = s.sh.pin(ref, num)
        s.flag(name, (x, y), d, stub)

    def add(s, lib):
        s.sh.add('LIB', lib); return lib

    def text(s, txt, x, y):
        s.sh.add_text(txt, x, y)


def split_wire_at(sh, p):
    """insert vertex p into the wire whose segment interior contains it."""
    for i, w in sh.wires():
        for k, (a, b) in enumerate(w.segs()):
            if p not in (a, b) and on_seg(p, a, b):
                w.pts.insert(k + 1, p); w.raw = None
                return True
    return False


def translate_group(sh, refs, dx, dy, wires=(), flags=()):
    for r in refs:
        i, l = sh.lib(r); l.transform(Xf(d=(dx, dy)))
    for wi in wires:
        w = sh.items[wi][1]; w.pts = [(R2(x + dx), R2(y + dy)) for x, y in w.pts]; w.raw = None
    for fi in flags:
        raw = sh.items[fi][1]; xy, name = flag_info(raw)
        from schedit import flag_outward
        sh.items[fi][1] = make_flag(name, xy[0] + dx, xy[1] + dy, flag_outward(raw))


def island_of(sh, ref, num):
    key = '%s.%s' % (ref, num)
    for isl in sh.islands():
        if key in isl['pins']: return isl
    raise KeyError(key)


# ------------------------------------------------------------------ the build

def build(verbose=True):
    ref = reference()
    pin2net = {p: n for n, l in ref.items() for p in l}
    allpins = set(pin2net)
    sh = Sheet(SRC)
    b = B(sh)
    log = []

    # ---------------- 1. removals
    for r in CH.REMOVE:
        for num in sh.lib(r)[1].pins():
            sh.detach(r, num, log)
        sh.delete(sh.lib(r)[0])

    # ---------------- 2. value / part swaps
    for r, (part, value, tmpl) in CH.SWAP.items():
        i, lib = sh.lib(r)
        if tmpl and tmpl.startswith('lcsc:'):
            continue  # symbol replacement, handled below
        lib.set_attrs(lcsc_attrs(part)); lib.set_text('N', value)
        if tmpl:
            _, t = sh.lib(tmpl)
            lib.set_attrs({'package': t.attrs()['package']})
            lib.head[7] = t.head[7]
    # U2 keeps its SOIC-8 symbol; show the TJA1051 pin names
    if 'U2' in CH.SWAP:
        _, u2 = sh.lib('U2')
        names = {'1': 'TXD', '4': 'RXD', '5': 'VIO', '8': 'S', '6': 'CANL', '7': 'CANH'}
        for k, p in enumerate(u2.parts):
            if p.startswith('P~'):
                g = p.split('^^'); num = g[0].split('~')[3]
                if num in names:
                    q = g[3].split('~'); q[4] = names[num]; g[3] = '~'.join(q); u2.parts[k] = '^^'.join(g)

    # ---------------- 3. parts drawn the wrong way round: mirror in place
    for r in ('D8', 'LED4'):
        i, lib = sh.lib(r)
        ps = lib.pins(); xs = [p[0] for p in ps.values()]
        keep = {k: lib.text(k)[1][2:4] for k in ('P', 'N')}
        lib.transform(Xf(c=((min(xs) + max(xs)) / 2, 0), mirror=True))
        for k, xy in keep.items():   # keep the texts where they were
            lib.set_text(k, xy=tuple(map(float, xy)))

    # ---------------- 4. hand edits that the generic pass can't do nicely
    hand_edits(sh, b, ref)

    # ---------------- 5. new parts
    new_parts(sh, b, ref)

    # ---------------- 6. generic reconciliation of all islands
    reconcile(sh, ref, log, verbose)

    sh.fix_junctions()
    return sh, ref, log


# ------------------------------------------------------------------ hand edits

def hand_edits(sh, b, ref):
    # --- LDO U14: TLV75533 -> AMS1117-3.3 (new symbol, local wiring redrawn)
    if 'U14' in CH.SWAP:
        i_old, old = sh.lib('U14')
        isls = [island_of(sh, 'U14', n) for n in old.pins()]
        kill_w = set().union(*[isl['wires'] for isl in isls])
        kill_f = set().union(*[set(isl['flags']) for isl in isls])
        for wi in kill_w: sh.delete(wi)
        for fi in kill_f: sh.delete(fi)
        sh.delete(i_old)
        part = CH.SWAP['U14'][0]
        u14 = place(lcsc_symbol(part, 'U14', CH.SWAP['U14'][1]), (300, -790))
        labels(u14, ((285, -826), (285, -817)))
        b.add(u14)
        # pins: 1 GND (255,-800)  2 VOUT (255,-790)  3 VIN (255,-780)  4 TAB/VOUT (345,-790)
        vin, gnd, vo, tab = b.P('U14', '3'), b.P('U14', '1'), b.P('U14', '2'), b.P('U14', '4')
        c35 = orient(place(sh.lib('C35')[1], (200, -760)), (200, -760), 'top')   # pin1 (+5V) top
        labels(c35, 'right')
        b.wire(vin, (200, vin[1]), (150, vin[1]))
        assert b.P('C35', '1') == (200, vin[1])
        b.flag('+5V_MAIN', (150, vin[1]), 'left')
        b.flag('GND', b.P('C35', '2'), 'down', 10)
        b.wire(gnd, (240, gnd[1]), (240, gnd[1] - 15))
        b.flag('GND', (240, gnd[1] - 15), 'up')
        b.flag('+3V3', vo, 'left', 15)
        c36 = orient(place(sh.lib('C36')[1], (390, -770)), (390, -770), 'bottom')  # pin2 (+3V3) on top
        labels(c36, 'right')
        b.wire(tab, (390, tab[1]), (420, tab[1]))
        assert b.P('C36', '2') == (390, tab[1])
        b.flag('+3V3', (420, tab[1]), 'right')
        b.flag('GND', b.P('C36', '1'), 'down', 10)

    # --- U1 dead-battery pins tied to CC1 / CC2 (pin 1 next to pin 2, pin 5 next to pin 4)
    for a, c in (('1', '2'), ('5', '4')):
        pa, pc = b.P('U1', a), b.P('U1', c)
        b.wire(pa, (pa[0] - 5, pa[1]), (pc[0] - 5, pc[1]))
        split_wire_at(sh, (pc[0] - 5, pc[1]))

    # --- U1.18 VBUS_VS_DISCH: its USB_VBUS_RAW flag becomes PD_VBUS_VS (R57 drawn in block E)
    # (generic rename does it)

    # --- U1.25 exposed pad + R2.2 (now GND): share one GND symbol above U1
    if CH.NETS.get(('R2', '2')) == 'GND':
        isl = island_of(sh, 'R2', '2')
        for fi in isl['flags']: sh.delete(fi)
        p = b.P('R2', '2'); ep = b.P('U1', '25')
        for wi in isl['wires']: sh.delete(wi)
        b.wire(p, (ep[0], p[1]))
        b.wire(ep, (ep[0], p[1]), (ep[0], p[1] - 10))
        b.flag('GND', (ep[0], p[1] - 10), 'up')

    # --- LED4 chain (R27, LED4) moves away from the ESP32 right edge: R27.1 and U15.33
    #     both change net and faced each other with a 10-unit wire
    isl_a = island_of(sh, 'LED4', '1'); isl_b = island_of(sh, 'LED4', '2')
    sh.detach('R27', '1')
    w = (isl_a['wires'] | isl_b['wires'])
    f = set(isl_a['flags']) | set(isl_b['flags'])
    translate_group(sh, ['R27', 'LED4'], 120, 115, wires=w, flags=f)

    # --- R1 moves to block E (see new_parts)
    sh.detach('R1', '1'); sh.detach('R1', '2')

    # --- C28 (MP1584 COMP) leaves U13: it now sits behind R40 in the power block
    sh.detach('C28', '1'); sh.detach('C28', '2')

    # --- U13 EN: old wire to +20V_BUS goes (R38 pulls it up now)
    sh.detach('U13', '2')

    # --- U6 (LMP91200) VREF loop to VCM goes; VREF gets its own filtered net
    sh.detach('U6', '9')

    # --- ESP32 bottom-row pins that were unused and now carry signals: a staircase of
    #     stubs (rightmost pin turns first) ending in flags to the right of the module
    allp = {p for l in ref.values() for p in l}
    stair = []
    for num in ('25', '24', '23', '22'):
        net = ref_net(ref, 'U15', num)
        if len(ref[net]) == 1 and auto_named(net, allp): continue
        stair.append((num, net))
    for k, (num, net) in enumerate(stair):
        x, y, od = sh.pin('U15', num)
        assert od == 'down' and not island_of(sh, 'U15', num)['wires']
        yy = y + 10 * (k + 1)
        b.wire((x, y), (x, yy), (1100, yy))
        b.flag(net, (1100, yy), 'right')

    # --- USB-C shells: comb + one GND symbol per connector
    for c in ('USBC1', 'USBC2', 'USBC3'):
        ps = [b.P(c, s) for s in '1234']
        x, _, od = sh.pin(c, '1')
        dx = DIRV[od][0] * 10
        ys = sorted(p[1] for p in ps)
        for p in ps: b.wire(p, (p[0] + dx, p[1]))
        b.wire(*[(ps[0][0] + dx, y) for y in ys] + [(ps[0][0] + dx, ys[-1] + 10)])
        b.flag('GND', (ps[0][0] + dx, ys[-1] + 10), 'down')


# ------------------------------------------------------------------ new parts

LCSC_SYMBOL = {'C8545'}   # parts whose template footprint symbol is the wrong device type (P-FET for N-FET)


def place_pin(lib, num, target, deg=0):
    """rotate by deg, then translate so pin `num` lands on target."""
    place(lib, lib.xy(), deg)
    x, y, _ = lib.pins()[num]
    lib.transform(Xf(d=(target[0] - x, target[1] - y)))
    return lib


def mk(sh, ref, at, deg=0, lab='above', pin=None):
    tmpl, part, value = CH.NEW[ref]
    if tmpl.startswith('lcsc:') or part in LCSC_SYMBOL:
        lib = lcsc_symbol(tmpl[5:] if tmpl.startswith('lcsc:') else part, ref, value)
    else:
        lib = clone(sh, tmpl, ref, value)
        lib.set_attrs(lcsc_attrs(part))
    if pin: place_pin(lib, pin, at, deg)
    else: place(lib, at, deg)
    if lab: labels(lib, lab)
    sh.add('LIB', lib)
    return lib


def orient(lib, at, how):
    """turn a 2-pin symbol about `at` until pin1 is on the requested side
    ('left'/'right' = horizontal, pin1 there; 'top'/'bottom' = vertical)."""
    place(lib, at, 0)
    for _ in range(4):
        p1, p2 = lib.pins()['1'], lib.pins()['2']
        ok = {'left': p1[1] == p2[1] and p1[0] < p2[0], 'right': p1[1] == p2[1] and p1[0] > p2[0],
              'top': p1[0] == p2[0] and p1[1] < p2[1], 'bottom': p1[0] == p2[0] and p1[1] > p2[1]}[how]
        if ok: return lib
        place(lib, at, 90)
    raise ValueError('cannot orient %s' % lib.ref)


def two_pin(sh, b, ref, at, vertical=False, n1=None, n2=None, lab=None, stub=10):
    """Resistor/cap with flags on both ends. Horizontal: pin1 left. Vertical: pin1 top."""
    lib = mk(sh, ref, at, 0, None)
    orient(lib, at, 'top' if vertical else 'left')
    labels(lib, lab or ('right' if vertical else 'above'))
    p = lib.pins()
    for num, name in (('1', n1), ('2', n2)):
        if name:
            x, y, d = p[num]
            b.flag(name, (x, y), d, stub)
    return lib


def new_parts(sh, b, ref):
    N = lambda r, p: ref_net(ref, r, p)

    # ===== block E: STUSB4500 support (right of the USB input caps)
    b.text('STUSB4500 (R2)', 700, -1470)
    two_pin(sh, b, 'R37', (790, -1440), n1=N('R37', '1'), n2=N('R37', '2'))
    two_pin(sh, b, 'R57', (790, -1385), n1=N('R57', '1'), n2=N('R57', '2'))
    # R1 (Q1 gate pull-up, now to the source) had no room at Q1: drawn here with flags
    r1 = place(sh.lib('R1')[1], (790, -1330))
    labels(r1, 'above')
    for num in ('1', '2'):
        x, y, d = r1.pins()[num]
        b.flag(N('R1', num), (x, y), d, 10)
    two_pin(sh, b, 'C47', (740, -1250), vertical=True, n1=N('C47', '1'), n2=N('C47', '2'))
    two_pin(sh, b, 'C46', (840, -1250), vertical=True, n1=N('C46', '1'), n2=N('C46', '2'))

    # ===== block A: ESP32 EN/BOOT, USB ESD, pH VOCM filter (above the ESP32)
    b.text('ESP32 EN / BOOT (R2)', 760, -1130)
    two_pin(sh, b, 'C48', (780, -1060), vertical=True, n1=N('C48', '1'), n2=N('C48', '2'))
    for k, (r, x) in enumerate((('SW2', 870), ('SW1', 960))):
        lib = mk(sh, r, (x, -1060), lab=None)
        labels(lib, ((x + 25, -1060), (x + 25, -1051)))
        p = lib.pins()
        top = N(r, '1'); bot = N(r, '3')
        assert N(r, '2') == top and N(r, '4') == bot
        for (a, c, name, od) in (('1', '2', top, 'up'), ('3', '4', bot, 'down')):
            pa, pc = p[a][:2], p[c][:2]
            yy = pa[1] + (-10 if od == 'up' else 10)
            mid = ((pa[0] + pc[0]) / 2, yy)
            b.wire(pa, (pa[0], yy), mid); b.wire(pc, (pc[0], yy), mid)
            b.flag(name, mid, od, 10)

    b.text('USB ESD (R2)', 1150, -1120)
    u16 = mk(sh, 'U16', (1200, -1050), lab=None)
    labels(u16, ((1160, -1102), (1160, -1093)))
    for num, (x, y, d) in u16.pins().items():
        b.flag(N('U16', num), (x, y), d, 10)

    b.text('pH VOCM FILTER (R2)', 1420, -1130)
    r56 = two_pin(sh, b, 'R56', (1460, -1060), n1=N('R56', '1'))
    p2 = r56.pins()['2'][:2]
    b.wire(p2, (1500, p2[1]), (1520, p2[1]))
    c49 = orient(mk(sh, 'C49', (1500, -1040), 0, None), (1500, -1040), 'top'); labels(c49, 'right')
    b.flag(N('C49', '2'), c49.pins()['2'][:2], 'down', 10)
    b.flag(N('R56', '2'), (1520, p2[1]), 'right')

    # ===== block G: MP1584 support + 20 V bulk (below the LDO)
    b.text('MP1584 / +20V BUS (R2)', 40, -715)
    two_pin(sh, b, 'R38', (150, -670), n1=N('R38', '1'), n2=N('R38', '2'))
    two_pin(sh, b, 'R39', (150, -615), n1=N('R39', '1'), n2=N('R39', '2'))
    r40 = two_pin(sh, b, 'R40', (360, -670), n1=N('R40', '1'), lab='below')
    p2 = r40.pins()['2'][:2]
    c28 = orient(place(sh.lib('C28')[1], (420, -650)), (420, -650), 'top')
    labels(c28, 'right')
    b.wire(p2, (395, p2[1]), c28.pins()['1'][:2])
    b.flag(N('C28', '1'), (395, p2[1]), 'up', 10)
    b.flag(N('C28', '2'), c28.pins()['2'][:2], 'down', 10)
    two_pin(sh, b, 'C50', (520, -650), vertical=True, n1=N('C50', '1'), n2=N('C50', '2'))
    two_pin(sh, b, 'C51', (600, -650), vertical=True, n1=N('C51', '1'), n2=N('C51', '2'))

    # ===== block B: module ports (USBC3 = port 2 left, USBC2 = port 1 right)
    port(sh, b, ref, 2, ox=170, oy=-320)
    port(sh, b, ref, 1, ox=650, oy=-320)

    # ===== CAN termination jumper next to the transceiver
    two_pin(sh, b, 'R55', (1440, -300), n1=N('R55', '1'), n2=N('R55', '2'))


def ref_net(ref, r, p):
    k = '%s.%s' % (r, p)
    for n, l in ref.items():
        if k in l: return n
    raise KeyError(k)


def port(sh, b, ref, k, ox, oy):
    N = lambda r, p: ref_net(ref, r, p)
    q_p, q_n, r_gs, r_g, r_pd, rp1, rs1, rp2, rs2 = {
        1: ('Q2', 'Q3', 'R41', 'R42', 'R43', 'R44', 'R45', 'R46', 'R47'),
        2: ('Q4', 'Q5', 'R48', 'R49', 'R50', 'R51', 'R52', 'R53', 'R54')}[k]
    cgd = {1: 'C52', 2: 'C53'}[k]
    conn = {1: 'USBC2, CAN1', 2: 'USBC3, CAN2'}[k]
    b.text('MODULE PORT %d (%s)' % (k, conn), ox - 125, -515)
    # P-FET high side switch (Q1 symbol: gate up, source left, drain right)
    qp = mk(sh, q_p, (ox, oy), lab=((ox - 14, oy + 28), (ox - 14, oy + 37)))
    G, S, D = (qp.pins()[n][:2] for n in ('1', '2', '3'))
    assert G == (ox, oy - 10) and S == (ox - 20, oy + 10) and D == (ox + 20, oy + 10), (G, S, D)
    b.wire(S, (ox - 40, oy + 10), (ox - 50, oy + 10))
    b.flag(N(q_p, '2'), (ox - 50, oy + 10), 'left')
    rgs = orient(mk(sh, r_gs, (ox - 40, oy - 10), 0, None), (ox - 40, oy - 10), 'bottom'); labels(rgs, 'left')
    assert rgs.pins()['1'][:2] == (ox - 40, oy + 10)
    b.wire(rgs.pins()['2'][:2], (ox, oy - 30))
    b.wire((ox, oy - 30), (ox, oy - 20), G)
    rg = orient(mk(sh, r_g, (ox, oy - 50), 0, None), (ox, oy - 50), 'bottom'); labels(rg, 'right')
    assert rg.pins()['1'][:2] == (ox, oy - 30)
    # gate-drain soft-start cap
    c = orient(mk(sh, cgd, (ox + 45, oy - 20), 0, None), (ox + 45, oy - 20), 'left')
    labels(c, ((ox + 70, oy - 14), (ox + 70, oy - 5)))
    assert c.pins()['1'][:2] == (ox + 25, oy - 20)
    b.wire((ox, oy - 20), (ox + 25, oy - 20))
    b.wire(c.pins()['2'][:2], (ox + 65, oy + 10))
    b.wire(D, (ox + 65, oy + 10), (ox + 80, oy + 10))
    b.flag(N(q_p, '3'), (ox + 80, oy + 10), 'right')
    # N-FET pull-down (2N7002 symbol rotated: drain down, source up, gate right)
    qn = mk(sh, q_n, (ox, oy - 90), 180, ((ox - 52, oy - 112), (ox - 52, oy - 103)), pin='3')
    G2, S2, D2 = (qn.pins()[n][:2] for n in ('1', '2', '3'))
    assert D2 == (ox, oy - 90) and S2 == (ox, oy - 130) and G2 == (ox + 30, oy - 110), (G2, S2, D2)
    b.wire(rg.pins()['2'][:2], D2)
    b.flag(N(q_n, '2'), S2, 'up', 10)
    b.wire(G2, (ox + 60, oy - 110), (ox + 70, oy - 110))
    b.flag(N(q_n, '1'), (ox + 70, oy - 110), 'right')
    rpd = orient(mk(sh, r_pd, (ox + 60, oy - 90), 0, None), (ox + 60, oy - 90), 'top'); labels(rpd, 'right')
    assert rpd.pins()['1'][:2] == (ox + 60, oy - 110)
    b.flag(N(r_pd, '2'), rpd.pins()['2'][:2], 'down', 10)
    # CC pull-ups and ADC taps
    xa = ox + 208; yt = -470
    for j, (rp, rs) in enumerate(((rp1, rs1), (rp2, rs2))):
        x = xa + 90 * j
        top = orient(mk(sh, rp, (x, yt + 30), 0, None), (x, yt + 30), 'top'); labels(top, 'right')
        b.flag(N(rp, '1'), top.pins()['1'][:2], 'up', 10)
        bot = orient(mk(sh, rs, (x, yt + 90), 0, None), (x, yt + 90), 'top'); labels(bot, 'right')
        b.wire(top.pins()['2'][:2], (x, yt + 60), bot.pins()['1'][:2])
        b.flag(N(rp, '2'), (x, yt + 60), 'left', 10)
        b.flag(N(rs, '2'), bot.pins()['2'][:2], 'down', 10)


# ------------------------------------------------------------------ generic reconciliation

def reconcile(sh, ref, log, verbose):
    pin2net = {p: n for n, l in ref.items() for p in l}
    allpins = set(pin2net)
    # phase 1: split islands that mix nets
    for _ in range(50):
        changed = False
        for isl in sh.islands():
            pins = sorted(set(isl['pins']))
            tg = {p: pin2net.get(p) for p in pins}
            if None in tg.values():
                raise SystemExit('pins missing from reference: %s' % [p for p in pins if tg[p] is None])
            cnt = collections.Counter(tg.values())
            if len(cnt) <= 1: continue
            names = {flag_info(sh.items[fi][1])[1] for fi in isl['flags']}
            best = max(cnt.values())
            top = [n for n, c in cnt.items() if c == best]
            keep = None
            if len(top) == 1: keep = top[0]
            else:
                t2 = [n for n in top if n in names]
                if len(t2) == 1: keep = t2[0]
            for p in pins:
                if tg[p] != keep:
                    r, n = p.split('.')
                    sh.detach(r, n, log)
                    if verbose: print('  detach %s (%s -> %s)' % (p, sorted(names) or '-', tg[p]))
                    changed = True
            break
        if not changed: break
    # phase 2: names and flags
    isls = sh.islands()
    span = collections.Counter()
    for isl in isls:
        for n in {pin2net[p] for p in isl['pins']}: span[n] += 1
    todo = []
    for isl in isls:
        pins = sorted(set(isl['pins']))
        if not pins: continue
        T = pin2net[pins[0]]
        names = [(fi, flag_info(sh.items[fi][1])[1]) for fi in isl['flags']]
        if len(ref[T]) == 1 and auto_named(T, allpins):
            if names or isl['wires']:
                r, n = pins[0].split('.')
                if names and all(nm != T for _, nm in names):
                    sh.detach(r, n, log)
                    if verbose: print('  unconnect %s (was %s)' % (pins[0], [nm for _, nm in names]))
            continue
        for fi, nm in names:
            if nm != T and nm not in ALLOWED_EXTRA:
                sh.rename_flag(fi, T)
                if verbose: print('  rename flag %s -> %s (%s)' % (nm, T, pins))
        has = bool(names)   # after the renames every flag is T or an original alias
        need = (not auto_named(T, allpins)) or span[T] > 1
        if need and not has:
            todo.append((T, isl))
    # place the flags, hardest (fewest options) first: bare pins before wired islands
    todo.sort(key=lambda t: (len(t[1]['wires']) > 0, t[0]))
    # pass 1: straight stubs only (keeps every pin's own row free for it); pass 2: jogs too
    left = []
    for T, isl in todo:
        res = place_flag(sh, T, flag_starts(sh, isl), turns=False, quiet=True)
        if res:
            if verbose: print('  flag %-14s at %s' % (T, res))
        else:
            left.append((T, isl))
    for T, isl in left:
        res = place_flag(sh, T, flag_starts(sh, isl), turns=True)
        if verbose: print('  flag %-14s %s' % (T, 'at %s' % (res,) if res else 'FAILED for %s' % isl['pins']))
        if not res:
            FAILED.append((T, isl['pins']))


FAILED = []


def flag_starts(sh, isl):
    """candidate start points: bare pins of the island, then points along its wires."""
    starts = []
    edges, adj, pins, flags = sh.graph()
    for p in isl['pts']:
        for (r, n) in pins.get(p, []):
            od = sh.pin(r, n)[2]
            if not adj.get(p) and not flags.get(p):
                starts.append((p, od, 0))
    for wi in isl['wires']:
        w = sh.items[wi][1]
        if w is None: continue
        for a, c in w.segs():
            horiz = a[1] == c[1]
            L = abs(c[0] - a[0]) + abs(c[1] - a[1])
            steps = int(L // 5)
            for k in range(steps + 1):
                t = k * 5 / L if L else 0
                q = (R2(a[0] + (c[0] - a[0]) * t), R2(a[1] + (c[1] - a[1]) * t))
                for od in (('up', 'down') if horiz else ('left', 'right')):
                    starts.append((q, od, 6))
    return starts


def place_flag(sh, name, starts, turns=True, quiet=False):
    obst = sh.prepare_obstacles()
    segs = sh.wire_points()
    pinpts = {xy for _, _, xy, _ in sh.all_pins()}
    flagpts = {flag_info(raw)[0] for _, raw in sh.flags()}
    cands = []
    for p, od, extra in starts:
        for path, outward, cost in sh.candidates_from(p, od, turns=turns):
            cands.append((cost + extra, path, outward))
    cands.sort(key=lambda c: c[0])
    for cost, path, outward in cands:
        if sh.flag_candidate_ok(name, path, outward, obst, segs, pinpts, flagpts):
            if len(path) > 1: sh.add_wire(path)
            sh.add_flag(name, path[-1][0], path[-1][1], outward)
            return path, outward
    for cost, path, outward in ([] if quiet else cands[:12]):
        why = []
        sh.flag_candidate_ok(name, path, outward, obst, segs, pinpts, flagpts, why=why)
        print('    rejected', path, outward, why)
    return None


# ------------------------------------------------------------------ checks and previews

def check(path, ref):
    from schnet import schnetlist
    groups, pins = schnetlist(path)
    allpins = {p for l in ref.values() for p in l}
    probs = verify(groups, ref, ALLOWED_EXTRA, allpins)
    sch_refs = collections.Counter(p.split('.')[0] for p in {'%s.%s' % (r, n) for r, n, xy in pins})
    pcb_refs = {p.split('.')[0] for p in allpins}
    libs = collections.Counter()
    d = json.load(open(path))
    for x in d['schematics'][0]['dataStr']['shape']:
        if x.startswith('LIB'):
            for sub in x.split('#@$')[1:]:
                f = sub.split('~')
                if f[0] == 'T' and f[1] == 'P': libs[f[12]] += 1
    libs.pop('A', None)
    for r, c in libs.items():
        if c != 1: probs.append('REF %s appears %d times' % (r, c))
    for r in set(libs) - pcb_refs: probs.append('REF %s only in schematic' % r)
    for r in pcb_refs - set(libs): probs.append('REF %s only in PCB' % r)
    return probs


def preview(path):
    pdir = os.path.join(OUT_DIR, 'sch_preview'); os.makedirs(pdir, exist_ok=True)
    from schrender import render
    views = {
        'full': (0, -1600, 2100, 2100),
        'power_usb': (20, -1500, 650, 650),
        'stusb_esp_top': (650, -1500, 600, 600),
        'esp32': (700, -1150, 700, 700),
        'ph_adc': (1300, -1350, 700, 700),
        'buck_ldo': (20, -1120, 620, 620),
        'ports': (20, -740, 1050, 1050),
        'can_usbc': (1100, -760, 950, 950),
    }
    outs = []
    for name, vb in views.items():
        svg = os.path.join(pdir, name + '.svg')
        render(path, svg, crop=vb)
        subprocess.run(['qlmanage', '-t', '-s', '2400', '-o', pdir, svg], capture_output=True)
        png = svg + '.png'
        if os.path.exists(png):
            os.replace(png, os.path.join(pdir, name + '.png'))
            outs.append(os.path.join(pdir, name + '.png'))
        os.remove(svg)
    return outs


if __name__ == '__main__':
    os.makedirs(OUT_DIR, exist_ok=True)
    sh, ref, log = build(verbose='-q' not in sys.argv)
    sh.save(OUT)
    print('wrote', OUT)
    probs = check(OUT, ref)
    for T, pins in FAILED: probs.append('NO FLAG PLACED for %s %s' % (T, pins))
    for p in probs: print('DIFF', p)
    print('verification: %d difference(s)' % len(probs))
    if '--png' in sys.argv:
        for p in preview(OUT): print('preview', p)
    sys.exit(1 if probs else 0)
