"""Helpers to inspect and edit EasyEDA Standard PCB JSON (editorVersion 6.x).

Units: EasyEDA canvas units, 1 unit = 10 mil = 0.254 mm. Y grows downward.
"""
import json, math, re, copy, random, string

U = 0.254  # mm per unit


def mm(v):
    return v / U


def _fmt(v):
    return ('%.4f' % v).rstrip('0').rstrip('.')


def new_gid():
    return 'gge' + ''.join(random.choice('0123456789abcdef') for _ in range(12))


class Xf:
    """Rotate by `deg` (multiple of 90 recommended) about (cx,cy), then translate by (dx,dy)."""

    def __init__(s, cx=0, cy=0, deg=0, dx=0, dy=0):
        s.cx, s.cy, s.deg, s.dx, s.dy = cx, cy, deg % 360, dx, dy
        # EasyEDA's rotation attribute turns the opposite way to the usual
        # y-down math rotation, so geometry is rotated by -deg.
        r = math.radians(-s.deg)
        s.c, s.s = round(math.cos(r), 12), round(math.sin(r), 12)

    def pt(s, x, y):
        x -= s.cx; y -= s.cy
        return (s.cx + x * s.c - y * s.s + s.dx, s.cy + x * s.s + y * s.c + s.dy)

    def rot(s, a):
        a = float(a or 0)
        return (a + s.deg) % 360

    def pts(s, txt):
        n = [float(v) for v in txt.replace(',', ' ').split()]
        out = []
        for i in range(0, len(n), 2):
            x, y = s.pt(n[i], n[i + 1]); out += [_fmt(x), _fmt(y)]
        return ' '.join(out)

    def path(s, d):
        toks = re.findall(r'[A-Za-z]|-?\d*\.?\d+(?:e-?\d+)?', d)
        out = []; i = 0; cmd = None
        while i < len(toks):
            t = toks[i]
            if re.match('[A-Za-z]', t):
                cmd = t; out.append(t); i += 1; continue
            if cmd in 'Aa':
                rx, ry, xr, la, sw, x, y = toks[i:i + 7]
                X, Y = s.pt(float(x), float(y))
                out += [rx, ry, xr, la, sw, _fmt(X), _fmt(Y)]; i += 7
            else:  # M L C Q S T  -> coordinate pairs
                X, Y = s.pt(float(toks[i]), float(toks[i + 1]))
                out += [_fmt(X), _fmt(Y)]; i += 2
        return ' '.join(out)


def xform_sub(sub, xf):
    f = sub.split('~'); t = f[0]
    if t == 'PAD':
        f[2], f[3] = map(_fmt, xf.pt(float(f[2]), float(f[3])))
        if f[10].strip(): f[10] = xf.pts(f[10])
        f[11] = _fmt(xf.rot(f[11]))
        if len(f) > 21 and ',' in f[-1]:
            x, y = map(float, f[-1].split(',')); X, Y = xf.pt(x, y); f[-1] = _fmt(X) + ',' + _fmt(Y)
        if len(f) > 14 and f[14].strip():  # slot hole points
            f[14] = xf.pts(f[14])
    elif t == 'TRACK':
        f[4] = xf.pts(f[4])
    elif t == 'ARC':
        f[4] = xf.path(f[4])
    elif t == 'CIRCLE':
        f[1], f[2] = map(_fmt, xf.pt(float(f[1]), float(f[2])))
    elif t == 'HOLE':
        f[1], f[2] = map(_fmt, xf.pt(float(f[1]), float(f[2])))
    elif t == 'VIA':
        f[1], f[2] = map(_fmt, xf.pt(float(f[1]), float(f[2])))
    elif t == 'SOLIDREGION':
        f[3] = xf.path(f[3])
    elif t == 'TEXT':
        f[2], f[3] = map(_fmt, xf.pt(float(f[2]), float(f[3])))
        f[5] = _fmt(xf.rot(f[5]))
        f[11] = xf.path(f[11])
    elif t == 'RECT':
        # axis aligned rect; only translation supported cleanly
        x, y = xf.pt(float(f[1]), float(f[2])); f[1], f[2] = _fmt(x), _fmt(y)
    elif t == 'SVGNODE':
        j = json.loads(sub[8:])
        a = j['attrs']
        if 'c_origin' in a:
            x, y = map(float, a['c_origin'].split(',')); X, Y = xf.pt(x, y); a['c_origin'] = _fmt(X) + ',' + _fmt(Y)
        if 'c_rotation' in a:
            r = a['c_rotation'].split(','); r[2] = _fmt((float(r[2]) + xf.deg) % 360); a['c_rotation'] = ','.join(r)
        def walk(n):
            at = n.get('attrs', {})
            if 'points' in at: at['points'] = xf.pts(at['points'])
            if 'd' in at: at['d'] = xf.path(at['d'])
            for ch in n.get('childNodes', []) or []: walk(ch)
        for ch in j.get('childNodes', []) or []: walk(ch)
        return 'SVGNODE~' + json.dumps(j, separators=(',', ':'), ensure_ascii=False)
    return '~'.join(f)


class Lib:
    def __init__(s, raw):
        s.parts = raw.split('#@$')
        s.head = s.parts[0].split('~')

    @property
    def ref(s):
        for sub in s.parts[1:]:
            f = sub.split('~')
            if f[0] == 'TEXT' and f[1] == 'P': return f[10]
        return ''

    @property
    def xy(s): return float(s.head[1]), float(s.head[2])

    @property
    def rot(s): return float(s.head[4] or 0)

    def attrs(s):
        a = s.head[3].split('`'); return dict(zip(a[0::2], a[1::2]))

    def pads(s):
        for i, sub in enumerate(s.parts[1:], 1):
            if sub.startswith('PAD~'): yield i, sub.split('~')

    def transform(s, xf):
        x, y = xf.pt(*s.xy); s.head[1], s.head[2] = _fmt(x), _fmt(y)
        s.head[4] = _fmt(xf.rot(s.head[4]))
        s.parts[1:] = [xform_sub(p, xf) for p in s.parts[1:]]

    def place(s, x, y, rot=None):
        """move origin to (x,y) [units]; optionally set absolute rotation"""
        ox, oy = s.xy
        d = 0 if rot is None else (rot - s.rot)
        s.transform(Xf(ox, oy, d, x - ox, y - oy))

    def set_net(s, num, net):
        for i, f in s.pads():
            if f[8] == num:
                f[7] = net; s.parts[i] = '~'.join(f)

    def set_ref(s, ref):
        for i, sub in enumerate(s.parts[1:], 1):
            f = sub.split('~')
            if f[0] == 'TEXT' and f[1] == 'P':
                f[10] = ref; f[11] = ''  # path regenerated by EasyEDA on open
                s.parts[i] = '~'.join(f)

    def set_value(s, val):
        for i, sub in enumerate(s.parts[1:], 1):
            f = sub.split('~')
            if f[0] == 'TEXT' and f[1] == 'N':
                f[10] = val; f[11] = ''
                s.parts[i] = '~'.join(f)

    def fresh_ids(s):
        def rep(m): return new_gid()
        s.head[6] = new_gid()
        out = []
        for sub in s.parts[1:]:
            if sub.startswith('SVGNODE~'):
                j = json.loads(sub[8:])
                def walk(n):
                    if 'gId' in n: n['gId'] = new_gid()
                    if 'attrs' in n and 'id' in n['attrs']: n['attrs']['id'] = n['gId'] if 'gId' in n else new_gid()
                    for ch in n.get('childNodes', []) or []: walk(ch)
                walk(j)
                out.append('SVGNODE~' + json.dumps(j, separators=(',', ':'), ensure_ascii=False))
            else:
                out.append(re.sub(r'gge[0-9a-f]+', rep, sub))
        s.parts[1:] = out

    def raw(s):
        return '#@$'.join(['~'.join(s.head)] + s.parts[1:])

    def pad_geoms(s):
        """yield (num, net, layer, shape, cx, cy, w, h, hole_r, poly_points) in units, axis aligned bbox"""
        for i, f in s.pads():
            cx, cy = float(f[2]), float(f[3])
            pts = [float(v) for v in f[10].split()] if f[10].strip() else []
            if f[1] not in ('RECT', 'POLYGON'): pts = []
            if pts:
                xs, ys = pts[0::2], pts[1::2]
                w, h = max(xs) - min(xs), max(ys) - min(ys)
            else:
                w, h = float(f[4]), float(f[5])
                if round(float(f[11] or 0)) % 180 == 90: w, h = h, w
            yield f[8], f[7], f[6], f[1], cx, cy, w, h, float(f[9] or 0), pts


class Pcb:
    def __init__(s, path):
        s.doc = json.load(open(path))

    def save(s, path):
        json.dump(s.doc, open(path, 'w'), ensure_ascii=False, indent=1)

    @property
    def shape(s): return s.doc['shape']

    def libs(s):
        for i, x in enumerate(s.shape):
            if x.startswith('LIB~'): yield i, Lib(x)

    def lib(s, ref):
        for i, l in s.libs():
            if l.ref == ref: return i, l
        raise KeyError(ref)

    def put(s, i, lib): s.shape[i] = lib.raw()

    def add(s, lib): s.shape.append(lib.raw())

    def remove(s, ref):
        i, _ = s.lib(ref); del s.shape[i]

    def update(s, ref, fn):
        i, l = s.lib(ref); fn(l); s.shape[i] = l.raw()

    def clone(s, template_ref, new_ref, value=None, attrs=None):
        _, l = s.lib(template_ref)
        n = Lib(l.raw()); n.fresh_ids(); n.set_ref(new_ref)
        if value is not None: n.set_value(value)
        if attrs:
            a = n.attrs(); a.update(attrs)
            n.head[3] = '`'.join(k + '`' + v for k, v in a.items()) + '`'
        for i, f in list(n.pads()):
            f[7] = ''; n.parts[i] = '~'.join(f)
        return n

    def netlist(s):
        nets = {}
        for _, l in s.libs():
            for i, f in l.pads():
                nets.setdefault(f[7], []).append(f'{l.ref}.{f[8]}')
        return nets
