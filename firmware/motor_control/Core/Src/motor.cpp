#include "config.h"
#include "motor.h"
#include "can_comm.h"

bool motor_set_speed(uint16_t can_id, int rpm) {
    // 속도 제한
    if (rpm > MAX_RPM) rpm = MAX_RPM;
    if (rpm < -MAX_RPM) rpm = -MAX_RPM;

    uint16_t speed = rpm < 0 ? -rpm : rpm;

    // MKS 속도 제어 명령 (0xF6)
    uint8_t data[5] = {
        0xF6,
        (uint8_t)((rpm < 0 ? 0x80 : 0x00) | (speed >> 8)),
        (uint8_t)(speed & 0xFF),
        ACC,
        0
    };

    // 체크섬 계산
    uint16_t sum = can_id;

    for (int i = 0; i < 4; i++) {
        sum += data[i];
    }

    data[4] = sum & 0xFF;

    return can_send(can_id, data, 5);
}

bool motor_stop(uint16_t can_id) {
    return motor_set_speed(can_id, 0);
}

// Pan
bool motor_pan(int rpm) {
    bool m1 = motor_set_speed(0x01, rpm);
    bool m2 = motor_set_speed(0x02, rpm);

    return m1 && m2;
}

// Tilt
bool motor_tilt(int rpm) {
    bool m1 = motor_stop(0x01);
    bool m2 = motor_set_speed(0x02, rpm);

    return m1 && m2;
}

// Stop
bool motor_stop_all() {
    bool m1 = motor_stop(0x01);
    bool m2 = motor_stop(0x02);

    return m1 && m2;
}
