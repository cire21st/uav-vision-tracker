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
