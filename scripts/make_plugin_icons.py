"""Generates icons for history_today, joke_of_day, moon_phase, top_stories plugins."""
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PIL import Image, ImageDraw
import numpy as np

SIZE = 512
BLACK = (0, 0, 0, 255)
CLEAR = (0, 0, 0, 0)
CX = CY = SIZE // 2
PLUGINS_DIR = os.path.join(os.path.dirname(__file__), '..', 'src', 'plugins')


def canvas():
    return Image.new("RGBA", (SIZE, SIZE), CLEAR)


def save(im, plugin_id):
    path = os.path.join(PLUGINS_DIR, plugin_id, 'icon.png')
    im.save(path)
    print(f"Saved {path}")


# ── History Today: Hourglass ───────────────────────────────────────────────
def make_history_today():
    im = canvas()
    d = ImageDraw.Draw(im)
    pad, waist, bar = 75, 42, 32

    # Top trapezoid (wide at top, narrows to waist at center)
    d.polygon([
        (pad,        pad + bar),
        (SIZE - pad, pad + bar),
        (CX + waist, CY),
        (CX - waist, CY),
    ], fill=BLACK)

    # Bottom trapezoid (widens from waist to bottom)
    d.polygon([
        (CX - waist, CY),
        (CX + waist, CY),
        (SIZE - pad, SIZE - pad - bar),
        (pad,        SIZE - pad - bar),
    ], fill=BLACK)

    # Top bar
    d.rectangle([pad - 12, pad, SIZE - pad + 12, pad + bar], fill=BLACK)
    # Bottom bar
    d.rectangle([pad - 12, SIZE - pad - bar, SIZE - pad + 12, SIZE - pad], fill=BLACK)

    # Small sand pile at bottom (triangle punch-out in top half to imply sand)
    # Sand pile in lower half: small white triangle at the waist pointing down
    sand_w = 55
    sand_h = 80
    d.polygon([
        (CX - sand_w, SIZE - pad - bar - 2),
        (CX + sand_w, SIZE - pad - bar - 2),
        (CX,          SIZE - pad - bar - 2 - sand_h),
    ], fill=CLEAR)

    return im


# ── Joke of Day: Speech Bubble ─────────────────────────────────────────────
def make_joke_of_day():
    im = canvas()
    d = ImageDraw.Draw(im)

    pad = 55
    bubble_bot = int(SIZE * 0.68)

    # Bubble body
    d.rounded_rectangle([pad, pad, SIZE - pad, bubble_bot], radius=65, fill=BLACK)

    # Triangle tail (bottom-left)
    d.polygon([
        (pad + 55,  bubble_bot - 2),
        (pad + 55,  bubble_bot + 100),
        (pad + 160, bubble_bot - 2),
    ], fill=BLACK)

    # Three text-line punch-outs inside the bubble
    lpad = pad + 60
    for i, ly in enumerate([int(SIZE * 0.28), int(SIZE * 0.43), int(SIZE * 0.57)]):
        rpad = SIZE - pad - 60 if i < 2 else SIZE - pad - 140  # last line shorter
        d.rounded_rectangle([lpad, ly - 17, rpad, ly + 17], radius=17, fill=CLEAR)

    return im


# ── Moon Phase: Crescent ───────────────────────────────────────────────────
def make_moon_phase():
    pad = 58
    r_outer = CX - pad
    offset  = int(r_outer * 0.42)
    r_inner = int(r_outer * 0.88)

    y_arr, x_arr = np.ogrid[:SIZE, :SIZE]
    outer   = (x_arr - CX) ** 2 + (y_arr - CY) ** 2 <= r_outer ** 2
    inner   = (x_arr - (CX + offset)) ** 2 + (y_arr - CY) ** 2 <= r_inner ** 2

    crescent = outer & ~inner
    pixels = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
    pixels[crescent] = [0, 0, 0, 255]
    return Image.fromarray(pixels, 'RGBA')


# ── Top Stories: Newspaper ─────────────────────────────────────────────────
def make_top_stories():
    im = canvas()
    d = ImageDraw.Draw(im)

    pad    = 55
    radius = 28
    col    = SIZE // 2 - 8   # x-position of column divider
    lpad   = pad + 38        # left content padding
    rpad   = SIZE - pad - 38 # right content padding

    # Newspaper body
    d.rounded_rectangle([pad, pad, SIZE - pad, SIZE - pad], radius=radius, fill=BLACK)

    # Headline punch-out (full width, tall bar)
    d.rounded_rectangle([lpad, pad + 38, rpad, pad + 112], radius=14, fill=CLEAR)

    # Two-column text lines
    gap = 14  # gap between columns
    for ly in [int(SIZE * 0.46), int(SIZE * 0.56), int(SIZE * 0.66), int(SIZE * 0.76)]:
        d.rounded_rectangle([lpad,      ly - 14, col - gap, ly + 14], radius=14, fill=CLEAR)
        d.rounded_rectangle([col + gap, ly - 14, rpad,      ly + 14], radius=14, fill=CLEAR)

    # Bottom shorter lines
    ly = int(SIZE * 0.86)
    d.rounded_rectangle([lpad,            ly - 14, col - gap - 30,  ly + 14], radius=14, fill=CLEAR)
    d.rounded_rectangle([col + gap,       ly - 14, rpad - 30,       ly + 14], radius=14, fill=CLEAR)

    return im


if __name__ == '__main__':
    save(make_history_today(), 'history_today')
    save(make_joke_of_day(),   'joke_of_day')
    save(make_moon_phase(),    'moon_phase')
    save(make_top_stories(),   'top_stories')
    print("Done.")
