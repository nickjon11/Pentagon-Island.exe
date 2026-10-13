"""Server-owned 19-hex balanced randomized board, pointy-top 3-4-5-4-3."""
import random
import secrets
import math
ROWS = [3,4,5,4,3]
SLOTS = [(row,col) for row,count in enumerate(ROWS) for col in range(count)]
TERRAINS = ['forest']*4 + ['wheat']*4 + ['pasture']*4 + ['hills']*3 + ['mountain']*3 + ['desert']
NUMBERS = [2,3,3,4,4,5,5,6,6,8,8,9,9,10,10,11,11,12]

def center(slot):
    row,col = slot
    return ((col-(ROWS[row]-1)/2)*math.sqrt(3), row*1.5)

def neighbors(a,b):
    x1,y1=center(SLOTS[a]); x2,y2=center(SLOTS[b])
    return a!=b and abs(math.hypot(x1-x2,y1-y2)-math.sqrt(3))<.01

def generate_board(seed=None):
    if seed is None: seed=secrets.randbits(64)
    rng=random.Random(seed)
    terrains=TERRAINS.copy();rng.shuffle(terrains)
    active=[i for i,t in enumerate(terrains) if t!='desert']
    best=None; penalty_best=10000
    for _ in range(1500):
        nums=NUMBERS.copy();rng.shuffle(nums)
        current=dict(zip(active,nums))
        hot=[i for i,n in current.items() if n in (6,8)]
        penalty=sum(neighbors(a,b) for ix,a in enumerate(hot) for b in hot[ix+1:])
        if penalty<penalty_best:best=current;penalty_best=penalty
        if penalty==0:break
    return {'seed':seed,'mode':'balanced','desert_location':'random','shuffle_numbers':True,
      'tiles':[{'id':f't{i}','row':r,'col':c,'terrain':terrains[i],'number':best.get(i)} for i,(r,c) in enumerate(SLOTS)]}
