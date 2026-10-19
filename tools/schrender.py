"""Render an EasyEDA Std schematic JSON to SVG (rough, for review)."""
import json,sys,html,re
def render(path,out,sheet=0,crop=None,scale=1.0):
  d=json.load(open(path)); sh=d['schematics'][sheet]['dataStr']['shape']
  el=[]
  def T(x,y,t,c='#000080',sz=7,anchor='start',rot=0):
    el.append(f'<text x="{x}" y="{y}" font-size="{sz}" fill="{c}" text-anchor="{anchor}" font-family="Arial" transform="rotate({rot} {x} {y})">{html.escape(t)}</text>')
  def sub(sub):
    f=sub.split('~')
    t=f[0]
    if t=='PL': el.append(f'<polyline points="{f[1]}" fill="none" stroke="{f[2] or "#880000"}" stroke-width="1"/>')
    elif t=='PG': el.append(f'<polygon points="{f[1]}" fill="{f[5] if len(f)>5 and f[5] not in ("none","") else "none"}" stroke="#880000" stroke-width="1"/>')
    elif t=='R': el.append(f'<rect x="{f[1]}" y="{f[2]}" width="{f[5]}" height="{f[6]}" fill="none" stroke="#880000"/>')
    elif t=='E': el.append(f'<ellipse cx="{f[1]}" cy="{f[2]}" rx="{f[3]}" ry="{f[4]}" fill="none" stroke="#880000"/>')
    elif t in('A','PT'): el.append(f'<path d="{f[1]}" fill="none" stroke="#880000"/>')
    elif t=='T':
      try: T(float(f[2]),float(f[3]),f[12],c=f[5] or '#000080',sz=7,rot=float(f[4] or 0))
      except: pass
    elif t=='P':
      g=sub.split('^^')
      el.append(f'<path d="{g[2].split("~")[0]}" stroke="#800" fill="none"/>')
      gg=g[3].split('~') if len(g)>3 else []
      if len(gg)>4 and gg[0]=='1':
        try: T(float(gg[1]),float(gg[2])+2,gg[4],c='#555',sz=5,anchor=gg[6] if len(gg)>6 else 'start',rot=float(gg[3] or 0))
        except: pass
  for x in sh:
    t=x.split('~')[0]
    if t=='W':
      el.append(f'<polyline points="{x.split("~")[1]}" fill="none" stroke="#008800" stroke-width="1"/>')
    elif t=='J':
      f=x.split('~'); el.append(f'<circle cx="{f[1]}" cy="{f[2]}" r="2.5" fill="#c00"/>')
    elif t=='F':
      g=x.split('^^'); xy=g[1].split('~'); nm=g[2].split('~')
      for s in g[3:]: sub(s)
      T(float(nm[2]),float(nm[3]),nm[0],c='#000',sz=7)
    elif t=='N':
      f=x.split('~'); T(float(f[1]),float(f[2])-2,f[5],c='#0000cc',sz=7)
    elif t=='T':
      f=x.split('~'); T(float(f[2]),float(f[3]),f[12],c=f[5],sz=12)
    elif t=='LIB':
      for s in x.split('#@$')[1:]: sub(s)
  vb=crop or (0,-1600,2100,1620)
  svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb[0]} {vb[1]} {vb[2]} {vb[3]}" width="{vb[2]*scale}" height="{vb[3]*scale}"><rect x="{vb[0]}" y="{vb[1]}" width="{vb[2]}" height="{vb[3]}" fill="white"/>'+''.join(el)+'</svg>'
  open(out,'w').write(svg)
if __name__=='__main__':
  a=sys.argv; crop=tuple(map(float,a[3].split(','))) if len(a)>3 else None
  render(a[1],a[2],crop=crop,scale=float(a[4]) if len(a)>4 else 1.0)
