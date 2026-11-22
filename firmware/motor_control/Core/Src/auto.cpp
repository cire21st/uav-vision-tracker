#include <Arduino.h>
#include <math.h>

#include "config.h"
#include "motor.h"
#include "auto.h"

// Normalization
static float normalize(int16_t error, float half_size) {
    float value = float(error);

    if (fabsf(value) <= AUTO_DEADBAND) {
        return 0.0f;
    }

    return constrain(value / half_size, -1.0f, 1.0f);
}

// Auto Control
bool auto_control(int16_t dx, int16_t dy, int flag) {
    // 미탐지: PAN만 한 방향으로 계속 회전
    if (flag == 0) {
        return motor_pan(AUTO_SEARCH_RPM);
    }

    if (flag != 1) {
        return motor_stop_all();
    }

    // 탐지: 아래부터 기존 추적 코드 그대로 유지
    float ux = normalize(dx, AUTO_HALF_WIDTH);
    float uy = normalize(dy, AUTO_HALF_HEIGHT);

    // Linear Mapping
    float pan = -AUTO_PAN_MAX_RPM * ux;
    float tilt = AUTO_TILT_MAX_RPM * uy;

    // Motor Speed
    float rpm1 = pan;
    float rpm2 = pan + tilt;

    // Speed Limitation
    float peak = max(fabsf(rpm1), fabsf(rpm2));

    if (peak > AUTO_MOTOR_MAX_RPM) {
        float scale = AUTO_MOTOR_MAX_RPM / peak;

        rpm1 *= scale;
        rpm2 *= scale;
    }

    bool m1 = motor_set_speed(MOTOR1_CAN_ID, roundf(rpm1));
    bool m2 = motor_set_speed(MOTOR2_CAN_ID, roundf(rpm2));

    return m1 && m2;
}
