"""Place silkscreen reference designators where they are readable:
horizontal, next to their own part, never on top of a part body/pad, another
label, a hole or the board edge. Value texts stay hidden.

Text metrics (EasyEDA stroke font, measured): height ~0.96*fs, advance ~0.62*fs per
character, anchor = left/baseline. fs in EasyEDA units (1 unit = 0.254 mm).
"""
import os, sys, re
sys.path.insert(0, os.path.dirname(__file__))
from pcbtool import U, _fmt
from build_r2_pcb import bbox, X0, Y0

FS = 4.5        # 1.14 mm text (JLCPCB minimum ~1 mm)
FS_SMALL = 3.2  # 0.81 mm fallback (JLCPCB minimum legible ~0.8 mm)
GAP = 0.25      # mm between label and part outline
EDGE = 0.6      # mm from board edge

# free-standing silk labels that are connector/LED captions: keep them, but move if covered
FREE_LABELS = ('TEMP', 'TDS', 'LEAK1', 'LEAK2', 'PH', 'CAN1', 'CAN2', 'OTG', 'DISPLAY', 'BUTTON', '20V', '5V', '3.3V')


def text_box(x, y, s, fs, rot=0):
    """mm box of a text with EasyEDA anchor at (x, y) mm. rot 0: left/baseline, reads
    left-to-right above the anchor. rot 270: reads top-to-bottom, right of the anchor."""
    w = 0.62 * fs * U * len(s); h = 0.96 * fs * U
    if rot == 270: return (x, y, x + h, y + w)
    return (x, y - h, x + w, y)


def overlap(a, b, m=0.0):
    return a[0] < b[2] + m and b[0] < a[2] + m and a[1] < b[3] + m and b[1] < a[3] + m


def inside_board(b, poly_ok):
    return poly_ok(b[0], b[1]) and poly_ok(b[2], b[1]) and poly_ok(b[0], b[3]) and poly_ok(b[2], b[3])


def place_labels(p, holes, board_ok):
    parts = []
    for i, l in p.libs():
        x0, y0, x1, y1 = bbox(l)
        parts.append((i, l, ((x0 - X0) * U, (y0 - Y0) * U, (x1 - X0) * U, (y1 - Y0) * U)))
    obstacles = [b for _, _, b in parts]
    obstacles += [(hx - r - 0.3, hy - r - 0.3, hx + r + 0.3, hy + r + 0.3) for hx, hy, r in holes]
    placed = []
    failed = []
    # most constrained parts first: count spots that are free of part bodies alone
    def n_free(b, ref):
        n = 0
        for fs in (FS, FS_SMALL):
            w = 0.62 * fs * U * len(ref); h = 0.96 * fs * U
            cx = (b[0] + b[2]) / 2; cy = (b[1] + b[3]) / 2
            for g in (GAP, GAP + 0.4, GAP + 0.9, GAP + 1.5):
                for tb in (text_box(cx - w / 2, b[1] - g, ref, fs), text_box(cx - w / 2, b[3] + g + h, ref, fs),
                           text_box(b[2] + g, cy + h / 2, ref, fs), text_box(b[0] - g - w, cy + h / 2, ref, fs),
                           text_box(b[2] + g, cy - w / 2, ref, fs, 270), text_box(b[0] - g - h, cy - w / 2, ref, fs, 270)):
                    if inside_board(tb, board_ok) and not any(overlap(tb, o, 0.05) for o in obstacles): n += 1
        return n
    order = sorted(parts, key=lambda t: n_free(t[2], t[1].ref))
    new_text = {}
    for i, l, b in order:
        ref = l.ref
        if not ref: continue
        best = None
        for fs in (FS, FS_SMALL):
            w = 0.62 * fs * U * len(ref); h = 0.96 * fs * U
            cx = (b[0] + b[2]) / 2; cy = (b[1] + b[3]) / 2
            cands = []
            for extra in (0.0, 0.4, 0.9, 1.5, 2.0, 2.5):
                g = GAP + extra
                cands += [
                    (cx - w / 2, b[1] - g),               # above, centred
                    (cx - w / 2, b[3] + g + h),           # below, centred
                    (b[2] + g, cy + h / 2),               # right, middle
                    (b[0] - g - w, cy + h / 2),           # left, middle
                    (b[0], b[1] - g), (b[2] - w, b[1] - g),          # above, left/right aligned
                    (b[0], b[3] + g + h), (b[2] - w, b[3] + g + h),  # below, left/right aligned
                ]
            cands = [(x_, y_, 0) for x_, y_ in cands]
            for extra in (0.0, 0.4, 0.9, 1.5):   # vertical fallback, beside the part
                g = GAP + extra
                cands += [(b[2] + g, cy - w / 2, 270), (b[0] - g - h, cy - w / 2, 270),
                          (cx - h / 2, b[1] - g - w, 270), (cx - h / 2, b[3] + g, 270)]
            for tx, ty, rot in cands:
                tb = text_box(tx, ty, ref, fs, rot)
                if not inside_board(tb, board_ok): continue
                if any(overlap(tb, o, 0.05) for o in obstacles): continue
                if any(overlap(tb, o, 0.15) for o in placed): continue
                best = (tx, ty, fs, tb, rot); break
            if best: break
        if not best:
            failed.append(ref); continue
        placed.append(best[3])
        new_text[i] = (best[0], best[1], best[2], best[4])
    # rewrite the prefix TEXT of each part
    for i, (tx, ty, fs, rot) in new_text.items():
        parts_ = p.shape[i].split('#@$')
        for k, sub in enumerate(parts_):
            f = sub.split('~')
            if f[0] == 'TEXT' and f[1] == 'P':
                f[2] = _fmt(X0 + tx / U); f[3] = _fmt(Y0 + ty / U)
                f[5] = str(rot); f[6] = '0'; f[7] = '3'; f[9] = _fmt(fs); f[11] = ''
                if len(f) > 12: f[12] = ''          # display: visible
                parts_[k] = '~'.join(f)
            elif f[0] == 'TEXT' and f[1] == 'N':
                if len(f) > 12: f[12] = 'none'      # value text hidden
                parts_[k] = '~'.join(f)
        p.shape[i] = '#@$'.join(parts_)
    return placed, obstacles, failed


def fix_free_labels(p, placed, obstacles, board_ok):
    """Move free-standing captions that sit on a part to the nearest clear spot."""
    moved = []
    for i, s in enumerate(p.shape):
        f = s.split('~')
        if f[0] != 'TEXT' or f[7] != '3': continue
        txt = f[10]
        fs = float(f[9]); x = (float(f[2]) - X0) * U; y = (float(f[3]) - Y0) * U
        tb = text_box(x, y, txt, fs)
        if not any(overlap(tb, o, 0.1) for o in obstacles) and not any(overlap(tb, o, 0.1) for o in placed):
            placed.append(tb); continue
        done = False
        for fs2 in (fs, FS):
            for r, rot in [(k * 0.5, 0) for k in range(1, 25)] + [(k * 0.5, 270) for k in range(0, 25)]:
                for dx, dy in ((0, -r), (0, r), (r, 0), (-r, 0), (r, -r), (-r, -r), (r, r), (-r, r)):
                    nb = text_box(x + dx, y + dy, txt, fs2, rot)
                    if not inside_board(nb, board_ok): continue
                    if any(overlap(nb, o, 0.1) for o in obstacles) or any(overlap(nb, o, 0.2) for o in placed): continue
                    f[2] = _fmt(X0 + (x + dx) / U); f[3] = _fmt(Y0 + (y + dy) / U); f[5] = str(rot); f[9] = _fmt(fs2); f[11] = ''
                    p.shape[i] = '~'.join(f); placed.append(nb); moved.append(txt); done = True
                    break
                if done: break
            if done: break
        if not done: moved.append(txt + ' (no spot)')
    return moved


def place_logo(p, placed, obstacles, board_ok):
    """Move (and if needed shrink) the silkscreen logo SVGNODE to a clear area."""
    import json
    for i, s in enumerate(p.shape):
        if not s.startswith('SVGNODE'): continue
        j = json.loads(s[8:])
        d = j['attrs'].get('d', '')
        if not d or j['attrs'].get('layerid') != '3': continue
        n = [float(v) for v in re.findall(r'-?\d+\.?\d*', d)]
        xs, ys = n[0::2], n[1::2]
        b = ((min(xs) - X0) * U, (min(ys) - Y0) * U, (max(xs) - X0) * U, (max(ys) - Y0) * U)
        w0, h0 = b[2] - b[0], b[3] - b[1]
        best = None
        for sc in (1.0, 0.85, 0.7, 0.6, 0.5):
            w, h = w0 * sc, h0 * sc
            cands = []
            for y in [k * 0.5 for k in range(0, 135)]:
                for x in [k * 0.5 for k in range(0, 309)]:
                    cands.append((abs(x - b[0]) + abs(y - b[1]), x, y))
            cands.sort()
            for _, x, y in cands:
                nb = (x, y, x + w, y + h)
                if not inside_board(nb, board_ok): continue
                if any(overlap(nb, o, 0.3) for o in obstacles) or any(overlap(nb, o, 0.3) for o in placed): continue
                best = (sc, x, y, nb); break
            if best: break
        if not best: return 'logo: no spot'
        sc, x, y, nb = best
        ox, oy = min(xs), min(ys)
        tx, ty = X0 + x / U, Y0 + y / U
        def tr(m):
            return '%s %s' % (_fmt(tx + (float(m.group(1)) - ox) * sc), _fmt(ty + (float(m.group(2)) - oy) * sc))
        j['attrs']['d'] = re.sub(r'(-?\d+\.?\d*)[ ,]+(-?\d+\.?\d*)', tr, d)
        p.shape[i] = 'SVGNODE~' + json.dumps(j, separators=(',', ':'), ensure_ascii=False)
        placed.append(nb)
        return 'logo: scale %.2f at (%.1f, %.1f) mm' % (sc, x, y)
    return 'logo: none'
