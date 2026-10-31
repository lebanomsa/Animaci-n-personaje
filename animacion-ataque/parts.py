"""Load the real sprite (recovered from the screenshot) and split it into parts."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_data = json.load(open(os.path.join(HERE, 'src', 'sprite.json')))
PAL = [tuple(c) for c in _data['pal']]
IDX = _data['idx']
BG_IDX = 0
OUTLINE = PAL[1]


def load_pixels():
    px = {}
    for y, row in enumerate(IDX):
        for x, i in enumerate(row):
            if i != BG_IDX:
                px[(x, y)] = PAL[i]
    # remove the single JPEG-noise pixel (colour #978070 appears once)
    noise = PAL[13]
    for k, v in list(px.items()):
        if v == noise:
            x, y = k
            neigh = [px.get(n) for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))]
            neigh = [n for n in neigh if n and n != noise]
            px[k] = max(set(neigh), key=neigh.count) if neigh else OUTLINE
    return px


def split(px):
    """Return dict name -> {(x,y): colour}. Every sprite pixel belongs to exactly one part."""
    parts = {n: {} for n in ('head', 'torso', 'back_arm', 'front_arm', 'tail', 'leg_b', 'leg_f')}
    for (x, y), c in px.items():
        if y <= 19 and x <= 31:
            n = 'head'
        elif x >= 32 and y <= 29:
            n = 'front_arm'
        elif y <= 29 and x >= 26 and y >= 20:
            n = 'front_arm'
        elif y <= 29 and x <= 17 and y >= 20:
            n = 'back_arm'
        elif y <= 29:
            n = 'torso'
        elif y <= 36 and x <= 11:
            n = 'tail'
        elif x <= 19:
            n = 'leg_b'
        else:
            n = 'leg_f'
        parts[n][(x, y)] = c
    return parts


if __name__ == '__main__':
    from PIL import Image
    px = load_pixels()
    parts = split(px)
    tint = {'head': (255, 80, 80), 'torso': (80, 255, 80), 'back_arm': (80, 80, 255),
            'front_arm': (255, 255, 0), 'tail': (0, 255, 255), 'leg_b': (255, 128, 0), 'leg_f': (200, 0, 255)}
    w, h = len(IDX[0]), len(IDX)
    im = Image.new('RGB', (w, h), (30, 30, 30))
    for n, p in parts.items():
        for (x, y), c in p.items():
            t = tint[n]
            k = sum(c) / 765.0
            im.putpixel((x, y), tuple(int(v * (0.35 + 0.65 * k)) for v in t))
    im.resize((w * 14, h * 14), Image.NEAREST).save(os.path.join(HERE, 'src', 'parts_debug.png'))
    print({n: len(p) for n, p in parts.items()}, sum(len(p) for p in parts.values()), len(px))
