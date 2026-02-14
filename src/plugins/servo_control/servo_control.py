import logging
from display.mock_display import MockDisplay
from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageDraw, ImageFont
from utils.servo_utils import ServoDriver, DEFAULT_GPIO_PIN, DEFAULT_ANGLE, DEFAULT_SPEED

logger = logging.getLogger(__name__)

DEFAULT_PWM_CHIP = "pwmchip0"

class ServoControl(BasePlugin):
    """
    Plugin to control a servo motor connected to a Raspberry Pi GPIO pin.
    Supports manual angle control and orientation updates.
    """
    
    def __init__(self, config, **dependencies):
        super().__init__(config, **dependencies)
        self.pwm_chip = DEFAULT_PWM_CHIP
        self.pwm_channel = None
        self.servo_driver = ServoDriver()
        
    def generate_settings_template(self):
        """Provide settings template."""
        template_params = super().generate_settings_template()
        return template_params
    
    def generate_image(self, settings, device_config):
        """
        Generate a status image showing current servo state and move servo to target angle.
        
        Args:
            settings: Plugin settings containing gpio_pin, target_angle, servo_speed, orientation
            device_config: Device configuration instance
            
        Returns:
            PIL.Image: Status display image
        """
        # Get current settings (convert strings to integers)
        gpio_pin = int(settings.get('gpio_pin', DEFAULT_GPIO_PIN))
        target_angle = int(settings.get('target_angle', DEFAULT_ANGLE))
        servo_speed = int(settings.get('servo_speed', DEFAULT_SPEED))
        orientation = settings.get('orientation', 'current')
        invert_setting = settings.get('inverted_image', None)
        self.pwm_chip = str(settings.get('pwm_chip', DEFAULT_PWM_CHIP))
        pwm_channel = settings.get('pwm_channel', None)
        self.pwm_channel = int(pwm_channel) if pwm_channel not in (None, "") else None
        display_type = device_config.get_config("display_type")
        
        # Get current angle from device config (persistent across reboots)
        current_angle = device_config.get_config('current_servo_angle', DEFAULT_ANGLE)
        
        # Update orientation if specified
        if orientation == 'landscape':
            device_config.update_value("orientation", "horizontal", write=True)
            logger.info("Updated device orientation to horizontal (landscape)")
        elif orientation == 'portrait':
            device_config.update_value("orientation", "vertical", write=True)
            logger.info("Updated device orientation to vertical (portrait)")
        # if 'current', do not change orientation

        # Update image inversion if specified
        invert_value = str(invert_setting).lower() in ("1", "true", "yes", "on")
        device_config.update_value("inverted_image", invert_value, write=True)
        logger.info(f"Updated inverted_image to {invert_value}")
        
        
        # Move servo to the target angle
        logger.info("Call Servo Move")
        if display_type == "mock":
            logger.info(f"Mock Servo move from {current_angle}° to {target_angle}° at speed {servo_speed} (GPIO pin {gpio_pin})")
        else:
            self.servo_driver.configure(gpio_pin=gpio_pin, pwm_chip=self.pwm_chip, pwm_channel=self.pwm_channel)
            self.servo_driver.move(current_angle, target_angle, servo_speed)
        logger.info("Finished Servo Move Call")
        
        # Store new angle in device config for next boot
        device_config.update_value('current_servo_angle', target_angle, write=True)
        
        # Get dimensions
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        
        # Check if test image should be shown
        show_test_image = str(settings.get('show_test_image', 'false')).lower() in ("1", "true", "yes", "on")
        
        if show_test_image:
            # Create status image with virtual horizon
            return self._create_status_image(dimensions, gpio_pin, target_angle, orientation)
        else:
            # No image to display - servo has been moved, return None
            return None
    
    def _create_status_image(self, dimensions, gpio_pin, target_angle, orientation):
        """
        Create a virtual horizon test image.
        
        The horizon is drawn at an angle that compensates for the physical rotation
        of the display. When the screen is rotated to match the servo angle (target_angle),
        the horizon should appear level/straight.
        
        For example:
        - If target_angle = 90° (level), the horizon is drawn horizontally
        - If target_angle = 0° (rotated 90° CCW), the horizon is drawn at 90° CW
          so it appears horizontal when the screen is physically rotated
        
        Args:
            dimensions: Image dimensions (width, height)
            gpio_pin: GPIO pin number
            target_angle: Target servo angle in degrees
            orientation: Display orientation setting
            
        Returns:
            PIL.Image: Virtual horizon test image
        """
        import math
        
        width, height = dimensions
        image = Image.new('RGB', (width, height), color='black')
        draw = ImageDraw.Draw(image)

        # High-contrast color palette
        sky_color = '#00CFEB'      # Cyan for sky
        ground_color = '#EACE00'   # Yellow for ground
        horizon_color = '#EB0078'  # Magenta for horizon line
        text_color = '#00EB00'     # Light green for text

        # Calculate the rotation angle for the virtual horizon
        # The horizon should be tilted opposite to the physical rotation
        # so it appears level when the display is rotated
        # Assuming 90° is level, and angles rotate from there
        rotation_angle = 90 - target_angle  # Degrees to rotate the horizon
        rotation_rad = math.radians(rotation_angle)

        # Center point of the image
        cx, cy = width / 2, height / 2
        
        # Length of the horizon line (diagonal across the image)
        line_len = math.sqrt(width**2 + height**2) * 1.2

        # Calculate horizon line endpoints using rotation
        cos_r = math.cos(rotation_rad)
        sin_r = math.sin(rotation_rad)
        x1 = cx - (line_len / 2) * cos_r
        y1 = cy - (line_len / 2) * sin_r
        x2 = cx + (line_len / 2) * cos_r
        y2 = cy + (line_len / 2) * sin_r

        # Determine which corners are above/below the horizon line
        # Create polygons for sky (above) and ground (below)
        corners = [(0, 0), (width, 0), (width, height), (0, height)]
        
        # Sky polygon: top corners + horizon line points
        if rotation_angle >= -45 and rotation_angle <= 45:
            # Horizon is mostly horizontal
            sky_points = [(0, 0), (width, 0), (x2, y2), (x1, y1)]
            ground_points = [(0, height), (width, height), (x2, y2), (x1, y1)]
        else:
            # For steep angles, use all corners and line points
            sky_points = [(0, 0), (width, 0), (x2, y2), (x1, y1)]
            ground_points = [(0, height), (width, height), (x2, y2), (x1, y1)]

        # Fill sky and ground
        draw.polygon(sky_points, fill=sky_color)
        draw.polygon(ground_points, fill=ground_color)

        # Draw the horizon line (thick)
        line_width = max(3, int(min(width, height) * 0.015))
        draw.line([(x1, y1), (x2, y2)], fill=horizon_color, width=line_width)

        # Draw center marker (crosshair)
        marker_size = max(8, int(min(width, height) * 0.03))
        # Horizontal line
        draw.line(
            [(cx - marker_size, cy), (cx + marker_size, cy)],
            fill=horizon_color,
            width=max(2, line_width // 2)
        )
        # Vertical line
        draw.line(
            [(cx, cy - marker_size), (cx, cy + marker_size)],
            fill=horizon_color,
            width=max(2, line_width // 2)
        )

        # Draw angle information
        font = ImageFont.load_default()
        angle_text = f"Servo: {target_angle}°"
        rotation_text = f"Horizon: {rotation_angle:.1f}°"
        
        # Position text in corner with padding
        padding = int(min(width, height) * 0.03)
        draw.text((padding, padding), angle_text, font=font, fill=text_color)
        draw.text((padding, padding + 15), rotation_text, font=font, fill=text_color)
        
        # Add instructions at bottom
        instruction_text = "Rotate display to match servo angle"
        bbox = draw.textbbox((0, 0), instruction_text, font=font)
        text_width = bbox[2] - bbox[0]
        draw.text(
            ((width - text_width) // 2, height - padding - 15),
            instruction_text,
            font=font,
            fill=text_color
        )

        return image
    
    def cleanup(self, settings):
        """Clean up servo resources when plugin instance is deleted."""
        self.servo_driver.cleanup()
