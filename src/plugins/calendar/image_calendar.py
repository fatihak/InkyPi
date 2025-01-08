import calendar
from PIL import Image, ImageDraw


class ImageCalendar:
    def __init__(self, year, month):
        self.year = year
        self.month = month
        self.calendar = calendar.monthcalendar(year, month)
        self.events = dict()
        self.colors = dict()
        self.slashed = dict()

    def add_event(self, day, summary, time=None, color=None, background=None):
        self.events[day] = self.events.get(day, []) + [
            (summary, time, color, background)
        ]

    def color_day(self, day, color):
        self.colors[day] = color

    def slash_day(self, day, slashed=True, direction="down"):
        self.slashed[day] = direction if slashed else None

    def render(
        self,
        dimensions=(800, 600),
        background_color=(255, 255, 255, 255),
        border_color=(0, 0, 0, 255),
        border_width=1,
        padding=1,
        margin=1,
        header_height=18,
        event_height=12,
        header_font=None,
        day_font=None,
        event_font=None,
    ):

        width, height = dimensions
        base = Image.new("RGBA", dimensions, background_color)
        draw = ImageDraw.Draw(base)

        rows = len(self.calendar)
        columns = len(self.calendar[0])

        column_width = (width - margin) / columns
        row_height = (height - header_height - margin) / rows

        for day in range(columns):
            x = day * column_width
            draw.rectangle(
                [(x, 0), (x + column_width, 0 + header_height)],
                fill=None,
                outline=border_color,
                width=border_width,
            )
            draw.text(
                (x + column_width / 2, 0 + header_height / 2),
                calendar.day_name[day],
                anchor="mm",
                font=header_font,
                font_size=header_height,
                fill=border_color,
            )

            for week in range(rows):
                x = day * column_width
                y = week * row_height + header_height
                date = self.calendar[week][day]
                fill = self.colors.get(date, background_color)
                draw.rectangle(
                    [(x, y), (x + column_width, y + row_height)],
                    fill=fill,
                    outline=border_color,
                    width=border_width,
                )
                if date > 0:
                    text_x = x + padding + border_width
                    text_y = y + padding + border_width + event_height / 2
                    draw.text(
                        (text_x, text_y),
                        str(date),
                        anchor="lm",
                        font=day_font,
                        font_size=event_height,
                        fill=border_color,
                        width=border_width,
                    )
                    line = 1
                    all_day = []
                    regular = []
                    for summary, time, color, background in self.events.get(date, []):
                        if time is not None:
                            regular.append((summary, time, color, background))
                        else:
                            all_day.append((summary, time, color, background))
                    for summary, time, color, background in all_day + regular:
                        text_y = (
                            y
                            + padding
                            + border_width
                            + event_height / 2
                            + line * event_height
                        )
                        text_margin = 0
                        if time is None:
                            draw.rounded_rectangle(
                                [
                                    (x + border_width, text_y - event_height / 2),
                                    (
                                        x + column_width - border_width,
                                        text_y + event_height / 2,
                                    ),
                                ],
                                radius=5,
                                fill=background,
                                outline=background_color,
                                width=1,
                                corners=None,
                            )
                        else:
                            radius = event_height / 3
                            draw.circle(
                                (x + border_width + radius, text_y),
                                radius,
                                fill=background,
                                outline=background_color,
                                width=1,
                            )
                            text_margin = radius * 2 + padding
                        draw.text(
                            (text_x + text_margin, text_y),
                            f"{time} {summary}" if time is not None else summary,
                            anchor="lm",
                            font=event_font,
                            font_size=event_height,
                            fill=color if time is None else border_color,
                            width=border_width,
                        )
                        line += 1

                    slashed = self.slashed.get(date, None)
                    if slashed == "down":
                        draw.line(
                            [(x, y), (x + column_width, y + row_height)],
                            fill=border_color,
                            width=border_width,
                        )
                    elif slashed == "up":
                        draw.line(
                            [(x + column_width, y), (x, y + row_height)],
                            fill=border_color,
                            width=border_width,
                        )

                    draw.rectangle(
                        [
                            (x + border_width, y + border_width),
                            (
                                x + column_width - border_width,
                                y + row_height - border_width,
                            ),
                        ],
                        fill=None,
                        outline=fill,
                        width=padding,
                    )
        return base


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate a calendar image.")
    parser.add_argument("year", type=int, help="Year of the calendar")
    parser.add_argument("month", type=int, help="Month of the calendar (1-12)")
    parser.add_argument(
        "--output", type=str, default="calendar.png", help="Output file path"
    )
    parser.add_argument("--width", type=str, default=800, help="Width")
    parser.add_argument("--height", type=str, default=600, help="Height")
    args = parser.parse_args()

    cal = ImageCalendar(args.year, args.month)
    image = cal.render((args.width, args.height))
    image.save(args.output)
