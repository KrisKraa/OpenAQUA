"""Build the R2 PCB (EasyEDA Std JSON) from the 2026-10-08 original.

  python3 tools/build_r2_pcb.py            -> hardware/main-controller/r2/work/PCB_R2_placed.json

Steps: apply r2_changes (parts, values, nets), then placement from r2_placement.
Routing is a separate step (route_r2.py).
"""
import json, os, sys, copy
sys.path.insert(0, os.path.dirname(__file__))
from pcbtool import Pcb, Lib, U, new_gid, _fmt, Xf
import r2_changes as CH

ROOT = os.path.join(os.path.dirname(__file__), '..')
SRC = os.path.join(ROOT, 'hardware/main-controller/original/PCB_PCB_Aquacontrol_2026-10-08.json')
LCSC_DIR = os.environ.get('LCSC_CACHE', os.path.join(ROOT, 'tools/lcsc_cache'))
OUT_DIR = os.path.join(ROOT, 'hardware/main-controller/r2/work')

# board frame: top-left of outline in EasyEDA units
X0, Y0 = 4020.387, 3134.815


def lcsc(part):
    path = os.path.join(LCSC_DIR, part + '.json')
    if not os.path.exists(path):
        import subprocess
        os.makedirs(LCSC_DIR, exist_ok=True)
        url = 'https://easyeda.com/api/products/%s/components?version=6.5.54' % part
        subprocess.run(['curl', '-s', '-m', '30', '-o', path, url], check=True)
    return json.load(open(path))['result']


def lcsc_attrs(part):
    r = lcsc(part)
    cp = r['dataStr']['head'].get('c_para', {})
    return {k: cp[k] for k in ('Supplier', 'Supplier Part', 'Manufacturer', 'Manufacturer Part', 'JLCPCB Part Class') if k in cp}


def set_attrs(lib, attrs):
    a = lib.attrs(); a.update(attrs)
    lib.head[3] = '`'.join(k + '`' + v for k, v in a.items()) + '`'


def footprint_from_lcsc(part, ref, value):
    r = lcsc(part)
    pk = r['packageDetail']['dataStr']
    h = pk['head']
    attrs = dict(h.get('c_para', {}))
    attrs.pop('pre', None)
    attrs.update(lcsc_attrs(part))
    head = ['LIB', str(h['x']), str(h['y']),
            '`'.join(k + '`' + str(v) for k, v in attrs.items()) + '`',
            '0', '', new_gid(), '1', h.get('uuid', ''), str(h.get('utime', '')), '0', '', 'yes', '', '']
    # header field 7 must be '1' (as in every footprint EasyEDA writes): with '0' the
    # editor drops/half-loads the footprint and its pads are ignored by copper pours
    shapes = []
    for s in pk['shape']:
        if s.startswith('TEXT~P~'):
            f = s.split('~'); f[10] = ref; f[11] = ''; s = '~'.join(f)
        elif s.startswith('TEXT~N~'):
            f = s.split('~'); f[10] = value; f[11] = ''; s = '~'.join(f)
        shapes.append(s)
    lib = Lib('#@$'.join(['~'.join(head)] + shapes))
    if not any(s.startswith('TEXT~P~') for s in shapes):
        lib.parts.append('TEXT~P~%s~%s~0.6~0~0~3~~4.5~%s~~~%s~~0' % (h['x'], float(h['y']) - 8, ref, new_gid()))
    lib.fresh_ids()
    return lib


def apply_changes(p):
    for ref in CH.REMOVE:
        p.remove(ref)
    for ref, (part, value, tmpl) in CH.SWAP.items():
        i, old = p.lib(ref)
        if tmpl and tmpl.startswith('lcsc:'):
            new = footprint_from_lcsc(tmpl[5:], ref, value)
            new.place(*old.xy, old.rot)
            lib = new
        elif tmpl:
            new = p.clone(tmpl, ref, value)
            nets = {f[8]: f[7] for _, f in old.pads()}
            for j, f in list(new.pads()):
                f[7] = nets.get(f[8], ''); new.parts[j] = '~'.join(f)
            new.place(*old.xy, old.rot)
            lib = new
        else:
            lib = old; lib.set_value(value)
        set_attrs(lib, lcsc_attrs(part))
        p.shape[i] = lib.raw()
    for ref, (tmpl, part, value) in CH.NEW.items():
        if tmpl.startswith('lcsc:'):
            lib = footprint_from_lcsc(tmpl[5:], ref, value)
        else:
            lib = p.clone(tmpl, ref, value)
            set_attrs(lib, lcsc_attrs(part))
        p.add(lib)
    # nets
    byref = {}
    for (ref, pin), net in CH.NETS.items():
        byref.setdefault(ref, {})[pin] = net
    for ref, pins in byref.items():
        i, lib = p.lib(ref)
        have = {f[8] for _, f in lib.pads()}
        missing = set(pins) - have
        if missing: raise SystemExit('%s has no pad(s) %s' % (ref, missing))
        for pin, net in pins.items(): lib.set_net(pin, net)
        p.shape[i] = lib.raw()
    # every pad of a new part must have a net
    for ref in CH.NEW:
        _, lib = p.lib(ref)
        for _, f in lib.pads():
            if not f[7]: raise SystemExit('new part %s pad %s has no net' % (ref, f[8]))


def bbox(lib):
    import re
    xs, ys = [], []
    for sub in lib.parts[1:]:
        f = sub.split('~')
        if (f[0] == 'SOLIDREGION' and f[1] == '99') or (f[0] == 'TRACK' and f[2] == '3'):
            src = f[3] if f[0] == 'SOLIDREGION' else f[4]
            n = [float(v) for v in re.findall(r'-?\d+\.?\d*', src)]
            xs += n[0::2]; ys += n[1::2]
    for g in lib.pad_geoms():
        xs += [g[4] - g[6] / 2, g[4] + g[6] / 2]; ys += [g[5] - g[7] / 2, g[5] + g[7] / 2]
    return min(xs), min(ys), max(xs), max(ys)


def place_center(p, ref, bx, by, rot):
    """Place so the footprint's bbox centre lands on board coords (bx,by) mm, y down."""
    i, lib = p.lib(ref)
    lib.place(*lib.xy, rot)
    x0, y0, x1, y1 = bbox(lib)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    tx, ty = X0 + bx / U, Y0 + by / U
    ox, oy = lib.xy
    lib.place(ox + (tx - cx), oy + (ty - cy))
    p.shape[i] = lib.raw()


def apply_placement(p, placement):
    for ref, v in placement.items():
        place_center(p, ref, *v)


def strip_routing(p):
    """Drop old copper (none routed except outline) and the stale pour fill."""
    keep = []
    for s in p.shape:
        f = s.split('~')
        if f[0] == 'TRACK' and f[2] in ('1', '2'): continue
        if f[0] == 'VIA': continue
        keep.append(s)
    p.doc['shape'] = keep


def build(placement=None):
    p = Pcb(SRC)
    strip_routing(p)
    apply_changes(p)
    if placement:
        apply_placement(p, placement)
    return p


if __name__ == '__main__':
    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        from r2_placement import PLACEMENT
    except ImportError:
        PLACEMENT = None
    p = build(PLACEMENT)
    out = os.path.join(OUT_DIR, 'PCB_R2_placed.json')
    p.save(out)
    print('wrote', out)
