from datetime import datetime
import logging
from plugins.base_plugin.base_plugin import BasePlugin
from utils.image_utils import resize_image
from utils.app_utils import get_font
from PIL import Image, ImageDraw
#import textwrap
#import os

logger = logging.getLogger(__name__)

FRAME_STYLES = [
    {
        "name": "None",
        "icon": "frames/blank.png"
    },
    {
        "name": "Corner",
        "icon": "frames/corner.png"
    },
    {
        "name": "Top and Bottom",
        "icon": "frames/top_and_bottom.png"
    },
    {
        "name": "Rectangle",
        "icon": "frames/rectangle.png"
    }
]

class Countdown(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['frame_styles'] = FRAME_STYLES
        return template_params

    def generate_image(self, settings, device_config):

        now = datetime.now()
        title = "Today is {}".format(now.strftime("%d %B %Y"))
        event_name = settings.get('eventName')
        if not event_name:
            raise RuntimeError("Event Name is required.")

        frame = settings.get('selectedFrame')
        if not frame or frame not in [frame['name'] for frame in FRAME_STYLES]:
            frame = "None"

        event_date = settings.get('eventDate')
        if not event_date:
            raise RuntimeError("Event Date is required.")

        try:
            days = Countdown.count_days(event_name, event_date)
        except Exception as e:
            logger.error(f"Failed to get days countdown: {str(e)}")
            raise RuntimeError("Countdown failure, please check logs.")

        background_color = settings.get('backgroundColor', "white")
        background_image = settings.get('backgroundImageFile')
        text_color = settings.get('textColor', "black")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        try:
            if background_image:
                image = Image.open(background_image)
                image = resize_image(image, dimensions)
            else:
                image = Image.new("RGBA", dimensions, background_color)

            if frame:
                image = Countdown.draw_frame(frame, image, text_color)

            image = Countdown.generate_text_image(image, dimensions, title, days, text_color)
        except Exception as e:
            logger.error(f"Failed to generate text image: {str(e)}")
            raise RuntimeError("Failed to generate image, please check logs.")
        return image

    @staticmethod
    def count_days(eventName, eventDate):
        now = datetime.now()
        date_of_event = datetime.strptime(eventDate, "%Y-%m-%d")
        days_until = date_of_event - datetime(year=now.year, month=now.month, day=now.day)
        if(days_until.days<0):
            days_left = "{} has already passed!".format(eventName)
        elif(days_until.days==0):
            days_left = "{} is today!".format(eventName)
        elif(days_until.days==1):
            days_left = "It's {} day until {}!".format(days_until.days, eventName)
        else:
            days_left = "It's {} days until {}!".format(days_until.days, eventName)
        return days_left

    @staticmethod
    def generate_text_image(base_image, dimensions, title, body, color=(0,0,0)):
        w,h = dimensions
        dim = min(w,h)
        image_draw = ImageDraw.Draw(base_image)

        # Adaptive font size based on image dimensions
        font_size = max(10, min(w, h) // 20)
        font = get_font("jost", font_size)
        line_height = Countdown.get_text_height(font, body) + 4

        title_font_size = max(10, min(w, h) // 18)
        title_font = get_font("jost-semibold", title_font_size)
        title_height = Countdown.get_text_height(title_font, title)

        # Maximum text width in pixels
        text_padding = max(dim*0.08, 1)
        max_text_width = w - (text_padding*2)

        wrapped_lines = Countdown.wrap_lines(body, image_draw, font, max_text_width)

        total_text_height = len(wrapped_lines) * line_height

        title_height = title_height if title else 0
        y = max((h - total_text_height - title_height) // 2, 0)
        x = w/2

        if title:
            image_draw.text((x, y), title, anchor="mm", fill=color, font=title_font)
            y += title_height

        for line in wrapped_lines:
            image_draw.text((x, y), line, font=font, anchor="mt", fill=color)
            y += line_height
        return base_image

    @staticmethod
    def draw_frame(frame, image, color):
        w,h = image.size
        dim = min(w,h)
        image_draw = ImageDraw.Draw(image)
        width = max(int(dim*0.015), 1)
        padding = max(dim*0.05, 1)

        if frame == "Corner":
            corner_length = max(dim*0.16, 1)
            image_draw.line([ (padding+corner_length, padding), (padding, padding), (padding, padding+corner_length)], fill=color, width = width, joint="curve")
            image_draw.line([ (w-padding-corner_length, h-padding), (w-padding, h-padding), (w-padding, h-padding-corner_length)], fill=color, width = width, joint="curve")
        elif frame == "Top and Bottom":
            image_draw.line([ (padding, 2*padding), (w-padding, 2*padding)], fill=color, width=width)
            image_draw.line([ (padding, h-(2*padding)), (w-padding, h-(2*padding))], fill=color, width=width)
        elif frame == "Rectangle":
            shape = [(padding,padding),(w-padding, h-padding)]
            image_draw.rectangle(shape, outline=color, width=width)

        return image

    @staticmethod
    def wrap_lines(body, image_draw, font, max_text_width):
        # Word-wrap text using pixel-based constraints
        words = body.replace("\n", " \n").split(" ")
        wrapped_lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            test_width = image_draw.textlength(test_line.replace("\n", ""), font=font)
            if test_width <= max_text_width and "\n" not in word:
                current_line.append(word)
            else:
                wrapped_lines.append(' '.join(current_line))
                current_line = [word.replace("\n", "")]

        if current_line:
            wrapped_lines.append(' '.join(current_line))
        return wrapped_lines

    @staticmethod
    def get_text_height(font, text):
        # Word-wrap text using pixel-based constraints
        left, top, right, bottom = font.getbbox(text)
        return bottom - top

