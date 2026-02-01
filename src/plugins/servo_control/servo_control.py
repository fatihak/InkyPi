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
        
        # Move servo to the target angle
        self.servo_driver.configure(gpio_pin=gpio_pin, pwm_chip=self.pwm_chip, pwm_channel=self.pwm_channel)
        self.servo_driver.move(current_angle, target_angle, servo_speed)
        
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
        
        # Create white background
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)
        
        title_font = ImageFont.load_default()
        large_font = ImageFont.load_default()
        medium_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

        
        # Title
        title = "Servo Control"
        draw.text((width // 2, height * 0.1), title, font=title_font, fill='black', anchor='mm')
        
        # Target angle - large display
        angle_text = f"{target_angle}°"
        draw.text((width // 2, height * 0.3), angle_text, font=large_font, fill='#2c3e50', anchor='mm')
        
        # GPIO pin info
        gpio_text = f"GPIO Pin: {gpio_pin}"
        draw.text((width // 2, height * 0.45), gpio_text, font=medium_font, fill='#7f8c8d', anchor='mm')
        
        # Draw a simple arc to visualize angle
        arc_y = height * 0.6
        arc_radius = min(width, height) * 0.15
        arc_bbox = [
            width // 2 - arc_radius,
            arc_y - arc_radius,
            width // 2 + arc_radius,
            arc_y + arc_radius
        ]
        
        # Background arc (0-180)
        draw.arc(arc_bbox, start=0, end=180, fill='#ecf0f1', width=int(height * 0.02))
        
        # Target position arc
        draw.arc(arc_bbox, start=0, end=target_angle, fill='#3498db', width=int(height * 0.02))
        
        # Orientation info
        if orientation in ['landscape', 'portrait']:
            y_offset = height * 0.78
            draw.text((width // 2, y_offset), "Orientation:", font=medium_font, fill='black', anchor='mm')
            
            y_offset += height * 0.06
            orientation_text = orientation.capitalize()
            orientation_color = '#e74c3c'
            draw.text((width // 2, y_offset), orientation_text, font=small_font, fill=orientation_color, anchor='mm')
        
        return image
    
    def cleanup(self, settings):
        """Clean up servo resources when plugin instance is deleted."""
        self.servo_driver.cleanup()
