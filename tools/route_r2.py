"""Route the R2 board.

1. build the placed PCB (build_r2_pcb + r2_placement)
2. hand-routed critical copper (buck switch node / input loop, pH input + guard)
3. GND: a via next to (or in) every SMD ground pad -> solid bottom plane + top pour
4. Freerouting stage 1 (top layer only), stage 2 (both layers, bottom expensive)
5. import, add copper pours / keep-outs, save EasyEDA JSON

GND is not routed with traces at all; it lives on the pours. Keep-outs and the
GND fanout are passed to Freerouting as net-less obstacle "components"
(the CLI build crashes on DSN keepout/plane areas).

  python3 tools/route_r2.py [--passes N]
"""
import os, sys, math, json, subprocess, shutil
sys.path.insert(0, os.path.dirname(__file__))
from build_r2_pcb import build, X0, Y0, OUT_DIR
from r2_placement import PLACEMENT
from pcbtool import U, new_gid, _fmt
import dsn as D

ROOT = os.path.join(os.path.dirname(__file__), '..')
FR = os.environ.get('FREEROUTING_DIR', '/private/tmp/claude-501/-Users-kris-Documents-Claude-Local/b61844df-efaa-4680-8dcb-24ec437a143c/scratchpad/fr')
JAVA = os.path.join(FR, 'jre/Contents/Home/bin/java')
JAR = os.path.join(FR, 'freerouting-2.5.0.jar')

VIA_D, VIA_HOLE = 0.6, 0.3
CLR = 0.2


def E(x, y):  # board mm -> easyeda units
    return (X0 + x / U, Y0 + y / U)


def track(net, layer, w, pts):
    q = ' '.join('%s %s' % tuple(map(_fmt, E(x, y))) for x, y in pts)
    return 'TRACK~%s~%s~%s~%s~%s~0' % (_fmt(w / U), layer, net, q, new_gid())


def via(net, x, y, d=VIA_D, hole=VIA_HOLE):
    ex, ey = E(x, y)
    return 'VIA~%s~%s~%s~%s~%s~%s~0' % (_fmt(ex), _fmt(ey), _fmt(d / U), net, _fmt(hole / 2 / U), new_gid())


# ------------------------------------------------------------------ hand routes (mm, top layer unless noted)
HAND = [
    # buck switch node: U13.SW -> D8 cathode -> L2.1, plus bootstrap cap
    ('U13_1', '1', 1.0, [(28.4, 4.48), (28.4, 3.64), (33.4, 3.64), (40.0, 3.4)]),
    ('U13_1', '1', 0.6, [(30.4, 6.8), (30.4, 3.64)]),
    ('U13_8', '1', 0.4, [(28.4, 10.52), (29.6, 9.3), (30.4, 8.2)]),
    # input loop: VIN / GND pins to C26 (100n) and C10 (10u)
    ('+20V_BUS', '1', 0.6, [(27.13, 10.52), (27.13, 11.9), (26.6, 12.75)]),
    ('+20V_BUS', '1', 0.8, [(26.6, 12.75), (27.49, 13.6), (27.49, 15.1)]),
    ('GND', '1', 0.6, [(24.59, 10.52), (24.59, 11.9), (25.2, 12.75)]),
    ('GND', '1', 0.8, [(25.2, 12.75), (24.31, 13.6), (24.31, 15.1)]),
    ('BUCK_FREQ', '1', 0.15, [(25.86, 10.52), (25.86, 11.4), (25.9, 11.8), (25.9, 17.45)]),  # squeezes between C26 pads
    # +20V trunk to the module ports: corridor between the ESP32 and the analog zone
    # (the autorouter otherwise drags it through the pH/TDS area)
    ('+20V_BUS', '1', 0.8, [(22.91, 21.0), (22.91, 37.6), (23.8, 38.5), (116.1, 38.5), (117.0, 37.6),
                             (117.0, 14.6), (119.6, 12.0), (127.15, 12.0)]),
    ('+20V_BUS', '1', 0.8, [(124.5, 12.0), (124.5, 13.59)]),
    # buck input caps -> trunk (around R39 / C50's GND pad)
    ('+20V_BUS', '1', 0.6, [(27.49, 15.1), (28.9, 16.5), (28.9, 22.0), (28.3, 22.6), (22.91, 22.6)]),
    ('+20V_BUS', '1', 0.8, [(116.1, 38.5), (117.0, 39.4), (117.0, 57.6), (118.4, 59.0), (120.15, 59.0)]),
    ('+20V_BUS', '1', 0.4, [(36.85, 22.5), (36.85, 21.1), (28.9, 21.1)]),     # R25 (LED1) feed
    # ---- everything inside the buck zone is hand-routed; the zone is fenced off for the router
    ('U13_4', '1', 0.25, [(24.59, 4.25), (19.8, 4.25)]),                       # FB -> R9/R10 (short)
    ('BUCK_COMP', '1', 0.25, [(25.86, 4.48), (25.86, 2.5), (24.96, 1.6), (22.75, 1.6)]),
    ('BUCK_COMP_RC', '1', 0.25, [(21.25, 1.6), (19.3, 1.6)]),
    ('BUCK_EN', '1', 0.25, [(27.13, 4.48), (27.13, 3.0), (27.73, 2.4), (29.15, 2.4), (29.15, 1.4)]),
    # R38 (EN pull-up) gets +20 V from Q1 along the top edge on the bottom layer
    ('+20V_BUS', '1', 0.3, [(27.65, 1.4), (26.7, 1.45)]),
    ('+20V_BUS', '2', 0.3, [(26.7, 1.45), (26.0, 0.75), (13.8, 0.75), (13.8, 15.2)]),
    ('+20V_BUS', '1', 0.4, [(13.8, 15.2), (15.0, 15.2)]),
    # +5 V output: L2 -> C29 / C30 / C35 -> AMS1117 VIN
    ('+5V_MAIN', '1', 0.8, [(42.0, 13.68), (42.0, 19.75), (47.5, 19.75), (47.43, 21.0), (47.43, 22.1)]),
    ('+5V_MAIN', '1', 0.6, [(42.0, 17.8), (40.41, 17.8)]),
    ('+5V_MAIN', '1', 0.4, [(45.6, 18.7), (45.6, 19.75)]),
    # +5 V sense to the FB divider: bottom layer around (not under) the switching loop
    ('+5V_MAIN', '1', 0.3, [(40.41, 17.8), (39.6, 19.45)]),
    ('+5V_MAIN', '2', 0.3, [(39.6, 19.45), (22.3, 19.45), (22.3, 7.2), (22.4, 6.9)]),
    ('+5V_MAIN', '1', 0.3, [(22.4, 6.9), (21.6, 5.75)]),
    # USB 2.0 from the USB-C receptacle (interleaved pins): D+ A6/B6 joined by two vias
    # under the connector body, D- B7/A7 joined right at the pads, both straight into U16
    ('USB_D+', '1', 0.25, [(5.82, 27.15), (5.25, 27.15)]),
    ('USB_D+', '1', 0.25, [(5.82, 28.15), (5.25, 28.15)]),
    ('USB_D+', '2', 0.25, [(5.25, 27.15), (5.25, 28.15)]),
    ('USB_D+', '1', 0.25, [(7.12, 28.15), (11.55, 28.15), (11.55, 30.5)]),
    ('USB_D-', '1', 0.25, [(7.12, 26.65), (7.8, 26.65), (7.8, 27.65)]),
    ('USB_D-', '1', 0.25, [(7.12, 27.65), (13.45, 27.65), (13.45, 30.5)]),
    # pH: INP straight from the U.FL centre pin, guard traces either side
    ('PH_INP', '1', 0.25, [(23.92, 55.67), (24.6, 55.83), (28.13, 55.83)]),
    ('PH_GUARD', '1', 0.25, [(28.13, 55.18), (25.3, 55.18)]),
    ('PH_GUARD', '1', 0.25, [(28.13, 56.48), (25.3, 56.48)]),
    # QFN ground pins with no room for a via: U1 pins are tied into the exposed pad
    # (added in main() from real pad positions), U4 pins share one via
    ('GND', '1', 0.25, [(45.2, 52.1), (45.2, 53.2), (45.7, 53.7)]),   # U4.1
    ('GND', '1', 0.25, [(46.2, 52.1), (46.2, 53.2), (45.7, 53.7)]),   # U4.3
]
HAND_VIAS = [('PH_GUARD', 25.3, 55.18), ('PH_GUARD', 25.3, 56.48), ('GND', 45.7, 54.15),
             ('USB_D+', 5.25, 27.15, 0.5, 0.25), ('USB_D+', 5.25, 28.15, 0.5, 0.25),
             ('+20V_BUS', 26.7, 1.45), ('+20V_BUS', 13.8, 15.2), ('+5V_MAIN', 39.6, 19.45), ('+5V_MAIN', 22.4, 6.9)]
# buck zone fenced off for the autorouter (both layers); its nets are all in HAND
BUCK_ZONE = [(17.2, 0.0, 49.0, 12.0), (23.4, 12.0, 49.0, 20.4)]
# bottom-layer guard patch under the pH input (net PH_GUARD), GND plane clears it
GUARD_PATCH = [(22.4, 54.55), (29.0, 54.55), (29.0, 57.05), (22.4, 57.05)]

ANTENNA = (57.0, 0.0, 83.0, 7.5)
HOLES = [(5, 5), (149, 5), (15, 55), (139, 63)]

CLASSES = {
    'pwr20': (['+20V_BUS', 'P1_VFUSED', 'P2_VFUSED'], 0.6, 0.25),
    'vbus': (['USB_VBUS_RAW', 'P1_VBUS', 'P2_VBUS'], 0.45, 0.2),   # must reach 0.6 mm USB-C pads
    'pwr5': (['+5V_MAIN'], 0.5, 0.2),
    'pwr3': (['+3V3'], 0.3, 0.2),
    'usb': (['USB_D+', 'USB_D-', 'U15_13', 'U15_14'], 0.3, 0.2),
}


# ------------------------------------------------------------------ geometry helpers
def pads_mm(p):
    out = []
    for _, l in p.libs():
        for num, net, lay, shp, cx, cy, w, h, hr, pts in l.pad_geoms():
            out.append(dict(ref=l.ref, num=num, net=net, layer=lay,
                            x=(cx - X0) * U, y=(cy - Y0) * U, w=w * U, h=h * U))
    return out


def d_rect(px, py, r):
    dx = max(abs(px - r['x']) - r['w'] / 2, 0); dy = max(abs(py - r['y']) - r['h'] / 2, 0)
    return math.hypot(dx, dy)


def d_seg(px, py, a, b):
    ax, ay = a; bx, by = b
    L = (bx - ax) ** 2 + (by - ay) ** 2
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / L))
    return math.hypot(px - ax - t * (bx - ax), py - ay - t * (by - ay))


def on_board(x, y, m=0.6):
    if not (m < x < 154 - m and m < y < 67 - m): return False
    if x < 35.03 and y > 53.28 + (x - 3.07) * (66.61 - 53.28) / (35.03 - 3.07) - m * 1.2: return False
    for cx, cy, r in ((5, 5, 5), (149, 5, 5), (149, 62, 5), (5, 5, 5)):
        pass
    return True


def gnd_fanout(p, pads, hand_segs, hand_vias):
    """Return list of (pad, via_xy, [track pts]) for every SMD GND pad."""
    vias = [(v[1], v[2]) for v in hand_vias]
    res = []
    other = [q for q in pads if q['net'] != 'GND']
    def ok(x, y, pad):
        if not on_board(x, y): return False
        if ANTENNA[0] - 0.5 < x < ANTENNA[2] + 0.5 and y < ANTENNA[3] + 0.5: return False
        for hx, hy in HOLES:
            if math.hypot(x - hx, y - hy) < 1.65 + 0.3 + 0.4: return False
        for q in other:
            if d_rect(x, y, q) < VIA_D / 2 + CLR: return False
        for q in pads:  # don't drop vias into other GND pads of fine-pitch parts
            if q is not pad and q['net'] == 'GND' and d_rect(x, y, q) < VIA_D / 2 + 0.05 and q['layer'] == '1': return False
        for vx, vy in vias:
            if math.hypot(x - vx, y - vy) < VIA_D + CLR: return False
        for net, layer, w, pts in hand_segs:
            if net == 'GND': continue
            for a, b in zip(pts, pts[1:]):
                if d_seg(x, y, a, b) < VIA_D / 2 + w / 2 + CLR: return False
        return True
    def track_ok(a, b, pad, w=0.4):
        n = max(2, int(math.dist(a, b) / 0.1))
        for i in range(n + 1):
            x = a[0] + (b[0] - a[0]) * i / n; y = a[1] + (b[1] - a[1]) * i / n
            for q in other:
                if d_rect(x, y, q) < w / 2 + CLR: return False
        return True
    comp_centre = {}
    for q in pads:
        comp_centre.setdefault(q['ref'], []).append((q['x'], q['y']))
    comp_centre = {k: (sum(a for a, _ in v) / len(v), sum(b for _, b in v) / len(v)) for k, v in comp_centre.items()}
    for pad in pads:
        if pad['net'] != 'GND' or pad['layer'] != '1': continue
        big = pad['w'] * pad['h'] > 4.0
        if (pad['ref'] == 'U15' and pad['num'] == '41') or (pad['ref'] in ('U13', 'U1') and pad['num'] in ('9', '25')):
            # via-in-pad for exposed / thermal pads
            cand = [(pad['x'], pad['y'])] if pad['ref'] == 'U15' else \
                   [(pad['x'] + dx, pad['y'] + dy) for dx in (-0.7, 0.7) for dy in (-0.45, 0.45)] if pad['ref'] == 'U13' else \
                   [(pad['x'] + dx, pad['y'] + dy) for dx in (-0.55, 0.55) for dy in (-0.55, 0.55)]
            for c in cand:
                vias.append(c); res.append((pad, c, None))
            continue
        if big:  # large pads (D8 anode, 1206/SMB, USB shell-less GND): via inside the pad edge
            cx, cy = comp_centre[pad['ref']]
            ux, uy = pad['x'] - cx, pad['y'] - cy
            n = math.hypot(ux, uy) or 1
            ux, uy = ux / n, uy / n
            c = (pad['x'] + ux * (pad['w'] / 2 - 0.45), pad['y'] + uy * (pad['h'] / 2 - 0.45))
            if ok(*c, pad):
                vias.append(c); res.append((pad, c, None))
                continue
        cx, cy = comp_centre[pad['ref']]
        best = None
        for ang in range(0, 360, 45):
            a = math.radians(ang)
            ux, uy = math.cos(a), math.sin(a)
            out = ux * (pad['x'] - cx) + uy * (pad['y'] - cy)
            ext = abs(ux) * pad['w'] / 2 + abs(uy) * pad['h'] / 2
            for extra in (0.45, 0.7, 1.0, 1.4, 1.9, 2.5):
                x, y = pad['x'] + ux * (ext + extra), pad['y'] + uy * (ext + extra)
                if ok(x, y, pad) and track_ok((pad['x'], pad['y']), (x, y), pad):
                    score = extra - 0.3 * out
                    if best is None or score < best[0]: best = (score, (x, y))
                    break
        if best:
            vias.append(best[1]); res.append((pad, best[1], [(pad['x'], pad['y']), best[1]]))
        else:
            res.append((pad, None, None))
    return res


# ------------------------------------------------------------------ DSN obstacle component
def obstacle_image(fr, items):
    """items: list of (kind, layers, geometry) in mm; returns (image lines, padstack lines, place line)."""
    pins, stacks = [], []
    for i, (kind, layers, g) in enumerate(items):
        name = 'OBS_%d' % i
        shapes = []
        for L in layers:
            if kind == 'circle':
                x, y, d = g
                shapes.append('(shape (circle %s %d))' % (L, d * 1000))
                px, py = x, y
            elif kind == 'rect':
                x0, y0, x1, y1 = g
                px, py = (x0 + x1) / 2, (y0 + y1) / 2
                w, h = (x1 - x0) * 1000, (y1 - y0) * 1000
                shapes.append('(shape (rect %s %d %d %d %d))' % (L, -w / 2, -h / 2, w / 2, h / 2))
            elif kind == 'path':
                w, pts = g
                px, py = pts[0]
                rel = ' '.join('%d %d' % ((x - px) * 1000, -(y - py) * 1000) for x, y in pts)
                shapes.append('(shape (path %s %d %s))' % (L, w * 1000, rel))
        stacks.append('  (padstack "%s" %s (attach off))' % (name, ' '.join(shapes)))
        pins.append('   (pin "%s" "%d" %d %d)' % (name, i, px * 1000, -py * 1000))
    return pins, stacks


def write_dsn(p, path, wiring, obstacles, b_cu=True, b_cost=(4.0, 6.0)):
    tmp = path + '.tmp'
    D.export_dsn(p, tmp, classes={k: v for k, v in CLASSES.items()}, planes=(),
                 default_width_mm=0.25, clearance_mm=CLR, via=(VIA_D, VIA_HOLE), wiring=wiring)
    t = open(tmp).read(); os.remove(tmp)
    # drop GND from the network (pins become net-less obstacles; GND lives on the pours)
    import re
    t = re.sub(r'  \(net "GND" \(pins [^)]*\)\)\n', '', t)
    t = t.replace(' "GND"', '', 1) if False else t
    t = re.sub(r'(\(class "default" [^\n]*?)"GND" ', r'\1', t)
    # obstacle component
    pins, stacks = obstacle_image(None, obstacles)
    t = t.replace(' (placement\n', ' (placement\n  (component "IMG_OBS" (place "OBS1" 0 0 front 0))\n', 1)
    t = t.replace(' (library\n', ' (library\n  (image "IMG_OBS"\n' + '\n'.join(pins) + '\n  )\n' + '\n'.join(stacks) + '\n', 1)
    ar = ('  (autoroute_settings (fanout off) (autoroute on) (postroute on) (vias on) (via_costs 25) '
          '(plane_via_costs 5) (start_ripup_costs 100) (start_pass_no 1) '
          '(layer_rule F.Cu (active on) (preferred_direction horizontal) (preferred_direction_trace_costs 1.0) (against_preferred_direction_trace_costs 1.3)) '
          '(layer_rule B.Cu (active %s) (preferred_direction vertical) (preferred_direction_trace_costs %.1f) (against_preferred_direction_trace_costs %.1f)))\n'
          % ('on' if b_cu else 'off', b_cost[0], b_cost[1]))
    t = t.replace('  (rule (width', ar + '  (rule (width', 1)
    open(path, 'w').write(t)


def run_fr(dsn_path, ses_path, passes, log):
    if os.path.exists(ses_path): os.remove(ses_path)
    cmd = [JAVA, '-Djava.awt.headless=true', '-jar', JAR, '-de', dsn_path, '-do', ses_path,
           '--router.autorouter.max_passes=%d' % passes, '--gui.enabled=false']
    with open(log, 'w') as fh:
        subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, timeout=3600)
    return os.path.exists(ses_path)


def main(passes=40):
    os.makedirs(OUT_DIR, exist_ok=True)
    p = build(PLACEMENT)
    pads = pads_mm(p)
    # U1 (STUSB4500) ground pins -> exposed pad, computed from actual pad positions
    ep = next(q for q in pads if q['ref'] == 'U1' and q['num'] == '25')
    for q in pads:
        if q['ref'] == 'U1' and q['net'] == 'GND' and q['num'] != '25':
            dx, dy = ep['x'] - q['x'], ep['y'] - q['y']
            n = math.hypot(dx, dy)
            # straight in along the pad's long axis until inside the EP
            if q['w'] > q['h']: end = (q['x'] + math.copysign(min(abs(dx), q['w'] / 2 + 0.55), dx), q['y'])
            else: end = (q['x'], q['y'] + math.copysign(min(abs(dy), q['h'] / 2 + 0.55), dy))
            HAND.append(('GND', '1', 0.25, [(q['x'], q['y']), end]))
    fan = gnd_fanout(p, pads, HAND, HAND_VIAS)
    missing = [(f[0]['ref'], f[0]['num']) for f in fan if f[1] is None]
    print('GND fanout: %d vias, no spot for %s' % (sum(1 for f in fan if f[1]), missing))

    # copper added to the EasyEDA file up front
    shapes = [track(*h) for h in HAND] + [via(*v) for v in HAND_VIAS]
    for pad, v, tr in fan:
        if v is None: continue
        shapes.append(via('GND', *v))
        if tr: shapes.append(track('GND', '1', 0.4, tr))

    # DSN: hand routes as protected wiring (except GND), GND copper + keep-outs as obstacles
    wiring = [(net, 'F.Cu' if lay == '1' else 'B.Cu', w, [E(x, y) for x, y in pts]) for net, lay, w, pts in HAND if net != 'GND']
    D.export_dsn.vias = [(v[0], *E(v[1], v[2])) for v in HAND_VIAS if v[0] != 'GND']
    obstacles = [('rect', ['F.Cu', 'B.Cu'], ANTENNA)]
    obstacles += [('rect', ['F.Cu', 'B.Cu'], z) for z in BUCK_ZONE]
    obstacles += [('circle', ['F.Cu', 'B.Cu'], (hx, hy, 3.3 + 0.8)) for hx, hy in HOLES]
    # 0.4 mm copper-free strip along the board edge (Freerouting ignores edge clearance)
    edge = [((x - X0) * U, (y - Y0) * U) for x, y in D.outline_pts(p)]
    for a, b in zip(edge, edge[1:] + edge[:1]):
        obstacles.append(('path', ['F.Cu', 'B.Cu'], (0.8, [a, b])))
    obstacles += [('rect', ['B.Cu'], (GUARD_PATCH[0][0], GUARD_PATCH[0][1], GUARD_PATCH[2][0], GUARD_PATCH[2][1]))]
    for net, lay, w, pts in HAND:
        if net == 'GND': obstacles.append(('path', ['F.Cu'], (w, pts)))
    obstacles += [('circle', ['F.Cu', 'B.Cu'], (v[1], v[2], VIA_D)) for v in HAND_VIAS if v[0] == 'GND']
    for pad, v, tr in fan:
        if v is None: continue
        obstacles.append(('circle', ['F.Cu', 'B.Cu'], (v[0], v[1], VIA_D)))
        if tr: obstacles.append(('path', ['F.Cu'], (0.4, tr)))

    work = OUT_DIR
    if DRY:
        p.shape.extend(shapes)
        p.save(os.path.join(work, 'PCB_R2_handonly.json'))
        print('dry run: wrote hand-routed copper only'); return
    d1, s1 = os.path.join(work, 'r2_stage1.dsn'), os.path.join(work, 'r2_stage1.ses')
    write_dsn(p, d1, wiring, obstacles, b_cu=False)
    ok = run_fr(d1, s1, passes, os.path.join(work, 'r2_stage1.log'))
    print('stage 1 (top only):', 'ok' if ok else 'FAILED')
    fr = D.Frame(p)
    st1 = D.import_ses(p, s1, fr) if ok else []
    # stage 2: stage-1 copper becomes protected wiring, bottom layer allowed (expensive)
    w2 = list(wiring)
    v2 = list(D.export_dsn.vias)
    for s in st1:
        f = s.split('~')
        if f[0] == 'TRACK':
            n = [float(v) for v in f[4].split()]
            w2.append((f[3], 'F.Cu' if f[2] == '1' else 'B.Cu', float(f[1]) * U, list(zip(n[0::2], n[1::2])), False))
        elif f[0] == 'VIA':
            v2.append((f[4], float(f[1]), float(f[2]), False))
    D.export_dsn.vias = v2
    d2, s2 = os.path.join(work, 'r2_stage2.dsn'), os.path.join(work, 'r2_stage2.ses')
    write_dsn(p, d2, w2, obstacles, b_cu=True)
    ok2 = run_fr(d2, s2, passes, os.path.join(work, 'r2_stage2.log'))
    print('stage 2 (both layers):', 'ok' if ok2 else 'FAILED')
    st2 = D.import_ses(p, s2, fr) if ok2 else []

    # stage-2 session holds every non-protected wire (stage-1 survivors + new ones)
    p.shape.extend(shapes + (st2 if ok2 else st1))
    out = os.path.join(work, 'PCB_R2_routed_nopour.json')
    p.save(out)
    json.dump({'fanout_missing': missing}, open(os.path.join(work, 'route_meta.json'), 'w'))
    print('wrote', out)


DRY = '--dry' in sys.argv

if __name__ == '__main__':
    n = 40
    if '--passes' in sys.argv: n = int(sys.argv[sys.argv.index('--passes') + 1])
    main(n)
