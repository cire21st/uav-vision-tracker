## 아두이노 펌웨어 안내

실제로 쓰는 펌웨어는 [`../motor_control`](../motor_control)입니다 (PlatformIO 프로젝트, Arduino Uno + MCP2515 CAN + MKS SERVO42D 2개).

PC 프로그램 [`../motor_control/Core/Python/control.py`](../motor_control/Core/Python/control.py)가 COM 포트를 열고, F1~F3으로 모드를 바꿔 가며 한 줄씩 보냅니다.

| 모드 | 메시지 | 뜻 |
|---|---|---|
| F1 키보드 | `P,a` / `P,d` / `P,w` / `P,s` / `P,x` | 좌 / 우 / 위 / 아래 / 정지 |
| F2 조이스틱 | `M,x,y` | 스틱 기울기 (−1200 ~ +1200) |
| F3 자동 추적 (제안) | `A,dx,dy,flag` | 비전이 계산한 각도 오차 × 10 (오른쪽 +, 위쪽 +), flag 1 = 탐지 |
| 대기 | `I` | 정지 |

자동 추적(F3)은 아직 연결되어 있지 않습니다. 비전 프로그램(`uav-tracker-test`, `main.py --udp`)은 UDP로 값을 보낼 준비가 되어 있고, `control.py`·`main.cpp`·`auto.cpp`에 필요한 변경은 [제안 패치](../../docs/proposals/motor_control_auto_mode.patch)로 정리했습니다. 형식과 그렇게 정한 이유는 [`docs/serial-integration-report.md`](../../docs/serial-integration-report.md)를 참고하세요.

예전에 이 폴더에 있던 `pan_tilt_tracker` 뼈대 스케치는 형식을 `motor_control`로 통일하면서 삭제했습니다. 필요하면 git 기록에서 볼 수 있습니다.
