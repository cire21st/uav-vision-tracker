#include <Arduino.h>
#include <stdio.h>
#include <string.h>
#include "config.h"
#include "motor.h"
#include "can_comm.h"
#include "manual.h"
#include "pc.h"
#include "shot_motor.h"
#include "auto.h"

enum ControlMode {
    IDLE,
    PC,
    MANUAL,
    AUTO
};

ControlMode mode = IDLE;

bool armed = false;
bool stop_pending = true;

unsigned long last_rx = 0;
unsigned long last_stop_try = 0;

int prev_x = 0;
int prev_y = 0;

// Stop Request
void request_stop() {
    armed = false;
    stop_pending = true;
    last_stop_try = millis() - STOP_RETRY_INTERVAL_MS;
}

// Stop Control
void service_stop() {
    if (stop_pending && millis() - last_stop_try >= STOP_RETRY_INTERVAL_MS) {
        last_stop_try = millis();
        stop_pending = !motor_stop_all();
    }
}

// Control Mode Change
void set_mode(ControlMode new_mode) {
    if (mode == new_mode) return;

    request_stop();
    mode = new_mode;

    switch (mode) {
        case PC:
            Serial.println("Mode: PC");
            break;

        case MANUAL:
            Serial.println("Mode: MANUAL");
            break;

        case AUTO:
            Serial.println("Mode: AUTO");
            break;

        case IDLE:
            Serial.println("Mode: IDLE");
            break;
    }
}

// Control Command
void handle_command(ControlMode new_mode, int x, int y, int flag = 1) {
    last_rx = millis();

    set_mode(new_mode);

    if (stop_pending) return;
    if (mode == IDLE) return;

    // AUTO는 전달받은 오차값으로 바로 추적
    if (mode == AUTO) {
        if (!auto_control(int16_t(x), int16_t(y), flag)) {
            request_stop();
        }
        return;
    }

    // Neutral Position Check
    if (!armed) {
        bool neutral = (mode == PC && x == 'x') ||
                       (mode == MANUAL && x == 0 && y == 0);

        if (neutral) {
            armed = true;
            prev_x = x;
            prev_y = y;
        }

        return;
    }

    // Skip Identical Commands
    if (x == prev_x && y == prev_y) return;

    bool success = false;

    switch (mode) {
        case PC:
            success = pc_control((char)x);
            break;

        case MANUAL:
            success = manual_control(x, y);
            break;

        default:
            return;
    }

    if (success) {
        prev_x = x;
        prev_y = y;
    } else {
        request_stop();
    }
}

// Forward pixel errors supplied by the vision integration.
void handle_vision_error(int16_t dx, int16_t dy, int flag) {
    handle_command(AUTO, dx, dy, flag);
}

// Serial Data Parsing
void process_command(char* data) {
    if (strncmp(data, "P,", 2) == 0 &&
        strlen(data) == 3) {

        char key = data[2];

        if (strchr("wasdx", key)) {
            handle_command(PC, key, 0);
        }
    }

    else if (strncmp(data, "M,", 2) == 0) {
        long x, y;
        char extra;

        if (sscanf(data + 2, "%ld,%ld%c",
                   &x, &y, &extra) == 2) {

            if (x < -JOYSTICK_MAX || x > JOYSTICK_MAX ||
                y < -JOYSTICK_MAX || y > JOYSTICK_MAX) {
                return;
            }

            if (abs(x) <= JOYSTICK_DEADZONE) x = 0;
            if (abs(y) <= JOYSTICK_DEADZONE) y = 0;

            handle_command(MANUAL, x, y);
        }
    }

    else if (strcmp(data, "I") == 0) {
        handle_command(IDLE, 0, 0);
    }

    else if (strcmp(data, "X") == 0) {
        if ((mode == PC || mode == MANUAL) && armed && !stop_pending) {
            shot_motor_trigger();
        }
    }
}

// Serial Reception
void serial_receive() {
    static char buffer[COMMAND_BUFFER_SIZE];
    static uint8_t index = 0;
    static bool overflow = false;

    while (Serial.available() > 0) {
        char c = Serial.read();

        if (c == '\n') {
            buffer[index] = '\0';

            if (!overflow) {
                process_command(buffer);
            }

            index = 0;
            overflow = false;
        }

        else if (c != '\r' && !overflow) {
            if (index < sizeof(buffer) - 1) {
                buffer[index++] = c;
            } else {
                overflow = true;
            }
        }
    }
}

void setup() {
    shot_motor_init();

    Serial.begin(SERIAL_BAUD_RATE);

    if (!can_init()) {
        Serial.println("CAN Init Failed");

        while (1) {
            delay(1000);
        }
    }

    Serial.println("CAN Init Success");

    delay(STARTUP_DELAY_MS);

    request_stop();
}

void loop() {
    // Communication Timeout
    if (mode != IDLE && millis() - last_rx >= CONTROL_TIMEOUT_MS) {
        set_mode(IDLE);
    }
    
    shot_motor_update();

    service_stop();

    serial_receive();

    service_stop();
}
