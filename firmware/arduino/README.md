# Arduino Firmware

This area will receive and parse PC messages, compute or apply the agreed control output, and command the pan and tilt motors.

Document the board, required libraries, pin mapping, flashing steps, motor limits, and stop behavior when hardware is chosen. Keep the PC message format aligned with [the integration interface](../../docs/interface.md).

안녕하세요 저는 조완호입니다.

## pan_tilt_tracker (draft)

[`pan_tilt_tracker/pan_tilt_tracker.ino`](pan_tilt_tracker/pan_tilt_tracker.ino) receives `<valid,ax,ay>\n` at 115200 baud and drives two hobby servos (pan pin 9, tilt pin 10). `ax`, `ay` are the angle errors from the image center in 0.1° units, right/down positive. Servos hold position when the target is lost or no message arrives for 300 ms.

The sketch is a skeleton with Korean comments: the receive part is complete, and the control owner fills in three callbacks — `onTarget(ax, ay)`, `onLost()`, `onLinkTimeout()`. A two-servo example is included in `onTarget` and can be replaced with existing motor code.

1. Arduino IDE → Board: **Arduino Uno** → upload the sketch.
2. Quick test without the PC app: Serial Monitor at 115200, type `<1,200,0>` and send. Pan should move 8° (0.4 × 20°).
3. If an axis moves the wrong way, flip `PAN_DIR` / `TILT_DIR`. Tune `K` (lower if it oscillates).
4. Power the servos from an external 5–6 V supply and connect its GND to the Arduino GND.
5. Close the Serial Monitor before starting the PC app; only one program can open the port.
