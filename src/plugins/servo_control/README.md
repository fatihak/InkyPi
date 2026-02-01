# Servo Control Plugin

This Plugin provides controll of a Servo motor connected to your Raspberry Pi via a configurable GPIO pin.
You can set the Target Angle and optional the orientation saved in device_config.

** This Plugin will not update the Screen **

## Settings Page Configuration

### Controllable Settings

- **GPIO Pin**: The GPIO pin number where the Servo signal wire is connected.
- **TargetAngle**: A Slider to manually set the Servo angle between 0° and 180°.
- **ServoSpeed**: A Slider to adjust the speed of the Servo movement (delay between angle steps in milliseconds).
- **Orientation**: An optional setting to define the orientation of the Servo. (landscape | portrait | current). This will update and persist the device_config orientation setting when changed.

## Usage

Include the Servo Control Plugin in your Playlists.
** Tipp: **
You can do a POST Request to the InkyPi to set the TargetAngle configured in a Playlist with the following command.
This way you can store predifined Positions in different Playlists and switch between them via API.

```
curl -X POST "http://<INKYPI_IP_ADDRESS>/api/plugin/servo_control" -H "Content-Type: application/json" -d '{"playlist_name": "YOUR_PLAYLIST_NAME", "plugin_instance": "YOUR_PLUGIN_INSTANCE_NAME", "plugin_id": "servo_control"}'
```

## Servo Control
This Plugin currently is optimised for a SG90 Micro Servo.
The Servo is controlled via PWM signals on the specified GPIO pin.
The angle is set by adjusting the duty cycle of the PWM signal.
When moving to a new angle, the Plugin will incrementally adjust the angle in small steps to ensure smooth movement.
The speed of the movement can be adjusted via the ServoSpeed setting.
The current Angle is always stored in the device_config under "current_servo_angle" and used after bootup as the current starting Angle.

