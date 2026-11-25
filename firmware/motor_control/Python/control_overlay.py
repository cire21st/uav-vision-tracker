"""Single OpenCV window for camera preview and motor controls (Windows).

Run with the vision project's Python environment; do not run control.py alongside it.
"""

import argparse
import ctypes
from pathlib import Path
import sys
import threading
import time

from vision_input import VISION_CAMERA, VISION_DIR


def close_serial(ser, send_stop=True):
    """Best-effort shutdown: a disconnected port must not mask another error."""
    import serial
    try:
        if send_stop and ser.is_open:
            ser.write(b'I\n')
    except (serial.SerialException, OSError) as exc:
        print(f'Stop command could not be delivered: {exc}', flush=True)
    finally:
        try:
            ser.close()
        except (serial.SerialException, OSError) as exc:
            print(f'Serial close failed: {exc}', flush=True)


class VisionWorker:
    def __init__(self, camera, detector_factory, draw, pick_target, to_control_values):
        self.camera, self.detector_factory = camera, detector_factory
        self.detector = None
        self.auto_enabled = threading.Event()
        self.draw, self.pick_target = draw, pick_target
        self.to_control_values = to_control_values
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.frame = None
        self.values = (0, 0, 0)
        self.updated = 0.0
        self.error = None
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        locked_id = None
        try:
            while not self.stop.is_set():
                started = time.monotonic()
                frame = self.camera.read()
                # Preview does not depend on model loading or a completed inference.
                with self.lock:
                    self.frame = frame.copy()
                if not self.auto_enabled.is_set():
                    with self.lock:
                        self.values, self.updated = (0, 0, 0), 0.0
                    continue
                if self.detector is None:
                    self.detector = self.detector_factory()
                detections = self.detector.process(frame)
                target = self.pick_target(detections, locked_id)
                values = (0, 0, 0)
                if target is not None:
                    locked_id = target.track_id
                    height, width = frame.shape[:2]
                    point = target.coordinates(width, height)
                    dx, dy = self.to_control_values(point['error_x'], point['error_y'])
                    if -32768 <= dx <= 32767 and -32768 <= dy <= 32767:
                        values = (dx, dy, 1)
                frame = self.draw(frame, detections,
                                  1 / max(time.monotonic() - started, 1e-9), 'track')
                with self.lock:
                    self.frame, self.values = frame, values
                    self.updated = time.monotonic()
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
        finally:
            self.camera.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM7')
    parser.add_argument('--camera', type=int, default=VISION_CAMERA)
    parser.add_argument('--vision-dir', type=Path, default=VISION_DIR)
    args = parser.parse_args()
    sys.path.insert(0, str(args.vision_dir))

    import cv2
    import numpy as np
    import serial
    from uav_tracker.camera import Camera
    from uav_tracker.display import draw
    from uav_tracker.geometry import pick_target, to_control_values

    # pygame is optional and is used only for Xbox input, without a second window.
    try:
        import pygame
        pygame.display.init()
        pygame.joystick.init()
    except ImportError:
        pygame = None

    worker = None
    ser = None
    joystick = None
    window = 'Pan & Tilt - Camera Control'
    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    try:
        def load_detector():
            from uav_tracker.detector import Detector
            return Detector(str(args.vision_dir / 'models/best.pt'), 'track',
                            'bytetrack.yaml', 0.5, 640, 'cpu', None)

        camera = Camera(args.camera, 'dshow', 1280, 720, 30)
        worker = VisionWorker(camera, load_detector, draw, pick_target, to_control_values)
        worker.thread.start()
        serial_failed = False
        status = 'Ready'
        try:
            ser = serial.Serial(args.port, 115200, timeout=0, write_timeout=0.2)
            time.sleep(3)
        except (serial.SerialException, OSError) as exc:
            serial_failed = True
            status = f'SERIAL ERROR ({args.port}) - preview only; check USB and restart'
            print(f'{status}: {exc}', flush=True)
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        mode, command = 'PC', 'I'
        next_send = 0.0
        while True:
            started = time.monotonic()
            with worker.lock:
                frame = None if worker.frame is None else worker.frame.copy()
                values, updated, error = worker.values, worker.updated, worker.error
            if frame is None:
                frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            height, width = frame.shape[:2]
            cv2.drawMarker(frame, (width // 2, height // 2), (0, 0, 255),
                           cv2.MARKER_CROSS, 30, 2, cv2.LINE_AA)
            stale = started - updated > 1.0
            panel = frame.copy()
            cv2.rectangle(panel, (0, 0), (frame.shape[1], 175), (20, 20, 20), -1)
            cv2.addWeighted(panel, 0.85, frame, 0.15, 0, frame)
            lines = [f'Mode: {mode} | Command: {command} | Camera: {args.camera}',
                     'F1 / 1: PC    F2 / 2: MANUAL    F3 / 3: AUTO    ESC: Exit',
                     'PC: WASD (hold)    SPACE: Shot (PC / AUTO)    Xbox LB: Shot (MANUAL)',
                     f'Xbox: {"Connected" if joystick else "Disconnected"} | Vision: {("WAITING" if stale else "OK") if mode == "AUTO" else "PREVIEW"}',
                     f'Status: {error or status}']
            for i, line in enumerate(lines):
                cv2.putText(frame, line, (15, 28 + i * 32), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (0, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow(window, frame)
            key = cv2.waitKeyEx(1)
            if key == 27 or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                break
            hwnd = user32.FindWindowW(None, window)
            focused = bool(hwnd) and user32.GetForegroundWindow() == hwnd
            shot = False
            if focused:
                if key in (0x700000, ord('1')):
                    mode = 'PC'
                elif key in (0x710000, ord('2')):
                    mode = 'MANUAL'
                elif key in (0x720000, ord('3')):
                    mode = 'AUTO'
                shot = key == 32 and mode in ('PC', 'AUTO')
            if mode == 'AUTO':
                worker.auto_enabled.set()
            else:
                worker.auto_enabled.clear()
                with worker.lock:
                    worker.updated = 0.0
            if pygame is not None:
                for event in pygame.event.get():
                    if event.type == pygame.JOYDEVICEADDED and joystick is None:
                        joystick = pygame.joystick.Joystick(event.device_index)
                        joystick.init()
                    elif event.type == pygame.JOYDEVICEREMOVED:
                        if joystick and event.instance_id == joystick.get_instance_id():
                            joystick = None
                    elif event.type == pygame.JOYBUTTONDOWN:
                        shot |= focused and mode == 'MANUAL' and event.button == 4
            command = 'I'
            if mode == 'AUTO' and not stale and error is None:
                command = 'A,{},{},{}'.format(*values)
            elif focused and mode == 'PC':
                direction = next((c for c in 'adws'
                                  if user32.GetAsyncKeyState(ord(c.upper())) & 0x8000), 'x')
                command = f'P,{direction}'
            elif focused and mode == 'MANUAL' and joystick is not None:
                command = f'M,{round(joystick.get_axis(0) * 1200)},{round(joystick.get_axis(1) * 1200)}'
            if not serial_failed:
                try:
                    if started >= next_send or shot:
                        ser.write(f'{command}\n'.encode())
                        if shot:
                            ser.write(b'X\n')
                            status = 'Shot command sent'
                            print(status, flush=True)
                        next_send = started + 0.05
                    if ser.in_waiting:
                        print(ser.read(ser.in_waiting).decode('utf-8', errors='replace'),
                              end='', flush=True)
                except (serial.SerialException, OSError) as exc:
                    serial_failed = True
                    status = 'SERIAL ERROR - controls disabled; check USB/COM and restart'
                    print(f'{status}: {exc}', flush=True)
                    # Never retry a possibly partially transmitted shot command.
                    close_serial(ser, send_stop=False)
            if error:
                raise RuntimeError(error)
            time.sleep(max(0, 0.01 - (time.monotonic() - started)))
    finally:
        try:
            if ser is not None:
                close_serial(ser)
        finally:
            if worker is not None:
                worker.stop.set()
                worker.thread.join(timeout=2)
            cv2.destroyAllWindows()
            if pygame is not None:
                pygame.quit()


if __name__ == '__main__':
    main()
