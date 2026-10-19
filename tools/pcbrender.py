"""Render an EasyEDA Std PCB JSON to SVG (review aid). Coordinates in mm, board-local."""
import sys, json, html
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from pcbtool import *

COL = {'1': '#c83232', '2': '#3264c8', '11': '#b0a030', '21': '#999966', '22': '#008000'}

def render(path, out, overlays=None, nets=True, title='', rats=False, zones=None):
    p = Pcb(path)
    sh = p.shape
    xs = []; ys = []
    outline = []
    for x in sh:
        f = x.split('~')
        if f[0] in ('TRACK',) and f[2] == '10':
            n = [float(v) for v in f[4].split()]; outline.append(n); xs += n[0::2]; ys += n[1::2]
    x0, y0 = min(xs), min(ys)
    def T(x, y): return ((x - x0) * U, (y - y0) * U)
    W = (max(xs) - x0) * U; H = (max(ys) - y0) * U
    el = []
    def poly(pts, stroke, w=0.15, fill='none', op=1):
        el.append(f'<polyline points="{" ".join("%.3f,%.3f" % T(pts[i], pts[i+1]) for i in range(0, len(pts), 2))}" stroke="{stroke}" stroke-width="{w}" fill="{fill}" opacity="{op}" stroke-linecap="round" stroke-linejoin="round"/>')
    for x in sh:
        f = x.split('~')
        if f[0] == 'TRACK':
            n = [float(v) for v in f[4].split()]
            if f[2] == '10': poly(n, '#d0d', 0.3)
            elif f[2] in COL: poly(n, COL[f[2]], float(f[1]) * U, op=0.85)
        elif f[0] == 'ARC' and f[2] == '10':
            el.append(f'<path d="{Xf(x0,y0,0,-x0,-y0).path(f[4])}" transform="scale({U})" stroke="#d0d" stroke-width="{0.3/U}" fill="none"/>')
        elif f[0] == 'VIA':
            cx, cy = T(float(f[1]), float(f[2])); el.append(f'<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{float(f[3])*U/2:.3f}" fill="#b0a030"/><circle cx="{cx:.3f}" cy="{cy:.3f}" r="{float(f[5])*U:.3f}" fill="#222"/>')
        elif f[0] == 'HOLE':
            cx, cy = T(float(f[1]), float(f[2])); el.append(f'<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{float(f[3])*U:.3f}" fill="#fff" stroke="#888" stroke-width="0.1"/>')
    for i, l in p.libs():
        for sub in l.parts[1:]:
            f = sub.split('~')
            if f[0] == 'TRACK' and f[2] == '3':
                poly([float(v) for v in f[4].split()], '#aa9', 0.12)
        for num, net, lay, shp, cx, cy, w, h, hr, pts in l.pad_geoms():
            c = COL.get(lay, '#888')
            X, Y = T(cx - w / 2, cy - h / 2)
            if shp == 'ELLIPSE' or (shp == 'OVAL' and abs(w-h) < 0.01):
                el.append(f'<ellipse cx="{X+w*U/2:.3f}" cy="{Y+h*U/2:.3f}" rx="{w*U/2:.3f}" ry="{h*U/2:.3f}" fill="{c}" opacity="0.8"/>')
            else:
                el.append(f'<rect x="{X:.3f}" y="{Y:.3f}" width="{w*U:.3f}" height="{h*U:.3f}" fill="{c}" opacity="0.8" rx="{min(w,h)*U*0.15 if shp=="OVAL" else 0:.3f}"/>')
            if hr: 
                X, Y = T(cx, cy); el.append(f'<circle cx="{X:.3f}" cy="{Y:.3f}" r="{hr*U:.3f}" fill="#222"/>')
        X, Y = T(*l.xy)
        el.append(f'<text x="{X:.2f}" y="{Y:.2f}" font-size="1.3" fill="#000" text-anchor="middle" font-family="Arial" font-weight="bold" opacity="0.75">{html.escape(l.ref)}</text>')
    for z in zones or []:  # (label, x0,y0,x1,y1 mm board coords, colour) or circle (label,cx,cy,r,colour)
        if len(z) == 6:
            lab, a, b, c, d, col = z
            el.append(f'<rect x="{a}" y="{b}" width="{c-a}" height="{d-b}" fill="{col}" opacity="0.12" stroke="{col}" stroke-width="0.2" stroke-dasharray="1,0.6"/><text x="{a+0.5}" y="{b+2}" font-size="1.6" fill="{col}" font-family="Arial">{html.escape(lab)}</text>')
        else:
            lab, cx, cy, r, col = z
            el.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{col}" opacity="0.12" stroke="{col}" stroke-width="0.2" stroke-dasharray="1,0.6"/><text x="{cx-r+0.5}" y="{cy}" font-size="1.6" fill="{col}" font-family="Arial">{html.escape(lab)}</text>')
    if rats:
        pads = {}
        for i, l in p.libs():
            for num, net, lay, shp, cx, cy, w, h, hr, pts in l.pad_geoms():
                if net and net != 'GND': pads.setdefault(net, []).append(T(cx, cy))
        import math
        for net, pts in pads.items():
            if len(pts) < 2: continue
            inn = [pts[0]]; rest = pts[1:]
            while rest:
                best = min(((math.dist(a, b), a, b) for a in inn for b in rest))
                _, a, b = best
                col = '#e08000' if net in ('+20V_BUS', '+5V_MAIN', '+3V3', 'USB_VBUS_RAW') else '#5050ff'
                el.append(f'<line x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" y2="{b[1]:.2f}" stroke="{col}" stroke-width="0.12" opacity="0.7"/>')
                inn.append(b); rest.remove(b)
    for o in overlays or []:
        el.append(o(T))
    # square canvas so macOS quicklook thumbnails don't crop it
    S = max(W + 8, H + 10)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -6 {S:.2f} {S:.2f}" width="{S*12:.0f}" height="{S*12:.0f}">'
           f'<rect x="-4" y="-6" width="{S}" height="{S}" fill="#f4f4ee"/>'
           f'<text x="0" y="-2.5" font-size="2.5" font-family="Arial">{html.escape(title)}</text>' + ''.join(el) + '</svg>')
    open(out, 'w').write(svg)

# mechanical context (board mm, y down), derived from the enclosure STEP
ZONES = [
    ('display above (11 mm)', 19, 17, 100, 67, '#008080'),
    ('antenna keep-out', 57, 0, 83, 7.5, '#d00000'),
    ('button above', 117, 31.5, 8.1, '#a000a0'),
]

if __name__ == '__main__':
    render(sys.argv[1], sys.argv[2], title=sys.argv[3] if len(sys.argv) > 3 else '', rats='--rats' in sys.argv, zones=ZONES if '--zones' in sys.argv else None)
