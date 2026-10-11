import sys, glob, os
from PIL import Image, ImageChops
a, b = sys.argv[1], sys.argv[2]
for f in sorted(glob.glob(a + '/*.png')):
    n = os.path.basename(f); g = os.path.join(b, n)
    if not os.path.exists(g): print(n, 'MISSING in', b); continue
    x, y = Image.open(f).convert('RGB'), Image.open(g).convert('RGB')
    if x.size != y.size: print(n, 'SIZE', x.size, y.size); continue
    bb = ImageChops.difference(x, y).getbbox()
    print(n, 'identical' if bb is None else f'DIFF bbox={bb}')
