import json, math, pathlib
C = pathlib.Path(__file__).parent / 'cache'
peaks = [e for e in json.loads((C/'peaks.json').read_text())['elements']]
rels = json.loads((C/'hiking_routes.json').read_text())['elements']
def mi(a, b):
    R=3958.8; la1,lo1,la2,lo2=map(math.radians,(a[0],a[1],b[0],b[1]))
    h=math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*R*math.asin(math.sqrt(h))
# grid index of peaks
grid={}
for p in peaks:
    k=(round(p['lat']*20),round(p['lon']*20)); grid.setdefault(k,[]).append(p)
def near_peaks(pt, r_mi=0.16):
    out=[]
    k=(round(pt[0]*20),round(pt[1]*20))
    for dx in (-1,0,1):
        for dy in (-1,0,1):
            for p in grid.get((k[0]+dx,k[1]+dy),[]):
                if mi(pt,(p['lat'],p['lon']))<=r_mi: out.append(p)
    return out
rows=[]
for r in rels:
    ways=[m for m in r.get('members',[]) if m['type']=='way' and m.get('geometry')]
    pts=[(g['lat'],g['lon']) for w in ways for g in w['geometry']]
    if len(pts)<2: continue
    length=sum(mi((w['geometry'][i-1]['lat'],w['geometry'][i-1]['lon']),(w['geometry'][i]['lat'],w['geometry'][i]['lon'])) for w in ways for i in range(1,len(w['geometry'])))
    summits={}
    for pt in pts[::3]:
        for p in near_peaks(pt): summits[p['id']]=p
    t=r.get('tags',{})
    rows.append((t.get('name'), round(length,2), [ (p['tags'].get('name'), p['tags'].get('ele')) for p in summits.values()], t.get('network'), round(mi((44.1004,-70.2148),pts[0]),0)))
mount=[x for x in rows if x[2] and 0.4<=x[1]<=14]
print('relations',len(rows),'with summit & 0.4-14mi',len(mount))
for x in sorted(mount,key=lambda x:x[4])[:200]: print(x)
