#include <Arduino.h>
#include <math.h>
#include "config.h"
#include "motor.h"
#include "manual.h"

// Normalization
static float normalize(int pulse) {
    pulse = constrain(pulse, -JOYSTICK_MAX, JOYSTICK_MAX);

    if (abs(pulse) <= JOYSTICK_DEADZONE) {
        return 0.0f;
    }

    return (float)pulse / JOYSTICK_MAX;
}

// Cubic Mapping
static float cubic(float u) {
    return u * u * u;
}

// Manual Control
bool manual_control(int x, int y) {

    float ux = normalize(x);
    float uy = normalize(y);

    float pan = MANUAL_PAN_RPM * cubic(ux);
    float tilt = MANUAL_TILT_RPM * cubic(uy);

    // Motor Speed
    float rpm1 = pan;
    float rpm2 = pan + tilt;

    // Speed Limitation
    float peak = max(fabs(rpm1), fabs(rpm2));

    if (peak > MAX_RPM) {
        float scale = MAX_RPM / peak;

        rpm1 *= scale;
        rpm2 *= scale;
    }

    bool m1 = motor_set_speed(0x01, roundf(rpm1));
    bool m2 = motor_set_speed(0x02, roundf(rpm2));

    return m1 && m2;
}
