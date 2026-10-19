"""Small helpers to inspect and edit EasyEDA Standard schematic JSON."""
import json,re,random,collections
class Sch:
  def __init__(s,path):
    s.doc=json.load(open(path)); s.sh=s.doc['schematics'][0]['dataStr']['shape']
  def save(s,path): json.dump(s.doc,open(path,'w'),ensure_ascii=False,indent=1)
  # ---- parsing
  def wires(s):
    for i,x in enumerate(s.sh):
      if x.startswith('W~'):
        c=list(map(float,x.split('~')[1].split())); yield i,[(c[k],c[k+1]) for k in range(0,len(c),2)]
  def flags(s):
    for i,x in enumerate(s.sh):
      if x.startswith('F~'):
        g=x.split('^^'); yield i,tuple(map(float,g[1].split('~')[:2])),g[2].split('~')[0]
      elif x.startswith('N~'):
        g=x.split('~'); yield i,(float(g[1]),float(g[2])),g[5]
  def libs(s):
    for i,x in enumerate(s.sh):
      if x.startswith('LIB~'):
        pre=''
        for sub in x.split('#@$')[1:]:
          f=sub.split('~')
          if f[0]=='T' and f[1]=='P': pre=f[12]
        yield i,pre,x
  def pin(s,ref,num):
    for i,pre,x in s.libs():
      if pre==ref:
        for sub in x.split('#@$'):
          if sub.startswith('P~') and sub.split('^^')[0].split('~')[3]==num:
            return tuple(map(float,sub.split('^^')[1].split('~')[:2]))
    raise KeyError((ref,num))
  def at(s,p):
    """elements touching point p: wires (with segment index) and flags"""
    out=[]
    for i,P in s.wires():
      for k,(a,b) in enumerate(zip(P,P[1:])):
        if on_seg(p,a,b): out.append(('W',i,k,P)); break
    for i,q,n in s.flags():
      if q==p: out.append(('F',i,n))
    return out
def on_seg(p,a,b):
  if a[0]==b[0]==p[0] and min(a[1],b[1])<=p[1]<=max(a[1],b[1]): return True
  if a[1]==b[1]==p[1] and min(a[0],b[0])<=p[0]<=max(a[0],b[0]): return True
  return False
