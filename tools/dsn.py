"""EasyEDA Std PCB JSON  <->  Specctra DSN/SES (for Freerouting).

export_dsn(pcb, path, ...) writes a .dsn using one image per component instance
(pins at absolute offsets, rotation 0), so no rotation maths is needed.
import_ses(pcb, ses_path) turns routed wires/vias back into EasyEDA TRACK/VIA shapes.

Board frame: DSN um, origin = board outline top-left, Y up (DSN) vs Y down (EasyEDA).
"""
import math, re
from pcbtool import Pcb, Lib, U, new_gid, _fmt

UM = 254.0  # um per EasyEDA unit
LAYER = {'1': 'F.Cu', '2': 'B.Cu'}
LAYER_ID = {'F.Cu': '1', 'B.Cu': '2'}


def q(s):
    return '"' + s.replace('"', "'") + '"'


def outline_pts(pcb):
    """Ordered outline polygon (EasyEDA units) from layer-10 TRACK/ARC."""
    segs = []
    for x in pcb.shape:
        f = x.split('~')
        if f[0] == 'TRACK' and f[2] == '10':
            n = [float(v) for v in f[4].split()]
            for i in range(0, len(n) - 2, 2): segs.append([(n[i], n[i + 1]), (n[i + 2], n[i + 3])])
        elif f[0] == 'ARC' and f[2] == '10':
            m = re.findall(r'-?\d+\.?\d*', f[4])
            x1, y1, rx, ry, _, la, sw, x2, y2 = map(float, m[:9])
            segs.append(arc_pts(x1, y1, rx, la, sw, x2, y2))
    # chain
    poly = segs.pop(0)
    while segs:
        end = poly[-1]
        for i, s in enumerate(segs):
            if math.dist(s[0], end) < 0.05: poly += s[1:]; segs.pop(i); break
            if math.dist(s[-1], end) < 0.05: poly += s[::-1][1:]; segs.pop(i); break
        else:
            raise ValueError('outline not closed near %s' % (end,))
    return poly


def arc_pts(x1, y1, r, la, sw, x2, y2, n=8):
    # SVG arc endpoint -> center parameterisation (circle)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    d2 = dx * dx + dy * dy
    k = math.sqrt(max(r * r / d2 - 1, 0)) * (-1 if la == sw else 1)
    cx = k * dy + (x1 + x2) / 2; cy = -k * dx + (y1 + y2) / 2
    a1 = math.atan2(y1 - cy, x1 - cx); a2 = math.atan2(y2 - cy, x2 - cx)
    da = a2 - a1
    if sw and da < 0: da += 2 * math.pi
    if not sw and da > 0: da -= 2 * math.pi
    return [(cx + r * math.cos(a1 + da * i / n), cy + r * math.sin(a1 + da * i / n)) for i in range(n + 1)]


class Frame:
    def __init__(s, pcb):
        pts = outline_pts(pcb)
        s.x0 = min(p[0] for p in pts); s.y0 = min(p[1] for p in pts)
        s.outline = pts

    def d(s, x, y):  # easyeda units -> dsn um
        return (round((x - s.x0) * UM, 1), round(-(y - s.y0) * UM, 1))

    def e(s, X, Y):  # dsn um -> easyeda units
        return (X / UM + s.x0, -Y / UM + s.y0)


def export_dsn(pcb, path, classes=None, keepouts=(), wiring=(), planes=(('GND', 'B.Cu'),),
               default_width_mm=0.25, clearance_mm=0.2, via=(0.6, 0.3), layer_costs=None):
    fr = Frame(pcb)
    out = []
    w = out.append
    w('(pcb %s' % q('openaqua'))
    w(' (parser (string_quote ") (space_in_quoted_tokens on) (host_cad "openaqua-tools") (host_version "1"))')
    w(' (resolution um 10)\n (unit um)')
    w(' (structure')
    w('  (layer F.Cu (type signal) (property (index 0)))')
    w('  (layer B.Cu (type signal) (property (index 1)))')
    bpts = ' '.join('%s %s' % fr.d(*p) for p in fr.outline)
    w('  (boundary (path pcb 0 %s))' % bpts)
    for net, layer in planes:
        w('  (plane %s (polygon %s 0 %s))' % (q(net), layer, bpts))
    for k in keepouts:  # (layer or 'signal', [(mm x,y) board coords y down])
        lay, pts = k
        P = ' '.join('%s %s' % (round(x * 1000, 1), round(-y * 1000, 1)) for x, y in pts)
        w('  (keepout "" (polygon %s 0 %s))' % (lay, P))
    vname = 'Via[0-1]_%d:%d_um' % (via[0] * 1000, via[1] * 1000)
    w('  (via %s)' % q(vname))
    w('  (rule (width %d) (clearance %d))' % (default_width_mm * 1000, clearance_mm * 1000))
    if layer_costs:
        w('  (control (via_at_smd off))')
    w(' )')
    # placement + library
    plc = [' (placement']
    lib = [' (library']
    stacks = {}
    pinmap = {}
    for _, l in pcb.libs():
        ox, oy = l.xy
        OX, OY = fr.d(ox, oy)
        plc.append('  (component %s (place %s %s %s front 0))' % (q('IMG_' + l.ref), q(l.ref), OX, OY))
        img = ['  (image %s' % q('IMG_' + l.ref)]
        seen = {}
        for num, net, lay, shp, cx, cy, wdt, hgt, hr, pts in l.pad_geoms():
            if not num: num = 'X'
            seen[num] = seen.get(num, 0) + 1
            pid = num if seen[num] == 1 else '%s@%d' % (num, seen[num])
            layers = ['F.Cu', 'B.Cu'] if lay == '11' else [LAYER.get(lay, 'F.Cu')]
            Wu, Hu = round(wdt * UM, 1), round(hgt * UM, 1)
            key = (shp, Wu, Hu, tuple(layers), round(hr * UM * 2, 1))
            if key not in stacks:
                nm = 'PS%d_%s_%gx%g' % (len(stacks), shp, Wu, Hu)
                body = []
                for L in layers:
                    if shp == 'ELLIPSE' or (shp == 'OVAL' and abs(Wu - Hu) < 1):
                        body.append('(shape (circle %s %s))' % (L, max(Wu, Hu)))
                    elif shp == 'OVAL':
                        if Wu > Hu: body.append('(shape (path %s %s %s 0 %s 0))' % (L, Hu, -(Wu - Hu) / 2, (Wu - Hu) / 2))
                        else: body.append('(shape (path %s %s 0 %s 0 %s))' % (L, Wu, -(Hu - Wu) / 2, (Hu - Wu) / 2))
                    else:
                        body.append('(shape (rect %s %s %s %s %s))' % (L, -Wu / 2, -Hu / 2, Wu / 2, Hu / 2))
                stacks[key] = (nm, body)
            PX, PY = round((cx - ox) * UM, 1), round(-(cy - oy) * UM, 1)
            img.append('   (pin %s %s %s %s)' % (q(stacks[key][0]), q(pid), PX, PY))
            if net: pinmap.setdefault(net, []).append('%s-%s' % (l.ref, pid))
        img.append('  )')
        lib += img
    for nm, body in stacks.values():
        lib.append('  (padstack %s %s (attach off))' % (q(nm), ' '.join(body)))
    lib.append('  (padstack %s (shape (circle F.Cu %d)) (shape (circle B.Cu %d)) (attach off))' % (q(vname), via[0] * 1000, via[0] * 1000))
    out += plc + [' )'] + lib + [' )']
    # network
    w(' (network')
    for net, pins in sorted(pinmap.items()):
        w('  (net %s (pins %s))' % (q(net), ' '.join(pins)))
    classes = classes or {}
    assigned = set()
    for cname, (nets, width_mm, clr_mm) in classes.items():
        nets = [n for n in nets if n in pinmap]
        assigned |= set(nets)
        w('  (class %s %s (circuit (use_via %s)) (rule (width %d) (clearance %d)))' % (
            q(cname), ' '.join(q(n) for n in nets), q(vname), width_mm * 1000, clr_mm * 1000))
    rest = [n for n in pinmap if n not in assigned]
    w('  (class "default" %s (circuit (use_via %s)) (rule (width %d) (clearance %d)))' % (
        ' '.join(q(n) for n in rest), q(vname), default_width_mm * 1000, clearance_mm * 1000))
    w(' )')
    # pre-routed (protected) wiring
    w(' (wiring')
    for wire in wiring:  # (net, layer, width_mm, pts easyeda units[, protect])
        net, layer, width_mm, pts = wire[:4]
        prot = wire[4] if len(wire) > 4 else True
        P = ' '.join('%s %s' % fr.d(x, y) for x, y in pts)
        w('  (wire (path %s %d %s) (net %s)%s)' % (layer, width_mm * 1000, P, q(net), ' (type protect)' if prot else ''))
    for v in getattr(export_dsn, 'vias', []):
        net, x, y = v[:3]
        prot = v[3] if len(v) > 3 else True
        X, Y = fr.d(x, y); w('  (via %s %s %s (net %s)%s)' % (q(vname), X, Y, q(net), ' (type protect)' if prot else ''))
    w(' )')
    w(')')
    open(path, 'w').write('\n'.join(out) + '\n')
    return fr


def parse_sexp(txt):
    toks = re.findall(r'\(|\)|"[^"]*"|[^\s()]+', txt)
    st = [[]]
    for t in toks:
        if t == '(': st.append([])
        elif t == ')':
            x = st.pop(); st[-1].append(x)
        else: st[-1].append(t.strip('"'))
    return st[0][0]


def find(node, key):
    for n in node:
        if isinstance(n, list) and n and n[0] == key: yield n


def import_ses(pcb, ses_path, fr, skip_protected=True):
    """Return list of EasyEDA shape strings (TRACK/VIA) from a Freerouting .ses."""
    t = parse_sexp(open(ses_path).read())
    routes = next(find(t, 'routes'))
    res = 1.0
    for r in find(routes, 'resolution'): res = float(r[2]) / 1.0
    scale = 1.0 / res  # ses coords are in (unit / resolution); unit um
    via_dia = {}
    for lib in find(routes, 'library_out'):
        for ps in find(lib, 'padstack'):
            for sh in find(ps, 'shape'):
                c = sh[1]
                if c[0] == 'circle': via_dia[ps[1]] = float(c[2]) * scale
    shapes = []
    netout = next(find(routes, 'network_out'), [])
    for net in find(netout, 'net'):
        name = net[1]
        for wire in find(net, 'wire'):
            if skip_protected and any(isinstance(n, list) and n[:2] == ['type', 'protect'] for n in wire):
                continue
            p = next(find(wire, 'path'))
            layer, width = p[1], float(p[2]) * scale
            co = [float(v) * scale for v in p[3:]]
            pts = [fr.e(co[i], co[i + 1]) for i in range(0, len(co), 2)]
            shapes.append('TRACK~%s~%s~%s~%s~%s~0' % (_fmt(width / UM), LAYER_ID[layer], name,
                          ' '.join('%s %s' % (_fmt(x), _fmt(y)) for x, y in pts), new_gid()))
        for v in find(net, 'via'):
            if skip_protected and any(isinstance(n, list) and n[:2] == ['type', 'protect'] for n in v):
                continue
            dia = via_dia.get(v[1], 600)
            x, y = fr.e(float(v[2]) * scale, float(v[3]) * scale)
            shapes.append('VIA~%s~%s~%s~%s~%s~%s~0' % (_fmt(x), _fmt(y), _fmt(dia / UM), name,
                          _fmt(dia / UM * 0.25), new_gid()))
    return shapes
