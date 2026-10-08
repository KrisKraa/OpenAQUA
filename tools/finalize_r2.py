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
    if len(f) > 18: f[18] = _fmt(0.3 / U)   # thermal spoke width 0.3 mm (was 0 in the template)
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


# Hand-finished links the autorouter left open (checked by verify_pcb afterwards)
POST = []        # hand links live in route_r2.HAND (routed around by Freerouting)
POST_VIAS = []


def main():
    p = Pcb(SRC)
    for net, lay, w, pts in POST:
        p.shape.append(RR.track(net, lay, w, pts))
    for net, x, y in POST_VIAS:
        p.shape.append(RR.via(net, x, y))
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
    # where a via may go: bottom plane present, and on top nothing but (potential) GND pour,
    # so isolated top islands get tied down instead of being removed
    def free(L):
        other = (layers[L] > 0) & (layers[L] != g)
        cl = int(math.ceil(0.3 / V.RES)); s2 = np.zeros((2 * cl + 1, 2 * cl + 1), bool)
        yy2, xx2 = np.mgrid[-cl:cl + 1, -cl:cl + 1]; s2[xx2 * xx2 + yy2 * yy2 <= cl * cl] = True
        e = int(math.ceil(0.6 / V.RES))
        inner = ndimage.binary_erosion(R2.board, structure=np.ones((2 * e + 1, 2 * e + 1), bool))
        return ~ndimage.binary_dilation(other, structure=s2) & inner
    ant_m = np.zeros_like(R2.board)
    a0, b0, a1, b1 = RR.ANTENNA
    ant_m[:int(b1 / V.RES) + 12, int(a0 / V.RES) - 12:int(a1 / V.RES) + 12] = True
    both = (layers['2'] == g) & free('1') & free('2') & ~ant_m
    r = int(math.ceil((RR.VIA_D / 2 + 0.05) / V.RES))
    st = np.zeros((2 * r + 1, 2 * r + 1), bool); yy, xx = np.mgrid[-r:r + 1, -r:r + 1]; st[xx * xx + yy * yy <= r * r] = True
    safe = ndimage.binary_erosion(both, structure=st)
    added = 0
    # existing drill holes (vias, through-hole pads, mounting holes): keep >= 0.3 mm hole-to-hole
    holes = []
    for s in p.shape:
        f = s.split('~')
        if f[0] == 'VIA': holes.append(((float(f[1]) - X0) * U, (float(f[2]) - Y0) * U, float(f[5]) * U))
        elif f[0] == 'HOLE': holes.append(((float(f[1]) - X0) * U, (float(f[2]) - Y0) * U, float(f[3]) * U))
    for _, l in p.libs():
        for _, f in l.pads():
            if float(f[9] or 0) > 0:
                holes.append(((float(f[2]) - X0) * U, (float(f[3]) - Y0) * U, float(f[9]) * U + (float(f[13] or 0) * U / 2)))
    def hole_ok(x, y):
        return all(math.hypot(x - hx, y - hy) >= hr + RR.VIA_HOLE / 2 + 0.3 for hx, hy, hr in holes)
    vias = []
    for y in np.arange(2.5, 66, 5.0):
        for x in np.arange(2.5, 153, 5.0):
            # search a small neighbourhood for a safe spot
            best = None
            for dy in (0, -0.6, 0.6, -1.2, 1.2):
                for dx in (0, -0.6, 0.6, -1.2, 1.2):
                    cx, cy = x + dx, y + dy
                    i, j = int(cy / V.RES), int(cx / V.RES)
                    if 0 <= i < safe.shape[0] and 0 <= j < safe.shape[1] and safe[i, j]:
                        if all(math.hypot(cx - a, cy - b) > 3.5 for a, b in vias) and hole_ok(cx, cy):
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
    # silkscreen: readable reference designators next to their parts
    import silk_r2
    e = int(math.ceil(silk_r2.EDGE / V.RES))
    inner_m = ndimage.binary_erosion(R2.board, structure=np.ones((2 * e + 1, 2 * e + 1), bool))
    def board_ok(x, y):
        i, j = int(y / V.RES), int(x / V.RES)
        return 0 <= i < inner_m.shape[0] and 0 <= j < inner_m.shape[1] and inner_m[i, j]
    hl = [(hx, hy, hr) for hx, hy, hr in holes]
    for _, l in p.libs():
        for sub in l.parts[1:]:
            f = sub.split('~')
            if f[0] == 'HOLE': hl.append(((float(f[1]) - X0) * U, (float(f[2]) - Y0) * U, float(f[3]) * U))
    placed, obst, failed = silk_r2.place_labels(p, hl, board_ok)
    logo = silk_r2.place_logo(p, placed, obst, board_ok)
    moved = silk_r2.fix_free_labels(p, placed, obst, board_ok)
    print(logo)
    print('silk: %d labels placed, no spot for %s; captions moved: %s' % (len(placed), failed, moved))
    # manufacturing normalisation: JLCPCB 2-layer limits (min track 0.127 mm, standard via 0.6/0.3)
    for i, s in enumerate(p.shape):
        f = s.split('~')
        if f[0] == 'TRACK' and f[2] in ('1', '2') and float(f[1]) * U < 0.15:
            f[1] = _fmt(0.15 / U); p.shape[i] = '~'.join(f)
        elif f[0] == 'VIA' and float(f[3]) * U < 0.6:
            f[3] = _fmt(0.6 / U); f[5] = _fmt(0.15 / U); p.shape[i] = '~'.join(f)
    # design rules matching how the board was routed (replaces the original 24v/GND sets)
    mm = lambda v: round(v / U, 4)
    p.doc['DRCRULE'] = {
        'Default': {'trackWidth': mm(0.15), 'clearance': mm(0.15), 'viaHoleDiameter': mm(0.6), 'viaHoleD': mm(0.3)},
        'isRealtime': True, 'isDrcOnRoutingOrPlaceVia': False, 'checkObjectToCopperarea': True, 'showDRCRangeLine': True,
    }
    # every footprint header needs field 7 = '1' for EasyEDA to load it fully
    for i, s in enumerate(p.shape):
        if s.startswith('LIB~'):
            parts_ = s.split('#@$'); h = parts_[0].split('~')
            if h[7] != '1': h[7] = '1'; parts_[0] = '~'.join(h); p.shape[i] = '#@$'.join(parts_)
    p.save(DST)
    print('stitching vias:', added, '->', DST)


if __name__ == '__main__':
    main()
