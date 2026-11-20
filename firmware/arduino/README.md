## 아두이노 펌웨어 안내

실제로 쓰는 펌웨어는 [`../motor_control`](../motor_control)입니다 (PlatformIO 프로젝트, Arduino Uno + MCP2515 CAN + MKS SERVO42D 2개).

펌웨어는 USB 시리얼(115200 baud)로 아래 메시지를 한 줄씩 받습니다.

| 보내는 프로그램 | 메시지 | 뜻 |
|---|---|---|
| `control.py` (키보드) | `P,a` / `P,d` / `P,w` / `P,s` / `P,x` | 좌 / 우 / 위 / 아래 / 정지 |
| `control.py` (조이스틱) | `M,x,y` | 스틱 기울기 (−1200 ~ +1200) |
| 비전 (`uav-tracker-test`, `main.py --serial auto`) | `A,dx,dy,flag` | 화면 중앙 기준 픽셀 오차, 정수. 오른쪽 +, 위쪽 +. flag 1 = 탐지 |
| 공통 | `I` | 대기 (정지) |

- COM 포트는 프로그램 하나만 열 수 있어서, `control.py`와 비전은 **동시에 실행할 수 없습니다.**
- 지금 펌웨어는 `A,dx,dy,flag`를 아직 읽지 못합니다. 필요한 변경은 [참고용 코드](../../docs/proposals/motor_control_참고용/)로 정리했습니다 (원본은 수정하지 않음).

형식과 그렇게 정한 이유는 [`docs/serial-integration-report.md`](../../docs/serial-integration-report.md)를 참고하세요.
