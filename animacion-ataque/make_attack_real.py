"""Punch animation built from the REAL sprite pixels (recovered from the screenshot).

Every frame is made only by moving/stretching original pixel groups on an integer grid,
so nothing is resampled, rotated or antialiased. Upscaling is nearest-neighbour only.
"""
import math
import os
from PIL import Image

from parts import PAL, load_pixels, split

W, H = 92, 58
OX, OY = 8, 6          # where sprite (0,0) lands on the canvas
SCALE = 8
MAGENTA = PAL[0]
OUT = PAL[1]           # 101010 outline
CLOTH_MAIN = PAL[2]    # 383838
CLOTH_LIGHT = PAL[14]  # 484848
FX_WHITE = (248, 239, 231)
FX_YELLOW = (255, 228, 92)
FX_ORANGE = (232, 129, 4)
FX_RED = (184, 81, 15)
FX_BLUE = (152, 176, 224)

PX = load_pixels()
PARTS = split(PX)

# Front arm: shoulder stub (x<=29) stays attached to the torso; cuff + fist (x>=30) travel.
STUB = {k: v for k, v in PARTS['front_arm'].items() if k[0] <= 29}
FIST = {k: v for k, v in PARTS['front_arm'].items() if k[0] >= 30}
FIST_LEFT = min(x for x, _ in FIST)
FIST_RIGHT = max(x for x, _ in FIST)
CUFF_Y = 24            # vertical centre of the sleeve/cuff in the original
HIP_Y, FOOT_Y = 30, 44


def clamp(v, a, b):
    return max(a, min(b, v))


def shifted(part, fx, dy=0):
    return {(x + fx(y), y + dy): c for (x, y), c in part.items()}


def const(n):
    return lambda y: n


def leg_fn(hip, foot):
    def f(y):
        t = clamp((y - HIP_Y) / (FOOT_Y - HIP_Y), 0, 1)
        return round(hip * (1 - t) + foot * t)
    return f


def star(canvas, cx, cy, R, rot, color, spikes=8, inner=0.5):
    pts = []
    for i in range(spikes * 2):
        a = rot + i * math.pi / spikes
        r = R if i % 2 == 0 else R * inner
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r * 0.9))
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    for y in range(int(min(ys)) - 1, int(max(ys)) + 2):
        for x in range(int(min(xs)) - 1, int(max(xs)) + 2):
            if _inside(x + 0.5, y + 0.5, pts):
                canvas[(x, y)] = color


def _inside(x, y, pts):
    ins = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]; xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            ins = not ins
        j = i
    return ins


def build(p):
    hip = p.get('hip', 0)            # whole-body forward shift at the hips
    lean = p.get('lean', 0)          # extra forward shift of the shoulders/head
    dy = p.get('dy', 0)              # crouch (px down)
    foot_b = p.get('foot_b', 0)
    foot_f = p.get('foot_f', 0)
    ext = p.get('ext', 0)            # fist horizontal travel from the guard position
    fdy = p.get('fdy', 0)
    bax, bay = p.get('back', (0, 0))
    hdx, hdy = p.get('head', (0, 0))
    sway = p.get('tail', 0)
    shake = p.get('shake', 0)

    # torso: shear by row (lean grows towards the shoulders)
    def tor(y):
        return hip + round(lean * clamp((29 - y) / 9, 0, 1))
    lean_top = hip + lean

    cv = {}

    def put(d):
        cv.update(d)

    # tail swings from its base (bottom) to its tip (top)
    put(shifted(PARTS['tail'], lambda y: hip - round(sway * clamp((36 - y) / 6, 0, 1)) - round(0.5 * abs(sway) * 0), -0 + (dy if False else 0)))
    put(shifted(PARTS['leg_b'], leg_fn(hip, foot_b)))
    put(shifted(PARTS['leg_f'], leg_fn(hip, foot_f)))

    # back arm (left side of the image)
    put(shifted(PARTS['back_arm'], lambda y: tor(y) + bax, dy + bay))
    put(shifted(PARTS['torso'], tor, dy))
    put(shifted(PARTS['head'], lambda y: lean_top + hdx, dy + hdy))

    # front arm: stub + sleeve tube + fist
    stub = dict(STUB)
    if ext > 6:   # arm is straight: drop the bent-elbow pixels under the sleeve
        stub = {k: v for k, v in STUB.items() if not (k[0] >= 27 and k[1] >= 26)}
    put(shifted(stub, lambda y: lean_top, dy))

    fist_dx = lean_top + ext
    fist_dy = dy + fdy
    if ext > 0:
        x0 = 28 + lean_top
        x1 = FIST_LEFT + fist_dx          # tube ends where the cuff starts
        yc = CUFF_Y + fist_dy
        # 7-row sleeve, same colours as the original sleeve: outline / highlight / body / outline
        rows = [(-3, OUT), (-2, CLOTH_LIGHT), (-1, CLOTH_LIGHT), (0, CLOTH_MAIN),
                (1, CLOTH_MAIN), (2, CLOTH_MAIN), (3, OUT)]
        for x in range(x0, x1 + 1):
            for r, col in rows:
                cv[(x, yc + r)] = col
    put(shifted(FIST, lambda y: fist_dx, fist_dy))

    # close small horizontal gaps (<=2 px) left in the upper body by the part offsets
    for y in range(20, 30 + dy + 1):
        xs = sorted(x for (x, yy) in cv if yy == y)
        for a, b in zip(xs, xs[1:]):
            if 1 < b - a <= 3:
                for x in range(a + 1, b):
                    cv[(x, y)] = OUT

    # drop tiny detached groups of pixels (outline leftovers separated by the part offsets)
    seen = set()
    for start in list(cv):
        if start in seen:
            continue
        comp, stack = [], [start]
        seen.add(start)
        while stack:
            cx_, cy_ = stack.pop()
            comp.append((cx_, cy_))
            for ddx in (-1, 0, 1):
                for ddy in (-1, 0, 1):
                    n = (cx_ + ddx, cy_ + ddy)
                    if n in cv and n not in seen:
                        seen.add(n)
                        stack.append(n)
        if len(comp) < 10:
            for k in comp:
                del cv[k]

    fist_right = FIST_RIGHT + fist_dx
    fist_cy = 21 + fist_dy

    # motion lines behind everything on top of bg (added first by caller order -> here after, but only on empty px)
    lines = p.get('lines')
    extra = {}
    if lines:
        for (ly, ln, off) in lines:
            xs = fist_right - off
            for x in range(xs - ln, xs):
                if (x, ly + fist_dy) not in cv:
                    extra[(x, ly + fist_dy)] = FX_WHITE if ln > 8 else FX_BLUE
    for k, v in extra.items():
        cv[k] = v

    b = p.get('burst')
    if b:
        cx, cy = fist_right + 4, fist_cy
        star(cv, cx, cy, b['R'], b.get('rot', 0.0), FX_RED, 8, 0.5)
        star(cv, cx, cy, b['R'] * 0.78, b.get('rot', 0.0) + 0.2, FX_ORANGE, 8, 0.5)
        star(cv, cx, cy, b['R'] * 0.52, b.get('rot', 0.0) + 0.35, FX_YELLOW, 8, 0.5)
        star(cv, cx, cy, b['R'] * 0.26, b.get('rot', 0.0) + 0.5, FX_WHITE, 6, 0.55)
        for (sx, sy) in b.get('sparks', []):
            cv[(cx + sx, cy + sy)] = FX_YELLOW
            cv[(cx + sx + 1, cy + sy)] = FX_WHITE

    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    pix = img.load()
    for (x, y), col in cv.items():
        X, Y = x + OX, y + OY + shake
        if 0 <= X < W and 0 <= Y < H:
            pix[X, Y] = tuple(col) + (255,)
    return img


# (params, duration ms)  guard -> anticipation -> strike -> impact -> recover
FRAMES = [
    (dict(), 120),                                                                    # 0 guard
    (dict(dy=1, tail=1), 70),                                                         # 1 dip
    (dict(hip=-1, lean=-1, dy=1, ext=-4, fdy=3, back=(1, 0), tail=2), 80),            # 2 wind-up
    (dict(hip=-2, lean=-2, dy=2, ext=-8, fdy=5, back=(2, 0), tail=3,
          foot_b=-1, foot_f=-1), 130),                                                # 3 coil
    (dict(hip=-2, lean=-2, dy=2, ext=-9, fdy=5, back=(2, 0), tail=3,
          foot_b=-1, foot_f=-1), 60),                                                 # 4 hold
    (dict(hip=2, lean=2, dy=1, ext=5, fdy=0, tail=-1, foot_f=1,
          lines=[(18, 6, 3), (22, 9, 2), (26, 5, 3)]), 40),                           # 5 smear
    (dict(hip=3, lean=3, dy=1, ext=11, fdy=0, back=(-2, 1), tail=-3, foot_f=2,
          lines=[(17, 8, 2), (20, 12, 2), (23, 10, 2), (26, 8, 2), (28, 5, 2)]), 55), # 6 full extension
    (dict(hip=4, lean=3, dy=2, ext=12, fdy=0, back=(-2, 1), tail=-3, foot_f=2, shake=1,
          burst=dict(R=9, sparks=[(-4, -8), (8, -7), (9, 5), (-5, 8), (12, 0)])), 100), # 7 impact
    (dict(hip=4, lean=3, dy=2, ext=12, fdy=0, back=(-2, 1), tail=-2, foot_f=2,
          burst=dict(R=14, rot=0.2, sparks=[(-8, -12), (12, -11), (14, 9), (-7, 12), (17, 1), (3, -15)])), 90),  # 8
    (dict(hip=4, lean=2, dy=1, ext=11, fdy=0, back=(-2, 1), tail=-1, foot_f=2,
          burst=dict(R=8, rot=0.4, sparks=[(-10, -13), (15, -12), (16, 11), (-9, 13)])), 70),  # 9 fade
    (dict(hip=3, lean=2, dy=1, ext=8, fdy=0, back=(-1, 0), tail=0, foot_f=2), 80),    # 10 recover
    (dict(hip=2, lean=1, dy=1, ext=4, fdy=0, tail=1, foot_f=1), 80),                  # 11
    (dict(hip=1, lean=0, dy=0, ext=1, fdy=0, tail=1), 90),                            # 12
    (dict(), 110),                                                                    # 13 settle
]


def to_gif_frames(imgs, transparent):
    colors = {}
    for im in imgs:
        for p in im.getdata():
            if p[3]:
                colors.setdefault(p[:3], len(colors) + 1)
    assert len(colors) < 255, len(colors)
    pal = [0] * 768
    pal[0:3] = list(MAGENTA)
    for c, i in colors.items():
        pal[i * 3:i * 3 + 3] = list(c)
    out = []
    for im in imgs:
        small = Image.new('P', im.size, 0)
        small.putpalette(pal)
        small.putdata([colors[p[:3]] if p[3] else 0 for p in im.getdata()])
        out.append(small.resize((im.width * SCALE, im.height * SCALE), Image.NEAREST))
    return out


def export(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    imgs = [build(p) for p, _ in FRAMES]
    durs = [d for _, d in FRAMES]
    g = to_gif_frames(imgs, False)
    g[0].save(os.path.join(out_dir, 'attack.gif'), save_all=True, append_images=g[1:],
              duration=durs, loop=0, disposal=1, optimize=False)
    g[0].save(os.path.join(out_dir, 'attack_transparent.gif'), save_all=True, append_images=g[1:],
              duration=durs, loop=0, disposal=2, transparency=0, optimize=False)

    sheet = Image.new('RGBA', (W * len(imgs), H), (0, 0, 0, 0))
    for i, im in enumerate(imgs):
        sheet.paste(im, (i * W, 0))
    sheet.save(os.path.join(out_dir, 'spritesheet_1x.png'))
    sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST).save(
        os.path.join(out_dir, 'spritesheet_3x.png'))

    fdir = os.path.join(out_dir, 'frames')
    os.makedirs(fdir, exist_ok=True)
    for i, im in enumerate(imgs):
        im.resize((W * SCALE, H * SCALE), Image.NEAREST).save(os.path.join(fdir, f'frame_{i:02d}.png'))

    cols = 4
    rows = (len(imgs) + cols - 1) // cols
    z = 4
    cs = Image.new('RGB', (cols * W * z, rows * H * z), MAGENTA)
    for i, im in enumerate(imgs):
        b = im.resize((W * z, H * z), Image.NEAREST)
        cs.paste(b, ((i % cols) * W * z, (i // cols) * H * z), b)
    cs.save(os.path.join(out_dir, 'contact_sheet.png'))
    return len(imgs), sum(durs)


if __name__ == '__main__':
    n, t = export(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output'))
    print(f'{n} frames, {t} ms')
