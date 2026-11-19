# 8BitDo → Arduino Uno R3 Pan/Tilt Stepper Controller

Python reads the left stick and sends speed/direction commands over USB serial. Motor 1 is Tilt, Motor 2 is Pan. Holding the stick off center makes the corresponding stepper keep turning; returning it to center stops it at its current position. There is no angle limit or automatic return-to-center. Y switches between standby and control mode. X runs the SG90 360 continuous-rotation servo on D9 for one calibrated timed turn.

## Connections

### Pan/Tilt stepper drivers

| Driver input | Arduino Uno R3 pin |
| --- | --- |
| Motor 1 EN (Tilt) | D2 |
| Motor 1 STEP (Tilt) | D3 |
| Motor 1 DIR (Tilt) | D4 |
| Motor 2 EN (Pan) | D5 |
| Motor 2 STEP (Pan) | D6 |
| Motor 2 DIR (Pan) | D7 |
| Driver logic GND | Arduino GND |

EN is active LOW. Connect each stepper's coils to its driver outputs, never directly to Arduino pins. Set each driver's microstep switches/jumpers as required by the driver.

### SG90 360 continuous-rotation servo (Motor 3)

| Servo lead | Connection |
| --- | --- |
| Signal (usually orange/yellow) | Arduino D9 |
| Ground (usually brown/black) | External supply negative and Arduino GND |
| Power (usually red) | External regulated supply within the servo's rated voltage |

Use a suitable external supply for the motors and servo; do not power them from the Arduino 5 V pin or laptop USB. Join external supply ground to Arduino GND. Disconnect power while wiring.

## Install and run

1. Upload `arduino/pan_tilt_servo/pan_tilt_servo.ino` using Arduino IDE with board **Arduino Uno** and port **COM4**. Close Arduino Serial Monitor.
2. In this folder's VS Code terminal, install packages if needed:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Start the live window:

   ```powershell
   python controller.py
   ```

The program starts in standby and sends no motion commands. Press Y to enable the controller. Press Y again or close the window to send stop commands. The window shows step rates and Arduino acknowledgements (`ACK,V,...`). In control mode, X starts one timed SG90 turn; the window reports `ACK,X,STARTED` and `ACK,X,DONE`. `python controller.py --monitor` shows joystick input without opening the Arduino port or sending commands. `python controller.py --ports` lists serial ports.

## Controls and tuning

- Left stick horizontal controls Pan; vertical controls Tilt. The motors turn while deflected and stop when centered. `DEADZONE`, `MAX_STEP_RATE`, `PAN_INVERT`, and `TILT_INVERT` are near the top of `controller.py`.
- Arduino STEP pulse HIGH width is `STEP_HIGH_US = 100` microseconds; the minimum LOW interval is also 100 microseconds. The pulse rate follows stick deflection up to 1200 steps/s. Reduce `MAX_STEP_RATE` if the motors skip or stall.
- The DIR level for positive stick speed is LOW, matching the provided test sketch. If a motor turns the wrong way, invert that axis in Python.
- SG90 360 servos control speed/direction, not absolute position. `M3_FORWARD_US`, `M3_STOP_US`, and `M3_TURN_MS` in the sketch are adjustable. The default 550 ms is an initial estimate based on TowerPro's published 110 RPM at 4.8 V; actual speed varies by servo, voltage and load. Calibrate the time for one turn with the real servo. Adjust `M3_STOP_US` if it creeps while stopped.
- A continuous-rotation servo has no position feedback, so a timed turn cannot guarantee exactly 360° without calibration. Pressing X again starts another timed turn once the prior one finishes.

## Serial protocol

Python sends `V,<pan pulses/s>,<tilt pulses/s>\n` at 30 Hz only in control mode. Zero speed stops that axis without returning it to a home angle. Y mode changes are handled locally; timeout or standby sets both speeds to zero. X sends `X\n` to start Motor 3's timed turn. Baud rate is 115200.

## Safety

There are no mechanical angle limits or homing sensors. The stepper axes can turn indefinitely while the stick is held, so keep wires and linkages clear and provide a way to cut driver power. A serial timeout stops the motors; it cannot undo movement or establish an absolute position. Use the external supply voltage and current ratings specified for the drivers, steppers and servo.
