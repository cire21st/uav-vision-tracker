# Motor control firmware

Arduino Uno용 PlatformIO 프로젝트입니다. `Core/Src`와 `Core/Inc`를 사용하며,
`Arduino.h`는 `framework = arduino` 설정에 따라 PlatformIO가 제공합니다.

저장소 루트에서 빌드:

```powershell
pio run -d firmware/motor_control
```

VS Code에서는 PlatformIO IDE 확장을 설치하고 `firmware/motor_control` 폴더를
프로젝트로 열면 헤더 경로를 인식할 수 있습니다.

저장소 루트를 연 상태에서 C/C++ IntelliSense를 사용하려면 다음 명령으로
컴파일 데이터베이스를 생성합니다. 빌드 설정이나 라이브러리가 바뀌면 다시 실행합니다.

```powershell
pio run -d firmware/motor_control -t compiledb
```

루트의 `.vscode/settings.json`에 아래 설정을 추가합니다. 기존 설정이 있으면 병합합니다.

```json
{
    "C_Cpp.default.compileCommands": "${workspaceFolder}/firmware/motor_control/compile_commands.json"
}
```

경고가 남으면 명령 팔레트에서 `C/C++: Reset IntelliSense Database`를 실행합니다.
`.vscode` 설정과 `compile_commands.json`은 로컬 환경용이므로 Git에서 제외합니다.

## pygame에서 F3로 Vision 실행

일반 `uno` 펌웨어가 업로드된 상태에서 저장소 루트에서 실행합니다.

```powershell
python firmware/motor_control/Python/control.py
```

F1은 키보드, F2는 컨트롤러, F3는 Vision 추적·탐색입니다. F3를 누르면
`Python/vision_input.py`가 `C:/comet/uav-tracker-test/.venv/Scripts/python.exe`로
비전의 `main.py`를 실행하고 매 프레임 JSON 출력을 읽습니다. 비전은 `--serial`
없이 실행하며 Arduino COM 포트는 `control.py`만 사용합니다.
카메라는 기본 2번(`--camera 2`)입니다. `vision_input.py`의 `VISION_CAMERA`를
변경하거나 `control.py`에서 `VisionInput(camera=번호)`로 지정할 수 있습니다.

비전 창으로 포커스가 이동해도 AUTO는 계속 동작합니다. F1/F2 전환은 pygame
창을 클릭한 뒤 누릅니다. 이때 비전은 백그라운드에서 계속 실행됩니다.
미탐지는 PAN 탐색, 실행 준비 중이거나 1초 동안 새 결과가 없으면 대기입니다.
비전 창에서 Q로 닫으면 대기하며 F3로 다시 실행할 수 있습니다.
pygame 창의 Esc 또는 닫기 버튼으로 종료하면 비전 프로세스도 종료합니다.

비전 경로가 다르면 `vision_input.py`의 `VISION_DIR`를 변경합니다. 비전의 실제
영상 크기는 펌웨어의 `VISION_FRAME_WIDTH/HEIGHT`와 맞춰야 합니다(현재 1280×720).
비전 프로그램과 시리얼 모니터를 별도로 중복 실행하지 않습니다.

## Vision 없이 오차값으로 모터 테스트

`Core/Src/vision_tracking_test.cpp`는 비전 대신 입력한 오차값으로 기존
`auto_control(dx, dy, 1)`을 호출하는 별도 펌웨어입니다. 일반 `uno` 빌드에는
포함되지 않습니다. 저장소 루트에서 테스트 펌웨어를 업로드합니다.

```powershell
pio run -d firmware/motor_control -e vision_tracking_test -t upload
pio device monitor -d firmware/motor_control -e vision_tracking_test --filter send_on_enter
```

장치가 여러 개면 업로드에 `--upload-port COM번호`, 모니터에 `--port COM번호`를
추가합니다. `control.py` 등 같은 COM 포트를 사용하는 프로그램은 종료합니다.
모니터에서 `(320,0)`, `(-320,0)`, `(0,180)`, `(0,-180)` 등을 입력하고 Enter를 누릅니다.
괄호 없는 `320,0`도 가능합니다. `(10,20)`은 현재 데드밴드 10 때문에 가로 명령이 0입니다.

입력한 속도는 다음 명령까지 유지됩니다. 정지는 `stop` 또는 `(0,0)`입니다.
이 테스트는 방향·속도 계산과 실제 모터 구동을 확인하며, 영상 기반 추적 성능을
검증하지는 않습니다. 테스트가 끝나면 일반 펌웨어를 다시 업로드합니다.

```powershell
pio run -d firmware/motor_control -e uno -t upload
```
