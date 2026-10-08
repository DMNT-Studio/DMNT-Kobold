"""Einmalig: Meshy-Modell in Teile zerlegen -> web/labels.bin (Teil je Dreieck), web/parts.json (Ankerpunkte).
Teile: 0 Raute, 1/2 Handschuhe, 3/4 Schuhe, 5-8 Original-Arme/-Beine (werden nicht gezeichnet).
Aufruf: python segment.py [modell.glb]   (braucht trimesh, numpy, scipy)"""
import os, sys
import trimesh, numpy as np, json
os.chdir(os.path.dirname(os.path.abspath(__file__)))
MODELL = sys.argv[1] if len(sys.argv) > 1 else os.path.join('..', '..', 'quellen', 'dmnt9000_3d', 'modell', 'dmnt9000.glb')
s=trimesh.load(MODELL,process=False); m=list(s.geometry.values())[0]
v=m.vertices; f=m.faces
print(v.shape,f.shape)
c=v[f].mean(1)  # face centroids
x,y,z=c[:,0],c[:,1],c[:,2]
def halfw(y):  # diamond outline halfwidth
    hw=np.where(y<0.62, 0.78*(y+0.38)/1.0, 0.78-(y-0.62)/(0.94-0.62)*0.28)
    return hw
M=0.035
inside=(np.abs(x)<=halfw(y)+M)&(y>-0.40)&(y<0.97)
lab=np.zeros(len(f),np.uint8)  # 0 body
# 1 gloveL 2 gloveR 3 shoeL 4 shoeR 5 armL 6 armR 7 legL 8 legR
shoe=y<-0.585
lab[shoe&(x<0)]=3; lab[shoe&(x>=0)]=4
rest=~shoe&~inside
glove=rest&(np.abs(x)>0.40)&(y<0.01)
lab[glove&(x<0)]=1; lab[glove&(x>=0)]=2
arm=rest&~glove&(np.abs(x)>0.30)&(y>=-0.05)
lab[arm&(x<0)]=5; lab[arm&(x>=0)]=6
leg=rest&~glove&~arm&(y<-0.0)
lab[leg&(x<0)]=7; lab[leg&(x>=0)]=8
left=rest&(lab==0)
print('unassigned outside', left.sum(), c[left][:10] if left.sum() else '')
for k in range(9): print(k,(lab==k).sum())
lab.tofile('web/labels.bin')
def stats(k):
    sel=lab==k; vv=v[np.unique(f[sel])]
    return vv
P={}
for k,n in [(1,'gloveL'),(2,'gloveR'),(3,'shoeL'),(4,'shoeR')]:
    vv=stats(k); top=vv[vv[:,1]>vv[:,1].max()-0.04]
    P[n]={'top':top.mean(0).tolist(),'min':vv.min(0).tolist(),'max':vv.max(0).tolist()}
for k,n in [(5,'armL'),(6,'armR'),(7,'legL'),(8,'legR')]:
    vv=stats(k); 
    top=vv[vv[:,1]>vv[:,1].max()-0.04]; bot=vv[vv[:,1]<vv[:,1].min()+0.04]
    # radius estimate: tube cross-section spread at mid
    mid=vv[np.abs(vv[:,1]-np.median(vv[:,1]))<0.02]
    P[n]={'top':top.mean(0).tolist(),'bot':bot.mean(0).tolist(),'min':vv.min(0).tolist(),'max':vv.max(0).tolist(),'midspan':(mid.max(0)-mid.min(0)).tolist(),'midc':mid.mean(0).tolist()}
json.dump(P,open('web/parts.json','w'),indent=1)
for k,vv in P.items(): print(k,{a:[round(t,3) for t in b] for a,b in vv.items()})

# --- Nachschärfen: Reste der Original-Beine (Röhre um die Beinachse) entfernen ---
def achsabstand(pts, a, b):
    ab = b - a; t = np.clip(((pts - a) @ ab) / (ab @ ab), -0.6, 1.25)
    return np.linalg.norm(pts - (a + t[:, None] * ab), axis=1), t
RAD = float(__import__('os').environ.get('BEINRAD', 0.082))
for k, n, sgn in [(7, 'legL', -1), (8, 'legR', 1)]:
    a = np.array(P[n]['top']); b = np.array(P[n]['bot'])
    sel = np.isin(lab, [0, 3, 4]) & (np.sign(x) == sgn) & (y > -0.665) & (y < -0.02)
    d, t = achsabstand(c[sel], a, b)
    idx = np.flatnonzero(sel)[d < RAD]
    lab[idx] = k
    print(n, 'nachgeschärft', len(idx))
lab.tofile('web/labels.bin')
