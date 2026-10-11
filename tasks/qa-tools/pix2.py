import sys
from PIL import Image, ImageChops
x=Image.open(sys.argv[1]).convert('RGB'); y=Image.open(sys.argv[2]).convert('RGB')
print(x.size,y.size)
d=ImageChops.difference(x,y).convert('L').point(lambda v:255 if v>0 else 0)
w,h=d.size; px=d.load()
rows=[r for r in range(h) if any(px[c,r] for c in range(0,w,2))]
import itertools
print('diff rows', len(rows), rows[:3], rows[-3:])
print('count', sum(1 for r in range(h) for c in range(w) if px[c,r]))
