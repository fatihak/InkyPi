from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h


CANVAS_SIZE = (800, 480)

# Fixed pixel regions, derived from weather.css's dvh/dvw proportions at 800x480
# (no more responsive units needed - there's only ever one physical resolution).
# These are a first pass for visual review, not pixel-tuned yet. Stacked
# top-to-bottom with no overlap (the original CSS clawed back whitespace with
# a negative margin on the chart container; that space doesn't exist here
# since the data-point grid fills its whole row height).
HEADER = Region(0, 6, 800, 34)
TODAY = Region(0, HEADER.bottom + 6, 800, 165)
CURRENT_TEMPERATURE = Region(TODAY.x, TODAY.y, 320, TODAY.h)
DATA_POINTS = Region(320, TODAY.y, 480, TODAY.h)
CHART_AREA = Region(0, TODAY.bottom + 6, 800, 150)
FORECAST_ROW = Region(0, CHART_AREA.bottom + 8, 800, 95)

# Data-point grid: 2 columns x 3 rows, filled row-major in the same order as
# weather_data.py's data_points list (wind, humidity, pressure, uv, visibility, aqi).
DATA_POINT_COLS = 2
DATA_POINT_ROWS = 3
DATA_POINT_ICON_FRACTION = 0.38  # matches .data-point-img-container width:38%


def data_point_cell(index: int) -> Region:
    col = index % DATA_POINT_COLS
    row = index // DATA_POINT_COLS
    cell_w = DATA_POINTS.w // DATA_POINT_COLS
    cell_h = DATA_POINTS.h // DATA_POINT_ROWS
    return Region(DATA_POINTS.x + col * cell_w, DATA_POINTS.y + row * cell_h, cell_w, cell_h)


def forecast_card(index: int, count: int) -> Region:
    gap = 12
    card_w = (FORECAST_ROW.w - gap * (count - 1)) // count
    x = FORECAST_ROW.x + index * (card_w + gap)
    return Region(x, FORECAST_ROW.y, card_w, FORECAST_ROW.h)
