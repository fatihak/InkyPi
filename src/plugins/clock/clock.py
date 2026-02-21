import os
from utils.app_utils import resolve_path, get_font
from plugins.base_plugin.base_plugin import BasePlugin
from plugins.clock.constants import CLOCK_FACES, LOCALE_MAP, LANGUAGE_OPTIONS, LETTER_GRIDS, TEXT_BLOCKS, MINUTE_BLOCKS, HOURS_BLOCKS, HOUR_THRESHOLD
from PIL import Image, ImageColor, ImageDraw, ImageFont
from io import BytesIO
import logging
import numpy as np
import math
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "US/Eastern"
DEFAULT_CLOCK_FACE = "Gradient Clock"
DEFAULT_LANGUAGE = "en"

class Clock(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['clock_faces'] = CLOCK_FACES
        template_params['locale_map'] = LOCALE_MAP
        return template_params

    def generate_image(self, settings, device_config):
        clock_face = settings.get('selectedClockFace')
        primary_color = ImageColor.getcolor(settings.get('primaryColor') or "white", "RGB")
        secondary_color = ImageColor.getcolor(settings.get('secondaryColor') or "black", "RGB")
        if not clock_face or clock_face not in [face['name'] for face in CLOCK_FACES]:
            clock_face = DEFAULT_CLOCK_FACE

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        timezone_name = device_config.get_config("timezone") or DEFAULT_TIMEZONE
        tz = pytz.timezone(timezone_name)
        current_time = datetime.now(tz)

        language = settings.get('language') or DEFAULT_LANGUAGE

        img = None
        try:
            if clock_face == "Gradient Clock":
                img = self.draw_conic_clock(dimensions, current_time, primary_color, secondary_color)
            elif clock_face == "Digital Clock":
                img = self.draw_digital_clock(dimensions, current_time, primary_color, secondary_color)
            elif clock_face == "Divided Clock":
                img = self.draw_divided_clock(dimensions, current_time, primary_color, secondary_color)
            elif clock_face == "Word Clock":
                img = self.draw_word_clock(dimensions, current_time, primary_color, secondary_color, language)
        except Exception as e:
            logger.error(f"Failed to draw clock image: {str(e)}")
            raise RuntimeError("Failed to display clock.")
        return img
    
    def draw_digital_clock(self, dimensions, time, primary_color=(255,255,255), secondary_color=(0,0,0)):
        w,h = dimensions
        time_str = Clock.format_time(time.hour, time.minute, zero_pad = True)

        image = Image.new("RGBA", dimensions, secondary_color+(255,))
        text = Image.new("RGBA", dimensions, (0, 0, 0, 0))

        font_size = w * 0.36
        fnt = get_font("DS-Digital", font_size)
        text_draw = ImageDraw.Draw(text)

        # time text
        text_draw.text((w/2, h/2), "00:00", font=fnt, anchor="mm", fill=primary_color +(30,))
        text_draw.text((w/2, h/2), time_str, font=fnt, anchor="mm", fill=primary_color +(255,))

        combined = Image.alpha_composite(image, text)    

        return combined
        
    def draw_conic_clock(self, dimensions, time, primary_color=(219, 50, 70, 255), secondary_color=(0, 0, 0, 255) ):
        width, height = dimensions
        hour_angle, minute_angle = Clock.calculate_clock_angles(time)

        # Draw the hour hand gradient
        image_hour = Clock.draw_gradient_image(
            width, height, hour_angle, minute_angle, secondary_color, primary_color
        )
        # Draw the minute hand gradient
        image_minute = Clock.draw_gradient_image(
            width, height, minute_angle, hour_angle, secondary_color, primary_color
        )

        # Combine the images using alpha blending
        final_image = Image.alpha_composite(image_hour, image_minute)

        dim = min(width, height)
        minute_length = dim * 0.35
        hour_length = dim * 0.22
        
        hand_width = max(int(dim*0.013), 1)
        border_width = max(int(dim*0.005), 1)

        hand_offset = max(int(dim*0.05), 1)
        offset_width = max(int(dim*0.008), 1)
        Clock.draw_clock_hand(final_image, minute_length, minute_angle, primary_color, border_color=(255, 255, 255), border_width=border_width, hand_offset=hand_offset, offset_width=offset_width, hand_width=hand_width)
        Clock.draw_clock_hand(final_image, hour_length, hour_angle, primary_color, border_color=(255, 255, 255), border_width=border_width, hand_offset=hand_offset, offset_width=offset_width, hand_width=hand_width)
        
        Clock.drew_clock_center(final_image, max(int(dim*0.01), 1), primary_color, outline_color=(255, 255, 255, 255), width=max(int(dim*0.004), 1))

        return final_image

    def draw_divided_clock(self, dimensions, time, primary_color=(32,183,174), secondary_color=(255,255,255)):
        w,h = dimensions
        bg = Image.new("RGBA", dimensions, primary_color+(255,))
        bg_draw = ImageDraw.Draw(bg)

        # used to calculate percentages of sizes
        dim = min(w,h)

        corners = [(0, h/2), (w,h)]
        bg_draw.rectangle(corners, fill=secondary_color +(255,))

        canvas = Image.new("RGBA", dimensions, (0, 0, 0, 0))
        image_draw = ImageDraw.Draw(canvas)

        shadow_offset = max(int(dim * 0.0075), 1)
        face_size = int(dim * 0.45)

        # clock shadow
        image_draw.circle((w/2,h/2 + shadow_offset), face_size+2, fill=(0,0,0,50))

        # clock outline
        image_draw.circle((w/2,h/2), face_size, fill=primary_color, outline=secondary_color, width=int(dim * 0.03125))
        
        Clock.draw_hour_marks(image_draw._image, face_size - int(w*0.04375))

        hour_angle, minute_angle = Clock.calculate_clock_angles(time)
        hand_width = max(int(dim * 0.009), 1)
        Clock.draw_clock_hand(image_draw._image, int(dim*0.3), minute_angle, secondary_color, hand_width=hand_width, border_color=secondary_color, round_corners=False)
        Clock.draw_clock_hand(image_draw._image, int(dim*0.2), hour_angle, secondary_color, hand_width=hand_width, border_color=secondary_color, round_corners=False)

        Clock.drew_clock_center(image_draw._image, max(int(dim*0.014), 1), primary_color, secondary_color, width=max(int(dim* 0.007), 1))

        combined = Image.alpha_composite(bg, canvas)    

        return combined

    def draw_word_clock(self, dimensions, time, primary_color=(0,0,0), secondary_color=(255,255,255), language="en"):
        w,h = dimensions

        bg = Image.new("RGBA", dimensions, primary_color+(255,))

        dim = min(w,h)

        font_size = dim*0.05
        fnt = get_font("Napoli", font_size)

        canvas = Image.new("RGBA", dimensions, (0, 0, 0, 0))
        image_draw = ImageDraw.Draw(canvas)

        border = [40, 40]
        if w > h:
            border[0] += (w-h)/2
        elif h > w:
            border[1] += (h-w)/2

        letter_positions = Clock.translate_word_grid_positions(time.hour % 12, time.minute, language)

        letter_grid = LETTER_GRIDS.get(language)

        canvas_size = min(w,h) - min(border)*2
        for y, row in enumerate(letter_grid):
            for x, letter in enumerate(row):
                x_pos = x*(canvas_size/(len(row)-1)) + border[0] 
                y_pos = y*(canvas_size/(len(letter_grid)-1)) + border[1]

                fill=secondary_color+(50,)
                if [y,x] in letter_positions:
                    fill=secondary_color+(255,)
                    image_draw.text((x_pos+2, y_pos+2), letter, anchor="mm", fill=secondary_color+(80,), font=fnt)
                
                image_draw.text((x_pos, y_pos), letter, anchor="mm", fill=fill, font=fnt)

        combined = Image.alpha_composite(bg, canvas)
        return combined

    @staticmethod
    def format_time(hour, minute, zero_pad=False):
        hour_str = str(hour)
        if zero_pad and hour < 10:
            hour_str = "0" + hour_str
        minute_str = str(minute)
        if zero_pad and minute < 10:
            minute_str = "0" + str(minute_str)
        return f"{hour_str}:{minute_str}"

    @staticmethod
    def draw_gradient_image(w, h, start_angle, end_angle, start_color, end_color):
        """
        Draw a gradient that starts at start_angle and ends at end_angle, using RGBA colors.
        Angles are interpreted for a clock face (0 at 12 o'clock, increasing clockwise).
        """
        x,y = np.ogrid[:h,:w]
        cx,cy = h/2, w/2

        start_angle = -start_angle
        end_angle = -end_angle

        theta = (np.arctan2(x-cx,y-cy) - start_angle)  % (2*np.pi)

        angle_range = ((end_angle-start_angle) % (2 * np.pi))
        if angle_range == 0:
            angle_range = 2*np.pi  # Special case: full circle gradient

        anglemask = theta <= angle_range
        theta = theta / angle_range  # Normalize to [0, 1] within range

        # Interpolate colors between start and end within the mask
        gradient = np.zeros((h, w, 4), dtype=np.uint8)
        start_color = Clock.pad_color(start_color)
        end_color = Clock.pad_color(end_color)
        for c in range(4):  # Iterate through RGBA channels
            gradient[..., c] = (
                start_color[c] * (1 - theta) + end_color[c] * (theta)
            ).astype(np.uint8)
        
        # Fill with the specified solid color
        gradient[~anglemask] = (0, 0, 0, 0)
        return Image.fromarray(gradient, mode="RGBA")

    @staticmethod
    def pad_color(color):
        # Add 255, until 4 values (RGBA) are in that array
        return tuple(list(color) + [255] * (4 - len(color)))

    @staticmethod
    def draw_clock_hand(image, length, angle, hand_color, hand_length=14, border_color=None, border_width = 0, hand_offset=0, round_corners=True, offset_width=4, hand_width=4):
        draw = ImageDraw.Draw(image)
        # Get the image dimensions
        w, h = image.size
        # Calculate the coordinates of the rectangle based on the angle and length

        # center point
        x1 = w / 2
        y1 = h / 2

        if hand_offset:
            offset_start = (x1, y1)
            offset_end = (x1 + hand_offset * np.cos(-angle), y1 + hand_offset * np.sin(-angle))
            draw.line([offset_start, offset_end], fill=border_color, width=offset_width, joint=None)
        
        # add hand_offset if set
        x1 = x1 + hand_offset * np.cos(-angle)
        y1 = y1 + hand_offset * np.sin(-angle)

        # determine end point of hand
        x2 = x1 + length * np.cos(-angle)
        y2 = y1 + length * np.sin(-angle)

        start = (x1,y1)
        end = (x2,y2)

        corners = Clock.calculate_rectangle_corners(start, end, hand_width)
        if round_corners:
            draw.circle(start, hand_width-0.6, fill=border_color)
            draw.circle(end, hand_width-0.8, fill=border_color)
        draw.polygon(corners, fill=hand_color, outline=border_color, width=border_width)
        if round_corners:
            draw.circle(start, hand_width-2, fill=hand_color)
            draw.circle(end, hand_width-2, fill=hand_color)

        return image

    @staticmethod
    def calculate_rectangle_corners(start, end, half_width):

        # Calculate the direction vector (from start to end)
        dir_x = end[0] - start[0]
        dir_y = end[1] - start[1]

        # Calculate the length of the direction vector
        dir_length = math.sqrt(dir_x ** 2 + dir_y ** 2)

        # Normalize the direction vector
        dir_x /= dir_length
        dir_y /= dir_length

        # Perpendicular vector (90 degrees to the direction vector)
        perp_x = -dir_y
        perp_y = dir_x

        # Calculate the corner points
        corner1 = (start[0] + half_width * perp_x, start[1] + half_width * perp_y)
        corner2 = (start[0] - half_width * perp_x, start[1] - half_width * perp_y)
        corner3 = (end[0] - half_width * perp_x, end[1] - half_width * perp_y)
        corner4 = (end[0] + half_width * perp_x, end[1] + half_width * perp_y)

        return [corner1, corner2, corner3, corner4]

    @staticmethod
    def calculate_clock_angles(time):
        """
        Calculate the angles for the hour and minute hands on a clock face.

        :param time: A datetime object representing the current time.
        :return: A tuple (hour_angle, minute_angle) in radians,
                where 90° (pi/2 radians) is 12 o'clock, and angles increase clockwise.
        """
        # Extract the hour, minute, and second from the time
        hour = time.hour % 12  # Convert to 12-hour format
        minute = time.minute
        second = time.second

        # Minute hand angle (6 degrees per minute, 0.1 degrees per second)
        minute_angle = (90 - (minute * 6 + second * 0.1)) % 360  # Convert to degrees, shift so 12:00 = 90°
        minute_angle = math.radians(minute_angle)  # Convert to radians

        # Hour hand angle (30 degrees per hour + offset by minutes and seconds)
        hour_angle = (90 - (hour * 30 + minute * 0.5 + second * (0.5 / 60))) % 360  # Convert to degrees
        hour_angle = math.radians(hour_angle)  # Convert to radians

        return hour_angle, minute_angle

    @staticmethod
    def drew_clock_center(image, center_radius, fill_color, outline_color=None, width=None):
        draw = ImageDraw.Draw(image)
        w, h = image.size

        # center point
        center = (w / 2, h/2)
        draw.circle(center, center_radius, fill=fill_color, outline=outline_color, width=width)

    @staticmethod
    def draw_hour_marks(image, radius, line_color=(255, 255, 255), line_length=25, line_width=3):
        """
        Draws a circle and lines radiating out every 30 degrees on the given image.

        :param image: A PIL Image object to draw on.
        :param center: A tuple (x, y) representing the center of the circle.
        :param radius: The radius of the circle.
        :param line_color: The color of the lines (default: white).
        :param circle_color: The color of the circle (default: white).
        :param line_width: The width of the lines (default: 2).
        """
        draw = ImageDraw.Draw(image)

        # Draw the circle
        x, y = image.size
        x /= 2
        y /=2

        # Draw the lines for every 30 degrees
        for angle in range(0, 360, 30):
            # Convert angle to radians
            angle_rad = math.radians(angle)

            start_x = x + (radius-line_length) * math.cos(angle_rad)
            start_y =  y - (radius-line_length) * math.sin(angle_rad)

            # Calculate the end point of the line
            end_x = x + radius * math.cos(angle_rad)
            end_y = y - radius * math.sin(angle_rad)  # Negative y because PIL's y-coordinates increase downward

            # Draw the line
            draw.line([(start_x, start_y), (end_x, end_y)], fill=line_color, width=line_width)

        return image

    @staticmethod
    def translate_word_grid_positions(hour, minute, language="en"):
        text_blocks = TEXT_BLOCKS.get(language) # get the text blocks for the language from constants
        minute_blocks = MINUTE_BLOCKS.get(language) # get the minute blocks for the language from constants

        letters = [] # initialize list of letter positions to light up
        letters.extend(text_blocks.get("IT IS")) # Inital letters

        _minute = minute
        if((language=="swabian") and (43 <= minute < 48)): # Swabian specific handling of "QUARTER TO"
            letters.extend(text_blocks.get("DREIVIERTL")) # DREIVIERTL
        else:
            if (minute > 30):
                _minute = 60 - minute
            if _minute >= 3:
                mapped_minute_value = round((0 + (5 - 0) * ((_minute - 3) / (28 - 3))) - 0.4)
                letters.extend(minute_blocks[mapped_minute_value])

        
        if(language=="swabian"): # Swabian specific handling of PAST/TO
            if (3 <= (minute%30) < 13):
                letters.extend(text_blocks.get("NACH")) # PAST
            elif (18 <= (minute%30) <= 27):
                letters.extend(text_blocks.get("VOR")) # TO
        else:
            if 3 <= minute < 33:
                letters.extend(text_blocks.get("PAST")) # PAST
            elif 33 <= minute <= 57:
                letters.extend(text_blocks.get("TO")) # TO

        hours = HOURS_BLOCKS.get(language)
        
        if minute >= HOUR_THRESHOLD.get(language): # handle language specific hour reference ("past current hour" or "to next hour")
            letters.extend(hours[hour])
        else:
            letters.extend(hours[hour - 1])

        if ((0 <= minute < 3) or (57 < minute <= 60)) and (LANGUAGE_OPTIONS.get(language).get("OCLOCK")==True): # Final word only if needed
            letters.extend(text_blocks.get("OCLOCK")) # OCLOCK 
        logger.debug(letters)
        return letters
