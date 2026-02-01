import logging
import os
import time
import threading

logger = logging.getLogger(__name__)

# Try to import libgpiod for hardware control
try:
    import gpiod
    from gpiod.line import Direction, Value
    HAS_GPIOD = True
except ImportError as e:
    HAS_GPIOD = False
    logger.warning(f"libgpiod not available, will try kernel PWM only. Error: {e}")

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


class ServoDriver:
    """Hardware driver for servo control via kernel PWM or libgpiod."""

    def __init__(self, gpio_pin=DEFAULT_GPIO_PIN, pwm_chip=DEFAULT_PWM_CHIP, pwm_channel=None):
        self.current_gpio_pin = None
        self.gpio_pin = gpio_pin
        self.pwm_chip = pwm_chip
        self.pwm_channel = pwm_channel

        self.gpiod_chip = None
        self.gpiod_line = None
        self.gpiod_request = None
        self.gpiod_api = None

        self.backend = None
        self.pwm_chip_path = None
        self.pwm_path = None
        self.pwm_enabled = False
        self._move_lock = threading.Lock()
        self._move_thread = None

    def configure(self, gpio_pin=None, pwm_chip=None, pwm_channel=None):
        """Update servo configuration and reset backends if needed."""
        if pwm_chip is not None:
            self.pwm_chip = pwm_chip
        if pwm_channel is not None:
            self.pwm_channel = pwm_channel

        if gpio_pin is not None and gpio_pin != self.gpio_pin:
            self.gpio_pin = gpio_pin
            self.current_gpio_pin = None
            self._cleanup_gpiod()
            self._cleanup_pwm_sysfs()

    def move(self, current_angle, target_angle, speed_ms):
        """Move servo from current angle to target angle asynchronously."""
        if self._move_thread and self._move_thread.is_alive():
            logger.warning("Servo move already in progress; new request ignored.")
            return

        self._move_thread = threading.Thread(
            target=self._move_blocking,
            args=(current_angle, target_angle, speed_ms),
            daemon=True,
        )
        self._move_thread.start()

    def _move_blocking(self, current_angle, target_angle, speed_ms):
        with self._move_lock:
            if not HARDWARE_AVAILABLE:
                logger.info(
                    f"Mock: Would move servo on GPIO {self.gpio_pin} from {current_angle}° to {target_angle}° at {speed_ms}ms speed"
                )
                return

            current_angle = max(MIN_ANGLE, min(MAX_ANGLE, current_angle))
            target_angle = max(MIN_ANGLE, min(MAX_ANGLE, target_angle))

            self.backend = self._select_backend(self.gpio_pin)

            if self.backend == "pwm_sysfs":
                self._initialize_pwm_if_needed(self.gpio_pin)
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

            if self.backend == "gpiod":
                self._initialize_gpiod_if_needed(self.gpio_pin)
                step = 1 if target_angle > current_angle else -1
                for angle in range(int(current_angle), int(target_angle), step):
                    pulse_us = self._angle_to_pulse_us(angle)
                    step_duration_ms = max(speed_ms, 20)
                    self._gpiod_pwm_for_duration(pulse_us, step_duration_ms)
                    logger.info(f"new Angle: {angle}° new Pulse: {pulse_us}us")

                final_pulse_us = self._angle_to_pulse_us(target_angle)
                self._gpiod_pwm_for_duration(final_pulse_us, max(200, speed_ms))
                self._gpiod_set_value(False)
                logger.info(f"Moved servo from {current_angle}° to {target_angle}° (libgpiod)")
                return

            logger.warning("No supported backend available; servo move skipped.")

    def cleanup(self):
        """Clean up hardware resources."""
        self._cleanup_gpiod()
        self._cleanup_pwm_sysfs()

    def _select_backend(self, gpio_pin):
        if self._pwm_sysfs_available(gpio_pin):
            return "pwm_sysfs"
        if HAS_GPIOD:
            return "gpiod"
        return "mock"

    def _pwm_sysfs_available(self, gpio_pin):
        chip_path = f"/sys/class/pwm/{self.pwm_chip}"
        if not os.path.isdir(chip_path):
            return False
        if self.pwm_channel is not None:
            return True
        return gpio_pin in (12, 13, 18, 19)

    def _gpio_pin_to_pwm_channel(self, gpio_pin):
        if self.pwm_channel is not None:
            return self.pwm_channel
        mapping = {
            12: 0,
            18: 0,
            13: 1,
            19: 1,
        }
        return mapping.get(gpio_pin)

    def _initialize_pwm_if_needed(self, gpio_pin):
        if self.current_gpio_pin != gpio_pin:
            self._cleanup_pwm_sysfs()
        if not self.pwm_path:
            self._initialize_pwm_sysfs(gpio_pin)
            self.current_gpio_pin = gpio_pin
            logger.info(f"Initialized servo on GPIO pin {gpio_pin} with kernel PWM")

    def _initialize_pwm_sysfs(self, gpio_pin):
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

    def _initialize_gpiod_if_needed(self, gpio_pin):
        if self.current_gpio_pin != gpio_pin:
            self._cleanup_gpiod()
        if not self.gpiod_line and not self.gpiod_request:
            self._initialize_gpiod_line(gpio_pin)
            self.current_gpio_pin = gpio_pin
            logger.info(f"Initialized servo on GPIO pin {gpio_pin} with libgpiod")

    def _initialize_gpiod_line(self, gpio_pin):
        if hasattr(gpiod, "LineSettings") and hasattr(gpiod, "request_lines"):
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
            self.gpiod_api = "v1"
            self.gpiod_chip = gpiod.Chip("gpiochip0")
            self.gpiod_line = self.gpiod_chip.get_line(gpio_pin)
            self.gpiod_line.request(
                consumer="inkypi-servo",
                type=gpiod.LINE_REQ_DIR_OUT,
                default_vals=[0],
            )

    def _cleanup_gpiod(self):
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
        angle = max(MIN_ANGLE, min(MAX_ANGLE, angle))
        pulse = SERVO_0_DEGREE_PULSE_US + (angle * SERVO_US_PER_DEGREE)
        return int(max(SERVO_MIN_PULSE_US, min(SERVO_MAX_PULSE_US, pulse)))

    def _pwm_sysfs_set_pulse_us(self, pulse_us):
        if not self.pwm_path:
            return
        enable_path = f"{self.pwm_path}/enable"
        duty_path = f"{self.pwm_path}/duty_cycle"
        duty_ns = int(pulse_us * 1000)
        if os.path.exists(enable_path):
            with open(enable_path, "w", encoding="utf-8") as f:
                f.write("1")
        with open(duty_path, "w", encoding="utf-8") as f:
            f.write(str(duty_ns))

    def _pwm_sysfs_disable(self):
        if not self.pwm_path:
            return
        enable_path = f"{self.pwm_path}/enable"
        if os.path.exists(enable_path):
            with open(enable_path, "w", encoding="utf-8") as f:
                f.write("0")

    def _gpiod_set_value(self, active):
        if self.gpiod_api == "v2" and self.gpiod_request:
            value = Value.ACTIVE if active else Value.INACTIVE
            self.gpiod_request.set_value(self.current_gpio_pin, value)
        elif self.gpiod_line:
            self.gpiod_line.set_value(1 if active else 0)

    def _gpiod_pwm_for_duration(self, pulse_us, duration_ms):
        period_us = SERVO_PERIOD_US
        high_s = pulse_us / 1_000_000
        low_s = max(0.0, (period_us - pulse_us) / 1_000_000)
        end_time = time.monotonic() + (duration_ms / 1000.0)
        while time.monotonic() < end_time:
            self._gpiod_set_value(True)
            time.sleep(high_s)
            self._gpiod_set_value(False)
            time.sleep(low_s)
