"""Generates a simple shield icon for the AdGuard Home plugin."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PIL import Image, ImageDraw

SIZE = 512
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Shield path: top-left, top-right, bottom point
cx, cy = SIZE // 2, SIZE // 2
pad = 60
top_y   = pad
side_y  = int(SIZE * 0.55)
bot_y   = SIZE - pad
left_x  = pad
right_x = SIZE - pad

shield = [
    (left_x,  top_y),
    (right_x, top_y),
    (right_x, side_y),
    (cx,      bot_y),
    (left_x,  side_y),
]
d.polygon(shield, fill=(0, 0, 0, 255))

# Inner shield (white)
inset = 28
shield_inner = [
    (left_x  + inset, top_y  + inset),
    (right_x - inset, top_y  + inset),
    (right_x - inset, side_y - inset // 2),
    (cx,              bot_y  - inset * 2),
    (left_x  + inset, side_y - inset // 2),
]
d.polygon(shield_inner, fill=(255, 255, 255, 255))

# Checkmark inside shield
stroke = 22
cx1, cy1 = int(SIZE * 0.30), int(SIZE * 0.52)
cx2, cy2 = int(SIZE * 0.46), int(SIZE * 0.66)
cx3, cy3 = int(SIZE * 0.70), int(SIZE * 0.34)
d.line([cx1, cy1, cx2, cy2], fill=(0, 0, 0, 255), width=stroke)
d.line([cx2, cy2, cx3, cy3], fill=(0, 0, 0, 255), width=stroke)

out = os.path.join(os.path.dirname(__file__), '..', 'src', 'plugins', 'adguard_home', 'icon.png')
img.save(out)
print(f"Icon saved to {out}")
