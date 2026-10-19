"""Final checks on the finished R2 PCB (run with numpy + scipy):

  connectivity, shorts, clearance (verify_pcb), copper near the board edge,
  copper inside the antenna keep-out, and a few statistics.

  python3 tools/check_r2_final.py [pcb.json]
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from scipy import ndimage
import verify_pcb as V
from pcbtool import Pcb, U
from route_r2 import ANTENNA

EDGE_PARTS = ('USBC1', 'USBC2', 'USBC3', 'LED4', 'LED5', 'LED6')  # placed at the edge on purpose (case openings)


def main(path):
    rep, shorts, viol, (layers, R, nets) = V.verify(path)
    p = Pcb(path)
    its = V.items(p, R)
    e = int(round(0.3 / V.RES))
    inner = ndimage.binary_erosion(R.board, structure=np.ones((2 * e + 1, 2 * e + 1), bool))
    ys, xs = np.mgrid[0:R.H, 0:R.W]
    ant = ((xs + .5) * V.RES > ANTENNA[0]) & ((xs + .5) * V.RES < ANTENNA[2]) & ((ys + .5) * V.RES < ANTENNA[3])
    edge_hits, ant_hits = [], []
    n_via = n_track_top = n_track_bot = 0
    len_top = len_bot = 0.0
    for net, lays, kind, g, ref in its:
        if ref == 'via': n_via += 1
        if ref == 'track':
            (a, b, w) = g
            L = float(np.hypot(b[0] - a[0], b[1] - a[1]))
            if lays == ('1',): n_track_top += 1; len_top += L
            else: n_track_bot += 1; len_bot += L
        if ref.split('.')[0] in EDGE_PARTS: continue
        sl, m = V.draw(R, kind, g)
        if (m & ~inner[sl]).any(): edge_hits.append((ref, net))
        if ref.split('.')[0] != 'U15' and (m & ant[sl]).any(): ant_hits.append((ref, net))
    import exact_drc, hole_check, math
    exact = exact_drc.check(path, 0.15)
    H = hole_check.holes(p)
    close = [(a[3], b[3]) for i, a in enumerate(H) for b in H[i + 1:]
             if math.hypot(a[0] - b[0], a[1] - b[1]) - a[2] - b[2] < 0.25 and (a[3].startswith('via') or a[3].split('.')[0] != b[3].split('.')[0])]
    print('exact clearance < 0.15:', len(exact), exact[:5])
    print('hole-to-hole < 0.25   :', len(close), close[:5])
    ok = not rep and not shorts and not viol and not edge_hits and not ant_hits and not exact and not close
    print('unconnected nets      :', len(rep), list(rep)[:10])
    print('shorts                :', len(shorts))
    print('clearance < 0.20 mm   :', len(viol))
    print('copper < 0.3 mm to edge:', len(edge_hits), edge_hits[:10])
    print('copper in antenna area:', len(ant_hits), ant_hits[:10])
    print('vias: %d   top track %.0f mm (%d seg)   bottom track %.0f mm (%d seg)' % (n_via, len_top, n_track_top, len_bot, n_track_bot))
    print('RESULT:', 'PASS' if ok else 'FAIL')
    return ok


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '../hardware/main-controller/r2/PCB_OpenAQUA_R2.json')
    sys.exit(0 if main(path) else 1)
