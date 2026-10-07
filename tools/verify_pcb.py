"""Verify a routed EasyEDA Std PCB: per-net connectivity and clearances.

Copper is rasterised per layer at RES mm. Pads, tracks and vias are drawn with
their net id; pours (COPPERAREA) are modelled as: fill the pour polygon on its
layer wherever no other-net copper is within the pour clearance, keep only the
islands that touch a pad/via of the pour net (like EasyEDA's "remove islands").
Two items of a net are connected if their copper touches on a shared layer
(vias and through-hole pads exist on both layers).

  python3 tools/verify_pcb.py <pcb.json> [--clearance 0.2]
Prints unrouted nets (split into islands) and clearance violations.
"""
import sys, os, math, re, json
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from pcbtool import Pcb, U
from dsn import outline_pts

RES = 0.05  # mm per pixel


class Raster:
    def __init__(s, pcb):
        pts = outline_pts(pcb)
        s.x0 = min(p[0] for p in pts); s.y0 = min(p[1] for p in pts)
        s.W = int((max(p[0] for p in pts) - s.x0) * U / RES) + 4
        s.H = int((max(p[1] for p in pts) - s.y0) * U / RES) + 4
        s.outline = [((x - s.x0) * U, (y - s.y0) * U) for x, y in pts]
        s.board = s.poly_mask(s.outline)

    def mm(s, x, y): return ((x - s.x0) * U, (y - s.y0) * U)

    def grid(s):
        ys, xs = np.mgrid[0:s.H, 0:s.W]
        return xs * RES, ys * RES

    def poly_mask(s, poly):
        # even-odd scanline fill
        m = np.zeros((s.H, s.W), bool)
        xs = (np.arange(s.W) + 0.5) * RES
        n = len(poly)
        for r in range(s.H):
            y = (r + 0.5) * RES
            cross = []
            for i in range(n):
                (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
                if (y1 <= y < y2) or (y2 <= y < y1):
                    cross.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
            cross.sort()
            for a, b in zip(cross[0::2], cross[1::2]):
                m[r, (xs >= a) & (xs < b)] = True
        return m

    def disc(s, cx, cy, r):
        r0, r1 = max(int((cy - r) / RES) - 1, 0), min(int((cy + r) / RES) + 2, s.H)
        c0, c1 = max(int((cx - r) / RES) - 1, 0), min(int((cx + r) / RES) + 2, s.W)
        ys, xs = np.mgrid[r0:r1, c0:c1]
        return (slice(r0, r1), slice(c0, c1)), ((xs + .5) * RES - cx) ** 2 + ((ys + .5) * RES - cy) ** 2 <= r * r

    def seg(s, a, b, w):
        (ax, ay), (bx, by) = a, b
        r = w / 2
        r0, r1 = max(int((min(ay, by) - r) / RES) - 1, 0), min(int((max(ay, by) + r) / RES) + 2, s.H)
        c0, c1 = max(int((min(ax, bx) - r) / RES) - 1, 0), min(int((max(ax, bx) + r) / RES) + 2, s.W)
        ys, xs = np.mgrid[r0:r1, c0:c1]
        px, py = (xs + .5) * RES, (ys + .5) * RES
        L = (bx - ax) ** 2 + (by - ay) ** 2
        t = np.zeros_like(px) if L == 0 else np.clip(((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / L, 0, 1)
        d2 = (px - ax - t * (bx - ax)) ** 2 + (py - ay - t * (by - ay)) ** 2
        return (slice(r0, r1), slice(c0, c1)), d2 <= r * r

    def rect(s, cx, cy, w, h):
        r0, r1 = max(int((cy - h / 2) / RES), 0), min(int((cy + h / 2) / RES) + 1, s.H)
        c0, c1 = max(int((cx - w / 2) / RES), 0), min(int((cx + w / 2) / RES) + 1, s.W)
        return (slice(r0, r1), slice(c0, c1)), np.ones((r1 - r0, c1 - c0), bool)


def items(pcb, R):
    """yield (net, layers, kind, geom) in board mm."""
    out = []
    for _, l in pcb.libs():
        for num, net, lay, shp, cx, cy, w, h, hr, pts in l.pad_geoms():
            x, y = R.mm(cx, cy)
            layers = ('1', '2') if lay == '11' else (lay,)
            if pts and shp == 'POLYGON':
                P = [R.mm(pts[i], pts[i + 1]) for i in range(0, len(pts), 2)]
                out.append((net, layers, 'poly', P, '%s.%s' % (l.ref, num)))
            elif shp in ('ELLIPSE',) or (shp == 'OVAL' and abs(w - h) < 0.01):
                out.append((net, layers, 'disc', (x, y, w * U / 2), '%s.%s' % (l.ref, num)))
            elif shp == 'OVAL':
                if w > h: a, b, ww = (x - (w - h) * U / 2, y), (x + (w - h) * U / 2, y), h * U
                else: a, b, ww = (x, y - (h - w) * U / 2), (x, y + (h - w) * U / 2), w * U
                out.append((net, layers, 'seg', (a, b, ww), '%s.%s' % (l.ref, num)))
            else:
                out.append((net, layers, 'rect', (x, y, w * U, h * U), '%s.%s' % (l.ref, num)))
    for s in pcb.shape:
        f = s.split('~')
        if f[0] == 'TRACK' and f[2] in ('1', '2'):
            n = [float(v) for v in f[4].split()]
            P = [R.mm(n[i], n[i + 1]) for i in range(0, len(n), 2)]
            for a, b in zip(P, P[1:]):
                out.append((f[3], (f[2],), 'seg', (a, b, float(f[1]) * U), 'track'))
        elif f[0] == 'VIA':
            x, y = R.mm(float(f[1]), float(f[2]))
            out.append((f[4], ('1', '2'), 'disc', (x, y, float(f[3]) * U / 2), 'via'))
        elif f[0] == 'SOLIDREGION' and f[1] in ('1', '2') and f[4] == 'solid' and f[2]:
            n = [float(v) for v in re.findall(r'-?\d+\.?\d*', f[3])]
            P = [R.mm(n[i], n[i + 1]) for i in range(0, len(n), 2)]
            out.append((f[2], (f[1],), 'poly', P, 'region'))
    return out


def draw(R, kind, g, grow=0.0):
    if kind == 'disc': return R.disc(g[0], g[1], g[2] + grow)
    if kind == 'seg': return R.seg(g[0], g[1], g[2] + 2 * grow)
    if kind == 'rect': return R.rect(g[0], g[1], g[2] + 2 * grow, g[3] + 2 * grow)
    if kind == 'poly':
        xs = [p[0] for p in g]; ys = [p[1] for p in g]
        m = R.poly_mask(g)
        if grow > 0:
            from scipy import ndimage  # noqa (optional)
        return (slice(0, R.H), slice(0, R.W)), m


def label(mask):
    from scipy import ndimage
    return ndimage.label(mask)


def verify(path, clearance=0.2):
    pcb = Pcb(path)
    R = Raster(pcb)
    its = items(pcb, R)
    nets = sorted({i[0] for i in its if i[0]})
    nid = {n: k + 1 for k, n in enumerate(nets)}
    layers = {'1': np.zeros((R.H, R.W), np.int32), '2': np.zeros((R.H, R.W), np.int32)}
    conflicts = set()
    for net, lays, kind, g, ref in its:
        if not net: continue
        sl, m = draw(R, kind, g)
        for L in lays:
            sub = layers[L][sl]
            clash = (sub > 0) & (sub != nid[net]) & m
            if clash.any():
                other = {nets[v - 1] for v in np.unique(sub[clash])}
                conflicts.add(('short', L, net, tuple(sorted(other)), ref))
            sub[m] = nid[net]
    # pours
    pours = []
    for s in pcb.shape:
        f = s.split('~')
        if f[0] == 'COPPERAREA':
            n = [float(v) for v in re.findall(r'-?\d+\.?\d*', f[4])]
            P = [R.mm(n[i], n[i + 1]) for i in range(0, len(n), 2)]
            pours.append((f[3], f[2], P, float(f[5]) * U))
    cut = {'1': np.zeros((R.H, R.W), bool), '2': np.zeros((R.H, R.W), bool)}
    for s in pcb.shape:
        f = s.split('~')
        if f[0] == 'SOLIDREGION' and f[4] == 'cutout':
            n = [float(v) for v in re.findall(r'-?\d+\.?\d*', f[3])]
            P = [R.mm(n[i], n[i + 1]) for i in range(0, len(n), 2)]
            for L in (('1', '2') if f[1] in ('11', '12') else (f[1],)):
                if L in cut: cut[L] |= R.poly_mask(P)
    from scipy import ndimage
    for net, L, P, clr in pours:
        if L not in layers: continue
        area = R.poly_mask(P) & R.board & ~cut[L]
        other = (layers[L] > 0) & (layers[L] != nid.get(net, -1))
        r = int(math.ceil(clr / RES))
        st = np.zeros((2 * r + 1, 2 * r + 1), bool)
        yy, xx = np.mgrid[-r:r + 1, -r:r + 1]; st[xx * xx + yy * yy <= r * r] = True
        blocked = ndimage.binary_dilation(other, structure=st)
        # board edge clearance 0.3 mm
        e = int(math.ceil(0.3 / RES)); st2 = np.ones((2 * e + 1, 2 * e + 1), bool)
        inner = ndimage.binary_erosion(R.board, structure=st2)
        fill = area & ~blocked & inner
        own = layers[L] == nid.get(net, -1)
        lab, n = ndimage.label(fill)
        keep = np.unique(lab[own & (lab > 0)])
        fill = np.isin(lab, keep[keep > 0])
        layers[L][fill & (layers[L] == 0)] = nid[net]
    # connectivity per net: label each layer's copper of that net, join via items spanning both layers
    report = {}
    for net in nets:
        k = nid[net]
        l1, n1 = ndimage.label(layers['1'] == k)
        l2, n2 = ndimage.label(layers['2'] == k)
        parent = list(range(n1 + n2 + 1))
        def find(a):
            while parent[a] != a: parent[a] = parent[parent[a]]; a = parent[a]
            return a
        pads = []
        for inet, lays, kind, g, ref in its:
            if inet != net: continue
            sl, m = draw(R, kind, g)
            comps = []
            for L, lab, off in (('1', l1, 0), ('2', l2, n1)):
                if L in lays:
                    v = np.unique(lab[sl][m]); v = v[v > 0]
                    comps += [int(x) + off for x in v]
            for a in comps[1:]: parent[find(a)] = find(comps[0])
            if ref not in ('track', 'via', 'region'): pads.append((ref, find(comps[0]) if comps else None))
        groups = {}
        for ref, c in pads:
            groups.setdefault(find(c) if c else None, []).append(ref)
        if len(groups) > 1 and len(pads) > 1:
            report[net] = sorted(groups.values(), key=len)
    # clearance (different nets, same layer): dilate each net's copper by clearance/2 and look for overlap
    viol = []
    r = max(1, int(round(clearance / 2 / RES)))
    st = np.zeros((2 * r + 1, 2 * r + 1), bool)
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]; st[xx * xx + yy * yy <= r * r] = True
    for L in ('1', '2'):
        lay = layers[L]
        grown = ndimage.grey_dilation(lay, footprint=st)
        grown_min = -ndimage.grey_dilation(-np.where(lay > 0, lay, 10 ** 6), footprint=st)
        bad = (grown > 0) & (grown_min < 10 ** 6) & (grown != grown_min)
        lab, n = ndimage.label(bad)
        for i in ndimage.find_objects(lab):
            ys, xs = i
            sub = lay[ys, xs]; v = sorted({nets[x - 1] for x in np.unique(sub) if x > 0})
            if len(v) >= 2:
                viol.append((L, round((xs.start + xs.stop) / 2 * RES, 2), round((ys.start + ys.stop) / 2 * RES, 2), v))
    return report, sorted(conflicts), viol, (layers, R, nets)


if __name__ == '__main__':
    path = sys.argv[1]
    clr = float(sys.argv[sys.argv.index('--clearance') + 1]) if '--clearance' in sys.argv else 0.2
    rep, shorts, viol, _ = verify(path, clr)
    print('UNCONNECTED nets: %d' % len(rep))
    for net, g in rep.items():
        print('  %s: %s' % (net, ' | '.join(','.join(x) for x in g)))
    print('SHORTS (overlapping copper of different nets): %d' % len(shorts))
    for s in shorts[:40]: print('  ', s)
    print('CLEARANCE < %.2f mm: %d spots' % (clr, len(viol)))
    for v in viol[:60]: print('  ', v)
