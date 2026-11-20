/*
 * ============================================================================
 *  main_참고용.cpp  —  firmware/motor_control/Core/Src/main.cpp 참고용 수정본
 * ============================================================================
 *
 *  ※ 이 파일은 "참고용"입니다. 빌드에 들어가지 않고, 원본 파일도 고치지 않았습니다.
 *    원본(main.cpp)과 나란히 놓고 비교한 뒤, 필요한 부분만 직접 옮겨 주세요.
 *
 *  ■ 원본과 다른 곳: 3군데, 모두 "추가"만 했습니다 (원본 줄은 하나도 안 지움)
 *    ★ [변경 1]  #include "auto.h"  +  AUTO_LIMIT 상수
 *    ★ [변경 2]  handle_auto() 함수 추가
 *    ★ [변경 3]  process_command() 에 "A,dx,dy,flag" 읽는 갈래 추가
 *
 *  ■ 왜 필요한가
 *    지금 원본은 정확히 "A" 한 글자만 알아들어서(strcmp(data, "A") == 0),
 *    비전이 보내는 "A,310,20,1" 은 아무 데도 안 걸리고 버려집니다.
 *    그리고 auto.cpp 의 auto_control() 은 만들어져 있지만 아무 데서도 부르지 않습니다.
 *    → 이 두 가지를 이어 주는 것이 변경의 전부입니다.
 *
 *  ■ 비전이 보내는 메시지 (USB 시리얼 115200, 한 줄씩, 카메라 프레임마다 약 15~30번/초)
 *      A,dx,dy,flag\n        예) A,310,20,1   = 드론이 오른쪽 310px, 위 20px 에 보임
 *                                A,0,0,0      = 드론 안 보임
 *    조이스틱 메시지 "M,x,y" 와 같은 모양(글자 + 쉼표)이라서,
 *    원본의 serial_receive() 를 그대로 쓰고 process_command() 에 갈래 하나만 더하면 됩니다.
 *    (정수 값을 글자로 보냅니다. 2바이트 바이너리가 아니니 sscanf 로 읽으면 됩니다.)
 *
 *  ■ 확인한 것
 *    이 파일과 auto_참고용.cpp 를 원본 대신 넣고 PlatformIO 로 빌드 → 성공.
 *    시리얼 모니터(115200)에 "A,320,0,1" 을 직접 입력해서 시험할 수 있습니다.
 *    실제 모터를 돌려 보는 시험은 아직 안 했습니다.
 * ============================================================================
 */

#include <Arduino.h>
#include <stdio.h>
#include <string.h>
#include "config.h"
#include "motor.h"
#include "can_comm.h"
#include "manual.h"
#include "pc.h"

// ----------------------------------------------------------------------------
// ★ [변경 1] auto.h 포함 + 값 범위 상수
//
//   원래:   auto.h 를 include 하지 않음 → main.cpp 에서 auto_control() 을 부를 수 없음
//
//   바꾼 것: #include "auto.h" 추가
//           AUTO_LIMIT = 2000 추가
//
//   의미:  AUTO_LIMIT 는 "이보다 큰 값은 잘못 들어온 값"으로 보고 버리는 기준입니다.
//          1280×720 에서 정상 범위는 dx ±640, dy ±360 이라 2000 이면 넉넉합니다.
//          (조이스틱의 JOYSTICK_MAX 범위 검사와 같은 역할)
// ----------------------------------------------------------------------------
#include "auto.h"

const int AUTO_LIMIT = 2000;

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
    last_stop_try = millis() - 50UL;
}

// Stop Control
void service_stop() {
    if (stop_pending && millis() - last_stop_try >= 50) {
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
// (원본 그대로) PC / MANUAL 용. AUTO 는 아래 handle_auto() 가 따로 처리합니다.
void handle_command(ControlMode new_mode, int x, int y) {
    last_rx = millis();

    set_mode(new_mode);

    if (stop_pending) return;
    if (mode == IDLE || mode == AUTO) return;

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

// ----------------------------------------------------------------------------
// ★ [변경 2] handle_auto() 추가
//
//   원래:   없음. handle_command() 는 AUTO 모드일 때 바로 return 해서
//           (if (mode == IDLE || mode == AUTO) return;) 아무것도 안 함
//
//   바꾼 것: AUTO 전용 처리 함수를 새로 만듦 (handle_command() 는 안 건드림)
//
//   의미:  한 줄씩 보면
//          1) last_rx = millis();
//             → 메시지를 받은 시각 기록. loop() 의 기존 0.3초 타임아웃이 이걸 봅니다.
//               비전이 꺼져서 메시지가 끊기면 0.3초 뒤 IDLE 로 바뀌고 모터가 멈춥니다.
//          2) set_mode(AUTO);
//             → 처음 A 메시지가 오면 AUTO 모드로 전환 (기존 함수 그대로 사용).
//               전환할 때 request_stop() 이 불려서 모터를 먼저 한 번 세웁니다.
//          3) if (stop_pending) return;
//             → 그 정지 명령이 끝날 때까지는 움직이지 않음 (PC/MANUAL 과 같은 규칙)
//          4) auto_control(dx, dy, flag)
//             → auto.cpp 의 속도 계산 + CAN 전송. 실패하면 정지.
//
//          PC/MANUAL 에 있는 "중립 위치 확인(armed)" 과 "같은 값이면 건너뛰기" 는
//          AUTO 에는 넣지 않았습니다. 비전 값은 사람이 잡는 스틱이 아니라서
//          매 프레임 새 값이 오는 게 정상이기 때문입니다.
// ----------------------------------------------------------------------------
void handle_auto(int dx, int dy, int flag) {
    last_rx = millis();

    set_mode(AUTO);

    // 모드 전환 직후에는 정지 명령이 먼저 끝나야 함
    if (stop_pending) return;

    if (!auto_control(dx, dy, flag)) {
        request_stop();
    }
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

    // ------------------------------------------------------------------------
    // ★ [변경 3] "A,dx,dy,flag" 읽기
    //
    //   원래:   else if (strcmp(data, "A") == 0) 만 있음
    //           → 정확히 "A" 한 글자일 때만 걸림. "A,310,20,1" 은 무시됨.
    //
    //   바꾼 것: 바로 위 "M,x,y" 처리와 똑같은 방식으로 "A," 갈래를 추가
    //           (원래 있던 "A" 한 글자 처리는 그대로 아래에 남겨 둠)
    //
    //   의미:  1) strncmp(data, "A,", 2)   → "A," 로 시작하는 줄인지 확인
    //          2) sscanf(..., "%d,%d,%d%c") → 숫자 3개를 꺼냄
    //             == 3 일 때만 통과. 숫자가 모자라거나("A,1,2") 뒤에 쓰레기가 붙으면
    //             (extra 에 글자가 들어가서 4가 됨) 버림. M,x,y 처리와 같은 기법.
    //          3) 범위 검사 → AUTO_LIMIT 를 넘거나 flag 가 0/1 이 아니면 버림
    //          4) handle_auto() 로 넘김 (★ [변경 2])
    //
    //   시험:  시리얼 모니터(115200, 줄바꿈 LF)에 직접 입력
    //          A,320,0,1   → 오른쪽으로 천천히 (320/640 = 0.5, 0.5³×100 ≈ 12 RPM)
    //          A,640,0,1   → 오른쪽으로 최고 속도
    //          A,100,0,1   → 안 움직임 (100/640 = 0.16, 0.16³×100 = 0.4 → 반올림 0 RPM)
    //          A,0,360,1   → 위로 최고 속도
    //          A,0,0,0     → 정지
    //          (아무것도 안 보내면 0.3초 뒤 IDLE 로 바뀌므로, 계속 움직이게 하려면 반복 입력 필요)
    // ------------------------------------------------------------------------
    else if (strncmp(data, "A,", 2) == 0) {
        int dx, dy, flag;
        char extra;

        if (sscanf(data + 2, "%d,%d,%d%c",
                   &dx, &dy, &flag, &extra) == 3) {

            if (dx < -AUTO_LIMIT || dx > AUTO_LIMIT ||
                dy < -AUTO_LIMIT || dy > AUTO_LIMIT ||
                (flag != 0 && flag != 1)) {
                return;
            }

            handle_auto(dx, dy, flag);
        }
    }

    // (원본 그대로) "A" 한 글자: 모드만 AUTO 로 바꿈
    else if (strcmp(data, "A") == 0) {
        handle_command(AUTO, 0, 0);
    }

    else if (strcmp(data, "I") == 0) {
        handle_command(IDLE, 0, 0);
    }
}

// Serial Reception
// (원본 그대로) 줄바꿈('\n')까지 모아서 process_command() 로 넘김.
// 비전 메시지도 조이스틱과 같은 "글자 한 줄"이라 이 함수는 손댈 필요가 없습니다.
void serial_receive() {
    static char buffer[32];
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
    Serial.begin(115200);

    if (!can_init()) {
        Serial.println("CAN Init Failed");

        while (1) {
            delay(1000);
        }
    }

    Serial.println("CAN Init Success");

    delay(2000);

    request_stop();
}

void loop() {
    // Communication Timeout
    // (원본 그대로) AUTO 에서도 그대로 동작: 비전이 0.3초 넘게 조용하면 IDLE + 정지
    if (mode != IDLE && millis() - last_rx >= 300) {
        set_mode(IDLE);
    }

    service_stop();

    serial_receive();

    service_stop();
}
