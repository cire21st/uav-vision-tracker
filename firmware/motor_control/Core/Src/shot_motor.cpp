#include "shot_motor.h"
#include "config.h"
#include <Arduino.h>

static bool active = false;
static unsigned long started_at = 0;

void shot_motor_init(void) {
    digitalWrite(SHOT_MOTOR_PIN, LOW);
    pinMode(SHOT_MOTOR_PIN, OUTPUT);
    active = false;
}

bool shot_motor_trigger(void) {
    if (active) return false;

    digitalWrite(SHOT_MOTOR_PIN, HIGH);
    started_at = millis();
    active = true;
    return true;
}

void shot_motor_update(void) {
    if (active && millis() - started_at >= SHOT_MOTOR_DURATION_MS) {
        digitalWrite(SHOT_MOTOR_PIN, LOW);
        active = false;
    }
}
