"""8BitDo left stick controls continuous pan/tilt steppers over USB serial."""
from __future__ import annotations

import argparse
import sys
import time

import pygame
import serial
from serial.tools import list_ports

# ---- Adjust to your controller and board ----
PORT = "COM4"
BAUD = 115200
PAN_AXIS = 0
TILT_AXIS = 1
X_BUTTON = 2
Y_BUTTON = 3
PAN_INVERT = False
TILT_INVERT = True
DEADZONE = 0.10
MAX_STEP_RATE = 1200  # pulse/s at full stick deflection
SEND_HZ = 30
# --------------------------------------------


def speed_from_axis(value: float, invert: bool) -> int:
    """Convert joystick position to signed step rate; center means stop."""
    value = max(-1.0, min(1.0, value))
    if abs(value) <= DEADZONE:
        return 0
    if invert:
        value = -value
    magnitude = (abs(value) - DEADZONE) / (1.0 - DEADZONE)
    return round((1 if value > 0 else -1) * magnitude * MAX_STEP_RATE)


def show_ports() -> None:
    found = list(list_ports.comports())
    if not found:
        print("No serial ports found.")
    for port in found:
        print(f"{port.device}: {port.description}")


def monitor_controller() -> int:
    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print("No game controller detected. Pair the controller and retry.")
        pygame.quit()
        return 1
    stick = pygame.joystick.Joystick(0)
    stick.init()
    print(f"Controller: {stick.get_name()} | axes: {stick.get_numaxes()} | Ctrl+C to stop")
    clock = pygame.time.Clock()
    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or event.type == pygame.JOYDEVICEREMOVED:
                    return 0
            pygame.event.pump()
            buttons = [i for i in range(stick.get_numbuttons()) if stick.get_button(i)]
            pan = speed_from_axis(stick.get_axis(PAN_AXIS), PAN_INVERT)
            tilt = speed_from_axis(stick.get_axis(TILT_AXIS), TILT_INVERT)
            print(f"pan={pan:+d} pulse/s, tilt={tilt:+d} pulse/s, buttons={buttons}   ", end="\r")
            clock.tick(SEND_HZ)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    finally:
        pygame.quit()


def run_console(stick, link) -> int:
    mode_active = False
    clock = pygame.time.Clock()
    print("Standby mode. Press Y to start; press Y again to stop. Ctrl+C exits.")
    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or event.type == pygame.JOYDEVICEREMOVED:
                    return 0
                if event.type == pygame.JOYBUTTONDOWN and event.button == Y_BUTTON:
                    mode_active = not mode_active
                    print("Control mode" if mode_active else "Standby mode")
                    if not mode_active:
                        link.write(b"V,0,0\n")
                elif event.type == pygame.JOYBUTTONDOWN and event.button == X_BUTTON and mode_active:
                    link.write(b"X\n")
                    print("Motor 3 one-turn command sent")
            pygame.event.pump()
            if mode_active:
                pan = speed_from_axis(stick.get_axis(PAN_AXIS), PAN_INVERT)
                tilt = speed_from_axis(stick.get_axis(TILT_AXIS), TILT_INVERT)
                link.write(f"V,{pan},{tilt}\n".encode("ascii"))
            clock.tick(SEND_HZ)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    finally:
        if mode_active and link.is_open:
            link.write(b"V,0,0\n")


def run_window(stick, link) -> int:
    import tkinter as tk
    from tkinter.scrolledtext import ScrolledText

    root = tk.Tk()
    root.title("컨트롤러 / Arduino 실시간 확인")
    root.geometry("650x500")
    root.minsize(560, 430)

    def label(text: str, size: int = 13):
        return tk.Label(root, text=text, font=("맑은 고딕", size), anchor="w")

    label("왼쪽 스틱: 기울인 동안 회전 · 중립: 현재 위치에서 정지", 15).pack(fill="x", padx=16, pady=(14, 6))
    mode_label = label("대기 모드 — Y를 눌러 시작", 14)
    mode_label.config(fg="#a35a00")
    mode_label.pack(fill="x", padx=20, pady=3)
    pan_label = label("팬: 정지", 14)
    tilt_label = label("틸트: 정지", 14)
    pan_label.pack(fill="x", padx=20, pady=2)
    tilt_label.pack(fill="x", padx=20, pady=2)
    x_label = label("Motor 3 (SG90 360): X를 눌러 한 바퀴 회전", 11)
    x_label.pack(fill="x", padx=20, pady=(6, 2))
    buttons_label = label(f"누른 버튼: 없음  |  X={X_BUTTON}, Y={Y_BUTTON}", 10)
    buttons_label.pack(fill="x", padx=20, pady=2)
    ack_label = label("Arduino 수신 확인: 아직 없음", 10)
    ack_label.pack(fill="x", padx=20, pady=2)
    label("로그", 10).pack(fill="x", padx=16, pady=(8, 2))
    log = ScrolledText(root, height=12, state="disabled", font=("Consolas", 10))
    log.pack(fill="both", expand=True, padx=16, pady=(0, 8))
    label("대기 중에는 Arduino로 구동 명령을 보내지 않습니다. 창을 닫으면 정지 명령을 보냅니다.", 9).pack(fill="x", padx=16, pady=(0, 10))

    mode_active = False
    active = True
    receive_buffer = bytearray()
    ack_count = 0

    def add_log(message: str) -> None:
        log.configure(state="normal")
        log.insert("end", time.strftime("%H:%M:%S ") + message + "\n")
        log.see("end")
        log.configure(state="disabled")

    add_log(f"{stick.get_name()} 연결 / Arduino {PORT} 연결")
    add_log(f"대기 모드. Y 버튼(인덱스 {Y_BUTTON})을 눌러 동작 모드로 전환하세요.")

    def close_window() -> None:
        nonlocal active
        if mode_active and link.is_open:
            link.write(b"V,0,0\n")
        active = False
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close_window)

    def tick() -> None:
        nonlocal mode_active, receive_buffer, ack_count
        if not active:
            return
        for event in pygame.event.get():
            if event.type == pygame.QUIT or event.type == pygame.JOYDEVICEREMOVED:
                close_window()
                return
            if event.type == pygame.JOYBUTTONDOWN and event.button == Y_BUTTON:
                mode_active = not mode_active
                if mode_active:
                    mode_label.config(text="동작 모드 — 스틱을 기울이면 계속 회전", fg="#167d32")
                    add_log("Y 입력: 동작 모드 시작")
                else:
                    link.write(b"V,0,0\n")
                    mode_label.config(text="대기 모드 — 명령 전송 안 함", fg="#a35a00")
                    pan_label.config(text="팬: 정지 (중립 위치 유지)")
                    tilt_label.config(text="틸트: 정지 (중립 위치 유지)")
                    add_log("Y 입력: 대기 모드 전환, 두 축 정지 명령 전송")
            elif event.type == pygame.JOYBUTTONDOWN and event.button == X_BUTTON:
                if mode_active:
                    link.write(b"X\n")
                    x_label.config(text="Motor 3: X 명령 전송 — Arduino 응답 대기")
                    add_log("X 입력: SG90 360 한 바퀴 명령 전송")
                else:
                    add_log("대기 모드에서 X 입력: 보내지 않음")

        pygame.event.pump()
        pan_raw = stick.get_axis(PAN_AXIS)
        tilt_raw = stick.get_axis(TILT_AXIS)
        pan_rate = speed_from_axis(pan_raw, PAN_INVERT)
        tilt_rate = speed_from_axis(tilt_raw, TILT_INVERT)
        pressed = [i for i in range(stick.get_numbuttons()) if stick.get_button(i)]
        buttons_label.config(text=f"누른 버튼: {pressed or '없음'}  |  X={X_BUTTON}, Y={Y_BUTTON}")
        if mode_active:
            pan_label.config(text=f"팬: {pan_rate:+d} 펄스/초  (축 {PAN_AXIS}: {pan_raw:+.3f})")
            tilt_label.config(text=f"틸트: {tilt_rate:+d} 펄스/초  (축 {TILT_AXIS}: {tilt_raw:+.3f})")
            link.write(f"V,{pan_rate},{tilt_rate}\n".encode("ascii"))
        else:
            pan_label.config(text=f"팬 입력: {pan_rate:+d} 펄스/초 (대기 중, 미전송)")
            tilt_label.config(text=f"틸트 입력: {tilt_rate:+d} 펄스/초 (대기 중, 미전송)")

        waiting = link.in_waiting
        if waiting:
            receive_buffer.extend(link.read(waiting))
            while b"\n" in receive_buffer:
                raw_line, _, rest = receive_buffer.partition(b"\n")
                receive_buffer = bytearray(rest)
                response = raw_line.decode("ascii", errors="replace").strip()
                if response.startswith("ACK,V,"):
                    ack_count += 1
                    ack_label.config(text=f"Arduino 수신 확인: {response}  ({ack_count}회)")
                elif response.startswith("ACK,X,"):
                    x_label.config(text=f"Motor 3: {response}")
                    add_log(f"Arduino 응답: {response}")
        root.after(33, tick)

    try:
        root.after(0, tick)
        root.mainloop()
        return 0
    finally:
        if link.is_open:
            link.close()
        pygame.quit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ports", action="store_true", help="list serial ports and exit")
    parser.add_argument("--monitor", action="store_true", help="show joystick values without Arduino output")
    parser.add_argument("--console", action="store_true", help="use terminal mode instead of the window")
    args = parser.parse_args()
    if args.ports:
        show_ports()
        return 0

    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print("No game controller detected. Pair the 8BitDo and retry.")
        pygame.quit()
        return 1
    stick = pygame.joystick.Joystick(0)
    stick.init()
    if stick.get_numaxes() <= max(PAN_AXIS, TILT_AXIS):
        print("Configured joystick axes are not available; check PAN_AXIS/TILT_AXIS.")
        pygame.quit()
        return 1

    if args.monitor:
        pygame.quit()
        return monitor_controller()
    try:
        link = serial.Serial(PORT, BAUD, timeout=0.1, write_timeout=0.2)
        time.sleep(2)  # Uno R3 resets when its serial port is opened
        link.reset_input_buffer()
    except serial.SerialException as exc:
        print(f"Could not open {PORT}: {exc}\nRun python controller.py --ports and update PORT.")
        pygame.quit()
        return 1

    try:
        if args.console:
            return run_console(stick, link)
        return run_window(stick, link)
    finally:
        if link.is_open:
            link.close()
        pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
