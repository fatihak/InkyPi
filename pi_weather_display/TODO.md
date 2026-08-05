# pi_weather_display - known issues & ideas

Running list of things found during development/testing that aren't fixed yet.
Add to this whenever something rough turns up; check items off (don't delete
them) once fixed.

## Bugs

- [ ] **Missing font glyph fallback**: `AssetStore.font()` only loads Jost.ttf/Jost-SemiBold.ttf, which have no CJK (or other non-Latin) glyphs. When a location name comes back in a non-Latin script (e.g. Tokyo's Nominatim result), PIL silently drops the unsupported characters instead of rendering anything - the header ends up with a blank gap where the city name should be. The old Chromium/CSS renderer didn't hit this because browsers do automatic per-character font fallback; Pillow's single-TTF loader doesn't. Found via `mock_display_output/pi_zero/pi_zero_render_tokyo_japan.png`. Fix likely needs a bundled fallback font (broad Unicode coverage) tried per-character when Jost can't render something.

## Polish / not pixel-tuned yet

- [x] ~~Humidity drop icon shape is a bit chunky/merged where the drops touch in the top row (ellipse+triangle approximation of the original teardrop SVG path) - could look cleaner.~~ Fixed: `_draw_droplet` now builds one continuous teardrop polygon (tip + a 170deg arc) instead of a separately-drawn ellipse+triangle, which also fixes a seam - the empty (outline-only) drops used to show a stray straight line across them where the triangle's outline and the ellipse's outline didn't coincide. Also reduced size/overlap so all 5 drops stay individually readable at every fill count (0-5).
- [ ] All fonts, gauge sizes, and region positions in `layout.py` are a first-pass approximation of `weather.css`'s proportions, not pixel-matched to the original design yet.
- [ ] Chart's hourly icon strip can overflow slightly past the bottom edge of `CHART_AREA` (~4px) depending on content.
- [ ] Imperial/standard unit rendering (rain axis label, temperature conversion) has only been tested with metric units so far.
