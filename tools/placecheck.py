"""Placement checks: footprint bbox overlaps, outline, keep-outs (board mm, y down)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from build_r2_pcb import *
from pcbrender import ZONES

HOLES = [(5, 5), (149, 5), (15, 55), (139, 63)]
ANTENNA = (57, 0, 83, 7.5)

def boxes(p, margin=0.15):
    out = {}
    for i, l in p.libs():
        x0, y0, x1, y1 = bbox(l)
        out[l.ref] = ((x0 - X0) * U - margin, (y0 - Y0) * U - margin, (x1 - X0) * U + margin, (y1 - Y0) * U + margin)
    return out

def check(p):
    b = boxes(p); refs = sorted(b); probs = []
    for i, a in enumerate(refs):
        A = b[a]
        for c in refs[i + 1:]:
            C = b[c]
            if A[0] < C[2] and C[0] < A[2] and A[1] < C[3] and C[1] < A[3]:
                probs.append('overlap %s %s' % (a, c))
        if A[0] < 0.3 or A[1] < 0.0 or A[2] > 153.7 or A[3] > 66.7:
            if a not in ('USBC1', 'USBC2', 'USBC3', 'U15'): probs.append('edge %s %s' % (a, [round(v, 1) for v in A]))
        # chamfer: line (3.07,53.28)-(35.03,66.61); point below-left of it is off board
        for (x, y) in ((A[0], A[3]), (A[2], A[3])):
            if x < 35.03 and y > 53.28 + (x - 3.07) * (66.61 - 53.28) / (35.03 - 3.07) - 0.5:
                probs.append('chamfer %s' % a)
        for hx, hy in HOLES:
            if A[0] - 3.2 < hx < A[2] + 3.2 and A[1] - 3.2 < hy < A[3] + 3.2:
                probs.append('hole %s (%s,%s)' % (a, hx, hy))
        if a != 'U15' and A[0] < ANTENNA[2] and ANTENNA[0] < A[2] and A[1] < ANTENNA[3]:
            probs.append('antenna %s' % a)
    return probs

if __name__ == '__main__':
    from r2_placement import PLACEMENT
    p = build(PLACEMENT)
    pr = check(p)
    print('\n'.join(pr) if pr else 'placement OK')
