#include <Arduino.h>
#include <ctype.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>

#include "auto.h"
#include "can_comm.h"
#include "config.h"
#include "motor.h"

// Standalone entry point, compiled only in env:vision_tracking_test.
// Commands: (320,0), 0,-180, (0,0), stop. End each command with a newline.
// The last speed command remains active until the next command or reset.

static void skip_spaces(char*& text) {
    while (isspace(static_cast<unsigned char>(*text))) ++text;
}

static bool read_error(char*& text, int16_t& value) {
    skip_spaces(text);
    char* end;
    errno = 0;
    const long parsed = strtol(text, &end, 10);
    if (end == text || errno == ERANGE || parsed < -32768L || parsed > 32767L) {
        return false;
    }
    text = end;
    value = static_cast<int16_t>(parsed);
    return true;
}

static bool parse_errors(char* text, int16_t& dx, int16_t& dy) {
    skip_spaces(text);
    const bool wrapped = *text == '(';
    if (wrapped) ++text;

    if (!read_error(text, dx)) return false;
    skip_spaces(text);
    if (*text != ',') return false;
    ++text;
    if (!read_error(text, dy)) return false;

    skip_spaces(text);
    if (wrapped) {
        if (*text != ')') return false;
        ++text;
        skip_spaces(text);
    }
    return *text == '\0';
}

static void process_test_command(char* line) {
    char* text = line;
    skip_spaces(text);
    size_t length = strlen(text);
    while (length > 0 && isspace(static_cast<unsigned char>(text[length - 1]))) {
        text[--length] = '\0';
    }

    if (strcmp(text, "stop") == 0) {
        const bool ok = motor_stop_all();
        Serial.println(ok ? "Stopped" : "Stop CAN transmission failed");
        return;
    }

    int16_t dx, dy;
    if (!parse_errors(text, dx, dy)) {
        Serial.println("Input: (dx,dy) or stop; int16 values only");
        return;
    }

    Serial.print("Tracking dx=");
    Serial.print(dx);
    Serial.print(" dy=");
    Serial.println(dy);

    // Exercise the production normalization and linear mapping; flag=1.
    if (!auto_control(dx, dy, 1)) {
        Serial.println("Tracking CAN transmission failed; requesting stop");
        motor_stop_all();
    }
}

void setup() {
    Serial.begin(SERIAL_BAUD_RATE);
    if (!can_init()) {
        Serial.println("CAN init failed; check hardware and reset");
        while (true) delay(1000);
    }

    delay(STARTUP_DELAY_MS);
    motor_stop_all();
    Serial.println("Vision tracking test ready: (320,0), (0,180), (0,0), stop");
    Serial.println("Motion continues until another command or reset");
}

void loop() {
    static char line[32];
    static uint8_t used = 0;
    static bool overflow = false;

    while (Serial.available() > 0) {
        const char c = static_cast<char>(Serial.read());
        if (c == '\n') {
            line[used] = '\0';
            if (overflow) {
                Serial.println("Input too long; enter (dx,dy) or stop");
            } else if (used != 0) {
                process_test_command(line);
            }
            used = 0;
            overflow = false;
        } else if (c != '\r' && !overflow) {
            if (used < sizeof(line) - 1) {
                line[used++] = c;
            } else {
                overflow = true;
            }
        }
    }
}
