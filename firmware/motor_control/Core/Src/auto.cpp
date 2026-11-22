#include <Arduino.h>
#include "config.h"
#include "auto.h"
#include "motor.h"

bool auto_control(int dx, int dy, int flag) {

    // 목표물 탐지 실패
    if (flag != 1) {
        motor_stop_all();
        return true;
    }

    // Deadband
    if (abs(dx) <= AUTO_DEADBAND) dx = 0;
    if (abs(dy) <= AUTO_DEADBAND) dy = 0;

    // Normalization
    float x = constrain(dx / AUTO_HALF_WIDTH, -1.0f, 1.0f);
    float y = constrain(dy / AUTO_HALF_HEIGHT, -1.0f, 1.0f);

    // Cubic function
    int pan = roundf(AUTO_PAN_MAX_RPM * x * x * x);
    int tilt = roundf(AUTO_TILT_MAX_RPM * y * y * y);

    // Motor RPM
    int rpm1 = pan;
    int rpm2 = pan + tilt;

    // Motor speed limit
    int peak = max(abs(rpm1), abs(rpm2));

    if (peak > AUTO_MOTOR_MAX_RPM) {
        float scale = (float)AUTO_MOTOR_MAX_RPM / peak;

        rpm1 = roundf(rpm1 * scale);
        rpm2 = roundf(rpm2 * scale);
    }

    // CAN transmission
    motor_set_speed(MOTOR1_CAN_ID, rpm1);
    motor_set_speed(MOTOR2_CAN_ID, rpm2);

    return true;
}
