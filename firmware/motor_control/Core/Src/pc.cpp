#include <Arduino.h>
#include "config.h"
#include "motor.h"
#include "pc.h"

bool pc_control(char key) {
    switch (key) {
        case 'a':
            return motor_pan(-PAN_RPM);

        case 'd':
            return motor_pan(PAN_RPM);

        case 'w':
            return motor_tilt(TILT_RPM);

        case 's':
            return motor_tilt(-TILT_RPM);

        case 'x':
            return motor_stop_all();

        default:
            return false;
    }
}
