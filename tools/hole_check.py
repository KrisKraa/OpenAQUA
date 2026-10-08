"""Hole-to-hole spacing check (vias, drilled pads, mounting holes). python3 tools/hole_check.py <pcb.json> [min_mm]"""
import sys, os, math
sys.path.insert(0, os.path.dirname(__file__))
from pcbtool import Pcb, U
from build_r2_pcb import X0, Y0


def holes(p):
    h = []
    for s in p.shape:
        f = s.split('~')
        if f[0] == 'VIA': h.append(((float(f[1]) - X0) * U, (float(f[2]) - Y0) * U, float(f[5]) * U, 'via ' + f[4]))
        elif f[0] == 'HOLE': h.append(((float(f[1]) - X0) * U, (float(f[2]) - Y0) * U, float(f[3]) * U, 'mounting hole'))
    for _, l in p.libs():
        for _, f in l.pads():
            if float(f[9] or 0) > 0:
                h.append(((float(f[2]) - X0) * U, (float(f[3]) - Y0) * U, float(f[9]) * U, '%s.%s' % (l.ref, f[8])))
    return h


if __name__ == '__main__':
    mn = float(sys.argv[2]) if len(sys.argv) > 2 else 0.25
    H = holes(Pcb(sys.argv[1]))
    bad = [(round(math.hypot(a[0] - b[0], a[1] - b[1]) - a[2] - b[2], 3), a[3], b[3], (round(a[0], 2), round(a[1], 2)))
           for i, a in enumerate(H) for b in H[i + 1:]
           if math.hypot(a[0] - b[0], a[1] - b[1]) - a[2] - b[2] < mn and a[3].split('.')[0] != b[3].split('.')[0] or
           (math.hypot(a[0] - b[0], a[1] - b[1]) - a[2] - b[2] < mn and a[3].startswith('via'))]
    print('hole-to-hole < %.2f mm: %d' % (mn, len(bad)))
    for x in sorted(bad): print(' ', x)
