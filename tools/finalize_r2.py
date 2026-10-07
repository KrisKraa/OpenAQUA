"""Finish the routed R2 board: pours, keep-outs, guard patch, stitching vias,
silkscreen labels, revision text. Writes the importable EasyEDA file.

  python3 tools/finalize_r2.py   (run with the venv python: needs numpy + scipy)
"""
import os, sys, json, math, re
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from scipy import ndimage
from pcbtool import Pcb, U, new_gid, _fmt, Xf
from build_r2_pcb import X0, Y0, OUT_DIR
import route_r2 as RR
import verify_pcb as V

ROOT = os.path.join(os.path.dirname(__file__), '..')
SRC = os.path.join(OUT_DIR, 'PCB_R2_routed_nopour.json')
DST = os.path.join(ROOT, 'hardware/main-controller/r2/PCB_OpenAQUA_R2.json')


def E(x, y): return (X0 + x / U, Y0 + y / U)


def path_of(poly):
    pts = [E(x, y) for x, y in poly]
    return 'M ' + ' L '.join('%s %s' % (_fmt(x), _fmt(y)) for x, y in pts) + ' Z'


def copper_area(template, layer, net, poly, clearance_mm):
    f = template.split('~')
    gid = new_gid()
    f[2] = layer; f[3] = net; f[4] = path_of(poly); f[5] = _fmt(clearance_mm / U)
    f[7] = gid; f[10] = '[]'; f[12] = gid
    return '~'.join(f)


def region(layer, net, poly, kind):
    return 'SOLIDREGION~%s~%s~%s~%s~%s~~~~0' % (layer, net, path_of(poly), kind, new_gid())


def move_text(p, text, x, y):
    """Move a free silkscreen TEXT (by its string) so its anchor lands at board mm (x,y)."""
    for i, s in enumerate(p.shape):
        f = s.split('~')
        if f[0] == 'TEXT' and f[10] == text:
            tx, ty = E(x, y)
            xf = Xf(0, 0, 0, tx - float(f[2]), ty - float(f[3]))
            p.shape[i] = '~'.join(f[:2] + [_fmt(tx), _fmt(ty)] + f[4:11] + [xf.path(f[11])] + f[12:])
            return True
    return False


def main():
    p = Pcb(SRC)
    tmpl = next(s for s in p.shape if s.startswith('COPPERAREA'))
    p.doc['shape'] = [s for s in p.shape if not s.startswith('COPPERAREA')]
    # board polygon (mm)
    R = V.Raster(p)
    board = R.outline
    # pours: bottom = solid GND plane, top = GND fill between tracks
    p.shape.append(copper_area(tmpl, '2', 'GND', board, 0.3))
    p.shape.append(copper_area(tmpl, '1', 'GND', board, 0.3))
    # antenna keep-out: no copper on either layer
    ax0, ay0, ax1, ay1 = RR.ANTENNA
    ant = [(ax0, -1), (ax1, -1), (ax1, ay1), (ax0, ay1)]
    for L in ('1', '2'):
        p.shape.append(region(L, '', ant, 'cutout'))
    # pH guard patch on the bottom layer (driven by the LMP91200 guard buffer)
    p.shape.append(region('2', 'PH_GUARD', RR.GUARD_PATCH, 'solid'))

    # stitching vias: where both pours exist with margin, on a 6 mm grid
    tmp = os.path.join(OUT_DIR, '_stitch_tmp.json')
    p.save(tmp)
    rep, shorts, viol, (layers, R2, nets) = V.verify(tmp)
    g = nets.index('GND') + 1
    both = (layers['1'] == g) & (layers['2'] == g)
    r = int(math.ceil((RR.VIA_D / 2 + 0.35) / V.RES))
    st = np.zeros((2 * r + 1, 2 * r + 1), bool); yy, xx = np.mgrid[-r:r + 1, -r:r + 1]; st[xx * xx + yy * yy <= r * r] = True
    safe = ndimage.binary_erosion(both, structure=st)
    added = 0
    vias = []
    for y in np.arange(2.5, 66, 3.0):
        for x in np.arange(2.5, 153, 3.0):
            # search a small neighbourhood for a safe spot
            best = None
            for dy in (0, -0.6, 0.6, -1.2, 1.2):
                for dx in (0, -0.6, 0.6, -1.2, 1.2):
                    cx, cy = x + dx, y + dy
                    i, j = int(cy / V.RES), int(cx / V.RES)
                    if 0 <= i < safe.shape[0] and 0 <= j < safe.shape[1] and safe[i, j]:
                        if all(math.hypot(cx - a, cy - b) > 2.0 for a, b in vias):
                            best = (cx, cy); break
                if best: break
            if best:
                vias.append(best)
    # keep density reasonable: every other point in calm areas is plenty
    for x, y in vias:
        p.shape.append(RR.via('GND', round(x, 2), round(y, 2)))
        added += 1
    os.remove(tmp)

    # silkscreen labels that followed their parts
    moves = {'DISPLAY': (47.0, 16.6), 'BUTTON': (93.0, 13.8), '20V': (31.0, 22.9), '5V': (31.0, 25.0), '3.3V': (31.0, 27.1)}
    for t, (x, y) in moves.items():
        move_text(p, t, x, y)
    for i, s in enumerate(p.shape):
        if s.startswith('TEXT') and '~OpenAQUA_R1~' in s:
            f = s.split('~'); f[10] = 'OpenAQUA_R2'; f[11] = ''
            p.shape[i] = '~'.join(f)
    p.save(DST)
    print('stitching vias:', added, '->', DST)


if __name__ == '__main__':
    main()
