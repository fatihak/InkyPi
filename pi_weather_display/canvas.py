from PIL import Image, ImageDraw

import layout
from config import DisplayConfig
from weather_data import WeatherSnapshot
from widgets import gauge, forecast as forecast_widget, icons as icons_widget
from widgets import chart as chart_widget


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    hex_str = hex_str.lstrip("#")
    return tuple(int(hex_str[i:i + 2], 16) for i in (0, 2, 4))


class WeatherCanvas:
    def __init__(self, assets: icons_widget.AssetStore, config: DisplayConfig):
        self.assets = assets
        self.config = config
        self.bg = _hex_to_rgb(config.background_color)
        self.text_color = _hex_to_rgb(config.text_color)

    def render(self, data: WeatherSnapshot) -> Image.Image:
        image = Image.new("RGB", layout.CANVAS_SIZE, self.bg)
        draw = ImageDraw.Draw(image)

        self._draw_header(draw, data)
        self._draw_current_conditions(image, draw, data)
        self._draw_data_points(image, draw, data)
        self._draw_chart(image, data)
        self._draw_forecast_row(image, data)
        return image

    def _draw_header(self, draw, data: WeatherSnapshot):
        font_date = self.assets.font("bold", 22)
        font_refresh = self.assets.font("bold", 14)
        date_text = data.current_date
        if data.location:
            date_text += f", {data.location}"
        draw.text((layout.HEADER.x, layout.HEADER.bottom), date_text, font=font_date, fill=self.text_color, anchor="lb")
        draw.text((layout.HEADER.right - 4, layout.HEADER.y), f"Laatste update: {data.last_refresh_time}",
                   font=font_refresh, fill=(51, 51, 51), anchor="ra")

    def _draw_current_conditions(self, image, draw, data: WeatherSnapshot):
        region = layout.CURRENT_TEMPERATURE
        icon_size = int(region.h * 0.62)
        icon = self.assets.icon(data.current_icon_key, (icon_size, icon_size))
        icon_x = region.x + int(region.w * 0.22)
        icon_y = region.y + int(region.h * 0.12)
        if icon:
            image.paste(icon, (icon_x - icon_size // 2, icon_y), icon)

        text_cx = region.x + int(region.w * 0.68)
        font_temp = self.assets.font("bold", 64)
        font_unit = self.assets.font("bold", 24)
        font_small = self.assets.font("bold", 15)

        temp_str = str(data.current_temp)
        temp_y = region.y + int(region.h * 0.42)
        draw.text((text_cx, temp_y), temp_str, font=font_temp, fill=self.text_color, anchor="mm")
        temp_w = draw.textlength(temp_str, font=font_temp)
        draw.text((text_cx + temp_w / 2 + 4, temp_y - 22), data.temp_unit, font=font_unit, fill=self.text_color, anchor="lm")

        degree = "°" if data.temp_unit != "K" else ""
        draw.text((text_cx, temp_y + 34), f"Gevoelstemp. {data.feels_like}{degree}", font=font_small, fill=self.text_color, anchor="mm")
        draw.text((text_cx, temp_y + 56), f"{data.forecast_high}{degree} / {data.forecast_low}{degree}", font=font_small, fill=self.text_color, anchor="mm")

    def _draw_data_points(self, image, draw, data: WeatherSnapshot):
        for i, dp in enumerate(data.data_points):
            cell = layout.data_point_cell(i)
            icon_w = int(cell.w * layout.DATA_POINT_ICON_FRACTION)
            icon_box = layout.Region(cell.x, cell.y, icon_w, cell.h)
            self._draw_data_point_icon(image, icon_box, dp)

            text_x = cell.x + icon_w + 8
            font_label = self.assets.font("normal", 13)
            font_value = self.assets.font("bold", 18)
            label_y = cell.y + int(cell.h * 0.28)
            value_y = cell.y + int(cell.h * 0.68)
            draw.text((text_x, label_y), dp["label"], font=font_label, fill=self.text_color, anchor="lm")

            value_parts = [dp["direction"]] if dp.get("direction") else []
            value_parts.append(str(dp["measurement"]))
            value_text = " ".join(value_parts)
            if dp.get("unit"):
                value_text += f" {dp['unit']}"
            draw.text((text_x, value_y), value_text, font=font_value, fill=self.text_color, anchor="lm")

    def _draw_data_point_icon(self, image, box: layout.Region, dp: dict):
        kind = dp["kind"]
        if kind == "wind":
            gauge_img = gauge.render_wind_compass(dp["rotation"])
        elif kind == "pressure":
            gauge_img = gauge.render_pressure_gauge(dp["gauge_rotation"])
        elif kind == "uv":
            gauge_img = gauge.render_uv_icon(dp["uv_color"], dp["uv_beams"])
        elif kind == "aqi":
            gauge_img = gauge.render_aqi_gauge(dp["aqi_rotation"])
        elif kind == "humidity":
            icons_widget.draw_humidity_drops(image, box, self.assets, dp["drop_count"])
            return
        elif kind == "visibility":
            scale = 0.55
            w, h = max(1, int(box.w * scale)), max(1, int(box.h * scale))
            icon = self.assets.icon("visibility", (w, h))
            if icon:
                image.paste(icon, (box.x + (box.w - w) // 2, box.y + (box.h - h) // 2), icon)
            return
        else:
            return

        scale = min(box.w / gauge_img.width, box.h / gauge_img.height)
        target_size = (max(1, int(gauge_img.width * scale)), max(1, int(gauge_img.height * scale)))
        resized = gauge_img.resize(target_size, Image.LANCZOS)
        paste_x = box.x + (box.w - resized.width) // 2
        paste_y = box.y + (box.h - resized.height) // 2
        image.paste(resized, (paste_x, paste_y), resized)

    def _draw_chart(self, image, data: WeatherSnapshot):
        temp_unit_label = data.temp_unit.replace("°", "") if data.temp_unit != "K" else "K"
        rain_unit_label = "in" if self.config.units == "imperial" else "mm"
        chart_widget.render_chart(
            image, layout.CHART_AREA, data.hourly, data.sun_events, self.text_color,
            lambda key, size: self.assets.icon(key, size), self.config.graph_icon_step,
            self.assets.font("normal", 12), self.assets.font("bold", 12),
            temp_unit_label, rain_unit_label,
        )

    def _draw_forecast_row(self, image, data: WeatherSnapshot):
        count = len(data.daily)
        if count == 0:
            return
        for i, day in enumerate(data.daily):
            region = layout.forecast_card(i, count)
            forecast_widget.draw_forecast_card(image, region, day, self.assets, self.text_color, self.config.show_moon_phase)
