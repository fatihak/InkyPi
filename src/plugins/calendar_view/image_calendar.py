import itertools
import requests
import calendar
import icalendar
import recurring_ical_events
from datetime import datetime, timedelta
from PIL import Image, ImageDraw

COLOR_PAIRS = [
    ("white", "deepskyblue"),
    ("black", "chartreuse"),
    ("white", "deeppink"),
    ("black", "orange"),
    ("white", "blue"),
    ("white", "forestgreen"),
    ("white", "chocolate"),
    ("white", "red"),
    ("black", "lime"),
    ("black", "yellow"),
]


def fetch_ical(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return icalendar.Calendar.from_ical(response.text)
    except requests.exceptions.RequestException as e:
        return None


class ImageCalendar:
    def __init__(self, current_time):
        self.current_time = current_time
        self.day = current_time.day
        self.year = current_time.year
        self.month = current_time.month
        self.calendar = calendar.monthcalendar(self.year, self.month)
        self.events = dict()
        self.colors = dict()
        self.slashed = dict()

        _, last_day = calendar.monthrange(current_time.year, current_time.month)
        self.range_start = current_time.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        self.range_end = current_time.replace(
            day=last_day, hour=23, minute=59, second=59, microsecond=999999
        )

    def color_day(self, day, color):
        self.colors[day] = color

    def slash_day(self, day, slashed=True, direction="down"):
        self.slashed[day] = direction if slashed else None

    def slash_past_days(self):
        dt = self.range_start
        while dt.day < self.current_time.day:
            self.slash_day(dt.day, direction="down" if dt.day % 2 == 0 else "up")
            dt += timedelta(days=1)

    def add_event(self, day, summary, time=None, color=None, background=None):
        self.events[day] = self.events.get(day, []) + [
            (summary, time, color, background)
        ]

    def load_ical_url(self, url, color):
        range_start = self.range_start
        range_end = self.range_end
        text_color, background_color = color
        ical = fetch_ical(url)
        if ical:
            events = recurring_ical_events.of(ical).between(range_start, range_end)
            for event in events:
                start = event["DTSTART"].dt
                end = event["DTEND"].dt
                summary = event["SUMMARY"]
                time = start.strftime("%H:%M").strip() if isinstance(start, datetime) else None
                start_date = start.replace(tzinfo=None).date() if isinstance(start, datetime) else start
                end_date = end.replace(tzinfo=None).date() if isinstance(end, datetime) else end
                next_date = start_date
                last_date = min(end_date, range_end.date())

                if next_date == last_date:
                    self.add_event(
                        next_date.day,
                        summary,
                        time=time,
                        color=text_color,
                        background=background_color,
                    )
                else:
                    while next_date < last_date:
                        if next_date >= range_start.date():
                            self.add_event(
                                next_date.day,
                                summary,
                                time=time,
                                color=text_color,
                                background=background_color,
                            )
                        next_date += timedelta(days=1)

    def render(
        self,
        dimensions=(800, 600),
        background_color=(255, 255, 255, 255),
        border_color=(0, 0, 0, 255),
        border_width=1,
        padding=1,
        margin=1,
        title_height=20,
        header_height=18,
        event_height=12,
        title_font=None,
        header_font=None,
        day_font=None,
        event_font=None,
        show_time_line=True,
        show_month=True,
        show_year=True,
        show_time=True,
        sunrise=None,
        noon=None,
        sunset=None,
    ):
        
        if sunrise is None:
            sunrise=self.current_time.replace(hour=6, minute=0, second=0, microsecond=0),
        if noon is None:
            noon=self.current_time.replace(hour=12, minute=0, second=0, microsecond=0),
        if sunset is None:
            sunset=self.current_time.replace(hour=18, minute=0, second=0, microsecond=0),

        width, height = dimensions
        base = Image.new("RGBA", dimensions, background_color)
        draw = ImageDraw.Draw(base)

        rows = len(self.calendar)
        columns = len(self.calendar[0])

        column_width = (width - margin) / columns
        row_height = (height - title_height - header_height - margin) / rows

        draw.rectangle(
            [(0, 0), (width - margin, title_height)],
            fill=None,
            outline=border_color,
            width=border_width,
        )

        month_str = None
        if show_month:
            month_str = calendar.TextCalendar().formatmonthname(
                self.year, self.month, width, withyear=show_year
            )
        elif show_year:
            month_str = str(self.year)
        if month_str is not None:
            draw.text(
                (width - 10, border_width + title_height / 2),
                month_str.strip(),
                font=title_font,
                font_size=title_height,
                anchor="rm",
                fill=border_color,
            )

        if show_time:
            draw.text(
                (10, border_width + title_height / 2),
                self.current_time.strftime("%H:%M"),
                font=title_font,
                font_size=title_height,
                anchor="lm",
                fill=border_color,
            )

        for day in range(columns):
            x = day * column_width
            draw.rectangle(
                [
                    (x, title_height),
                    (x + column_width, 0 + title_height + header_height),
                ],
                fill=None,
                outline=border_color,
                width=border_width,
            )
            draw.text(
                (
                    x + column_width / 2,
                    0 + border_width + title_height + header_height / 2,
                ),
                calendar.day_name[day],
                anchor="mm",
                font=header_font,
                font_size=header_height,
                fill=border_color,
            )

            for week in range(rows):
                x = day * column_width
                y = week * row_height + title_height + header_height
                date = self.calendar[week][day]
                fill = self.colors.get(date, background_color)
                draw.rectangle(
                    [(x, y), (x + column_width, y + row_height)],
                    fill=fill if date > 0 else (235,235,235,255),
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
                    events = sorted(
                        self.events.get(date, []),
                        key=lambda x: (
                            x[1] is not None,
                            datetime.strptime(x[1], "%H:%M") if x[1] else None,
                        ),
                    )
                    for summary, time, color, background in events:
                        text_y = (
                            y
                            + event_height / 2
                            + line * (event_height + padding + padding)
                        )
                        radius = event_height / 3
                        if time is None:
                            draw.rounded_rectangle(
                                [
                                    (
                                        x + border_width + padding,
                                        text_y - event_height / 2,
                                    ),
                                    (
                                        x + column_width - border_width - padding,
                                        text_y + event_height / 2,
                                    ),
                                ],
                                radius=3,
                                fill=background,
                                outline=background,
                                width=1,
                                corners=None,
                            )
                            draw.rounded_rectangle(
                                [
                                    (
                                        x + border_width + radius + padding,
                                        text_y - event_height / 2 + padding,
                                    ),
                                    (
                                        x
                                        + column_width
                                        - radius
                                        - border_width
                                        - padding,
                                        text_y + event_height / 2 - padding,
                                    ),
                                ],
                                radius=3,
                                fill=fill,
                                outline=None,
                                width=1,
                                corners=None,
                            )
                        else:
                            draw.circle(
                                (x + padding + radius, text_y),
                                radius,
                                fill=background,
                                outline=fill,
                                width=1,
                            )
                        text_margin = radius + padding if time is None else radius * 1.5
                        draw.text(
                            (text_x + text_margin + padding, text_y),
                            f"{time} {summary}" if time is not None else summary,
                            anchor="lm",
                            font=event_font,
                            font_size=event_height,
                            fill=border_color,
                            width=border_width,
                        )
                        line += 1

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

                    if show_time_line and date == self.day:
                        delta = self.current_time - self.current_time.replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        time_percent = delta.total_seconds() / 86400
                        time_y = y + row_height * time_percent
                        draw.line(
                            [(x, time_y), (x + column_width, time_y)],
                            fill=border_color,
                            width=border_width,
                        )

                    if date == self.day:
                        midnight = self.current_time.replace(hour=0, minute=0, second=0, microsecond=0)
                        sunrise_percent = (sunrise - midnight).total_seconds() / 86400
                        noon_percent = (noon - midnight).total_seconds() / 86400
                        sunset_percent = (sunset - midnight).total_seconds() / 86400
                        time_percent = (self.current_time - midnight).total_seconds() / 86400
                        time_y = y + padding + border_width + event_height / 2
                        day_start = x + padding + border_width + 2 * event_height
                        day_end = x + column_width - event_height * 2 / 3
                        day_width = day_end - day_start
                        x_sunrise = sunrise_percent * day_width + day_start
                        x_noon = noon_percent * day_width + day_start
                        x_sunset = sunset_percent * day_width + day_start
                        x_curpos = time_percent * day_width + day_start
                        draw.line(
                            [(day_start, time_y), (day_end, time_y)],
                            fill=border_color,
                            width=border_width,
                        )
                        draw.line(
                            [(day_start, time_y), (x_curpos, time_y)],
                            fill=border_color,
                            width=3 * border_width,
                        )
                        small_radius = event_height / 6
                        large_radius = event_height / 3
                        draw.circle(
                            (day_start, time_y),
                            small_radius,
                            fill=border_color,
                            outline=border_color,
                            width=1,
                        )
                        draw.circle(
                            (day_end, time_y),
                            small_radius,
                            fill=border_color,
                            outline=border_color,
                            width=1,
                        )
                        draw.circle(
                            (x_sunrise, time_y),
                            small_radius,
                            fill=border_color,
                            outline=border_color,
                            width=1,
                        )
                        draw.circle(
                            (x_noon, time_y),
                            small_radius,
                            fill=border_color,
                            outline=border_color,
                            width=1,
                        )
                        draw.circle(
                            (x_sunset, time_y),
                            small_radius,
                            fill=border_color,
                            outline=border_color,
                            width=1,
                        )
                        if x_sunrise <= x_curpos < x_sunset:
                            draw.circle(
                                (x_curpos, time_y),
                                large_radius,
                                fill="yellow",
                                outline=border_color,
                                width=1,
                            )
                        else:
                            draw.circle(
                                (x_curpos, time_y),
                                large_radius,
                                fill="white",
                                outline=border_color,
                                width=1,
                            )
                            draw.circle(
                                (x_curpos + small_radius, time_y),
                                small_radius,
                                fill=border_color,
                                outline=border_color,
                                width=1,
                            )

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

        return base


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate a calendar image.")
    parser.add_argument("year", type=int, help="Year of the calendar")
    parser.add_argument("month", type=int, help="Month of the calendar (1-12)")
    parser.add_argument(
        "--output", type=str, default="calendar.png", help="Output file path"
    )
    parser.add_argument("--width", type=int, default=800, help="Width")
    parser.add_argument("--height", type=int, default=600, help="Height")
    parser.add_argument(
        "--url", type=str, action="append", help="iCal URL to load events from"
    )
    args = parser.parse_args()

    current_time = datetime.now().replace(year=args.year, month=args.month)
    cal = ImageCalendar(current_time)
    color_cycle = itertools.cycle(COLOR_PAIRS)
    for url in args.url or []:
        cal.load_ical_url(url, next(color_cycle))

    cal.slash_past_days()
    cal.color_day(cal.current_time.day, "lightblue")

    image = cal.render((args.width, args.height))
    image.save(args.output)
