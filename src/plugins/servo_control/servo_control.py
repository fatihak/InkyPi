import logging
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
        self.servo_driver.configure(gpio_pin=gpio_pin, pwm_chip=self.pwm_chip, pwm_channel=self.pwm_channel)
        self.servo_driver.move(current_angle, target_angle, servo_speed)
        logger.info("Finished Servo Move Call")
        
        # Store new angle in device config for next boot
        device_config.update_value('current_servo_angle', target_angle, write=True)
        
        # Get dimensions
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        
        # Create status image
        image = self._create_status_image(dimensions, gpio_pin, target_angle, orientation)
        
        return image
    
    def _create_status_image(self, dimensions, gpio_pin, target_angle, orientation):
        """
        Create a status image showing servo state.
        
        Args:
            dimensions: Image dimensions (width, height)
            gpio_pin: GPIO pin number
            current_angle: Current servo angle
            positions: Dictionary of saved positions
            
        Returns:
            PIL.Image: Status image
        """
        width, height = dimensions
        image = Image.new('RGB', (width, height), color='black')
        draw = ImageDraw.Draw(image)

        # High-contrast palette
        sky_color = '#00CFEB'
        ground_color = '#EACE00'
        horizon_color = '#EB0078'
        text_color = '#ffffff'

        # Map target angle (0-180) to horizon tilt (0 to 90 degrees)
        normalized = (target_angle - 90) / 90.0
        tilt_deg = max(0, min(90, normalized * 90))
        tilt_rad = (tilt_deg * 3.141592653589793) / 180.0

        # Horizon line parameters
        cx, cy = width / 2, height / 2
        line_len = max(width, height) * 1.5
        dx = (line_len / 2) * (1.0 if tilt_deg == 0 else (abs(__import__('math').cos(tilt_rad))))
        dy = (line_len / 2) * (1.0 if tilt_deg == 0 else (abs(__import__('math').sin(tilt_rad))))

        # Compute line endpoints using rotation matrix
        cos_t = __import__('math').cos(tilt_rad)
        sin_t = __import__('math').sin(tilt_rad)
        x1 = cx - (line_len / 2) * cos_t
        y1 = cy - (line_len / 2) * sin_t
        x2 = cx + (line_len / 2) * cos_t
        y2 = cy + (line_len / 2) * sin_t

        # Fill sky/ground polygons
        draw.polygon([(0, 0), (width, 0), (x2, y2), (x1, y1)], fill=sky_color)
        draw.polygon([(0, height), (width, height), (x2, y2), (x1, y1)], fill=ground_color)

        # Horizon line (thick)
        line_width = max(2, int(min(width, height) * 0.04))
        draw.line([(x1, y1), (x2, y2)], fill=horizon_color, width=line_width)

        # Center marker
        marker_size = max(4, int(min(width, height) * 0.06))
        draw.rectangle(
            [
                (cx - marker_size, cy - line_width),
                (cx + marker_size, cy + line_width)
            ],
            fill=horizon_color
        )

        # Angle text overlay
        font = ImageFont.load_default()
        angle_text = f"{target_angle}°"
        draw.text((width * 0.06, height * 0.06), angle_text, font=font, fill=text_color)

        return image
    
    def cleanup(self, settings):
        """Clean up servo resources when plugin instance is deleted."""
        self.servo_driver.cleanup()
