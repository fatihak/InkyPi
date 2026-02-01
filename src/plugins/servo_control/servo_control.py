import logging
import time
import os
from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageDraw, ImageFont
from utils.app_utils import get_font

logger = logging.getLogger(__name__)

# Try to import libgpiod for hardware control
try:
    import gpiod
    from gpiod.line import Direction, Value
    HAS_GPIOD = True
except ImportError as e:
    HAS_GPIOD = False
    logger.warning(f"libgpiod not available, will try gpiozero fallback. Error: {e}")

HAS_PWM_SYSFS = os.path.isdir("/sys/class/pwm")
HARDWARE_AVAILABLE = HAS_PWM_SYSFS or HAS_GPIOD

DEFAULT_PWM_CHIP = "pwmchip0"
DEFAULT_GPIO_PIN = 18
DEFAULT_ANGLE = 90
DEFAULT_SPEED = 10  # milliseconds delay between steps

SERVO_MIN_PULSE_US = 500
SERVO_0_DEGREE_PULSE_US = 1000
SERVO_180_DEGREE_PULSE_US = 2000
SERVO_MAX_PULSE_US = 2500
SERVO_US_PER_DEGREE = (SERVO_180_DEGREE_PULSE_US - SERVO_0_DEGREE_PULSE_US) / 180.0
MIN_ANGLE = (SERVO_MIN_PULSE_US - SERVO_0_DEGREE_PULSE_US) / SERVO_US_PER_DEGREE
MAX_ANGLE = (SERVO_MAX_PULSE_US - SERVO_0_DEGREE_PULSE_US) / SERVO_US_PER_DEGREE
SERVO_PERIOD_US = 20000  # 50Hz

class ServoControl(BasePlugin):
    """
    Plugin to control a servo motor connected to a Raspberry Pi GPIO pin.
    Supports manual angle control and orientation updates.
    """
    
    def __init__(self, config, **dependencies):
        super().__init__(config, **dependencies)
        self.current_gpio_pin = None
        self.gpiod_chip = None
        self.gpiod_line = None
        self.gpiod_request = None
        self.gpiod_api = None
        self.backend = None
        self.pwm_chip = DEFAULT_PWM_CHIP
        self.pwm_channel = None
        self.pwm_chip_path = None
        self.pwm_path = None
        self.pwm_enabled = False
        
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

        self.backend = self._select_backend(gpio_pin)

        if self.backend == "pwm_sysfs":
            if self.current_gpio_pin != gpio_pin:
                self._cleanup_pwm_sysfs()
            if not self.pwm_path:
                try:
                    self._initialize_pwm_sysfs(gpio_pin)
                    self.current_gpio_pin = gpio_pin
                    logger.info(f"Initialized servo on GPIO pin {gpio_pin} with kernel PWM")
                except Exception as e:
                    logger.error(f"Failed to initialize kernel PWM on GPIO {gpio_pin}: {e}")
                    raise RuntimeError(f"Failed to initialize kernel PWM on GPIO pin {gpio_pin}: {e}")
            return

        if self.backend == "gpiod":
            # Clean up existing line if pin changed
            if self.current_gpio_pin != gpio_pin:
                self._cleanup_gpiod()

            if not self.gpiod_line and not self.gpiod_request:
                try:
                    self._initialize_gpiod_line(gpio_pin)
                    self.current_gpio_pin = gpio_pin
                    logger.info(f"Initialized servo on GPIO pin {gpio_pin} with libgpiod")
                except Exception as e:
                    logger.error(f"Failed to initialize libgpiod on GPIO {gpio_pin}: {e}")
                    raise RuntimeError(f"Failed to initialize libgpiod on GPIO pin {gpio_pin}: {e}")
            return
        
        logger.info("No additional backend initialization required.")

    def _select_backend(self, gpio_pin):
        """Select the best available backend for servo control."""
        if self._pwm_sysfs_available(gpio_pin):
            return "pwm_sysfs"
        if HAS_GPIOD:
            return "gpiod"
        return "mock"

    def _pwm_sysfs_available(self, gpio_pin):
        """Check if kernel PWM sysfs is available for the GPIO pin."""
        chip_path = f"/sys/class/pwm/{self.pwm_chip}"
        if not os.path.isdir(chip_path):
            return False
        if self.pwm_channel is not None:
            return True
        return gpio_pin in (12, 13, 18, 19)

    def _gpio_pin_to_pwm_channel(self, gpio_pin):
        """Map common Raspberry Pi GPIO pins to PWM channels."""
        if self.pwm_channel is not None:
            return self.pwm_channel
        mapping = {
            12: 0,
            18: 0,
            13: 1,
            19: 1,
        }
        return mapping.get(gpio_pin)

    def _initialize_pwm_sysfs(self, gpio_pin):
        """Initialize kernel PWM sysfs for hardware-timed PWM."""
        channel = self._gpio_pin_to_pwm_channel(gpio_pin)
        if channel is None:
            raise RuntimeError("GPIO pin does not map to a PWM channel. Set pwm_channel in settings.")

        self.pwm_chip_path = f"/sys/class/pwm/{self.pwm_chip}"
        self.pwm_path = f"{self.pwm_chip_path}/pwm{channel}"

        export_path = f"{self.pwm_chip_path}/export"
        enable_path = f"{self.pwm_path}/enable"
        period_path = f"{self.pwm_path}/period"
        duty_path = f"{self.pwm_path}/duty_cycle"

        if not os.path.isdir(self.pwm_chip_path):
            raise RuntimeError(f"PWM chip path not found: {self.pwm_chip_path}")

        if not os.path.isdir(self.pwm_path):
            with open(export_path, "w", encoding="utf-8") as f:
                f.write(str(channel))

        # Disable before configuring
        if os.path.exists(enable_path):
            with open(enable_path, "w", encoding="utf-8") as f:
                f.write("0")

        period_ns = SERVO_PERIOD_US * 1000
        with open(period_path, "w", encoding="utf-8") as f:
            f.write(str(period_ns))
        with open(duty_path, "w", encoding="utf-8") as f:
            f.write(str(SERVO_MIN_PULSE_US * 1000))

        with open(enable_path, "w", encoding="utf-8") as f:
            f.write("1")
        self.pwm_enabled = True

    def _cleanup_pwm_sysfs(self):
        """Disable and unexport kernel PWM sysfs."""
        if not self.pwm_path or not self.pwm_chip_path:
            return

        enable_path = f"{self.pwm_path}/enable"
        unexport_path = f"{self.pwm_chip_path}/unexport"
        channel = self._gpio_pin_to_pwm_channel(self.current_gpio_pin) if self.current_gpio_pin is not None else None

        try:
            if os.path.exists(enable_path):
                with open(enable_path, "w", encoding="utf-8") as f:
                    f.write("0")
        except Exception:
            pass

        try:
            if channel is not None and os.path.exists(unexport_path):
                with open(unexport_path, "w", encoding="utf-8") as f:
                    f.write(str(channel))
        except Exception:
            pass

        self.pwm_path = None
        self.pwm_chip_path = None
        self.pwm_enabled = False

    def _initialize_gpiod_line(self, gpio_pin):
        """Initialize libgpiod line (supports v1 and v2 APIs)."""
        if hasattr(gpiod, "LineSettings") and hasattr(gpiod, "request_lines"):
            # libgpiod v2 API
            self.gpiod_api = "v2"
            config = {
                gpio_pin: gpiod.LineSettings(
                    direction=Direction.OUTPUT,
                    output_value=Value.INACTIVE,
                )
            }
            self.gpiod_request = gpiod.request_lines(
                "/dev/gpiochip0",
                consumer="inkypi-servo",
                config=config,
            )
        else:
            # libgpiod v1 API
            self.gpiod_api = "v1"
            self.gpiod_chip = gpiod.Chip("gpiochip0")
            self.gpiod_line = self.gpiod_chip.get_line(gpio_pin)
            self.gpiod_line.request(
                consumer="inkypi-servo",
                type=gpiod.LINE_REQ_DIR_OUT,
                default_vals=[0],
            )

    def _cleanup_gpiod(self):
        """Release libgpiod resources."""
        if self.gpiod_request:
            try:
                self.gpiod_request.close()
            except Exception:
                pass
            self.gpiod_request = None

        if self.gpiod_line:
            try:
                self.gpiod_line.release()
            except Exception:
                pass
            self.gpiod_line = None

        if self.gpiod_chip:
            try:
                self.gpiod_chip.close()
            except Exception:
                pass
            self.gpiod_chip = None
        self.gpiod_api = None
    
    def _angle_to_pulse_us(self, angle):
        """Convert angle (0-180) to PWM pulse width in microseconds."""
        angle = max(MIN_ANGLE, min(MAX_ANGLE, angle))
        pulse = SERVO_0_DEGREE_PULSE_US + (angle * SERVO_US_PER_DEGREE)
        return int(max(SERVO_MIN_PULSE_US, min(SERVO_MAX_PULSE_US, pulse)))

    def _pwm_sysfs_set_pulse_us(self, pulse_us):
        """Set PWM duty cycle via sysfs in nanoseconds."""
        if not self.pwm_path:
            return
        duty_path = f"{self.pwm_path}/duty_cycle"
        duty_ns = int(pulse_us * 1000)
        with open(duty_path, "w", encoding="utf-8") as f:
            f.write(str(duty_ns))

    def _pwm_sysfs_disable(self):
        """Disable PWM output without unexporting the channel."""
        if not self.pwm_path:
            return
        enable_path = f"{self.pwm_path}/enable"
        if os.path.exists(enable_path):
            with open(enable_path, "w", encoding="utf-8") as f:
                f.write("0")

    def _gpiod_set_value(self, active):
        """Set GPIO line value using libgpiod."""
        if self.gpiod_api == "v2" and self.gpiod_request:
            value = Value.ACTIVE if active else Value.INACTIVE
            self.gpiod_request.set_value(self.current_gpio_pin, value)
        elif self.gpiod_line:
            self.gpiod_line.set_value(1 if active else 0)

    def _gpiod_pwm_for_duration(self, pulse_us, duration_ms):
        """Software PWM via libgpiod for a specific duration."""
        period_us = SERVO_PERIOD_US
        high_s = pulse_us / 1_000_000
        low_s = max(0.0, (period_us - pulse_us) / 1_000_000)
        end_time = time.monotonic() + (duration_ms / 1000.0)
        while time.monotonic() < end_time:
            self._gpiod_set_value(True)
            time.sleep(high_s)
            self._gpiod_set_value(False)
            time.sleep(low_s)
    
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

        self.backend = self._select_backend(gpio_pin)

        if self.backend == "pwm_sysfs":
            try:
                self._initialize_servo(gpio_pin)
                step = 1 if target_angle > current_angle else -1
                for angle in range(int(current_angle), int(target_angle), step):
                    pulse_us = self._angle_to_pulse_us(angle)
                    self._pwm_sysfs_set_pulse_us(pulse_us)
                    logger.info(f"new Angle: {angle}° new Pulse: {pulse_us}us")
                    time.sleep(speed_ms / 1000)

                final_pulse_us = self._angle_to_pulse_us(target_angle)
                self._pwm_sysfs_set_pulse_us(final_pulse_us)
                time.sleep(0.2)
                self._pwm_sysfs_disable()
                logger.info(f"Moved servo from {current_angle}° to {target_angle}° (kernel PWM)")
                return
            except Exception as e:
                logger.error(f"Failed to move servo with kernel PWM: {e}")
                raise RuntimeError(f"Failed to move servo with kernel PWM: {e}")

        if self.backend == "gpiod":
            try:
                # Initialize line if needed
                self._initialize_servo(gpio_pin)

                # Calculate step direction
                step = 1 if target_angle > current_angle else -1

                for angle in range(int(current_angle), int(target_angle), step):
                    pulse_us = self._angle_to_pulse_us(angle)
                    step_duration_ms = max(speed_ms, 20)
                    self._gpiod_pwm_for_duration(pulse_us, step_duration_ms)
                    logger.info(f"new Angle: {angle}° new Pulse: {pulse_us}us")

                # Ensure we reach exact target
                final_pulse_us = self._angle_to_pulse_us(target_angle)
                self._gpiod_pwm_for_duration(final_pulse_us, max(200, speed_ms))
                self._gpiod_set_value(False)
                logger.info(f"Moved servo from {current_angle}° to {target_angle}° (libgpiod)")
                return
            except Exception as e:
                logger.error(f"Failed to move servo with libgpiod: {e}")
                raise RuntimeError(f"Failed to move servo with libgpiod: {e}")
        
        logger.warning("No supported backend available; servo move skipped.")
    
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
        self._cleanup_gpiod()
        self._cleanup_pwm_sysfs()
