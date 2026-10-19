"""Copper-only, compressed copy of a PCB JSON for loading into the EasyEDA web editor to run its DRC.
Writes base64(gzip(json)) chunks to <outdir>/chunk_N.txt."""
import json, gzip, base64, sys, os
src, outdir = sys.argv[1], sys.argv[2]
d = json.load(open(src))
out = []
for s in d['shape']:
    if s.startswith('LIB'):
        parts = s.split('#@$'); keep = [parts[0]]
        for sub in parts[1:]:
            f = sub.split('~')
            if f[0] in ('PAD', 'HOLE'): keep.append(sub)
            elif f[0] == 'TEXT' and f[1] == 'P': f[11] = ''; keep.append('~'.join(f))
        s = '#@$'.join(keep)
    elif s.startswith('TEXT') or s.startswith('SVGNODE'):
        continue
    out.append(s)
m = {k: d[k] for k in ('head', 'canvas', 'DRCRULE') if k in d}; m['shape'] = out
b = base64.b64encode(gzip.compress(json.dumps(m, ensure_ascii=False, separators=(',', ':')).encode(), 9)).decode()
os.makedirs(outdir, exist_ok=True)
n = 45000
for i in range(0, len(b), n):
    open(os.path.join(outdir, 'chunk_%d.txt' % (i // n)), 'w').write(b[i:i + n])
print(len(b), 'bytes in', (len(b) + n - 1) // n, 'chunks')
