"""R2 BOM: swap parts to JLCPCB Basic / in-stock equivalents (same value, package and
footprint - attributes only, no layout change). Applied to both the PCB and schematic.

  python3 tools/bom_r2.py <pcb.json|sch.json> [...]
"""
import json, os, sys

HERE = os.path.dirname(__file__)

# new part -> (Manufacturer, Manufacturer Part, JLCPCB class) ; used when the LCSC cache has no entry
PARTS = {
    'C14663': ('YAGEO', 'CC0603KRX7R9BB104', 'Basic Part'),          # 100nF 50V X7R 0603
    'C15849': ('SAMSUNG', 'CL10A105KB8NNNC', 'Basic Part'),          # 1uF 50V X5R 0603
    'C15850': ('SAMSUNG', 'CL21A106KAYNNNE', 'Basic Part'),          # 10uF 25V X5R 0805
    'C1588': ('SAMSUNG', 'CL10B102KB8NNNC', 'Basic Part'),           # 1nF 50V 0603
    'C25804': ('UNI-ROYAL', '0603WAF1002T5E', 'Basic Part'),         # 10k
    'C25803': ('UNI-ROYAL', '0603WAF1003T5E', 'Basic Part'),         # 100k
    'C4184': ('UNI-ROYAL', '0603WAF2002T5E', 'Basic Part'),          # 20k
    'C23345': ('UNI-ROYAL', '0603WAF220JT5E', 'Basic Part'),         # 22R
    'C22962': ('UNI-ROYAL', '0603WAF2200T5E', 'Basic Part'),         # 220R
    'C23162': ('UNI-ROYAL', '0603WAF4701T5E', 'Basic Part'),         # 4.7k
    'C21190': ('UNI-ROYAL', '0603WAF1001T5E', 'Basic Part'),         # 1k
    'C72043': ('Everlight', '19-217/GHC-YR1S2/3T', 'Extended Part'),  # green 0603, pin1 = cathode
    'C2286': ('Hubei KENTO', 'KT-0603R', 'Basic Part'),              # red 0603, pin1 = anode
    'C88374': ('HRS(Hirose)', 'U.FL-R-SMT-1(80)', 'Extended Part'),  # same land pattern as U.FL-R-SMT(10)
    'C15051': ('MPS', 'MP1584EN-LF-Z', 'Extended Part'),             # same chip, stocked listing
    'C131337': ('JST', 'B2B-PH-K-S(LF)(SN)', 'Extended Part'),       # PH 2.0 2P THT
    'C131339': ('JST', 'B3B-PH-K-S(LF)(SN)', 'Extended Part'),       # PH 2.0 3P THT
    'C157974': ('JST', 'B8B-PH-K-S(LF)(SN)', 'Extended Part'),       # PH 2.0 8P THT
    'C131342': ('JST', 'B6B-PH-K-S(LF)(SN)', 'Extended Part'),       # PH 2.0 6P THT
}

BY_REF = {}
def _set(refs, part):
    for r in refs.split(): BY_REF[r] = part
_set('C1 C27 C30 C4 C8 C7 C9 C13 C14 C38 C39 C42 C43 C44 C45 C11', 'C14663')
_set('C2 C12 C15 C40 C35', 'C15849')
_set('C3 C37', 'C15850')
_set('C16', 'C1588')
_set('R2 R8 R11 R25 R35', 'C25804')
_set('R9 R32 R33 R34', 'C25803')
_set('R10', 'C4184')
_set('R6 R7 R12 R13', 'C23345')
_set('R14 R15 R23 R36', 'C22962')
_set('R16 R17 R21', 'C23162')
_set('R18 R19 R24 R26 R27 R28 R29', 'C21190')
_set('LED1 LED2 LED3 LED4', 'C72043')
_set('LED5 LED6', 'C2286')
_set('RF1', 'C88374')
_set('U13', 'C15051')
_set('U7 U10 U11', 'C131337')
_set('U8', 'C131339')
_set('CN2', 'C157974')
_set('CN3', 'C131342')


def attrs_for(part):
    m, mp, cls = PARTS[part]
    return {'Supplier': 'LCSC', 'Supplier Part': part, 'Manufacturer': m, 'Manufacturer Part': mp, 'JLCPCB Part Class': cls}


def patch_attr_string(a, part):
    kv = a.split('`')
    d = dict(zip(kv[0::2], kv[1::2]))
    d.update(attrs_for(part))
    d.pop('spiceSymbolName', None)
    return '`'.join(k + '`' + v for k, v in d.items() if k) + '`'


def ref_of_pcb(parts):
    for sub in parts[1:]:
        f = sub.split('~')
        if f[0] == 'TEXT' and f[1] == 'P': return f[10]
    return ''


def ref_of_sch(parts):
    for sub in parts[1:]:
        f = sub.split('~')
        if f[0] == 'T' and f[1] == 'P': return f[12]
    return ''


def patch_shapes(shapes, ref_of):
    n = 0
    for i, s in enumerate(shapes):
        if not s.startswith('LIB~'): continue
        parts = s.split('#@$')
        ref = ref_of(parts)
        if ref in BY_REF:
            h = parts[0].split('~')
            h[3] = patch_attr_string(h[3], BY_REF[ref])
            parts[0] = '~'.join(h)
            shapes[i] = '#@$'.join(parts); n += 1
    return n


def patch_file(path):
    d = json.load(open(path))
    if 'schematics' in d:
        n = sum(patch_shapes(sh['dataStr']['shape'], ref_of_sch) for sh in d['schematics'])
    else:
        n = patch_shapes(d['shape'], ref_of_pcb)
    json.dump(d, open(path, 'w'), ensure_ascii=False, indent=1)
    return n


if __name__ == '__main__':
    for p in sys.argv[1:]:
        print(p, 'parts updated:', patch_file(p))
