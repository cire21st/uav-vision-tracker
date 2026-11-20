#pragma once

// CAN 설정
#define CAN_CS_PIN 10
#define MOTOR1_CAN_ID 0x01
#define MOTOR2_CAN_ID 0x02
#define CAN_OSC MCP_16MHZ

// 모터 설정
#define MAX_RPM 1500
#define TEST_RPM 60
#define ACC 100

//PC
#define PAN_RPM  100
#define TILT_RPM 100

// Xbox Controller
#define JOYSTICK_MAX       1200
#define JOYSTICK_DEADZONE  60

// Manual Control
#define MANUAL_PAN_RPM     120
#define MANUAL_TILT_RPM    120
#define MANUAL_TIMEOUT     300

// shot motor 설정
#define SHOT_MOTOR_PIN 7
#define SHOT_MOTOR_DURATION_MS 1380UL