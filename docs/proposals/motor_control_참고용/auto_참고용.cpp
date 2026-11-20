/*
 * ============================================================================
 *  auto_참고용.cpp  —  firmware/motor_control/Core/Src/auto.cpp 참고용 수정본
 * ============================================================================
 *
 *  ※ 이 파일은 "참고용"입니다. 빌드에 들어가지 않고, 원본 파일도 고치지 않았습니다.
 *    원본(auto.cpp)과 나란히 놓고 비교한 뒤, 필요한 부분만 직접 옮겨 주세요.
 *
 *  ■ 원본과 다른 곳: 딱 1군데 (★ [변경 1])
 *    HALF_WIDTH / HALF_HEIGHT 숫자 2개 (320/240 → 640/360)
 *    그 외 모든 줄(데드밴드, 3제곱 곡선, 속도 제한, rpm2 = pan + tilt)은 원본과 똑같습니다.
 *
 *  ■ 비전이 보내 주는 값 (A,dx,dy,flag)
 *    dx   : 드론이 화면 가운데에서 가로로 몇 픽셀 떨어졌나. 오른쪽 +, 왼쪽 −
 *    dy   : 드론이 화면 가운데에서 세로로 몇 픽셀 떨어졌나. 위쪽 +, 아래쪽 −   (xy 평면과 같음)
 *    flag : 1 = 드론 보임, 0 = 안 보임 (0일 때 dx, dy는 0)
 *    비전 화면 크기는 1280×720 이라서 dx는 약 −640 ~ +640, dy는 약 −360 ~ +360 입니다.
 *
 *  ■ 확인한 것
 *    이 파일과 main_참고용.cpp 를 원본 대신 넣고 PlatformIO 로 빌드 → 성공 (RAM 21%, Flash 30%).
 *    실제 모터를 돌려 보는 시험은 아직 안 했습니다.
 * ============================================================================
 */

#include <Arduino.h>
#include "auto.h"
#include "motor.h"

// ----------------------------------------------------------------------------
// ★ [변경 1] 화면 절반 크기
//
//   원래:   const float HALF_WIDTH = 320.0f;
//           const float HALF_HEIGHT = 240.0f;
//
//   바꾼 것: 640 / 360
//
//   의미:  아래 Normalization 에서 dx / HALF_WIDTH 를 해서 −1 ~ +1 로 만듭니다.
//          "화면 끝 = 1.0" 이 되려면 HALF_WIDTH 가 "화면 가로 크기의 절반"이어야 합니다.
//          320/240 은 640×480 화면 기준인데, 비전은 1280×720 으로 돌아갑니다.
//
//          숫자를 그대로 두면:
//            드론이 중앙과 오른쪽 끝의 중간(dx = 320)에만 있어도
//            320 / 320 = 1.0  →  벌써 최고 속도.  (화면 절반 바깥은 전부 최고 속도)
//          640 으로 바꾸면:
//            dx = 320  →  0.5  →  0.5³ × 100 = 약 12 RPM
//            dx = 640  →  1.0  →  최고 속도 (화면 끝)
//          → 3제곱 곡선(가까우면 살살, 멀면 빠르게)이 원래 의도대로 동작합니다.
//
//   주의:  비전 해상도를 바꾸면(--width, --height) 이 숫자도 같이 바꿔야 합니다.
// ----------------------------------------------------------------------------
const float HALF_WIDTH = 640.0f;   // 원래 320
const float HALF_HEIGHT = 360.0f;  // 원래 240

const int PAN_MAX_RPM = 100;
const int TILT_MAX_RPM = 100;
const int MOTOR_MAX_RPM = 100;

// 원본 그대로. 10 픽셀 안쪽 오차는 무시 (1280×720 에서 화면 폭의 약 0.8%)
const int DEADBAND = 10;

bool auto_control(int dx, int dy, int flag) {

    // 목표물 탐지 실패
    // (원본 그대로) 비전이 "A,0,0,0" 을 보내면 여기서 정지
    if (flag != 1) {
        motor_stop_all();
        return true;
    }

    // Deadband
    if (abs(dx) <= DEADBAND) dx = 0;
    if (abs(dy) <= DEADBAND) dy = 0;

    // Normalization
    // ★ [변경 1]의 숫자가 쓰이는 곳. 화면 끝에서 x, y = ±1.0
    float x = constrain(dx / HALF_WIDTH, -1.0f, 1.0f);
    float y = constrain(dy / HALF_HEIGHT, -1.0f, 1.0f);

    // Cubic function
    // (원본 그대로) 부호가 유지되므로 dx가 + 면 pan 도 +, dy가 + (드론이 위쪽) 면 tilt 도 +
    // → 조이스틱 모드(manual.cpp)와 같은 공식이라, 스틱을 위로 밀 때와 같은 방향으로 돕니다.
    int pan = roundf(PAN_MAX_RPM * x * x * x);
    int tilt = roundf(TILT_MAX_RPM * y * y * y);

    // Motor RPM
    int rpm1 = pan;
    int rpm2 = pan + tilt;

    // Motor speed limit
    int peak = max(abs(rpm1), abs(rpm2));

    if (peak > MOTOR_MAX_RPM) {
        float scale = (float)MOTOR_MAX_RPM / peak;

        rpm1 = roundf(rpm1 * scale);
        rpm2 = roundf(rpm2 * scale);
    }

    // CAN transmission
    motor_set_speed(0x01, rpm1);
    motor_set_speed(0x02, rpm2);

    // (참고, 바꾸지 않음) CAN 전송이 실패해도 항상 true 를 돌려줍니다.
    // manual_control() 처럼 "return m1 && m2;" 로 바꾸면,
    // 전송 실패 시 main.cpp 가 request_stop() 으로 정지시킬 수 있습니다.
    return true;
}
