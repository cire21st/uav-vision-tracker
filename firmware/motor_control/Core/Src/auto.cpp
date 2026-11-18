#include <Arduino.h>
#include "auto.h"
#include "motor.h"

const float HALF_WIDTH = 320.0f;
const float HALF_HEIGHT = 240.0f;

const int PAN_MAX_RPM = 100;
const int TILT_MAX_RPM = 100;
const int MOTOR_MAX_RPM = 100;

const int DEADBAND = 10;

bool auto_control(int dx, int dy, int flag) {

    // 목표물 탐지 실패
    if (flag != 1) {
        motor_stop_all();
        return true;
    }

    // Deadband
    if (abs(dx) <= DEADBAND) dx = 0;
    if (abs(dy) <= DEADBAND) dy = 0;

    // Normalization
    float x = constrain(dx / HALF_WIDTH, -1.0f, 1.0f);
    float y = constrain(dy / HALF_HEIGHT, -1.0f, 1.0f);

    // Cubic function
    int pan = roundf(PAN_MAX_RPM * x * x * x);
    int tilt = roundf(TILT_MAX_RPM * y * y * y);

    // Motor RPM
    int rpm1 = pan;
    int rpm2 = pan + tilt;

    // Motor speed limit
    int peak = max(abs(rpm1), abs(rpm2));

    if (peak > MOTOR_MAX_RPM) {
        float scale = (float)MOTOR_MAX_RPM / peak;

        rpm1 = roundf(rpm1 * scale);
        rpm2 = roundf(rpm2 * scale);
    }

    // CAN transmission
    motor_set_speed(0x01, rpm1);
    motor_set_speed(0x02, rpm2);

    return true;
}
