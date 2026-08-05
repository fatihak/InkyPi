# pi_weather_display - known issues & ideas

Running list of things found during development/testing that aren't fixed yet.
Add to this whenever something rough turns up; check items off (don't delete
them) once fixed.

## Bugs

- [ ] **Missing font glyph fallback**: `AssetStore.font()` only loads Jost.ttf/Jost-SemiBold.ttf, which have no CJK (or other non-Latin) glyphs. When a location name comes back in a non-Latin script (e.g. Tokyo's Nominatim result), PIL silently drops the unsupported characters instead of rendering anything - the header ends up with a blank gap where the city name should be. The old Chromium/CSS renderer didn't hit this because browsers do automatic per-character font fallback; Pillow's single-TTF loader doesn't. Found via `mock_display_output/pi_zero/pi_zero_render_tokyo_japan.png`. Fix likely needs a bundled fallback font (broad Unicode coverage) tried per-character when Jost can't render something.

## Polish / not pixel-tuned yet

- [x] ~~Humidity drop icon shape is a bit chunky/merged where the drops touch in the top row (ellipse+triangle approximation of the original teardrop SVG path) - could look cleaner.~~ Fixed for good by giving up on drawing the shape at all: two hand-drawn Pillow attempts (ellipse+triangle, then a single teardrop polygon) both still looked rough. Now uses `assets/icons/humidity_drop_filled.png` / `humidity_drop_empty.png`, two small transparent PNGs cropped directly out of a pi4-app (the original Chromium/CSS renderer) screenshot (`mock_display_output/icon_overviews/humidity_5drop_options.png`) via connected-component analysis, then pasted per-drop in `draw_humidity_drops` instead of drawn with `ImageDraw`. Pixel-identical to the original design, no seams, no overlap tuning needed.
- [ ] All fonts, gauge sizes, and region positions in `layout.py` are a first-pass approximation of `weather.css`'s proportions, not pixel-matched to the original design yet.
- [ ] Chart's hourly icon strip can overflow slightly past the bottom edge of `CHART_AREA` (~4px) depending on content.
- [ ] Imperial/standard unit rendering (rain axis label, temperature conversion) has only been tested with metric units so far.
