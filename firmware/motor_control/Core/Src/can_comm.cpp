
#include <Arduino.h>
#include <SPI.h>
#include <mcp_can.h>

#include "config.h"
#include "can_comm.h"

MCP_CAN CAN(CAN_CS_PIN);

bool can_init() {
    SPI.begin();

    byte result = CAN.begin(MCP_ANY, CAN_BITRATE, CAN_OSC);

    Serial.print("CAN init result: ");
    Serial.println(result);

    if (result != CAN_OK) {
        return false;
    }

    result = CAN.setMode(MCP_NORMAL);

    Serial.print("Normal mode result: ");
    Serial.println(result);

    return result == CAN_OK;
}

bool can_send(uint16_t id, uint8_t* data, uint8_t len) {
    if (len > 8 || (len > 0 && data == nullptr)) {
        Serial.println("Invalid CAN data");
        return false;
    }

    // 라이브러리가 8바이트를 읽어도 유효한 메모리에 접근하도록 준비
    uint8_t buffer[8] = {};

    for (uint8_t i = 0; i < len; ++i) {
        buffer[i] = data[i];
    }

    byte result = CAN.sendMsgBuf(id, 0, len, buffer);

    Serial.print("CAN TX result: ");
    Serial.println(result);

    // Read-only bus diagnostics, limited to once per second on failures.
    static unsigned long last_diagnostic = 0;
    const unsigned long now = millis();
    if (result != CAN_OK && now - last_diagnostic >= 1000UL) {
        last_diagnostic = now;
        const byte errors = CAN.getError();
        const byte tx_errors = CAN.errorCountTX();
        const byte rx_errors = CAN.errorCountRX();

        Serial.print("CAN diagnostic: id=0x");
        Serial.print(id, HEX);
        Serial.print(" EFLG=0x");
        Serial.print(errors, HEX);
        Serial.print(" TEC=");
        Serial.print(tx_errors);
        Serial.print(" REC=");
        Serial.println(rx_errors);
    }

    return result == CAN_OK;
}
