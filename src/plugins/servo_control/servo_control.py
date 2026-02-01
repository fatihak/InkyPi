import logging
import time
from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageDraw, ImageFont
from utils.app_utils import get_font

logger = logging.getLogger(__name__)

# Try to import gpiozero for hardware control
try:
    from gpiozero import Servo
    from gpiozero.pins.pigpio import PiGPIOFactory
    HARDWARE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"gpiozero not available, servo control will be mocked. Error: {e}")
    logger.info("To enable hardware control, install gpiozero: pip install gpiozero")
    HARDWARE_AVAILABLE = False

DEFAULT_GPIO_PIN = 13
DEFAULT_ANGLE = 90
DEFAULT_SPEED = 10  # milliseconds delay between steps
MIN_ANGLE = 0
MAX_ANGLE = 180

class ServoControl(BasePlugin):
    """
    Plugin to control a servo motor connected to a Raspberry Pi GPIO pin.
    Supports manual angle control and orientation updates.
    """
    
    def __init__(self, config, **dependencies):
        super().__init__(config, **dependencies)
        self.servo = None
        self.current_gpio_pin = None
        
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
        self._move_servo(gpio_pin, current_angle, target_angle, servo_speed)
        
        # Store new angle in device config for next boot
        device_config.update_value('current_servo_angle', target_angle, write=True)
        
        # Get dimensions
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        
        # Create status image
        image = self._create_status_image(dimensions, gpio_pin, target_angle, orientation)
        
        return image
    
    def _initialize_servo(self, gpio_pin):
        """Initialize servo on specified GPIO pin."""
        if not HARDWARE_AVAILABLE:
            logger.info(f"Mock: Would initialize servo on GPIO pin {gpio_pin}")
            return
        
        # Clean up existing servo if pin changed
        if self.servo and self.current_gpio_pin != gpio_pin:
            try:
                self.servo.close()
            except:
                pass
            self.servo = None
        
        # Initialize new servo
        if not self.servo or self.current_gpio_pin != gpio_pin:
            try:
                # Use pigpio for better PWM control if available
                factory = PiGPIOFactory()
                # SG90 specific pulse widths: 1ms (0°) to 2ms (180°)
                self.servo = Servo(gpio_pin, min_pulse_width=1/1000, max_pulse_width=2/1000, pin_factory=factory)
                self.current_gpio_pin = gpio_pin
                logger.info(f"Initialized servo on GPIO pin {gpio_pin} with pigpio")
            except Exception as e:
                logger.warning(f"Failed to use pigpio, falling back to default: {e}")
                try:
                    # SG90 specific pulse widths for default factory too
                    self.servo = Servo(gpio_pin, min_pulse_width=1/1000, max_pulse_width=2/1000)
                    self.current_gpio_pin = gpio_pin
                    logger.info(f"Initialized servo on GPIO pin {gpio_pin} (default pins)")
                except Exception as e:
                    logger.error(f"Failed to initialize servo: {e}")
                    raise RuntimeError(f"Failed to initialize servo on GPIO pin {gpio_pin}: {e}")
    
    def _angle_to_servo_value(self, angle):
        """
        Convert angle (0-180) to servo value (-1 to 1).
        For SG90 servo: -1 = 0°, 0 = 90°, 1 = 180°
        """
        # Map 0-180 to -1 to 1
        return (angle / 90.0) - 1.0
    
    def _move_servo(self, gpio_pin, current_angle, target_angle, speed_ms):
        """
        Move servo from current angle to target angle with smooth motion.
        
        Args:
            gpio_pin: GPIO pin number
            current_angle: Starting angle (0-180)
            target_angle: Target angle (0-180)
            speed_ms: Delay in milliseconds between angle steps
        """
        # Validate angles
        current_angle = max(MIN_ANGLE, min(MAX_ANGLE, current_angle))
        target_angle = max(MIN_ANGLE, min(MAX_ANGLE, target_angle))
        
        if not HARDWARE_AVAILABLE:
            logger.info(f"Mock: Would move servo on GPIO {gpio_pin} from {current_angle}° to {target_angle}° at {speed_ms}ms speed")
            return
        
        try:
            # Initialize servo if needed
            self._initialize_servo(gpio_pin)
            
            # Calculate step direction
            step = 1 if target_angle > current_angle else -1
            
            # Move incrementally for smooth motion
            for angle in range(int(current_angle), int(target_angle), step):
                servo_value = self._angle_to_servo_value(angle)
                self.servo.value = servo_value
                logger.info(f"new Angle: {angle}° new Servo Value: {servo_value}")
                time.sleep(speed_ms/1000)
            
            # Ensure we reach exact target
            final_value = self._angle_to_servo_value(target_angle)
            self.servo.value = final_value
            
            # Stop sending PWM signals without causing servo twitch
            time.sleep(0.5)  # Hold position briefly
            self.servo.value = None
            logger.info(f"Moved servo from {current_angle}° to {target_angle}°")
            
        except Exception as e:
            logger.error(f"Failed to move servo: {e}")
            raise RuntimeError(f"Failed to move servo: {e}")
    
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
        
        # Fonts
        try:
            title_font = get_font("Roboto-Bold", int(height * 0.08))
            large_font = get_font("Roboto-Bold", int(height * 0.15))
            medium_font = get_font("Roboto-Regular", int(height * 0.06))
            small_font = get_font("Roboto-Regular", int(height * 0.045))
        except:
            # Fallback to default font
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
        if self.servo:
            try:
                self.servo.close()
                logger.info("Closed servo connection")
            except Exception as e:
                logger.error(f"Error closing servo: {e}")
