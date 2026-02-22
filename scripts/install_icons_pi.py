"""
Run this on the Raspberry Pi to generate missing plugin icons.
Usage:
    sudo /usr/local/inkypi/venv_inkypi/bin/python3 install_icons_pi.py
or:
    python3 install_icons_pi.py
"""
import os
import math
import sys

try:
    from PIL import Image, ImageDraw
    import numpy as np
except ImportError:
    sys.exit("Pillow/numpy not found. Run with the InkyPi venv:\n"
             "  sudo /usr/local/inkypi/venv_inkypi/bin/python3 install_icons_pi.py")

SIZE  = 512
BLACK = (0, 0, 0, 255)
CLEAR = (0, 0, 0, 0)
CX = CY = SIZE // 2

# Determine plugin base directory
CANDIDATES = [
    "/usr/local/inkypi/src/plugins",
    "/home/dietpi/InkyPi/src/plugins",
]
PLUGINS_DIR = next((p for p in CANDIDATES if os.path.isdir(p)), None)
if PLUGINS_DIR is None:
    sys.exit("Could not find InkyPi plugins directory. Edit CANDIDATES in this script.")

print(f"Writing icons to: {PLUGINS_DIR}")


def canvas():
    return Image.new("RGBA", (SIZE, SIZE), CLEAR)


def save(im, plugin_id):
    out = os.path.join(PLUGINS_DIR, plugin_id, "icon.png")
    if not os.path.isdir(os.path.dirname(out)):
        print(f"  SKIP {plugin_id} — directory not found")
        return
    im.save(out)
    print(f"  OK   {out}")


# ── History Today: Hourglass ───────────────────────────────────────────────
def make_history_today():
    im = canvas()
    d = ImageDraw.Draw(im)
    pad, waist, bar = 75, 42, 32
    d.polygon([(pad, pad+bar), (SIZE-pad, pad+bar), (CX+waist, CY), (CX-waist, CY)], fill=BLACK)
    d.polygon([(CX-waist, CY), (CX+waist, CY), (SIZE-pad, SIZE-pad-bar), (pad, SIZE-pad-bar)], fill=BLACK)
    d.rectangle([pad-12, pad, SIZE-pad+12, pad+bar], fill=BLACK)
    d.rectangle([pad-12, SIZE-pad-bar, SIZE-pad+12, SIZE-pad], fill=BLACK)
    d.polygon([(CX-55, SIZE-pad-bar-2), (CX+55, SIZE-pad-bar-2), (CX, SIZE-pad-bar-82)], fill=CLEAR)
    return im


# ── Joke of Day: Speech Bubble ─────────────────────────────────────────────
def make_joke_of_day():
    im = canvas()
    d = ImageDraw.Draw(im)
    pad = 55
    bot = int(SIZE * 0.68)
    d.rounded_rectangle([pad, pad, SIZE-pad, bot], radius=65, fill=BLACK)
    d.polygon([(pad+55, bot-2), (pad+55, bot+100), (pad+160, bot-2)], fill=BLACK)
    lpad = pad + 60
    for i, ly in enumerate([int(SIZE*0.28), int(SIZE*0.43), int(SIZE*0.57)]):
        rpad = SIZE-pad-60 if i < 2 else SIZE-pad-140
        d.rounded_rectangle([lpad, ly-17, rpad, ly+17], radius=17, fill=CLEAR)
    return im


# ── Moon Phase: Crescent ───────────────────────────────────────────────────
def make_moon_phase():
    pad    = 58
    r_out  = CX - pad
    offset = int(r_out * 0.42)
    r_in   = int(r_out * 0.88)
    y, x   = np.ogrid[:SIZE, :SIZE]
    outer  = (x-CX)**2 + (y-CY)**2 <= r_out**2
    inner  = (x-(CX+offset))**2 + (y-CY)**2 <= r_in**2
    px     = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
    px[outer & ~inner] = [0, 0, 0, 255]
    return Image.fromarray(px, "RGBA")


# ── Top Stories: Newspaper ─────────────────────────────────────────────────
def make_top_stories():
    im = canvas()
    d  = ImageDraw.Draw(im)
    pad, radius = 55, 28
    col  = SIZE//2 - 8
    lpad = pad + 38
    rpad = SIZE - pad - 38
    d.rounded_rectangle([pad, pad, SIZE-pad, SIZE-pad], radius=radius, fill=BLACK)
    d.rounded_rectangle([lpad, pad+38, rpad, pad+112], radius=14, fill=CLEAR)
    gap = 14
    for ly in [int(SIZE*0.46), int(SIZE*0.56), int(SIZE*0.66), int(SIZE*0.76)]:
        d.rounded_rectangle([lpad,      ly-14, col-gap, ly+14], radius=14, fill=CLEAR)
        d.rounded_rectangle([col+gap,   ly-14, rpad,    ly+14], radius=14, fill=CLEAR)
    ly = int(SIZE * 0.86)
    d.rounded_rectangle([lpad,        ly-14, col-gap-30, ly+14], radius=14, fill=CLEAR)
    d.rounded_rectangle([col+gap,     ly-14, rpad-30,    ly+14], radius=14, fill=CLEAR)
    return im


# ── AdGuard Home: Shield + Checkmark ──────────────────────────────────────
def make_adguard_home():
    im = canvas()
    d  = ImageDraw.Draw(im)
    pad, inset = 60, 28
    top_y, side_y = pad, int(SIZE*0.55)
    bot_y = SIZE - pad
    shield = [(pad, top_y), (SIZE-pad, top_y), (SIZE-pad, side_y), (CX, bot_y), (pad, side_y)]
    d.polygon(shield, fill=BLACK)
    inner  = [(pad+inset, top_y+inset), (SIZE-pad-inset, top_y+inset),
              (SIZE-pad-inset, side_y-inset//2), (CX, bot_y-inset*2), (pad+inset, side_y-inset//2)]
    d.polygon(inner, fill=(255, 255, 255, 255))
    stroke = 22
    d.line([int(SIZE*0.30), int(SIZE*0.52), int(SIZE*0.46), int(SIZE*0.66)], fill=BLACK, width=stroke)
    d.line([int(SIZE*0.46), int(SIZE*0.66), int(SIZE*0.70), int(SIZE*0.34)], fill=BLACK, width=stroke)
    return im


# ── Crypto Portfolio: Coin + Bars ─────────────────────────────────────────
def make_crypto_portfolio():
    im = canvas()
    d  = ImageDraw.Draw(im)
    R, r = 200, 140
    d.ellipse([CX-R, CY-R, CX+R, CY+R], fill=BLACK)
    d.ellipse([CX-r, CY-r, CX+r, CY+r], fill=(255, 255, 255, 255))
    bar_w, gap = 42, 18
    heights    = [int(r*0.72), int(r*0.45), int(r*0.90)]
    total_w    = 3*bar_w + 2*gap
    ox         = CX - total_w//2
    base_y     = CY + int(r*0.55)
    for i, h in enumerate(heights):
        x0 = ox + i*(bar_w+gap)
        d.rectangle([x0, base_y-h, x0+bar_w, base_y], fill=BLACK)
    pts = [(ox, CY-int(r*0.15)), (ox+total_w//2, CY-int(r*0.55)), (ox+total_w, CY-int(r*0.30))]
    d.line(pts, fill=(0, 0, 0, 200), width=18)
    return im


if __name__ == "__main__":
    save(make_history_today(),    "history_today")
    save(make_joke_of_day(),      "joke_of_day")
    save(make_moon_phase(),       "moon_phase")
    save(make_top_stories(),      "top_stories")
    save(make_adguard_home(),     "adguard_home")
    save(make_crypto_portfolio(), "crypto_portfolio")
    print("Done.")
