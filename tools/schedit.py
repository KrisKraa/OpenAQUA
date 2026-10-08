"""Editing toolkit for EasyEDA Standard schematic JSON (editor 6.5.x).

Used by build_r2_sch.py. Coordinates are EasyEDA canvas units, y grows downward.
All wires are assumed axis-aligned (true for every wire in the OpenAQUA sheet).

Main pieces
  Sheet          load / save, wire / flag / part bookkeeping
  Sheet.detach   cut a pin loose from its wiring (prunes the now-dangling branch)
  Sheet.flag_at  add a net flag (with optional stub) at a point
  Sheet.auto_flag  search a collision-free stub + flag for an island
  connectivity() islands by wires only (no name merging) for the planner
  verify()       pin-level comparison against a reference netlist
"""
import json, re, copy, math, collections, itertools

# ------------------------------------------------------------------ small geometry

def R2(v):
    return round(float(v), 2)


def fmt(v):
    v = round(float(v), 3)
    return str(int(v)) if v == int(v) else ('%.3f' % v).rstrip('0').rstrip('.')


def on_seg(p, a, b):
    """p on axis-aligned segment a-b (inclusive)."""
    if a[0] == b[0] == p[0] and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]):
        return True
    if a[1] == b[1] == p[1] and min(a[0], b[0]) <= p[0] <= max(a[0], b[0]):
        return True
    return False


def seg_touch(a, b, c, d):
    """Do axis-aligned segments a-b and c-d share any point?"""
    ax0, ax1 = sorted((a[0], b[0])); ay0, ay1 = sorted((a[1], b[1]))
    cx0, cx1 = sorted((c[0], d[0])); cy0, cy1 = sorted((c[1], d[1]))
    return ax0 <= cx1 and cx0 <= ax1 and ay0 <= cy1 and cy0 <= ay1


def seg_cross_ok(a, b, c, d):
    """True if a-b and c-d either don't touch, or cross perpendicularly at a point
    that is interior to both (a plain wire crossing, no electrical contact)."""
    if not seg_touch(a, b, c, d):
        return False if False else True
    h1 = a[1] == b[1]; h2 = c[1] == d[1]
    if h1 == h2:
        return False  # collinear overlap / touch
    if h1:
        x, y = c[0], a[1]
    else:
        x, y = a[0], c[1]
    p = (x, y)
    return p not in (a, b, c, d)


def rect_hit(r1, r2, m=0.0):
    return r1[0] - m < r2[2] and r2[0] - m < r1[2] and r1[1] - m < r2[3] and r2[1] - m < r1[3]


DIRV = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}
# flag rotation per outward direction
VCC_ROT = {'up': 0, 'down': 180, 'right': 270, 'left': 90}
GND_ROT = {'down': 0, 'up': 180, 'right': 90, 'left': 270}

_gid = [100000]


def new_gid():
    _gid[0] += 1
    return 'gge%d' % _gid[0]


FLAG_CW = 6.5   # flag text char width estimate (Times 9pt)
PART_CW = 5.0   # part text char width estimate (Arial 7pt)


def is_gnd(name):
    return name == 'GND'


# ------------------------------------------------------------------ transforms for symbol sub-shapes

class Xf:
    """p' = R(p - c) + c + d, R = rotation by deg (multiple of 90, clockwise on screen)
    optionally preceded by a mirror about the vertical line x = c.x."""
    def __init__(s, c=(0, 0), deg=0, d=(0, 0), mirror=False):
        s.c, s.deg, s.d, s.mirror = c, deg % 360, d, mirror

    def v(s, dx, dy):
        if s.mirror: dx = -dx
        for _ in range(s.deg // 90):
            dx, dy = -dy, dx
        return dx, dy

    def p(s, x, y):
        dx, dy = s.v(x - s.c[0], y - s.c[1])
        return s.c[0] + dx + s.d[0], s.c[1] + dy + s.d[1]

    def rot(s, r):
        # EasyEDA rotation fields count counter-clockwise on screen (pin rot 0 = points
        # right, 90 = points up); this transform turns clockwise, hence the minus
        r = float(r or 0)
        if s.mirror: r = (180 - r) % 360
        return (r - s.deg) % 360

    def pts(s, txt):
        n = [float(v) for v in txt.split()]
        out = []
        for i in range(0, len(n), 2):
            out += list(s.p(n[i], n[i + 1]))
        return ' '.join(fmt(v) for v in out)

    def path(s, d):
        toks = re.findall(r'[A-Za-z]|-?\d+\.?\d*(?:e-?\d+)?', d)
        out = []; i = 0; cmd = None
        while i < len(toks):
            t = toks[i]
            if re.match(r'[A-Za-z]', t):
                cmd = t; out.append(t); i += 1
                if t in 'Zz': continue
                continue
            if cmd in 'MLC':
                x, y = s.p(float(toks[i]), float(toks[i + 1])); out += [fmt(x), fmt(y)]; i += 2
            elif cmd in 'hv':
                v = float(toks[i]); vec = (v, 0) if cmd == 'h' else (0, v)
                dx, dy = s.v(*vec)
                # replace the command letter
                out[-1] = 'h' if dy == 0 else 'v'
                out.append(fmt(dx if dy == 0 else dy)); i += 1
            else:
                raise ValueError('path cmd %r in %r' % (cmd, d))
        return ' '.join(out)


def xform_sub(sub, xf):
    f = sub.split('~'); t = f[0]
    if t == 'T':
        x, y = xf.p(float(f[2]), float(f[3])); f[2], f[3] = fmt(x), fmt(y)
        return '~'.join(f)
    if t in ('PL', 'PG'):
        f[1] = xf.pts(f[1]); return '~'.join(f)
    if t == 'PT':
        f[1] = xf.path(f[1]); return '~'.join(f)
    if t == 'R':
        x, y, w, h = float(f[1]), float(f[2]), float(f[5]), float(f[6])
        p1 = xf.p(x, y); p2 = xf.p(x + w, y + h)
        f[1], f[2] = fmt(min(p1[0], p2[0])), fmt(min(p1[1], p2[1]))
        f[5], f[6] = fmt(abs(p2[0] - p1[0])), fmt(abs(p2[1] - p1[1]))
        return '~'.join(f)
    if t == 'E':
        x, y = xf.p(float(f[1]), float(f[2])); f[1], f[2] = fmt(x), fmt(y)
        if xf.deg in (90, 270): f[3], f[4] = f[4], f[3]
        return '~'.join(f)
    if t == 'P':
        g = sub.split('^^')
        h = g[0].split('~')
        x, y = xf.p(float(h[4]), float(h[5])); h[4], h[5] = fmt(x), fmt(y)
        h[6] = fmt(xf.rot(h[6]))
        g[0] = '~'.join(h)
        d = g[1].split('~'); x, y = xf.p(float(d[0]), float(d[1])); d[0], d[1] = fmt(x), fmt(y); g[1] = '~'.join(d)
        pp = g[2].split('~'); pp[0] = xf.path(pp[0]); g[2] = '~'.join(pp)
        for k in (3, 4):  # name / number text
            q = g[k].split('~')
            x, y = xf.p(float(q[1]), float(q[2])); q[1], q[2] = fmt(x), fmt(y)
            if xf.mirror and len(q) > 5:
                q[5] = {'start': 'end', 'end': 'start'}.get(q[5], q[5])
            g[k] = '~'.join(q)
        q = g[5].split('~'); x, y = xf.p(float(q[1]), float(q[2])); q[1], q[2] = fmt(x), fmt(y); g[5] = '~'.join(q)
        q = g[6].split('~'); q[1] = xf.path(q[1]); g[6] = '~'.join(q)
        return '^^'.join(g)
    if t == 'A':
        raise ValueError('arc transform not supported')
    return sub


def fresh_ids(raw):
    return re.sub(r'(?<=~)(?:gge|rep)[0-9A-Za-z]+(?=~|$|\^)', lambda m: new_gid(), raw)


# ------------------------------------------------------------------ part wrapper

class Lib:
    def __init__(s, raw):
        s.parts = raw.split('#@$')
        s.head = s.parts[0].split('~')

    def raw(s):
        return '~'.join(s.head) + ''.join('#@$' + p for p in s.parts[1:])

    @property
    def ref(s):
        for p in s.parts[1:]:
            f = p.split('~')
            if f[0] == 'T' and f[1] == 'P': return f[12]
        return None

    def attrs(s):
        a = s.head[3].split('`')
        return dict(zip(a[0::2], a[1::2]))

    def set_attrs(s, upd):
        a = s.attrs(); a.update(upd)
        s.head[3] = '`'.join(k + '`' + v for k, v in a.items() if k) + '`'

    def text(s, kind):
        for i, p in enumerate(s.parts):
            f = p.split('~')
            if f[0] == 'T' and f[1] == kind: return i, f
        return None, None

    def set_text(s, kind, val=None, xy=None):
        i, f = s.text(kind)
        if i is None: return
        if val is not None: f[12] = val
        if xy is not None: f[2], f[3] = fmt(xy[0]), fmt(xy[1])
        s.parts[i] = '~'.join(f)

    def pins(s):
        """num -> (x, y, outward_dir)"""
        out = {}
        for p in s.parts[1:]:
            if not p.startswith('P~'): continue
            g = p.split('^^')
            num = g[0].split('~')[3]
            x, y = (R2(v) for v in g[1].split('~')[:2])
            m = re.match(r'M\s*(-?[\d.]+)[\s,]+(-?[\d.]+)\s*([hv])\s*(-?[\d.]+)', g[2].split('~')[0])
            sx, sy, hv, d = float(m.group(1)), float(m.group(2)), m.group(3), float(m.group(4))
            ex, ey = (sx + d, sy) if hv == 'h' else (sx, sy + d)
            # one end of the pin line is the connection point, the other touches the body
            if abs(sx - x) + abs(sy - y) < abs(ex - x) + abs(ey - y):
                bx, by = ex, ey
            else:
                bx, by = sx, sy
            vx, vy = x - bx, y - by
            od = ('right' if vx > 0 else 'left') if abs(vx) > abs(vy) else ('down' if vy > 0 else 'up')
            out[num] = (x, y, od)
        return out

    def transform(s, xf):
        x, y = xf.p(float(s.head[1]), float(s.head[2]))
        s.head[1], s.head[2] = fmt(x), fmt(y)
        s.head[4] = fmt(xf.rot(s.head[4])) if (xf.deg or xf.mirror) else s.head[4]
        s.parts = [s.parts[0]] + [xform_sub(p, xf) for p in s.parts[1:]]

    def xy(s):
        return float(s.head[1]), float(s.head[2])

    def rects(s, texts=True):
        """obstacle rectangles of the drawn symbol (graphics, pins, visible texts)."""
        out = []
        for p in s.parts[1:]:
            f = p.split('~')
            t = f[0]
            if t in ('PL', 'PG'):
                n = [float(v) for v in f[1].split()]
                out.append((min(n[0::2]), min(n[1::2]), max(n[0::2]), max(n[1::2])))
            elif t == 'PT':
                n = [float(v) for v in re.findall(r'-?\d+\.?\d*', f[1])]
                if n: out.append((min(n[0::2]), min(n[1::2]), max(n[0::2]), max(n[1::2])))
            elif t == 'R':
                x, y, w, h = float(f[1]), float(f[2]), float(f[5]), float(f[6])
                out.append((x, y, x + w, y + h))
            elif t == 'E':
                x, y, rx, ry = (float(v) for v in f[1:5])
                out.append((x - rx, y - ry, x + rx, y + ry))
            elif t == 'T':
                if texts and f[12].strip() and (len(f) < 14 or f[13] != '0'):
                    x, y = float(f[2]), float(f[3]); w = PART_CW * len(f[12])
                    rot = float(f[4] or 0)
                    if rot in (90, 270): out.append((x - 8, y - w, x + 1, y + 1))
                    else: out.append((x - 1, y - 8, x + w, y + 1))
            elif t == 'P':
                g = p.split('^^')
                m = re.match(r'M\s*(-?[\d.]+)[\s,]+(-?[\d.]+)\s*([hv])\s*(-?[\d.]+)', g[2].split('~')[0])
                x0, y0 = float(m.group(1)), float(m.group(2)); d = float(m.group(4))
                x1, y1 = (x0 + d, y0) if m.group(3) == 'h' else (x0, y0 + d)
                out.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
                for k in (3, 4):
                    q = g[k].split('~')
                    if texts and q[0] == '1' and q[4].strip():
                        x, y = float(q[1]), float(q[2]); w = 4 * len(q[4])
                        if q[5] == 'end': out.append((x - w, y - 6, x, y + 1))
                        else: out.append((x, y - 6, x + w, y + 1))
        return out


# ------------------------------------------------------------------ flags

def make_flag(name, x, y, outward):
    """Net flag whose connection point is (x,y); the symbol extends in `outward`."""
    g0, gt = new_gid(), new_gid()
    w = FLAG_CW * len(name)
    if is_gnd(name):
        rot = GND_ROT[outward]
        xf = Xf(deg=(360 - rot) % 360)   # EasyEDA rotates counter-clockwise on screen
        base = [((0, 10), (0, 0)), ((-9, 10), (9, 10)), ((-6, 12), (6, 12)), ((-3, 14), (3, 14)), ((-1, 16), (1, 16))]
        tx, ty = {0: (x - 13, y + 26), 180: (x - 13, y - 19), 90: (x + 16.5, y + 4), 270: (x - 42.8, y + 4)}[rot]
        kind = 'part_netLabel_gnD'
    else:
        rot = VCC_ROT[outward]
        xf = Xf(deg=0)
        base = {0: [((0, -10), (0, 0)), ((-5, -10), (5, -10))],
                180: [((0, 10), (0, 0)), ((5, 10), (-5, 10))],
                270: [((10, 0), (0, 0)), ((10, -5), (10, 5))],
                90: [((-10, 0), (0, 0)), ((-10, 5), (-10, -5))]}[rot]
        tx, ty = {0: (x - w / 2, y - 16), 180: (x - w / 2, y + 21.5), 270: (x + 10.5, y + 4), 90: (x - 10.5 - w, y + 4)}[rot]
        kind = 'part_netLabel_VCC'
    pls = []
    for a, b in base:
        if is_gnd(name):
            a = xf.v(*a); b = xf.v(*b)
        pls.append('PL~%s %s %s %s~#000000~1~0~transparent~%s~0' % (fmt(x + a[0]), fmt(y + a[1]), fmt(x + b[0]), fmt(y + b[1]), new_gid()))
    head = 'F~%s~%s~%s~%s~%s~~0' % (kind, fmt(x), fmt(y), rot, g0)
    txt = '%s~#000000~%s~%s~0~start~1~Times New Roman~9pt~flag_%s' % (name, fmt(tx), fmt(ty), gt)
    return '^^'.join([head, '%s~%s' % (fmt(x), fmt(y)), txt] + pls)


def flag_info(raw):
    g = raw.split('^^')
    xy = tuple(R2(v) for v in g[1].split('~')[:2])
    nm = g[2].split('~')
    return xy, nm[0]


def flag_outward(raw):
    """outward direction of an existing flag (where its symbol is drawn)."""
    f = raw.split('~'); kind = f[1]; rot = int(float(f[4] or 0))
    table = GND_ROT if 'gnD' in kind else VCC_ROT
    inv = {v: k for k, v in table.items()}
    return inv[rot]


def flag_rects(raw):
    g = raw.split('^^')
    out = []
    for s in g[3:]:
        f = s.split('~')
        if f[0] == 'PL':
            n = [float(v) for v in f[1].split()]
            x0, y0, x1, y1 = min(n[0::2]), min(n[1::2]), max(n[0::2]), max(n[1::2])
            # bars: shrink along their length so flags on a 10-unit pitch don't collide
            if x1 - x0 > y1 - y0: x0, x1 = x0 + 1.5, x1 - 1.5
            elif y1 - y0 > x1 - x0: y0, y1 = y0 + 1.5, y1 - 1.5
            out.append((x0, y0, x1, y1))
    nm = g[2].split('~')
    tx, ty = float(nm[2]), float(nm[3])
    out.append((tx, ty - 8, tx + FLAG_CW * len(nm[0]), ty))
    return out


# ------------------------------------------------------------------ sheet

class Wire:
    def __init__(s, pts, raw=None, gid=None):
        s.pts = [(R2(x), R2(y)) for x, y in pts]
        s.raw = raw; s.gid = gid or new_gid()

    def segs(s):
        return list(zip(s.pts, s.pts[1:]))

    def emit(s):
        if s.raw is not None: return s.raw
        # merge collinear runs for a clean drawing
        p = [s.pts[0]]
        for q in s.pts[1:]:
            if q == p[-1]: continue
            if len(p) >= 2 and ((p[-2][0] == p[-1][0] == q[0]) or (p[-2][1] == p[-1][1] == q[1])):
                p[-1] = q
            else:
                p.append(q)
        return 'W~%s~#008800~1~0~none~%s~0' % (' '.join('%s %s' % (fmt(x), fmt(y)) for x, y in p), s.gid)


class Sheet:
    def __init__(s, path):
        s.doc = json.load(open(path))
        sh = s.doc['schematics'][0]['dataStr']['shape']
        mx = max([int(m) for m in re.findall(r'gge(\d+)(?![0-9a-zA-Z])', json.dumps(s.doc))] + [0])
        _gid[0] = max(_gid[0], mx + 1000)
        s.items = []   # list of [kind, obj]; kind in W F LIB J T other ; obj None = deleted
        for x in sh:
            t = x.split('~')[0]
            if t == 'W':
                c = [float(v) for v in x.split('~')[1].split()]
                s.items.append(['W', Wire([(c[i], c[i + 1]) for i in range(0, len(c), 2)], raw=x, gid=x.split('~')[6])])
            elif t == 'LIB':
                s.items.append(['LIB', Lib(x)])
            else:
                s.items.append([t, x])
        s._orig_j = {(R2(x.split('~')[1]), R2(x.split('~')[2])) for x in sh if x.startswith('J~')}

    # ---------------- accessors
    def wires(s):
        return [(i, o) for i, (k, o) in enumerate(s.items) if k == 'W' and o is not None]

    def flags(s):
        return [(i, o) for i, (k, o) in enumerate(s.items) if k == 'F' and o is not None]

    def libs(s):
        return [(i, o) for i, (k, o) in enumerate(s.items) if k == 'LIB' and o is not None]

    def lib(s, ref):
        hits = [(i, o) for i, o in s.libs() if o.ref == ref]
        if len(hits) != 1: raise KeyError('%s found %d times' % (ref, len(hits)))
        return hits[0]

    def pin(s, ref, num):
        return s.lib(ref)[1].pins()[num]

    def all_pins(s):
        out = []
        for i, l in s.libs():
            r = l.ref
            if r == 'A' or r is None: continue
            for n, (x, y, d) in l.pins().items():
                out.append((r, n, (x, y), d))
        return out

    def add(s, kind, obj):
        s.items.append([kind, obj]); return len(s.items) - 1

    def add_wire(s, pts):
        for a, b in zip(pts, pts[1:]):
            assert a[0] == b[0] or a[1] == b[1], ('diagonal wire', pts)
        return s.add('W', Wire(pts))

    def add_flag(s, name, x, y, outward):
        return s.add('F', make_flag(name, x, y, outward))

    def add_text(s, txt, x, y, size='11pt', color='#FF0000'):
        return s.add('T', 'T~L~%s~%s~0~%s~~%s~bolder~~~comment~%s~1~start~%s~0~pinpart' % (fmt(x), fmt(y), color, size, txt, new_gid()))

    def delete(s, idx):
        s.items[idx][1] = None

    def rename_flag(s, idx, name):
        raw = s.items[idx][1]
        xy, old = flag_info(raw)
        if old == name: return
        if is_gnd(name) != is_gnd(old):
            out = flag_outward(raw)
            s.items[idx][1] = make_flag(name, xy[0], xy[1], out)
        else:
            g = raw.split('^^'); nm = g[2].split('~')
            # keep the text anchored at the flag body side
            rot = int(float(raw.split('~')[4] or 0))
            if not is_gnd(name):
                w0, w1 = FLAG_CW * len(old), FLAG_CW * len(name)
                tx = float(nm[2])
                if rot == 90: tx = tx + w0 - w1
                elif rot in (0, 180): tx = tx + (w0 - w1) / 2
                nm[2] = fmt(tx)
            nm[0] = name; g[2] = '~'.join(nm)
            s.items[idx][1] = '^^'.join(g)

    # ---------------- graph
    def graph(s):
        """Split every wire at every attachment point; return nodes/edges.
        edges: list of (wire_idx, a, b); node info: pins, flags."""
        pts = set()
        for i, w in s.wires():
            pts.update(w.pts)
        pins = collections.defaultdict(list)
        for r, n, xy, d in s.all_pins():
            pins[xy].append((r, n)); pts.add(xy)
        flags = collections.defaultdict(list)
        for i, raw in s.flags():
            xy, nm = flag_info(raw); flags[xy].append(i); pts.add(xy)
        edges = []
        for i, w in s.wires():
            for a, b in w.segs():
                if a == b: continue
                inner = sorted([p for p in pts if p not in (a, b) and on_seg(p, a, b)],
                               key=lambda p: abs(p[0] - a[0]) + abs(p[1] - a[1]))
                chain = [a] + inner + [b]
                for u, v in zip(chain, chain[1:]):
                    edges.append((i, u, v))
        adj = collections.defaultdict(list)
        for e in edges:
            adj[e[1]].append(e); adj[e[2]].append(e)
        return edges, adj, pins, flags

    def islands(s):
        edges, adj, pins, flags = s.graph()
        par = {}
        def f(a):
            par.setdefault(a, a)
            while par[a] != a:
                par[a] = par[par[a]]; a = par[a]
            return a
        for _, a, b in edges: par[f(a)] = f(b)
        for p in list(pins) + list(flags): f(p)
        isl = collections.defaultdict(lambda: {'pins': [], 'flags': [], 'wires': set(), 'pts': set()})
        for p, l in pins.items():
            isl[f(p)]['pins'] += ['%s.%s' % rn for rn in l]; isl[f(p)]['pts'].add(p)
        for p, l in flags.items():
            isl[f(p)]['flags'] += l; isl[f(p)]['pts'].add(p)
        for i, a, b in edges:
            isl[f(a)]['wires'].add(i); isl[f(a)]['pts'].update((a, b))
        return list(isl.values())

    def remove_subseg(s, widx, a, b):
        w = s.items[widx][1]
        pts = w.pts
        for k, (p, q) in enumerate(zip(pts, pts[1:])):
            if on_seg(a, p, q) and on_seg(b, p, q):
                seq = [p] + sorted({a, b} - {p, q}, key=lambda t: abs(t[0] - p[0]) + abs(t[1] - p[1])) + [q]
                # seq is p..a..b..q (or p..b..a..q); cut the a-b piece
                ia, ib = seq.index(a), seq.index(b)
                lo, hi = min(ia, ib), max(ia, ib)
                left = pts[:k] + seq[:lo + 1]
                right = seq[hi:] + pts[k + 2:]
                s.items[widx][1] = None
                for part in (left, right):
                    part2 = [x for j, x in enumerate(part) if j == 0 or x != part[j - 1]]
                    if len(part2) >= 2:
                        s.add('W', Wire(part2))
                return
        raise ValueError('subsegment %s-%s not in wire %d' % (a, b, widx))

    def detach(s, ref, num, log=None):
        """Disconnect pin ref.num from whatever wiring/flags touch it; prune the branch
        that only served this pin. Raises if the pin sits mid-way on a through wire."""
        x, y, _ = s.pin(ref, num)
        p = (x, y)
        removed = []
        while True:
            edges, adj, pins, flags = s.graph()
            others = [rn for rn in pins.get(p, []) if rn != (ref, num)]
            if others:
                raise ValueError('%s.%s touches pin %s directly' % (ref, num, others))
            es = adj.get(p, [])
            if not es:
                for fi in flags.get(p, []):
                    s.delete(fi); removed.append(('F', fi))
                break
            if len(es) > 1:
                raise ValueError('%s.%s is a through node (%d wire branches)' % (ref, num, len(es)))
            # walk
            cur = p; e = es[0]; seen_pins = {(ref, num)}
            while True:
                wi, a, b = e
                s.remove_subseg(wi, a, b); removed.append(('W', a, b))
                q = b if a == cur else a
                edges, adj, pins, flags = s.graph()
                rem = adj.get(q, [])
                if pins.get(q):
                    break
                if flags.get(q):
                    if not rem:
                        for fi in flags[q]: s.delete(fi); removed.append(('F', fi))
                    break
                if len(rem) == 1:
                    cur = q; e = rem[0]; continue
                break
            break
        if log is not None: log.append(('detach', ref, num, removed))
        return removed

    # ---------------- obstacles
    def obstacles(s, skip_flags=()):
        rs = []
        for i, w in s.wires():
            for a, b in w.segs():
                rs.append((min(a[0], b[0]) - .5, min(a[1], b[1]) - .5, max(a[0], b[0]) + .5, max(a[1], b[1]) + .5))
        for i, l in s.libs():
            if l.ref == 'A': continue
            rs += l.rects()
        for i, raw in s.flags():
            if i in skip_flags: continue
            rs += flag_rects(raw)
        for k, o in s.items:
            if k == 'T' and o is not None:
                f = o.split('~')
                x, y = float(f[2]), float(f[3]); rs.append((x, y - 14, x + 11 * len(f[12]), y + 2))
        rs += s.extra_obstacles
        return rs

    extra_obstacles = [(1610, -125, 2100, 0)]  # title block
    BOUNDS = (30, -1560, 2030, -30)

    def wire_points(s):
        segs = []
        for i, w in s.wires(): segs += w.segs()
        return segs

    def stub_ok(s, path, own_pts, segs, pinpts, flagpts):
        """electrical check for a new wire path (list of points): it may only touch
        existing wiring at path[0]; plain perpendicular crossings are allowed."""
        st = path[0]
        for a, b in zip(path, path[1:]):
            for c, d in segs:
                if not seg_touch(a, b, c, d): continue
                ha, hc = a[1] == b[1], c[1] == d[1]
                if ha == hc:  # collinear: overlap must be just the start point
                    if ha: lo, hi = max(min(a[0], b[0]), min(c[0], d[0])), min(max(a[0], b[0]), max(c[0], d[0]))
                    else: lo, hi = max(min(a[1], b[1]), min(c[1], d[1])), min(max(a[1], b[1]), max(c[1], d[1]))
                    if lo == hi and a == st and (st == c or st == d or on_seg(st, c, d)) and \
                            (st[0] if ha else st[1]) == lo:
                        continue
                    return False
                I = (c[0], a[1]) if ha else (a[0], c[1])
                if I == st and a == st: continue
                if I in (a, b, c, d): return False
            for q in list(pinpts) + list(flagpts):
                if q == st: continue
                if on_seg(q, a, b): return False
        return True

    def flag_candidate_ok(s, name, path, outward, obst, segs, pinpts, flagpts, extra=(), why=None):
        if not s.stub_ok(path, None, segs, pinpts, flagpts):
            if why is not None: why.append('electrical')
            return False
        end = path[-1]
        raw = make_flag(name, end[0], end[1], outward)
        frs = flag_rects(raw)
        bx0, by0, bx1, by1 = s.BOUNDS
        for r in frs:
            if r[0] < bx0 or r[2] > bx1 or r[1] < by0 or r[3] > by1: return False
            for o in list(obst) + list(extra):
                if rect_hit(r, o, 1.0):
                    if why is not None: why.append(('flag hits', r, o))
                    return False
        # stub body must not run through drawn graphics (other than wires, handled above)
        for a, b in zip(path, path[1:]):
            if a == b: continue
            sr = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
            # shrink at the start so the pin's own line doesn't count
            dx = (b[0] > a[0]) - (b[0] < a[0]); dy = (b[1] > a[1]) - (b[1] < a[1])
            sr2 = (sr[0] + (1.5 if dx > 0 else 0), sr[1] + (1.5 if dy > 0 else 0),
                   sr[2] - (1.5 if dx < 0 else 0), sr[3] - (1.5 if dy < 0 else 0))
            for o in s.part_obst:
                if rect_hit(sr2, o, 0.2):
                    if why is not None: why.append(('stub hits', sr2, o))
                    return False
        return True

    def candidates_from(s, p, outward, Ls=(10, 20, 30, 40, 50, 60, 80, 100, 120, 140), turns=True):
        dx, dy = DIRV[outward]
        for L in Ls:
            q = (R2(p[0] + dx * L), R2(p[1] + dy * L))
            yield [p, q], outward, L
        if turns:
            for L in (10, 20, 30, 40, 50, 60):
                q = (R2(p[0] + dx * L), R2(p[1] + dy * L))
                for side in DIRV:
                    sx, sy = DIRV[side]
                    if (sx, sy) in ((dx, dy), (-dx, -dy)): continue
                    yield [p, q], side, L + 5           # flag turns at the corner
                    for L2 in (10, 20, 30, 40):
                        r = (R2(q[0] + sx * L2), R2(q[1] + sy * L2))
                        yield [p, q, r], side, L + L2 + 8
                        yield [p, q, r], outward, L + L2 + 10   # jog, then flag parallel to the first leg

    def prepare_obstacles(s, skip_flags=()):
        s.part_obst = []
        for i, l in s.libs():
            if l.ref == 'A': continue
            s.part_obst += l.rects(texts=False)
        for i, raw in s.flags():
            s.part_obst += flag_rects(raw)          # stubs may cross part texts, not flag names
        return s.obstacles(skip_flags)

    def auto_flag(s, name, start_pts, extra_obst=(), prefer=None):
        """start_pts: list of (point, outward_dir_or_None). Try stubs from each."""
        obst = s.prepare_obstacles()
        segs = s.wire_points()
        pinpts = {xy for _, _, xy, _ in s.all_pins()}
        flagpts = {flag_info(raw)[0] for _, raw in s.flags()}
        best = None
        for p, od in start_pts:
            dirs = [od] if od else list(DIRV)
            for d in dirs:
                for path, outward, cost in s.candidates_from(p, d, turns=True):
                    if best and cost >= best[0]: continue
                    if s.flag_candidate_ok(name, path, outward, obst, segs, pinpts, flagpts, extra_obst):
                        best = (cost, path, outward)
        if not best: return None
        cost, path, outward = best
        if len(path) >= 2 and path[0] != path[-1]:
            s.add_wire(path)
        s.add_flag(name, path[-1][0], path[-1][1], outward)
        return path, outward

    # ---------------- junction dots
    def fix_junctions(s, keep_existing=False):
        edges, adj, pins, flags = s.graph()
        # degree from original (unsplit) geometry: count wire ends + 2*interior passes + pins
        segs = []
        for i, w in s.wires(): segs += w.segs()
        deg = collections.Counter()
        cand = set(adj) | set(pins)
        for p in cand:
            d = len(pins.get(p, [])) + len(flags.get(p, []))
            for a, b in segs:
                if p == a or p == b: d += 1
                elif on_seg(p, a, b): d += 2
            deg[p] = d
        need = {p for p, d in deg.items() if d >= 3 and adj.get(p)}
        if keep_existing:
            need |= set(e for e in s._orig_j if e in adj)
        have = {}
        for i, (k, o) in enumerate(s.items):
            if k == 'J' and o is not None:
                f = o.split('~'); have[(R2(f[1]), R2(f[2]))] = i
        for p, i in have.items():
            if p not in need: s.delete(i)
        for p in need - set(have):
            s.add('J', 'J~%s~%s~2.5~#CC0000~%s~0' % (fmt(p[0]), fmt(p[1]), new_gid()))

    # ---------------- output
    def shapes(s):
        out = []
        for k, o in s.items:
            if o is None: continue
            if k == 'W': out.append(o.emit())
            elif k == 'LIB': out.append(o.raw())
            else: out.append(o)
        return out

    def save(s, path):
        s.doc['schematics'][0]['dataStr']['shape'] = s.shapes()
        json.dump(s.doc, open(path, 'w'), ensure_ascii=False, separators=(',', ':'))


# ------------------------------------------------------------------ verification

def auto_named(net, allpins):
    """EasyEDA-style automatic net name 'REF_PIN' (e.g. U13_1, LED4_1, CN3_3)."""
    m = re.match(r'^([A-Z]+\d+)_([A-Z0-9]+)$', net)
    return bool(m) and '%s.%s' % (m.group(1), m.group(2)) in allpins


def verify(groups, refnet, allowed_extra_names=(), allpins=None):
    """groups: schnet.schnetlist() groups. refnet: name -> ['REF.PIN', ...].
    Returns list of problem strings (empty = exact match)."""
    probs = []
    ref = {n: sorted(set(l)) for n, l in refnet.items()}
    pin2net = {p: n for n, l in ref.items() for p in l}
    allpins = allpins or set(pin2net)
    seen = collections.Counter()
    for g in groups.values():
        ps = sorted(set(g['pins'])); names = set(g['names'])
        if not ps:
            if names: probs.append('FLAG-ONLY group %s' % sorted(names))
            continue
        nets = {pin2net.get(p, '?unknown:' + p) for p in ps}
        if len(nets) > 1:
            probs.append('MERGED %s : %s' % (sorted(nets), ps)); continue
        n = nets.pop(); seen[n] += 1
        if set(ps) != set(ref.get(n, [])):
            probs.append('PARTIAL %s: sch %s ref %s' % (n, ps, ref.get(n)))
        bad = names - {n} - set(allowed_extra_names)
        if bad: probs.append('NAME %s carries other names %s' % (n, sorted(bad)))
        if len(ref.get(n, [])) > 1 and not auto_named(n, allpins) and n not in names:
            probs.append('UNNAMED %s (pins %s)' % (n, ps))
    for n, l in ref.items():
        if seen[n] == 0: probs.append('MISSING %s %s' % (n, l))
        if seen[n] > 1: probs.append('SPLIT %s into %d groups' % (n, seen[n]))
    return probs
