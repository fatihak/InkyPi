from PIL import ImageDraw

CARD_BORDER = (90, 156, 90)
CARD_FILL = (227, 241, 227)


def draw_forecast_card(image, region, day, assets, text_color, show_moon: bool):
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        [region.x, region.y, region.right - 1, region.bottom - 1],
        radius=8, outline=CARD_BORDER, width=2, fill=CARD_FILL,
    )

    icon_size = int(min(region.w * 0.85, region.h * 0.45))
    icon = assets.icon(day.icon_key, (icon_size, icon_size))
    cx = region.center[0]
    top_y = region.y + 6
    if icon:
        image.paste(icon, (cx - icon_size // 2, top_y), icon)

    temps_y = top_y + icon_size + 4
    font_bold = assets.font("bold", max(10, int(region.w * 0.15)))
    draw.text((cx, temps_y), day.day_label, font=font_bold, fill=text_color, anchor="ma")
    draw.text((cx, temps_y + font_bold.size + 1), f"{day.high}° / {day.low}°", font=font_bold, fill=text_color, anchor="ma")

    if show_moon:
        moon_size = 14
        moon_y = region.bottom - moon_size - 4
        moon_icon = assets.icon(day.moon_icon_key, (moon_size, moon_size))
        if moon_icon:
            image.paste(moon_icon, (region.x + 6, moon_y), moon_icon)
        draw.text((region.x + 6 + moon_size + 4, moon_y + moon_size // 2), f"{day.moon_phase_pct}%",
                   font=assets.font("normal", 11), fill=text_color, anchor="lm")
