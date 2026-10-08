"""Exact (vector) clearance check between copper of different nets, per layer.
Mirrors an EDA DRC: pads (true shapes incl. polygons), tracks (with width), vias.
  python3 tools/exact_drc.py <pcb.json> [clearance_mm]
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))
from shapely.geometry import box, LineString, Point, Polygon
from shapely.strtree import STRtree
from pcbtool import Pcb, U
from dsn import outline_pts


def shapes(p):
    pts = outline_pts(p); x0 = min(a for a, _ in pts); y0 = min(b for _, b in pts)
    M = lambda x, y: ((x - x0) * U, (y - y0) * U)
    out = []
    for _, l in p.libs():
        for i, f in l.pads():
            shp, net, lay, num = f[1], f[7], f[6], f[8]
            cx, cy = M(float(f[2]), float(f[3]))
            pts_ = [float(v) for v in f[10].split()] if f[10].strip() else []
            if shp in ('RECT', 'POLYGON') and pts_:
                g = Polygon([M(pts_[k], pts_[k + 1]) for k in range(0, len(pts_), 2)])
            else:
                w, h = float(f[4]) * U, float(f[5]) * U
                if round(float(f[11] or 0)) % 180 == 90: w, h = h, w
                if shp == 'ELLIPSE' or abs(w - h) < 1e-3: g = Point(cx, cy).buffer(w / 2)
                elif w > h: g = LineString([(cx - (w - h) / 2, cy), (cx + (w - h) / 2, cy)]).buffer(h / 2)
                else: g = LineString([(cx, cy - (h - w) / 2), (cx, cy + (h - w) / 2)]).buffer(w / 2)
            for L in (('1', '2') if lay == '11' else (lay,)):
                out.append((L, net, g, '%s.%s' % (l.ref, num)))
    for s in p.shape:
        f = s.split('~')
        if f[0] == 'TRACK' and f[2] in ('1', '2'):
            n = [float(v) for v in f[4].split()]
            P = [M(n[k], n[k + 1]) for k in range(0, len(n), 2)]
            out.append((f[2], f[3], LineString(P).buffer(float(f[1]) * U / 2, cap_style=1), 'track'))
        elif f[0] == 'VIA':
            x, y = M(float(f[1]), float(f[2]))
            for L in ('1', '2'): out.append((L, f[4], Point(x, y).buffer(float(f[3]) * U / 2), 'via'))
        elif f[0] == 'SOLIDREGION' and f[4] == 'solid' and f[1] in ('1', '2') and f[2]:
            n = [float(v) for v in re.findall(r'-?\d+\.?\d*', f[3])]
            out.append((f[1], f[2], Polygon([M(n[k], n[k + 1]) for k in range(0, len(n), 2)]), 'region'))
    return out


def check(path, clr):
    p = Pcb(path)
    S = shapes(p)
    bad = []
    for L in ('1', '2'):
        items = [s for s in S if s[0] == L]
        geoms = [s[2] for s in items]
        tree = STRtree(geoms)
        for i, (lay, net, g, ref) in enumerate(items):
            for j in tree.query(g.buffer(clr)):
                if j <= i: continue
                n2, ref2 = items[j][1], items[j][3]
                if net == n2 and net: continue
                d = g.distance(geoms[j])
                if d < clr - 1e-4:
                    c = g.centroid if ref != 'track' else geoms[j].centroid
                    bad.append((round(d, 3), L, net, ref, n2, ref2, round(c.x, 2), round(c.y, 2)))
    return sorted(bad)


if __name__ == '__main__':
    clr = float(sys.argv[2]) if len(sys.argv) > 2 else 0.15
    b = check(sys.argv[1], clr)
    print('violations < %.3f mm: %d' % (clr, len(b)))
    for x in b: print(' ', x)
