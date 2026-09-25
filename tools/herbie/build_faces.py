"""Rebuild Herbie's face set from one shared map template.

Every face uses the same background: the hero Herbie from herbie-character-sheet-expanded.png
(compass, rolled map, rivers, mushrooms, green crystal) with his face and the "Explore & stay lit"
sign removed. Only the facial features change. Features are drawn as masks on a 4x canvas, painted
(fill + dark outline + highlight), then downsampled so edges stay smooth. Output: 300x261 RGBA PNGs.

Usage:  python tools/herbie/build_faces.py            (writes public/assets/herbie/**)
        python tools/herbie/build_faces.py --preview  (also writes tools/herbie/preview_sheet.png)
"""
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'public' / 'assets' / 'herbie'
OUT = SRC
TOOLS = ROOT / 'tools' / 'herbie'

SHEET_BOX = (15, 115, 322, 382)   # hero Herbie on the expanded character sheet (307 x 267)
TPL_W, TPL_H = 307, 267
UNIT = 2.1                 # template pixels per layout unit (feature coordinates below are in units)
DRAW = 4                   # drawing canvas = template x4, then downsampled
K = UNIT * DRAW            # canvas pixels per unit
CW, CH = TPL_W * DRAW, TPL_H * DRAW
OUT_W, OUT_H = 300, 261    # final asset size (same for every face, motion and turnaround)

# Palette sampled from the original art.
INK = (8, 22, 6)            # mouth / brows / arcs
EYE_FILL = (14, 34, 10)     # eyes are dark green
EYE_EDGE = (4, 12, 3)
PUPIL = (54, 104, 30)       # the sprout "pupil" takes the eyes' previous green
PUPIL_EDGE = (88, 140, 48)
INK_2 = EYE_FILL
SPROUT = (184, 206, 58)     # bright leaf (charge spark only)
SPROUT_DARK = (104, 140, 34)
HAND = (53, 65, 13)         # facepalm hand as drawn (original sampled colour x0.85)
HAND_DARK = (16, 24, 2)
HAND_LIGHT = (72, 90, 17)
HAND_SHADE = (34, 46, 6)
HAND_VEIN = (26, 36, 4)
SLEEVE = (88, 77, 18)
HIGH_EYE = (212, 108, 146)  # high AF: pink eyes, green pupils
HIGH_EYE_EDGE = (118, 40, 72)
LOCK_EYE = (16, 66, 22)     # GPS locked: radar-green reticle eyes
LOCK_EYE_EDGE = (4, 20, 6)
LOCK_PUPIL = (150, 250, 116)
LOCK_PUPIL_EDGE = (60, 150, 60)
RADAR = (130, 240, 100)
HIGH_PUPIL = (86, 164, 50)
HIGH_PUPIL_EDGE = (34, 84, 18)
BLUSH = (226, 108, 110)
TEAR = (96, 182, 222)
TEAR_DARK = (36, 102, 150)
TONGUE = (214, 96, 104)
RED_HEART = (212, 62, 84)
BG_DARK = (10, 22, 14)

# Face layout on the source grid.
EYE_L = (55, 55)
EYE_R = (92, 55)
MOUTH = (73.5, 73)

# Gaze: every expression is rendered looking straight, left and right (viewer's left/right).
# The whole face turns a little and the pupils travel a little further.
GAZES = {'center': 0, 'left': -1, 'right': 1}
GAZE_SHIFT = 5.5      # units the eyes + mouth move
GAZE_PUPIL = 2.8      # extra pupil travel inside the eye
_BASE_LAYOUT = (EYE_L, EYE_R, MOUTH)
GAZE = [0]


def set_gaze(name):
    global EYE_L, EYE_R, MOUTH
    g = GAZES[name]
    GAZE[0] = g
    (lx, ly), (rx, ry), (mx, my) = _BASE_LAYOUT
    EYE_L, EYE_R, MOUTH = (lx + g * GAZE_SHIFT, ly), (rx + g * GAZE_SHIFT, ry), (mx + g * GAZE_SHIFT * 0.8, my)


def s(v):
    return v * K


def new_mask():
    return Image.new('L', (CW, CH), 0)


# ---------------------------------------------------------------- template
def build_template():
    """Hero Herbie from the character sheet, face and sign removed."""
    sheet = Image.open(SRC / 'herbie-character-sheet-expanded.png').convert('RGB')
    hero = np.array(sheet.crop(SHEET_BOX))
    bgr = cv2.cvtColor(hero, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    # 1) remove his eyes and mouth (dark / saturated green inside the face boxes)
    mask = np.zeros(hero.shape[:2], np.uint8)
    for (x0, y0, x1, y1) in [(95, 90, 133, 137), (173, 88, 207, 139), (128, 135, 185, 169)]:
        r = hsv[y0:y1, x0:x1]
        dark = (r[..., 2] < 150) | ((r[..., 0] > 28) & (r[..., 0] < 60) & (r[..., 1] > 120) & (r[..., 2] < 200))
        mask[y0:y1, x0:x1][dark] = 255
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=2)
    img = Image.fromarray(cv2.cvtColor(cv2.inpaint(bgr, mask, 5, cv2.INPAINT_TELEA), cv2.COLOR_BGR2RGB))
    # 2) replace the wooden sign with the leafy ground from the lower-left corner
    sx0, sy0, sx1, sy1 = 76, 215, 236, 267
    tile = img.crop((6, sy0, 76, sy1))
    fill = Image.new('RGB', (sx1 - sx0, sy1 - sy0))
    x, flip = 0, False
    while x < fill.width:
        fill.paste(tile.transpose(Image.FLIP_LEFT_RIGHT) if flip else tile, (x, 0))
        x += tile.width - 8
        flip = not flip
    fm = Image.new('L', fill.size, 0)
    ImageDraw.Draw(fm).rounded_rectangle((0, 4, fill.width, fill.height + 10), radius=10, fill=255)
    img.paste(fill, (sx0, sy0), fm.filter(ImageFilter.GaussianBlur(4)))
    # 3) the tiled strip repeats the big mushroom's stem; paint those stems out (keep the small caps)
    b = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    h = cv2.cvtColor(b, cv2.COLOR_BGR2HSV)
    stems = np.zeros(b.shape[:2], np.uint8)
    for x0, x1 in [(105, 121), (161, 179), (220, 238)]:
        r = h[216:250, x0:x1]
        stems[216:250, x0:x1][(r[..., 2] > 95) & (r[..., 0] >= 15) & (r[..., 0] <= 30) & (r[..., 1] < 215)] = 255
    stems = cv2.dilate(stems, np.ones((3, 3), np.uint8), iterations=2)
    b = cv2.inpaint(b, stems, 4, cv2.INPAINT_TELEA)
    return Image.fromarray(cv2.cvtColor(b, cv2.COLOR_BGR2RGB)).convert('RGBA')


# ---------------------------------------------------------------- painting helpers
def paint(canvas, mask, fill, outline=None, outline_px=10, light=None, light_offset=(0, -6), shade=None):
    """Paint a mask onto the big canvas: dark outline, fill, optional top highlight / bottom shade."""
    if outline is not None:
        ring = mask.filter(ImageFilter.MaxFilter(outline_px | 1))
        canvas.paste(Image.new('RGBA', canvas.size, outline + (255,)), (0, 0), ring)
    canvas.paste(Image.new('RGBA', canvas.size, fill + (255,)), (0, 0), mask)
    if shade is not None:
        inner = ImageChops.subtract(mask, ImageChops.offset(mask, 0, -12))
        canvas.paste(Image.new('RGBA', canvas.size, shade + (255,)), (0, 0), inner.filter(ImageFilter.GaussianBlur(3)))
    if light is not None:
        hi = ImageChops.subtract(mask, ImageChops.offset(mask, *light_offset))
        hi = ImageChops.multiply(hi, mask.filter(ImageFilter.MinFilter(9)))
        canvas.paste(Image.new('RGBA', canvas.size, light + (255,)), (0, 0), hi.filter(ImageFilter.GaussianBlur(2)))


def ellipse_mask(cx, cy, rx, ry, angle=0.0):
    m = new_mask()
    big = Image.new('L', (int(s(rx) * 2 + 4), int(s(ry) * 2 + 4)), 0)
    ImageDraw.Draw(big).ellipse((2, 2, big.width - 2, big.height - 2), fill=255)
    if angle:
        big = big.rotate(angle, resample=Image.BICUBIC, expand=True)
    m.paste(big, (int(s(cx) - big.width / 2), int(s(cy) - big.height / 2)), big)
    return m


def poly_mask(points):
    m = new_mask()
    ImageDraw.Draw(m).polygon([(s(x), s(y)) for x, y in points], fill=255)
    return m


def stroke_mask(points, width, closed=False):
    """Round-capped polyline on the source grid."""
    m = new_mask()
    d = ImageDraw.Draw(m)
    pts = [(s(x), s(y)) for x, y in points]
    if closed:
        pts = pts + [pts[0]]
    d.line(pts, fill=255, width=int(s(width)), joint='curve')
    r = s(width) / 2
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=255)
    return m


def arc_points(cx, cy, rx, ry, a0, a1, n=28):
    return [(cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a)))
            for a in np.linspace(a0, a1, n)]


def union(*masks):
    out = masks[0]
    for m in masks[1:]:
        out = ImageChops.lighter(out, m)
    return out


def subtract(a, b):
    return ImageChops.subtract(a, b)


def egg_mask(cx, cy, w, h):
    """Neutral's right eye: an egg with a slightly pointed top."""
    pts = []
    for a in np.linspace(0, 360, 90):
        t = math.radians(a)
        x = math.sin(t) * w / 2
        y = -math.cos(t) * h / 2
        if y < 0:                      # narrow the top half into a soft point
            x *= 0.78 + 0.22 * (1 + y / (h / 2))
        pts.append((cx + x, cy + y))
    return poly_mask(pts)


def sprout_mask(cx, cy, size):
    """Three small leaves, like the sprout inside Neutral's right eye."""
    leaves = [
        ellipse_mask(cx, cy - size * 0.35, size * 0.22, size * 0.42),
        ellipse_mask(cx - size * 0.38, cy + size * 0.05, size * 0.2, size * 0.4, angle=55),
        ellipse_mask(cx + size * 0.38, cy + size * 0.05, size * 0.2, size * 0.4, angle=-55),
    ]
    return union(*leaves)


# ---------------------------------------------------------------- eyes
def eye_open(c, center, scale=1.0, look=(0, 0), lid=None, lid_side=None, red=False, palette=None):
    cx, cy = center
    w, h = 10 * scale, 16 * scale
    m = egg_mask(cx, cy, w, h)
    if lid:  # lid: 'half' (top third closed), 'sad' / 'angry' (slanted cut)
        if lid == 'half':
            cut = poly_mask([(cx - 9, cy - 12), (cx + 9, cy - 12), (cx + 9, cy - 1), (cx - 9, cy - 1)])
        else:
            inner_high = lid == 'sad'
            left_is_inner = lid_side == 'R'
            y_in = cy - (2 if inner_high else 8)
            y_out = cy - (8 if inner_high else 1)
            yl, yr = (y_in, y_out) if left_is_inner else (y_out, y_in)
            cut = poly_mask([(cx - 9, cy - 12), (cx + 9, cy - 12), (cx + 9, yr), (cx - 9, yl)])
        m = subtract(m, cut)
    fill, edge, pupil, pupil_edge = palette or ((HIGH_EYE, HIGH_EYE_EDGE, HIGH_PUPIL, HIGH_PUPIL_EDGE) if red else (EYE_FILL, EYE_EDGE, PUPIL, PUPIL_EDGE))
    look = (look[0] + GAZE[0] * GAZE_PUPIL, look[1])
    paint(c, m, fill, outline=edge, outline_px=9, shade=edge)
    spr = sprout_mask(cx + look[0], cy - h * 0.12 + look[1], 4.2 * scale)
    spr = ImageChops.multiply(spr, m.filter(ImageFilter.MinFilter(9)))
    paint(c, spr, pupil, outline=pupil_edge, outline_px=3)


def eye_reticle(c, center):
    """GPS locked: radar-green eye with a lock-on ring and crosshair, like the scanning screen."""
    cx, cy = center
    eye_open(c, center, palette=(LOCK_EYE, LOCK_EYE_EDGE, LOCK_PUPIL, LOCK_PUPIL_EDGE))
    ring = subtract(ellipse_mask(cx, cy, 8.2, 10.2), ellipse_mask(cx, cy, 7.4, 9.4))
    ticks = union(stroke_mask([(cx - 10.5, cy), (cx - 5.2, cy)], 0.9), stroke_mask([(cx + 5.2, cy), (cx + 10.5, cy)], 0.9),
                  stroke_mask([(cx, cy - 12.5), (cx, cy - 7.5)], 0.9), stroke_mask([(cx, cy + 7.5), (cx, cy + 12.5)], 0.9))
    paint(c, union(ring, ticks), RADAR, outline=LOCK_EYE_EDGE, outline_px=4)


def eye_arc(c, center, up=True, width=10, thick=2.2):
    cx, cy = center
    pts = arc_points(cx, cy + (3 if up else -2), width / 2, 5, 200, 340) if up else arc_points(cx, cy - 2, width / 2, 4.5, 20, 160)
    paint(c, stroke_mask(pts, thick), INK)


def eye_squeeze(c, center, side):
    """'>' / '<' squeezed-shut eye for laughing hard."""
    cx, cy = center
    d = 1 if side == 'L' else -1
    pts = [(cx - 4 * d, cy - 4), (cx + 3 * d, cy), (cx - 4 * d, cy + 4)]
    paint(c, stroke_mask(pts, 2.4), INK)


def eye_heart(c, center, color=RED_HEART):
    cx, cy = center
    m = union(ellipse_mask(cx - 2.4, cy - 1.5, 3.2, 3.2), ellipse_mask(cx + 2.4, cy - 1.5, 3.2, 3.2),
              poly_mask([(cx - 5.4, cy - 0.5), (cx + 5.4, cy - 0.5), (cx, cy + 6)]))
    paint(c, m, color, outline=INK, outline_px=7, light=(250, 150, 160), light_offset=(0, -8))


def eye_star(c, center):
    cx, cy = center
    pts = []
    for i in range(8):
        r = 7 if i % 2 == 0 else 2.2
        a = math.radians(i * 45 - 90)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    m = poly_mask(pts)
    paint(c, m, EYE_FILL, outline=EYE_EDGE, outline_px=7)
    paint(c, ellipse_mask(cx, cy, 1.6, 1.6), PUPIL_EDGE)


def eye_target(c, center):
    cx, cy = center
    ring = subtract(ellipse_mask(cx, cy, 6, 6), ellipse_mask(cx, cy, 4.2, 4.2))
    cross = union(stroke_mask([(cx - 8, cy), (cx + 8, cy)], 1.4), stroke_mask([(cx, cy - 8), (cx, cy + 8)], 1.4))
    paint(c, union(ring, cross), INK)
    paint(c, ellipse_mask(cx, cy, 1.5, 1.5), PUPIL_EDGE, outline=INK, outline_px=3)


def eye_x(c, center):
    cx, cy = center
    paint(c, union(stroke_mask([(cx - 4, cy - 4), (cx + 4, cy + 4)], 2.2), stroke_mask([(cx - 4, cy + 4), (cx + 4, cy - 4)], 2.2)), INK)


def eye_spiral(c, center):
    cx, cy = center
    pts = [(cx + (0.4 + a / 110) * math.cos(math.radians(a)), cy + (0.4 + a / 110) * math.sin(math.radians(a))) for a in range(0, 760, 12)]
    paint(c, stroke_mask(pts, 1.5), INK)


def eye_dot(c, center, r=2.6):
    paint(c, ellipse_mask(center[0], center[1], r, r * 1.2), INK_2, outline=INK, outline_px=5)


def brow(c, center, tilt, lift=0, side='L'):
    """tilt > 0 raises the inner end (worried); tilt < 0 lowers it (angry)."""
    cx, cy = center
    y = cy - 11 - lift
    inner, outer = (cx + 5, cx - 5) if side == 'L' else (cx - 5, cx + 5)
    paint(c, stroke_mask([(outer, y), (inner, y - tilt)], 1.8), INK)


# ---------------------------------------------------------------- mouths
def mouth_smile(c, width=22, depth=5, thick=2.6, y=None):
    cx, cy = MOUTH[0], y or MOUTH[1]
    paint(c, stroke_mask(arc_points(cx, cy - depth * 0.6, width / 2, depth, 20, 160), thick), INK)


def mouth_frown(c, width=16, depth=3.5, thick=2.4):
    cx, cy = MOUTH
    paint(c, stroke_mask(arc_points(cx, cy + depth + 1, width / 2, depth, 200, 340), thick), INK)


def mouth_flat(c, width=14, thick=2.4, dy=0):
    cx, cy = MOUTH
    paint(c, stroke_mask([(cx - width / 2, cy + dy), (cx + width / 2, cy + dy)], thick), INK)


def mouth_grin(c, width=22, depth=9, tongue=True):
    cx, cy = MOUTH
    top = cy - 3
    pts = [(cx - width / 2, top)] + arc_points(cx, top, width / 2, depth, 0, 180)[::-1] + [(cx + width / 2, top)]
    m = poly_mask(arc_points(cx, top, width / 2, depth, 0, 180) + [(cx - width / 2, top)])
    paint(c, m, INK, outline=INK, outline_px=5)
    if tongue:
        t = ImageChops.multiply(ellipse_mask(cx, top + depth * 0.82, width * 0.26, depth * 0.38), m.filter(ImageFilter.MinFilter(7)))
        paint(c, t, TONGUE)


def mouth_o(c, rx=3.2, ry=4, dy=0):
    cx, cy = MOUTH
    paint(c, ellipse_mask(cx, cy + dy, rx, ry), INK, outline=INK, outline_px=5)


def mouth_wavy(c, width=18, amp=1.6, thick=2.2):
    cx, cy = MOUTH
    pts = [(cx - width / 2 + i * width / 40, cy + amp * math.sin(i / 40 * math.pi * 3)) for i in range(41)]
    paint(c, stroke_mask(pts, thick), INK)


def mouth_zigzag(c, width=18, amp=1.8, thick=2.0):
    cx, cy = MOUTH
    n = 6
    pts = [(cx - width / 2 + i * width / n, cy + (amp if i % 2 else -amp)) for i in range(n + 1)]
    paint(c, stroke_mask(pts, thick), INK)


def mouth_smirk(c):
    cx, cy = MOUTH
    paint(c, stroke_mask(arc_points(cx + 3, cy - 3, 8, 4, 20, 150), 2.4), INK)


def mouth_tongue(c, width=18):
    mouth_smile(c, width=width, depth=4)
    cx, cy = MOUTH
    t = union(ellipse_mask(cx + 2, cy + 3.5, 3.2, 3.8))
    paint(c, t, TONGUE, outline=INK, outline_px=5)


def mouth_wobble(c, width=16):
    """Wobbly crying frown."""
    cx, cy = MOUTH
    pts = [(cx - width / 2 + i * width / 30, cy + 3 - 3.2 * math.sin(i / 30 * math.pi) + 0.7 * math.sin(i / 30 * math.pi * 5)) for i in range(31)]
    paint(c, stroke_mask(pts, 2.4), INK)


# ---------------------------------------------------------------- extras
def blush(c, strength=210, color=None):
    for cx in (EYE_L[0] - 6, EYE_R[0] + 6):
        m = ellipse_mask(cx, 66, 6.5, 3.2).filter(ImageFilter.GaussianBlur(12))
        m = m.point(lambda v: v * strength // 255)
        c.paste(Image.new('RGBA', c.size, (color or BLUSH) + (255,)), (0, 0), m)


def mouth_wail(c, width=14, depth=9):
    """Open crying / shouting mouth (wide at the bottom)."""
    cx, cy = MOUTH
    m = poly_mask(arc_points(cx, cy + 4, width / 2, depth * 0.55, 180, 360) + arc_points(cx, cy + 4, width / 2, depth * 0.45, 0, 180))
    paint(c, m, INK, outline=INK, outline_px=5)
    paint(c, ImageChops.multiply(ellipse_mask(cx, cy + 6.5, width * 0.26, depth * 0.22), m.filter(ImageFilter.MinFilter(7))), TONGUE)


def mouth_teeth(c, width=18):
    """Grimace: clenched teeth."""
    cx, cy = MOUTH
    m = rounded(poly_mask([(cx - width / 2, cy - 2.6), (cx + width / 2, cy - 2.6), (cx + width / 2, cy + 2.6), (cx - width / 2, cy + 2.6)]), 10)
    paint(c, m, (236, 232, 214), outline=INK, outline_px=7)
    lines = union(stroke_mask([(cx - width / 2 + 1, cy), (cx + width / 2 - 1, cy)], 0.5),
                  *[stroke_mask([(cx - width / 2 + k * width / 5, cy - 2.2), (cx - width / 2 + k * width / 5, cy + 2.2)], 0.5) for k in range(1, 5)])
    paint(c, lines, INK)


def big_tears(c):
    """Sobbing: wide streams and drops flying off the cheeks."""
    for cx, side in ((EYE_L[0], -1), (EYE_R[0], 1)):
        pts = [(cx + side * 0.8 * i / 14 * 3, 60 + i * 1.3) for i in range(0, 15)]
        paint(c, stroke_mask(pts, 4.2), TEAR, outline=TEAR_DARK, outline_px=5, light=(200, 236, 255), light_offset=(4, 0))
        tear_drop(c, cx + side * 9, 60, 1.1)
        tear_drop(c, cx + side * 12, 66, 0.9)


def tear_drop(c, x, y, size=1.0):
    m = union(ellipse_mask(x, y + 1.5 * size, 1.9 * size, 2.1 * size), poly_mask([(x - 1.7 * size, y + 1.2 * size), (x + 1.7 * size, y + 1.2 * size), (x, y - 2.6 * size)]))
    paint(c, m, TEAR, outline=TEAR_DARK, outline_px=5, light=(210, 240, 255), light_offset=(3, 3))


def tear_streams(c):
    for cx in (EYE_L[0], EYE_R[0]):
        pts = [(cx + 0.6 * math.sin(i / 3), 61 + i * 1.1) for i in range(0, 15)]
        paint(c, stroke_mask(pts, 2.6), TEAR, outline=TEAR_DARK, outline_px=5)
        tear_drop(c, cx + 0.5, 78, 1.1)


def sweat(c, x=108, y=44):
    tear_drop(c, x, y, 1.4)


def zzz(c):
    for (x, y, sz) in [(102, 44, 3.2), (108, 38, 2.6), (113, 33, 2.0)]:
        paint(c, stroke_mask([(x - sz, y - sz), (x + sz, y - sz), (x - sz, y + sz), (x + sz, y + sz)], 1.3), (10, 10, 10))


def question(c, x=107, y=38):
    pts = arc_points(x, y - 2, 3.2, 3.2, 180, 400) + [(x, y + 3.5)]
    paint(c, stroke_mask(pts, 1.8), INK)
    paint(c, ellipse_mask(x, y + 7, 1.1, 1.1), INK)


def rounded(mask, radius_px=14):
    return mask.filter(ImageFilter.GaussianBlur(radius_px)).point(lambda v: 255 if v > 128 else 0)


def sunglasses(c):
    """Wayfarer shades: rounded trapezoid lenses, thick black frame, bridge, arms, glass reflections."""
    y_top, y_bot = 49.5, 61.5
    lenses = []
    for ex, side in ((EYE_L[0], -1), (EYE_R[0], 1)):
        outer, inner = ex + side * 10.5, ex - side * 7.5
        pts = [(inner, y_top + 0.5), (outer, y_top), (outer - side * 1.8, y_bot - 1.5), (ex + side * 2, y_bot + 0.5), (inner + side * 0.5, y_bot - 2.5)]
        lenses.append((ex, side, rounded(poly_mask(pts), 16)))
    frame = new_mask()
    for _, _, lm in lenses:
        frame = union(frame, lm.filter(ImageFilter.MaxFilter(23)))
    bridge = stroke_mask(arc_points(MOUTH[0], 53.5, 7.2, 2.2, 200, 340), 2.0)
    temples = union(stroke_mask([(EYE_L[0] - 10, 50.5), (EYE_L[0] - 15.5, 51.5)], 1.8),
                    stroke_mask([(EYE_R[0] + 10, 50.5), (EYE_R[0] + 15.5, 51.5)], 1.8))
    brow_bar = union(*[stroke_mask([(ex - side * 7.5, y_top - 0.3), (ex + side * 10.5, y_top - 0.8)], 2.4) for ex, side, _ in lenses])
    paint(c, union(frame, bridge, temples, brow_bar), (12, 12, 13), outline=(2, 2, 2), outline_px=5, light=(70, 72, 76), light_offset=(0, -5))
    # lenses: dark smoked glass, lighter at the top
    grad = Image.linear_gradient('L').resize(c.size)
    top, bottom = np.array((58, 72, 78), float), np.array((6, 9, 11), float)
    ramp = np.array(grad, float)[..., None] / 255.0
    glass_rgb = (top * (1 - ramp) + bottom * ramp).astype(np.uint8)
    for ex, side, lm in lenses:
        glass = Image.fromarray(np.dstack([glass_rgb, np.full(glass_rgb.shape[:2], 255, np.uint8)]), 'RGBA')
        c.paste(glass, (0, 0), lm)
        inner = lm.filter(ImageFilter.MinFilter(15))
        for (a, b, w, alpha) in (((ex - 6.5, 59.5), (ex - 1.5, 51.5), 1.3, 170), ((ex - 2.8, 60.5), (ex + 1.2, 54.0), 0.6, 120)):
            streak = ImageChops.multiply(stroke_mask([a, b], w), inner).point(lambda v, al=alpha: v * al // 255)
            c.paste(Image.new('RGBA', c.size, (235, 245, 250, 255)), (0, 0), streak)


def fall_lines(c):
    """Speed lines above Herbie: he is dropping."""
    for x, y0, y1 in ((40, 20, 30), (50, 16, 24), (97, 16, 25), (107, 20, 31), (74, 12, 20)):
        paint(c, stroke_mask([(x, y0), (x, y1)], 1.3), (238, 240, 226), outline=INK, outline_px=4)


def charge_spark(c, x=108, y=44):
    pts = [(x + 1.5, y - 6), (x - 2.5, y + 0.5), (x + 0.5, y + 0.5), (x - 1.5, y + 6), (x + 3, y - 1), (x, y - 1)]
    paint(c, poly_mask(pts), SPROUT, outline=INK, outline_px=5)


def shiver_marks(c):
    for side in (-1, 1):
        x = MOUTH[0] + side * 36
        for dy in (-4, 3):
            paint(c, stroke_mask([(x, 61 + dy), (x + side * 3, 63 + dy), (x, 65 + dy)], 1.1), (80, 150, 200))


# ---------------------------------------------------------------- hands (all built like the Facepalm hand)
_SLEEVE_TEX = {}


def sleeve_texture(scale):
    """Woven moss sleeve texture sampled from the original facepalm arm, tiled to the canvas."""
    key = round(scale, 3)
    if key not in _SLEEVE_TEX:
        arm = Image.open(TOOLS / 'sources' / 'facepalm_arm_old.png').convert('RGBA')
        patch = arm.crop((6, 34, 30, 54))
        a = np.array(patch)
        a[..., 3] = 255
        patch = Image.fromarray(a, 'RGBA').resize((round(24 * K * scale), round(20 * K * scale)), Image.LANCZOS)
        patch = patch.filter(ImageFilter.UnsharpMask(radius=5, percent=120, threshold=2))
        tex = Image.new('RGBA', (CW, CH))
        for ty in range(0, CH, patch.height):
            for tx in range(0, CW, patch.width):
                tex.paste(patch, (tx, ty))
        rgb = np.array(tex).astype(float)
        rgb[..., :3] *= 0.85
        _SLEEVE_TEX[key] = Image.fromarray(rgb.clip(0, 255).astype(np.uint8), 'RGBA')
    return _SLEEVE_TEX[key]


def leaf_hand(c, cx, cy, angle=0, scale=1.0, pose='open', flip=False):
    """Hand built like the facepalm hand: olive leaf glove with finger veins and a woven moss sleeve.
    pose: open | thumb_up | thumb_down | middle"""
    hand = Image.new('L', (int(s(40) * scale), int(s(62) * scale)), 0)
    veins = Image.new('L', hand.size, 0)
    hw, hh = hand.size
    d, dv = ImageDraw.Draw(hand), ImageDraw.Draw(veins)
    u = s(1) * scale
    px, py = hw / 2, hh * 0.46
    vw = max(2, int(0.9 * u))

    def finger(cx_, cy_, w, ln, ang):
        f = Image.new('L', (int(w * u), int(ln * u)), 0)
        ImageDraw.Draw(f).ellipse((0, 0, f.width, f.height), fill=255)
        f = f.rotate(-ang, resample=Image.BICUBIC, expand=True)
        hand.paste(f, (int(cx_ - f.width / 2), int(cy_ - f.height / 2)), f)
        dx, dy = math.sin(math.radians(ang)) * ln * 0.32 * u, -math.cos(math.radians(ang)) * ln * 0.32 * u
        dv.line([(cx_ - dx * 0.4, cy_ - dy * 0.4), (cx_ + dx, cy_ + dy)], fill=255, width=vw)

    if pose == 'open':
        d.ellipse((px - 9 * u, py - 8 * u, px + 9 * u, py + 8 * u), fill=255)
        for ang, ln in [(-38, 26), (-14, 30), (10, 29), (32, 25)]:
            fx = px + math.sin(math.radians(ang)) * 12 * u
            fy = py - math.cos(math.radians(ang)) * 12 * u
            finger(fx, fy, 8, ln, ang)
        finger(px - 12 * u, py + 1 * u, 7, 18, -58)
    else:
        d.rounded_rectangle((px - 9 * u, py - 7 * u, px + 9 * u, py + 9 * u), radius=int(6 * u), fill=255)   # fist
        if pose == 'middle':
            for kx in (-6, 6.5):                                                                              # folded knuckles
                d.ellipse((px + (kx - 3.2) * u, py - 10 * u, px + (kx + 3.2) * u, py - 3 * u), fill=255)
            finger(px + 0.3 * u, py - 14 * u, 7.2, 24, 0)                                                     # middle finger up
            d.ellipse((px - 8 * u, py + 1 * u, px + 3 * u, py + 6.5 * u), fill=255)                           # thumb across
            dv.line([(px - 7 * u, py + 3.8 * u), (px + 1.5 * u, py + 3.8 * u)], fill=255, width=vw)
        else:
            for k in range(4):                                                                                # knuckles
                d.ellipse((px + 3 * u, py - 7 * u + k * 4 * u, px + 11 * u, py - 2 * u + k * 4 * u), fill=255)
                dv.line([(px + 4 * u, py - 4.5 * u + k * 4 * u), (px + 8 * u, py - 4.5 * u + k * 4 * u)], fill=255, width=vw)
            finger(px - 3.5 * u, py - 13 * u, 7.5, 21, 0)                                                     # thumb up
    sleeve = Image.new('L', hand.size, 0)
    s_top, s_bot = py + 6 * u, min(hh, py + 24 * u)
    ImageDraw.Draw(sleeve).polygon([(px - 7.5 * u, s_top), (px + 7.5 * u, s_top), (px + 9 * u, s_bot), (px - 9 * u, s_bot)], fill=255)
    wraps = Image.new('L', hand.size, 0)      # diagonal wrap bands across the sleeve
    wd = ImageDraw.Draw(wraps)
    for k in range(5):
        y0 = s_top + (k + 0.6) * 3.6 * u
        wd.line([(px - 11 * u, y0 + 2 * u), (px + 11 * u, y0 - 2 * u)], fill=255, width=max(2, int(0.9 * u)))
    if flip:
        hand, veins, sleeve, wraps = (im.transpose(Image.FLIP_LEFT_RIGHT) for im in (hand, veins, sleeve, wraps))
    if pose == 'thumb_down':
        angle += 180
    hand, veins, sleeve, wraps = (im.rotate(angle, resample=Image.BICUBIC, expand=True) for im in (hand, veins, sleeve, wraps))
    ox, oy = int(s(cx) - hand.width / 2), int(s(cy) - hand.height / 2)
    hm, vm, sm, wm = new_mask(), new_mask(), new_mask(), new_mask()
    hm.paste(hand, (ox, oy), hand)
    vm.paste(veins, (ox, oy), veins)
    sm.paste(sleeve, (ox, oy), sleeve)
    wm.paste(wraps, (ox, oy), wraps)
    sm = subtract(sm, hm)
    paint(c, sm, SLEEVE, outline=HAND_DARK, outline_px=9, light=(118, 106, 36), light_offset=(-5, 0), shade=(52, 45, 10))
    wm = ImageChops.multiply(wm, sm.filter(ImageFilter.MinFilter(5)))
    c.paste(Image.new('RGBA', c.size, (44, 48, 10, 255)), (0, 0), wm.filter(ImageFilter.GaussianBlur(1)))
    rng = np.random.default_rng(int(cx * 10 + cy))                 # moss flecks, like the woven original
    fleck = np.zeros((CH, CW), np.uint8)
    ys, xs = np.nonzero(np.array(sm.filter(ImageFilter.MinFilter(7))) > 128)
    if len(xs):
        pick = rng.choice(len(xs), size=min(len(xs), 140), replace=False)
        for x_, y_ in zip(xs[pick], ys[pick]):
            fleck[max(0, y_ - 3):y_ + 3, max(0, x_ - 3):x_ + 3] = 200
    c.paste(Image.new('RGBA', c.size, (98, 104, 28, 255)), (0, 0), Image.fromarray(fleck).filter(ImageFilter.GaussianBlur(1.5)))
    paint(c, hm, HAND, outline=HAND_DARK, outline_px=11, light=HAND_LIGHT, light_offset=(-6, -8), shade=HAND_SHADE)
    vm = ImageChops.multiply(vm, hm.filter(ImageFilter.MinFilter(11)))
    c.paste(Image.new('RGBA', c.size, HAND_VEIN + (255,)), (0, 0), vm.filter(ImageFilter.GaussianBlur(1.2)))


def ground_mist(c, strength=0.55, seed=7):
    """Soft uneven mist over the leafy ground under the map."""
    rng = np.random.default_rng(seed)
    w, h = c.size
    noise = Image.fromarray((rng.random((24, 36)) * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(28))
    y = np.linspace(0, 1, h)[:, None]
    start = 88 * K / h                         # mist fades in from just above the map's bottom edge
    ramp = np.clip((y - start) / (1 - start), 0, 1) ** 0.8
    alpha = (ramp * (0.45 + 0.55 * np.array(noise, float) / 255) * strength * 255).astype(np.uint8)
    c.paste(Image.new('RGBA', c.size, (226, 234, 224, 255)), (0, 0), Image.fromarray(alpha))


def old_facepalm_arm(c, dx=3, dy=3, darken=0.85, flip=False, center=None, scale=1.0, angle=0):
    """The original facepalm arm + leaf hand, lifted from the first-pass art and placed on the new template."""
    arm = Image.open(TOOLS / 'sources' / 'facepalm_arm_old.png').convert('RGBA')
    ox, oy = json.loads((TOOLS / 'sources' / 'facepalm_arm_old.json').read_text())['origin_on_145x105_grid']
    arm = arm.resize((round(arm.width * K * scale), round(arm.height * K * scale)), Image.LANCZOS)
    arm = arm.filter(ImageFilter.UnsharpMask(radius=6, percent=140, threshold=2))  # source is 145x105-era art
    rgb = np.array(arm).astype(float)
    rgb[..., :3] *= darken
    arm = Image.fromarray(rgb.clip(0, 255).astype(np.uint8), 'RGBA')
    arm.putalpha(arm.getchannel('A').filter(ImageFilter.GaussianBlur(3)).point(lambda v: 0 if v < 40 else min(255, int(v * 1.25))))
    if flip:
        arm = arm.transpose(Image.FLIP_LEFT_RIGHT)
    if angle:
        arm = arm.rotate(angle, resample=Image.BICUBIC, expand=True)
    if center is None:
        c.alpha_composite(arm, (round(s(ox + dx)), round(s(oy + dy))))
    else:
        layer = Image.new('RGBA', c.size, (0, 0, 0, 0))
        layer.paste(arm, (round(s(center[0]) - arm.width / 2), round(s(center[1]) - arm.height / 2)), arm)
        c.alpha_composite(layer)


def battery_panel(c):
    """Low battery: dark panel with a red battery outline and one low red bar (face hidden)."""
    panel = rounded(poly_mask([(47, 44), (101, 44), (101, 80), (47, 80)]), 30)
    paint(c, panel, (24, 28, 26), outline=(6, 8, 7), outline_px=9, light=(60, 66, 62), light_offset=(0, -6))
    body = subtract(rounded(poly_mask([(55, 52), (90, 52), (90, 72), (55, 72)]), 10), rounded(poly_mask([(56.8, 53.8), (88.2, 53.8), (88.2, 70.2), (56.8, 70.2)]), 8))
    red = (222, 64, 52)
    paint(c, body, red)
    paint(c, rounded(poly_mask([(90, 58), (93, 58), (93, 66), (90, 66)]), 6), red)
    paint(c, rounded(poly_mask([(58.5, 55.5), (64.5, 55.5), (64.5, 68.5), (58.5, 68.5)]), 6), red, light=(255, 150, 130), light_offset=(0, -5))


def radar_scan(img, sweep_deg=-30):
    """Scanning: the whole face in radar green with range rings, crosshair, grid and a sweep."""
    arr = np.array(img.convert('RGB')).astype(float)
    lum = (arr @ np.array([0.3, 0.55, 0.15])) / 255.0
    lum = lum ** 0.9
    dark, bright = np.array((4, 30, 10), float), np.array((168, 255, 120), float)
    out = Image.fromarray((dark + lum[..., None] * (bright - dark)).clip(0, 255).astype(np.uint8)).convert('RGBA')
    w, h = out.size
    cx, cy = w * 0.5, h * 0.47
    over = Image.new('RGBA', out.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    for gx in range(0, w, 20):
        d.line([(gx, 0), (gx, h)], fill=(120, 255, 120, 26))
    for gy in range(0, h, 20):
        d.line([(0, gy), (w, gy)], fill=(120, 255, 120, 26))
    for r in (26, 56, 86, 116):
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(150, 255, 140, 120), width=2)
    d.line([(cx - 128, cy), (cx + 128, cy)], fill=(170, 255, 150, 150), width=2)
    d.line([(cx, cy - 118), (cx, cy + 118)], fill=(170, 255, 150, 150), width=2)
    sweep = Image.new('L', out.size, 0)
    sd = ImageDraw.Draw(sweep)
    for k in range(40):
        a0 = sweep_deg - 40 + k
        sd.pieslice((cx - 130, cy - 130, cx + 130, cy + 130), a0, a0 + 1.2, fill=int(4 + k * 3.2))
    over.paste(Image.new('RGBA', out.size, (170, 255, 140, 255)), (0, 0), sweep.filter(ImageFilter.GaussianBlur(2)))
    d.line([(cx, cy), (cx + 130 * math.cos(math.radians(sweep_deg)), cy + 130 * math.sin(math.radians(sweep_deg)))], fill=(220, 255, 200, 220), width=2)
    d.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=(220, 255, 200, 230))
    out.alpha_composite(over)
    return out


# ---------------------------------------------------------------- the face set
def eyes(c, kind='open', **kw):
    if kind == 'open':
        eye_open(c, EYE_L, **kw); eye_open(c, EYE_R, **kw)
    elif kind == 'happy':
        eye_arc(c, EYE_L, up=True); eye_arc(c, EYE_R, up=True)
    elif kind == 'closed':
        eye_arc(c, EYE_L, up=False); eye_arc(c, EYE_R, up=False)


FACES = {
    'neutral':      lambda c: (eyes(c), mouth_smile(c)),
    'happy':        lambda c: (eyes(c, 'happy'), mouth_smile(c, width=24, depth=6)),
    'excited':      lambda c: (eyes(c, scale=1.15), mouth_grin(c)),
    'curious':      lambda c: (eyes(c, look=(0, -2)), brow(c, EYE_R, 2, lift=2, side='R'), mouth_o(c, 2.4, 2.8)),
    'thinking':     lambda c: (eyes(c, look=(2, -3)), brow(c, EYE_L, -1, side='L'), mouth_flat(c, 10, dy=1)),
    'side-eye':     lambda c: (eyes(c, look=(3, 0), lid='half'), mouth_flat(c, 12)),
    'suspicious':   lambda c: (eye_open(c, EYE_L, lid='half', look=(-2, 0)), eye_open(c, EYE_R, lid='angry', lid_side='R', look=(-2, 0)), mouth_smirk(c)),
    'confused':     lambda c: (eye_open(c, EYE_L, scale=0.9), eye_open(c, EYE_R, scale=1.1), brow(c, EYE_R, -2, lift=2, side='R'), mouth_wavy(c, 14), question(c)),
    'surprised':    lambda c: (eyes(c, scale=1.2), brow(c, EYE_L, 0, lift=3), brow(c, EYE_R, 0, lift=3, side='R'), mouth_o(c, 3.4, 4.4)),
    'worried':      lambda c: (eye_open(c, EYE_L, lid='sad', lid_side='L'), eye_open(c, EYE_R, lid='sad', lid_side='R'), brow(c, EYE_L, 3), brow(c, EYE_R, 3, side='R'), mouth_wavy(c)),
    'sad':          lambda c: (eye_open(c, EYE_L, lid='sad', lid_side='L', look=(0, 2)), eye_open(c, EYE_R, lid='sad', lid_side='R', look=(0, 2)), mouth_frown(c)),
    'angry':        lambda c: (eye_open(c, EYE_L, lid='angry', lid_side='L'), eye_open(c, EYE_R, lid='angry', lid_side='R'), brow(c, EYE_L, -3), brow(c, EYE_R, -3, side='R'), mouth_frown(c, 14, 3)),
    'annoyed':      lambda c: (eyes(c, lid='half', look=(0, 1)), brow(c, EYE_L, -1), mouth_flat(c, 12, dy=1)),
    'tired':        lambda c: (eyes(c, lid='half', look=(0, 2)), mouth_wavy(c, 12, 1.0)),
    'yawning':      lambda c: (eyes(c, 'closed'), mouth_o(c, 4.2, 6, dy=1), zzz(c) if False else None),
    'determined':   lambda c: (eye_open(c, EYE_L, lid='angry', lid_side='L'), eye_open(c, EYE_R, lid='angry', lid_side='R'), mouth_flat(c, 16)),
    'sleepy':       lambda c: (eyes(c, 'closed'), mouth_smile(c, 12, 2.5), zzz(c)),
    'blushing':     lambda c: (eyes(c, look=(0, 1)), blush(c), mouth_smile(c, 16, 3.5)),
    'laughing':     lambda c: (eyes(c, 'happy'), mouth_grin(c, 24, 10)),
    'cheeky':       lambda c: (eye_arc(c, EYE_L, up=True), eye_open(c, EYE_R), mouth_tongue(c)),
    'focused':      lambda c: (eye_target(c, EYE_L), eye_target(c, EYE_R), mouth_flat(c, 12)),
    'wow':          lambda c: (eye_star(c, EYE_L), eye_star(c, EYE_R), mouth_o(c, 3.2, 4)),
    'love':         lambda c: (eye_heart(c, EYE_L), eye_heart(c, EYE_R), mouth_smile(c, 20, 5)),
    'grateful':     lambda c: (eyes(c, 'happy'), blush(c, 110), mouth_smile(c, 16, 3.5)),
    'party-mode':   lambda c: (sunglasses(c), mouth_grin(c, 22, 8)),
    'high-af':      lambda c: (ground_mist(c), eye_open(c, EYE_L, lid='half', look=(0, 4.5), red=True), eye_open(c, EYE_R, lid='half', look=(0, 4.5), red=True), mouth_smile(c, 18, 3)),
    'chillin':      lambda c: (sunglasses(c), mouth_smile(c, 14, 2.6)),
    'meditating':   lambda c: (eyes(c, 'closed'), mouth_smile(c, 10, 2)),
    'bored':        lambda c: (eyes(c, lid='half', look=(-2, 1)), mouth_flat(c, 10, dy=1)),
    'melting':      lambda c: (eyes(c, lid='sad', lid_side='L', look=(0, 2)), mouth_tongue(c), sweat(c, 108, 48), sweat(c, 38, 50)),
    'sweating':     lambda c: (eyes(c, lid='sad', lid_side='L'), mouth_wavy(c, 14), sweat(c)),
    'overwhelmed':  lambda c: (eye_spiral(c, EYE_L), eye_spiral(c, EYE_R), mouth_wavy(c, 18, 2)),
    'greetings':    lambda c: (eyes(c, 'happy'), mouth_smile(c, 22, 6), old_facepalm_arm(c, flip=True, center=(121, 72), scale=0.82, angle=-6)),
    'wink':         lambda c: (eye_open(c, EYE_L), eye_arc(c, EYE_R, up=True), mouth_smile(c, 20, 5)),
    'thumbs-up':    lambda c: (eyes(c), mouth_smile(c, 20, 5), leaf_hand(c, 116, 74, angle=-8, scale=0.62, pose='thumb_up')),
    'thumbs-down':  lambda c: (eye_open(c, EYE_L, lid='sad', lid_side='L'), eye_open(c, EYE_R, lid='sad', lid_side='R'), mouth_frown(c), leaf_hand(c, 116, 62, angle=8, scale=0.62, pose='thumb_down')),
    'facepalm':     lambda c: (eye_open(c, EYE_R, lid='half'), mouth_flat(c, 10, dy=1), old_facepalm_arm(c)),
    'oh-no':        lambda c: (eyes(c, scale=1.2, look=(0, 1)), brow(c, EYE_L, 3, lift=2), brow(c, EYE_R, 3, lift=2, side='R'), mouth_o(c, 4.2, 5.2)),
    'face-with-tears': lambda c: (eye_arc(c, EYE_L, up=False), eye_arc(c, EYE_R, up=False), brow(c, EYE_L, 3), brow(c, EYE_R, 3, side='R'), tear_streams(c), mouth_wobble(c)),
    'party-hard':   lambda c: (eye_squeeze(c, EYE_L, 'L'), eye_squeeze(c, EYE_R, 'R'), mouth_grin(c, 26, 11), old_facepalm_arm(c, flip=True, center=(121, 66), scale=0.82, angle=-16)),
    # New faces for features added since the original set.
    'gps-searching': lambda c: (eyes(c, look=(-2, -3)), brow(c, EYE_L, 2, lift=1), mouth_o(c, 2.2, 2.4)),
    'gps-locked':   lambda c: (eye_reticle(c, EYE_L), eye_reticle(c, EYE_R), mouth_smile(c, 22, 5)),
    'falling':      lambda c: (eyes(c, scale=1.55, look=(0, -3.5)), brow(c, EYE_L, 5, lift=8), brow(c, EYE_R, 5, lift=8, side='R'), mouth_wail(c, 18, 13), sweat(c, 110, 40), sweat(c, 36, 42), fall_lines(c)),
    'middle-finger': lambda c: (eye_open(c, EYE_L, lid='half', look=(0, 1)), eye_open(c, EYE_R, lid='angry', lid_side='R', look=(0, 1)), mouth_smirk(c), leaf_hand(c, 116, 66, angle=-4, scale=0.78, pose='middle')),
    'off-route':    lambda c: (eyes(c, look=(3, 1), lid='sad', lid_side='R'), brow(c, EYE_R, 3, side='R'), mouth_wavy(c, 16)),
    'thirsty':      lambda c: (eyes(c, lid='half', look=(0, 2)), mouth_tongue(c, 14), sweat(c, 108, 48)),
    'cold':         lambda c: (eye_squeeze(c, EYE_L, 'L'), eye_squeeze(c, EYE_R, 'R'), mouth_zigzag(c), shiver_marks(c)),
    'storm-alert':  lambda c: (eyes(c, scale=1.25), brow(c, EYE_L, 3, lift=3), brow(c, EYE_R, 3, lift=3, side='R'), mouth_flat(c, 10, dy=1)),
    'storm-alert-2': lambda c: (eyes(c, scale=1.35, look=(0, -1)), brow(c, EYE_L, 4, lift=5), brow(c, EYE_R, 4, lift=5, side='R'), mouth_wavy(c, 14, 1.8), sweat(c)),
    'storm-alert-3': lambda c: (eyes(c, scale=1.5, look=(0, -1.5)), brow(c, EYE_L, 5, lift=7), brow(c, EYE_R, 5, lift=7, side='R'), mouth_wail(c, 12, 10), sweat(c), sweat(c, 38, 46), shiver_marks(c)),
    'face-with-tears-2': lambda c: (eye_arc(c, EYE_L, up=False), eye_arc(c, EYE_R, up=False), brow(c, EYE_L, 4, lift=1), brow(c, EYE_R, 4, lift=1, side='R'), tear_streams(c), mouth_wail(c, 12, 8)),
    'face-with-tears-3': lambda c: (eye_squeeze(c, EYE_L, 'L'), eye_squeeze(c, EYE_R, 'R'), brow(c, EYE_L, 5, lift=2), brow(c, EYE_R, 5, lift=2, side='R'), big_tears(c), mouth_wail(c, 16, 11)),
    'worried-2':    lambda c: (eye_open(c, EYE_L, lid='sad', lid_side='L', scale=1.1), eye_open(c, EYE_R, lid='sad', lid_side='R', scale=1.1), brow(c, EYE_L, 4, lift=2), brow(c, EYE_R, 4, lift=2, side='R'), mouth_wavy(c, 18, 2), sweat(c)),
    'worried-3':    lambda c: (eyes(c, scale=1.25, look=(0, 1)), brow(c, EYE_L, 5, lift=4), brow(c, EYE_R, 5, lift=4, side='R'), mouth_zigzag(c, 16, 2), sweat(c), sweat(c, 38, 46)),
    'angry-2':      lambda c: (eye_open(c, EYE_L, lid='angry', lid_side='L', scale=0.95), eye_open(c, EYE_R, lid='angry', lid_side='R', scale=0.95), brow(c, EYE_L, -4.5), brow(c, EYE_R, -4.5, side='R'), mouth_teeth(c)),
    'angry-3':      lambda c: (blush(c, 230, (214, 52, 40)), eye_open(c, EYE_L, lid='angry', lid_side='L', scale=0.9), eye_open(c, EYE_R, lid='angry', lid_side='R', scale=0.9), brow(c, EYE_L, -5.5), brow(c, EYE_R, -5.5, side='R'), mouth_wail(c, 16, 10)),
    'sad-2':        lambda c: (eye_open(c, EYE_L, lid='sad', lid_side='L', look=(0, 2.5)), eye_open(c, EYE_R, lid='sad', lid_side='R', look=(0, 2.5)), brow(c, EYE_L, 3), brow(c, EYE_R, 3, side='R'), mouth_frown(c, 16, 4), tear_drop(c, EYE_R[0] + 1, 66, 1.0)),
    'sad-3':        lambda c: (eye_open(c, EYE_L, lid='sad', lid_side='L', look=(0, 3)), eye_open(c, EYE_R, lid='sad', lid_side='R', look=(0, 3)), brow(c, EYE_L, 4), brow(c, EYE_R, 4, side='R'), mouth_wobble(c, 16), tear_drop(c, EYE_L[0] - 1, 66, 1.0), tear_drop(c, EYE_R[0] + 1, 68, 1.2)),
    'laughing-2':   lambda c: (eye_squeeze(c, EYE_L, 'L'), eye_squeeze(c, EYE_R, 'R'), mouth_grin(c, 26, 11)),
    'laughing-3':   lambda c: (eye_squeeze(c, EYE_L, 'L'), eye_squeeze(c, EYE_R, 'R'), mouth_grin(c, 28, 12), tear_drop(c, EYE_L[0] - 8, 58, 1.0), tear_drop(c, EYE_R[0] + 8, 58, 1.0)),
    'surprised-2':  lambda c: (eyes(c, scale=1.35), brow(c, EYE_L, 0, lift=5), brow(c, EYE_R, 0, lift=5, side='R'), mouth_o(c, 4.2, 5.6)),
    'surprised-3':  lambda c: (eyes(c, scale=1.5), brow(c, EYE_L, 1, lift=7), brow(c, EYE_R, 1, lift=7, side='R'), mouth_o(c, 5.2, 7.2, dy=1), sweat(c)),
    'cold-2':       lambda c: (blush(c, 200, (110, 160, 226)), eye_squeeze(c, EYE_L, 'L'), eye_squeeze(c, EYE_R, 'R'), mouth_zigzag(c, 20, 2.2), shiver_marks(c)),
    'cold-3':       lambda c: (blush(c, 255, (96, 150, 230)), eye_open(c, EYE_L, lid='sad', lid_side='L'), eye_open(c, EYE_R, lid='sad', lid_side='R'), mouth_teeth(c, 20), shiver_marks(c), zzz(c) if False else None),
    'summit':       lambda c: (eyes(c, 'happy'), mouth_grin(c, 24, 9), leaf_hand(c, 116, 50, angle=-8, scale=0.6, pose='thumb_up')),
    'charging':     lambda c: (eye_arc(c, EYE_L, up=False), eye_open(c, EYE_R, lid='half'), mouth_smile(c, 18, 4), charge_spark(c)),
}

LABELS = {'high-af': 'high AF', 'oh-no': 'oh no!', 'face-with-tears': 'face with tears', 'gps-searching': 'GPS searching',
          'gps-locked': 'GPS locked', 'off-route': 'off route', 'storm-alert': 'storm alert', 'party-mode': 'party mode',
          'party-hard': 'party hard', 'side-eye': 'side eye', 'thumbs-up': 'thumbs up', 'thumbs-down': 'thumbs down',
          'middle-finger': 'middle finger', 'falling': "I'm falling"}
# Stronger versions: <name>-2 / <name>-3 escalate the same expression.
LEVELS = {base: [base, f'{base}-2', f'{base}-3'] for base in ('storm-alert', 'face-with-tears', 'worried', 'angry', 'sad', 'laughing', 'surprised', 'cold')}
LABELS.update({f'{b}-{n}': f"{LABELS.get(b, b.replace('-', ' '))} {'(strong)' if n == 2 else '(extreme)'}" for b in LEVELS for n in (2, 3)})

# Event groups: when something happens Herbie picks from the whole group (and a gaze) instead of one face.
GROUPS = {
    'idle':          ['neutral', 'happy', 'curious', 'wink', 'chillin', 'grateful', 'thinking', 'excited'],
    'morning':       ['greetings', 'happy', 'excited', 'thumbs-up'],
    'day':           ['happy', 'curious', 'neutral', 'wink', 'excited'],
    'evening':       ['chillin', 'meditating', 'grateful', 'happy'],
    'night':         ['sleepy', 'yawning', 'meditating', 'tired'],
    'gps-searching': ['gps-searching', 'thinking', 'curious', 'focused'],
    'gps-locked':    ['gps-locked', 'determined', 'thumbs-up', 'happy'],
    'navigating':    ['focused', 'determined', 'curious', 'gps-locked'],
    'off-route':     ['off-route', 'confused', 'worried', 'oh-no'],
    'low-battery':   ['tired', 'worried', 'sweating'],
    'charging':      ['charging', 'meditating', 'grateful', 'happy'],
    'hot':           ['sweating', 'melting', 'thirsty', 'chillin'],
    'cold':          ['cold', 'cold-2', 'tired', 'sad'],
    'freezing':      ['cold-2', 'cold-3', 'worried-2'],
    'storm':         ['storm-alert', 'worried', 'oh-no', 'surprised'],
    'storm-watch':   ['storm-alert', 'worried', 'surprised'],
    'storm-warning': ['storm-alert-2', 'worried-2', 'oh-no', 'surprised-2'],
    'storm-danger':  ['storm-alert-3', 'worried-3', 'surprised-3'],
    'crying':        ['face-with-tears', 'face-with-tears-2', 'face-with-tears-3', 'sad-3'],
    'upset':         ['sad', 'sad-2', 'worried-2', 'face-with-tears'],
    'furious':       ['angry', 'angry-2', 'angry-3'],
    'summit':        ['summit', 'party-hard', 'excited', 'love', 'laughing', 'laughing-2'],
    'jolt':          ['surprised', 'oh-no', 'wow'],
    'dropped':       ['falling', 'oh-no', 'surprised-3'],
    'oops':          ['facepalm', 'thumbs-down', 'annoyed', 'face-with-tears'],
    'party':         ['party-mode', 'party-hard', 'laughing', 'laughing-3', 'cheeky'],
    'four-twenty':   ['high-af', 'chillin', 'laughing'],
    'rude':          ['middle-finger', 'annoyed', 'side-eye'],
}

def _shake(dl, dr, look_l, look_r):
    def draw(c):
        l, r = (EYE_L[0] + dl[0], EYE_L[1] + dl[1]), (EYE_R[0] + dr[0], EYE_R[1] + dr[1])
        eye_open(c, l, scale=1.2, look=look_l)
        eye_open(c, r, scale=1.2, look=look_r)
        brow(c, l, 0, lift=3)
        brow(c, r, 0, lift=3, side='R')
        mouth_o(c, 3.4, 4.4)
    return draw


def _bounce(dy, look_y):
    def draw(c):
        eye_open(c, (EYE_L[0], EYE_L[1] + dy), scale=1.15, look=(0, look_y))
        eye_open(c, (EYE_R[0], EYE_R[1] + dy), scale=1.15, look=(0, look_y))
        mouth_grin(c)
    return draw


def _split_scan(reticle_side):
    def draw(c):
        # one normal eye, the other the crosshair target eye used in scanning-2 (the focused face)
        if reticle_side == 'R':
            eye_open(c, EYE_L)
            eye_target(c, EYE_R)
        else:
            eye_target(c, EYE_L)
            eye_open(c, EYE_R)
        mouth_flat(c, 12)
    return draw


# Frames that only exist as motions (not listed as expressions).
MOTION_FACES = {
    'shake-1': _shake((-1.8, -1.2), (1.6, 1.2), (-1.5, 0), (1.5, 1)),
    'shake-2': _shake((1.6, 0.8), (-1.2, -1.6), (1.5, -1), (-1.5, 0)),
    'shake-3': _shake((0.2, 1.8), (0.8, -1.2), (0, 1.5), (0.5, -1.5)),
    'bounce-1': _bounce(-2.6, -2),
    'bounce-2': _bounce(0, 0),
    'bounce-3': _bounce(2.6, 2),
    'scan-reticle-right': _split_scan('R'),
    'scan-reticle-left': _split_scan('L'),
}

# (base face or motion frame, rotation / radar sweep). Tilt levels show at Sense HAT tilt >= 8 / 18 / 30 degrees.
MOTIONS = {
    'tilted-left':    ('curious', 6),
    'tilted-left-2':  ('oh-no', 24),
    'tilted-left-3':  ('falling', 40),
    'tilted-right':   ('curious', -6),
    'tilted-right-2': ('oh-no', -24),
    'tilted-right-3': ('falling', -40),
    'shaking':        ('shake-1', None),
    'shaking-2':      ('shake-2', None),
    'shaking-3':      ('shake-3', None),
    'bouncing':       ('bounce-1', None),
    'bouncing-2':     ('bounce-2', None),
    'bouncing-3':     ('bounce-3', None),
    'happy-hover':    ('happy', None),
    'happy-hover-2':  ('grateful', None),
    'happy-hover-3':  ('love', None),
    'spinning':       ('overwhelmed', None),
    'spinning-2':     ('overwhelmed', 15),
    'spinning-3':     ('overwhelmed', 30),
    'spinning-4':     ('overwhelmed', -15),
    'spinning-5':     ('overwhelmed', -30),
    'scanning':       ('neutral', -30),
    'scanning-2':     ('focused', 90),
    'scanning-3':     ('gps-searching', 210),
    'scanning-4':     ('scan-reticle-right', 30),
    'scanning-5':     ('scan-reticle-left', 150),
    'low-battery':    ('tired', None),
}
TILT_THRESHOLDS = (8, 18, 30)
# Frame order for looping motions ('' = the base frame). Spinning rocks both ways; scanning sweeps round.
MOTION_SEQUENCES = {
    'spinning':    ['', '-2', '-3', '-2', '', '-4', '-5', '-4'],
    'scanning':    ['', '-4', '-2', '-5', '-3'],
    'shaking':     ['', '-2', '-3'],
    'bouncing':    ['', '-2', '-3', '-2'],
    'happy-hover': ['', '-2', '-3'],
}


def render_face(template, name, draw=None):
    big = template.resize((CW, CH), Image.LANCZOS)
    (draw or FACES[name])(big)
    return big.resize((OUT_W, OUT_H), Image.LANCZOS)


def on_background(img, angle=None, ghost=False):
    canvas = Image.new('RGBA', (OUT_W, OUT_H), BG_DARK + (255,))
    face = img
    if angle:
        face = img.resize((int(OUT_W * 0.9), int(OUT_H * 0.9)), Image.LANCZOS).rotate(angle, resample=Image.BICUBIC, expand=True)
    if ghost:
        for dx, a in ((-6, 70), (6, 70)):
            g = face.copy(); g.putalpha(g.getchannel('A').point(lambda v: v * a // 255))
            canvas.alpha_composite(g, ((OUT_W - face.width) // 2 + dx, (OUT_H - face.height) // 2))
    canvas.alpha_composite(face, ((OUT_W - face.width) // 2, (OUT_H - face.height) // 2))
    return canvas


# On the expanded sheet. left / back / right are for menu-opening animations.
TURNAROUND_BOXES = {'top': (905, 875, 1060, 988), 'bottom': (1060, 875, 1205, 988),
                    'left': (490, 889, 612, 986), 'back': (612, 889, 762, 986), 'right': (770, 889, 905, 986)}


def center_turnaround(name):
    """Turnaround views cut from the character sheet, background faded out, centered on the canvas."""
    sheet = Image.open(SRC / 'herbie-character-sheet-expanded.png').convert('RGB')
    src = sheet.crop(TURNAROUND_BOXES[name])
    arr = np.array(src).astype(np.int16)
    maxc = arr.max(axis=2)
    # Solid silhouette: anything brighter than the sheet ground, closed and hole-filled, so dark wood stays opaque.
    solid = ((maxc > 30) * 255).astype(np.uint8)
    solid = cv2.morphologyEx(solid, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    flood = solid.copy()
    cv2.floodFill(flood, np.zeros((solid.shape[0] + 2, solid.shape[1] + 2), np.uint8), (0, 0), 255)
    solid = solid | cv2.bitwise_not(flood)
    solid = cv2.morphologyEx(solid, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    alpha = solid
    ys, xs = np.where(alpha > 128)
    rgba = src.convert('RGBA')
    rgba.putalpha(Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(0.8)))
    crop = rgba.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    scale = min(OUT_W * 0.88 / crop.width, OUT_H * 0.88 / crop.height)
    crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.LANCZOS)
    canvas = Image.new('RGBA', (OUT_W, OUT_H), BG_DARK + (255,))
    canvas.alpha_composite(crop, ((OUT_W - crop.width) // 2, (OUT_H - crop.height) // 2))
    return canvas


def save_png(img, path):
    """256-colour palette PNG (dithered): about a third of the size of full RGB for this painted art."""
    img.convert('RGB').quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG).save(path, optimize=True)


def main(preview=False):
    TOOLS.mkdir(parents=True, exist_ok=True)
    template = build_template()
    template.save(TOOLS / 'template.png')
    gazes = {}
    for g in GAZES:
        set_gaze(g)
        gazes[g] = {name: render_face(template, name) for name in FACES}
    set_gaze('center')
    faces = gazes['center']
    motions = {}
    frames = {k: render_face(template, k, draw=f) for k, f in MOTION_FACES.items()}
    frames.update(faces)
    for name, (base, angle) in MOTIONS.items():
        if name.startswith('scanning'):
            motions[name] = radar_scan(frames[base], sweep_deg=angle)
        elif name == 'low-battery':
            motions[name] = render_face(template, name, draw=battery_panel)
        else:
            motions[name] = on_background(frames[base], angle=angle, ghost=name.startswith('shaking'))
    turns = {n: center_turnaround(n) for n in TURNAROUND_BOXES}

    if '--dry' not in sys.argv:
        for g, set_ in gazes.items():
            for name, img in set_.items():
                save_png(img, OUT / 'expressions' / (f'{name}.png' if g == 'center' else f'{name}-{g}.png'))
        for name, img in motions.items():
            save_png(img, OUT / 'motions' / f'{name}.png')
        for name, img in turns.items():
            save_png(img, OUT / 'turnarounds' / f'{name}.png')
        manifest = json.loads((SRC / 'manifest.json').read_text())
        manifest['size'] = [OUT_W, OUT_H]
        manifest['expressions'] = {n: f'/assets/herbie/expressions/{n}.png' for n in FACES}
        manifest['labels'] = {n: LABELS.get(n, n.replace('-', ' ')) for n in FACES}
        manifest['motions'] = {n: f'/assets/herbie/motions/{n}.png' for n in MOTIONS}
        manifest['turnarounds'] = {n: f'/assets/herbie/turnarounds/{n}.png' for n in TURNAROUND_BOXES}
        manifest['gazes'] = list(GAZES)
        manifest['gaze_pattern'] = '/assets/herbie/expressions/{name}-{gaze}.png'
        manifest['groups'] = GROUPS
        manifest['levels'] = LEVELS
        manifest['tilt_thresholds'] = list(TILT_THRESHOLDS)
        manifest['motion_sequences'] = MOTION_SEQUENCES
        manifest['motion_variants'] = {b: [m for m in MOTIONS if m == b or m.startswith(b + '-') and m[len(b) + 1:].isdigit()] for b in MOTIONS if not b[-1].isdigit()}
        (SRC / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')

    if preview:
        items = list(faces.items()) + list(motions.items()) + list(turns.items())
        cols = 8
        cell_w, cell_h = OUT_W, OUT_H + 22
        rows = math.ceil(len(items) / cols)
        sheet = Image.new('RGBA', (cols * (cell_w + 8) + 8, rows * (cell_h + 8) + 8), (24, 30, 26, 255))
        d = ImageDraw.Draw(sheet)
        for i, (name, img) in enumerate(items):
            x = 8 + (i % cols) * (cell_w + 8)
            y = 8 + (i // cols) * (cell_h + 8)
            sheet.alpha_composite(img, (x, y))
            d.text((x + 4, y + OUT_H + 5), name, fill=(220, 235, 210, 255))
        sheet.save(TOOLS / 'preview_sheet.png')
    print(f'faces={len(faces)} motions={len(motions)} turnarounds={len(turns)} size={OUT_W}x{OUT_H}')


if __name__ == '__main__':
    main(preview='--preview' in sys.argv)
