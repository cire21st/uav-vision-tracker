#pragma once

// CAN controller pin, oscillator frequency, and bus bitrate.
#define CAN_CS_PIN  10
#define CAN_OSC     MCP_16MHZ
#define CAN_BITRATE CAN_500KBPS

// CAN identifiers for the two motors.
#define MOTOR1_CAN_ID 0x01
#define MOTOR2_CAN_ID 0x02

// Serial baud rate and command buffer size in bytes.
#define SERIAL_BAUD_RATE    115200UL
#define COMMAND_BUFFER_SIZE 32

// Communication timeout, stop retry interval, and startup delay in milliseconds.
#define CONTROL_TIMEOUT_MS     300UL
#define STOP_RETRY_INTERVAL_MS 50UL
#define STARTUP_DELAY_MS       2000UL

// Motor speed limit, test speed in RPM, and acceleration parameter.
#define MAX_RPM  1500
#define TEST_RPM 60
#define ACC      100

// Pan and tilt speeds for PC keyboard control in RPM.
#define PAN_RPM  100
#define TILT_RPM 100

// Joystick input limit and neutral deadzone.
#define JOYSTICK_MAX      1200
#define JOYSTICK_DEADZONE 60

// Maximum pan and tilt contributions from manual input in RPM.
#define MANUAL_PAN_RPM  120
#define MANUAL_TILT_RPM 120

// Image half-dimensions and target deadband for automatic tracking in pixels.
#define AUTO_DEADBAND    10

// Pan, tilt, and motor speed limits for automatic tracking in RPM.
#define AUTO_PAN_MAX_RPM   100
#define AUTO_TILT_MAX_RPM  100
#define AUTO_MOTOR_MAX_RPM 100

// Shot motor output pin and HIGH pulse duration in milliseconds.
#define SHOT_MOTOR_PIN         7
#define SHOT_MOTOR_DURATION_MS 1330UL

#define VISION_FRAME_WIDTH   1280
#define VISION_FRAME_HEIGHT  720

#define AUTO_HALF_WIDTH   (VISION_FRAME_WIDTH / 2.0f)
#define AUTO_HALF_HEIGHT  (VISION_FRAME_HEIGHT / 2.0f)

#define AUTO_PAN_MAX_RPM    100
#define AUTO_TILT_MAX_RPM   100
#define AUTO_MOTOR_MAX_RPM  100

// 양수: 한 방향 / 음수: 반대 방향
#define AUTO_SEARCH_RPM 20

#define disable_option 1