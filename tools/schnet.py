import json,collections,pickle,sys
def schnetlist(path):
  s=json.load(open(path))
  sh=s['schematics'][0]['dataStr']['shape']
  par={}
  def f(a):
    par.setdefault(a,a)
    while par[a]!=a: par[a]=par[par[a]]; a=par[a]
    return a
  def u(a,b): par[f(a)]=f(b)
  segs=[]; pts=[]
  pins=[]; flags=[]
  for x in sh:
    t=x.split('~')[0]
    if t=='W':
      c=list(map(float,x.split('~')[1].split()))
      P=[(round(c[i],2),round(c[i+1],2)) for i in range(0,len(c),2)]
      for a,b in zip(P,P[1:]): segs.append((a,b)); u(a,b)
    elif t=='F':
      g=x.split('^^'); xy=tuple(round(float(v),2) for v in g[1].split('~')[:2]); name=g[2].split('~')[0]
      flags.append((xy,name)); f(xy)
    elif t=='N':
      g=x.split('~'); xy=(round(float(g[1]),2),round(float(g[2]),2)); flags.append((xy,g[5])); f(xy)
    elif t=='LIB':
      parts=x.split('#@$'); pre=''
      pl=[]
      for sub in parts[1:]:
        ff=sub.split('~')
        if ff[0]=='T' and ff[1]=='P': pre=ff[12]
        if ff[0]=='P':
          g=sub.split('^^'); num=g[0].split('~')[3]; xy=tuple(round(float(v),2) for v in g[1].split('~')[:2])
          pl.append((num,xy))
      for num,xy in pl: pins.append((pre,num,xy)); f(xy)
  # points lying on segment interiors
  allpts=list(par.keys())
  for (a,b) in segs:
    for p in allpts:
      if p in (a,b): continue
      if a[0]==b[0]==p[0] and min(a[1],b[1])<=p[1]<=max(a[1],b[1]): u(p,a)
      elif a[1]==b[1]==p[1] and min(a[0],b[0])<=p[0]<=max(a[0],b[0]): u(p,a)
  # flags with same name connect
  byname=collections.defaultdict(list)
  for xy,n in flags: byname[n].append(xy)
  for n,l in byname.items():
    for p in l[1:]: u(p,l[0])
  groups=collections.defaultdict(lambda:{'names':set(),'pins':[]})
  for xy,n in flags: groups[f(xy)]['names'].add(n)
  for pre,num,xy in pins: groups[f(xy)]['pins'].append(f"{pre}.{num}")
  return groups,pins
if __name__=='__main__':
  g,pins=schnetlist(sys.argv[1])
  pcbnets,comp=pickle.load(open('pcbnets.pkl','rb'))
  # map pin -> pcb net
  pin2pcb={}
  for n,l in pcbnets.items():
    for p in l: pin2pcb[p.split('(')[0]]=n
  diffs=0
  for k,v in g.items():
    pcb=set(pin2pcb.get(p,'?') for p in v['pins'])
    if len(pcb)>1 or (v['names'] and pcb and not (pcb & v['names']) and len(v['pins'])>0 and not any(n.startswith(('U','R','C')) for n in pcb)):
      diffs+=1; print('MISMATCH',sorted(v['names']),v['pins'],pcb)
  # pins that are alone in schematic but connected in pcb
  for k,v in g.items():
    if len(v['pins'])==1 and not v['names']:
      p=v['pins'][0]; n=pin2pcb.get(p)
      if n and len(pcbnets[n])>1: print('SCH unconnected but PCB connected:',p,n)
  print('groups',len(g),'diffs',diffs)
