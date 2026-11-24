"""Camera controls, raw 5 FPS recording, and post-recording pixel annotation.

Run with the vision project's Python environment; do not run control.py alongside it.
"""

import argparse
import ctypes
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import threading
import time

from vision_input import VISION_CAMERA, VISION_DIR


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def make_sample(frame_index, width, height, x, y):
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError('Selected pixel is outside the image')
    cx, cy = width // 2, height // 2
    return dict(frame_index=frame_index, time_seconds=frame_index / 5.0,
                width=width, height=height, center_x=cx, center_y=cy,
                selected_x=x, selected_y=y, delta_x=x - cx, delta_y=y - cy)


class RecordedCamera:
    """Capture and record independently of slow inference. Video has no overlays.

    Sample the latest frame at 5 Hz. If capture temporarily stalls, repeat the
    latest frame so the AVI timeline remains at 5 FPS; record duplicates in metadata.
    """
    def __init__(self, camera, directory):
        self.camera, self.directory = camera, directory
        self.condition = threading.Condition()
        self.stop = threading.Event()
        self.latest = None
        self.sequence = 0
        self.last_delivered = -1
        self.error = None
        self.frames_written = 0
        self.duplicates = 0
        self.size = None
        self.video_path = directory / 'raw_5fps.avi'
        self.capture = threading.Thread(target=self.capture_loop, daemon=True)
        self.recorder = threading.Thread(target=self.record_loop, daemon=True)
        self.capture.start()
        self.recorder.start()

    def capture_loop(self):
        try:
            while not self.stop.is_set():
                frame = self.camera.read()
                with self.condition:
                    self.latest = frame.copy()
                    self.sequence += 1
                    self.condition.notify_all()
        except Exception as exc:
            self.error = str(exc)
            self.stop.set()
        finally:
            self.camera.close()
            with self.condition:
                self.condition.notify_all()

    def record_loop(self):
        import cv2
        writer = None
        previous_sequence = -1
        try:
            with self.condition:
                self.condition.wait_for(lambda: self.latest is not None or self.stop.is_set())
            deadline = time.monotonic()
            while not self.stop.is_set():
                if self.stop.wait(max(0, deadline - time.monotonic())):
                    break
                with self.condition:
                    frame = self.latest.copy()
                    sequence = self.sequence
                height, width = frame.shape[:2]
                if writer is None:
                    self.size = (width, height)
                    writer = cv2.VideoWriter(str(self.video_path),
                                             cv2.VideoWriter_fourcc(*'MJPG'), 5.0, self.size)
                    if not writer.isOpened():
                        raise RuntimeError(f'Cannot record to {self.video_path}')
                if (width, height) != self.size:
                    raise RuntimeError('Camera resolution changed during recording')
                writer.write(frame)
                self.frames_written += 1
                self.duplicates += sequence == previous_sequence
                previous_sequence = sequence
                deadline += 0.2
        except Exception as exc:
            self.error = str(exc)
            self.stop.set()
        finally:
            if writer is not None:
                writer.release()
            with self.condition:
                self.condition.notify_all()

    def read(self):
        with self.condition:
            self.condition.wait_for(lambda: (self.latest is not None and
                                             self.sequence != self.last_delivered) or self.stop.is_set())
            if self.error:
                raise RuntimeError(self.error)
            if self.stop.is_set():
                raise RuntimeError('Capture stopped')
            self.last_delivered = self.sequence
            return self.latest.copy()

    def close(self):
        self.stop.set()
        with self.condition:
            self.condition.notify_all()
        self.recorder.join(timeout=5)
        self.capture.join(timeout=2)
        if self.recorder.is_alive():
            raise RuntimeError('Recording is still closing; cannot open review yet')


def review_recording(video_path, samples_path):
    """Browse recorded frames, click one source pixel, Enter to append, Esc to finish."""
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(video_path))
    window = 'Frame selection - pixel samples'
    samples = []
    save_json(samples_path, samples)
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not cap.isOpened() or total < 1:
            raise RuntimeError('No recorded frames available for selection')
        cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)
        cv2.createTrackbar('Frame', window, 0, max(1, total - 1), lambda _: None)
        state = dict(point=None, frame=None, display_size=None)

        def click(event, x, y, flags, userdata):
            if event != cv2.EVENT_LBUTTONDOWN or state['frame'] is None:
                return
            dw, dh = state['display_size']
            height, width = state['frame'].shape[:2]
            if 0 <= x < dw and 150 <= y < 150 + dh:
                state['point'] = (min(width - 1, int(x * width / dw)),
                                  min(height - 1, int((y - 150) * height / dh)))

        cv2.setMouseCallback(window, click)
        current = -1
        message = 'Click, refine 1px with I/J/K/L, ENTER to save. ESC finishes.'
        while True:
            index = min(total - 1, cv2.getTrackbarPos('Frame', window))
            if index != current:
                cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, raw = cap.read()
                if not ok:
                    raise RuntimeError(f'Cannot decode frame {index}')
                state['frame'], state['point'] = raw, None
                current = index
            raw = state['frame']
            height, width = raw.shape[:2]
            scale = min(1.0, 1100 / width, 600 / height)
            dw, dh = max(1, round(width * scale)), max(1, round(height * scale))
            state['display_size'] = (dw, dh)
            canvas = np.zeros((dh + 150, max(dw, 760), 3), dtype=np.uint8)
            canvas[150:, :dw] = cv2.resize(raw, (dw, dh))
            center = (round((width // 2) * dw / width), 150 + round((height // 2) * dh / height))
            cv2.drawMarker(canvas, center, (0, 0, 255), cv2.MARKER_CROSS, 25, 1)
            text = 'No pixel selected'
            if state['point'] is not None:
                x, y = state['point']
                sample = make_sample(index, width, height, x, y)
                selected = (min(dw - 1, int(x * dw / width)), 150 + min(dh - 1, int(y * dh / height)))
                cv2.drawMarker(canvas, selected, (0, 255, 0), cv2.MARKER_CROSS, 19, 1)
                cv2.line(canvas, center, selected, (0, 255, 255), 1)
                # 15 x 15 source pixels, magnified without interpolation.
                padded = cv2.copyMakeBorder(raw, 7, 7, 7, 7, cv2.BORDER_REPLICATE)
                zoom = cv2.resize(padded[y:y + 15, x:x + 15], (120, 120),
                                  interpolation=cv2.INTER_NEAREST)
                cv2.rectangle(zoom, (56, 56), (63, 63), (0, 255, 0), 1)
                canvas[5:125, -125:-5] = zoom
                text = f'Pixel ({x}, {y}) | dx={sample["delta_x"]:+d}, dy={sample["delta_y"]:+d}'
            lines = [f'Frame {index}/{total - 1} | {index / 5:.1f}s | Samples: {len(samples)}',
                     'Arrows / A,D: frame | slider: seek | ENTER: save | ESC: finish',
                     text, message, 'Red: center | Green: selected | +dx: right, +dy: down']
            for i, line in enumerate(lines):
                cv2.putText(canvas, line, (8, 22 + i * 27), cv2.FONT_HERSHEY_SIMPLEX,
                            0.47, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow(window, canvas)
            key = cv2.waitKeyEx(20)
            if key == 27 or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key in (0x250000, ord('a'), 0x270000, ord('d')):
                step = -1 if key in (0x250000, ord('a')) else 1
                cv2.setTrackbarPos('Frame', window, max(0, min(total - 1, index + step)))
            elif key in (ord('i'), ord('j'), ord('k'), ord('l')) and state['point'] is not None:
                x, y = state['point']
                dx, dy = {ord('i'): (0, -1), ord('j'): (-1, 0),
                          ord('k'): (0, 1), ord('l'): (1, 0)}[key]
                state['point'] = (max(0, min(width - 1, x + dx)),
                                  max(0, min(height - 1, y + dy)))
            elif key in (10, 13) and state['point'] is not None:
                sample = make_sample(index, width, height, *state['point'])
                samples.append(sample)
                try:
                    save_json(samples_path, samples)
                except Exception:
                    samples.pop()
                    raise
                message = f'Saved sample #{len(samples)}. Select another pixel or frame.'
                state['point'] = None
        print(f'Saved {len(samples)} samples: {samples_path}', flush=True)
    finally:
        cap.release()
        cv2.destroyAllWindows()


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
    parser.add_argument('--output-dir', type=Path,
                        default=Path(__file__).resolve().parent / 'recordings')
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
    recorded = None
    review_requested = False
    ser = None
    joystick = None
    window = 'Pan & Tilt - Camera Control'
    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    session_time = datetime.now(timezone(timedelta(hours=9)))
    directory = args.output_dir / session_time.strftime('%Y%m%d_%H%M%S_%f')
    directory.mkdir(parents=True, exist_ok=False)
    samples_path = directory / 'samples.json'
    save_json(samples_path, [])
    print(f'Recording directory: {directory}', flush=True)
    try:
        def load_detector():
            from uav_tracker.detector import Detector
            return Detector(str(args.vision_dir / 'models/best.pt'), 'track',
                            'bytetrack.yaml', 0.5, 640, 'cpu', None)

        camera = Camera(args.camera, 'dshow', 1280, 720, 30)
        recorded = RecordedCamera(camera, directory)
        worker = VisionWorker(recorded, load_detector, draw, pick_target, to_control_values)
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
                     'F1/1: PC  F2/2: MANUAL  F3/3: AUTO  Q: stop & select frames  ESC: exit',
                     'PC: WASD (hold)    SPACE: Shot (PC / AUTO)    Xbox LB: Shot (MANUAL)',
                     f'Xbox: {"Connected" if joystick else "Disconnected"} | Vision: {("WAITING" if stale else "OK") if mode == "AUTO" else "PREVIEW"}',
                     f'REC 5 FPS: {recorded.frames_written} frames | Status: {error or status}']
            for i, line in enumerate(lines):
                cv2.putText(frame, line, (15, 28 + i * 32), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (0, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow(window, frame)
            key = cv2.waitKeyEx(1)
            if key in (ord('q'), ord('Q')):
                review_requested = True
                break
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
            if recorded.error:
                raise RuntimeError(recorded.error)
            time.sleep(max(0, 0.01 - (time.monotonic() - started)))
    finally:
        try:
            if ser is not None:
                close_serial(ser)
        finally:
            if worker is not None:
                worker.stop.set()
            if recorded is not None:
                recorded.close()
                save_json(directory / 'session.json', dict(
                    started_at=session_time.isoformat(), camera=args.camera,
                    video=recorded.video_path.name, fps=5,
                    frames=recorded.frames_written, repeated_frames=recorded.duplicates,
                    resolution=recorded.size, recording_error=recorded.error,
                    coordinates='pixels: origin top-left, +x right, +y down; center width//2,height//2',
                    delta_convention='delta_x=selected_x-center_x; delta_y=selected_y-center_y'))
            if worker is not None:
                worker.thread.join(timeout=2)
            cv2.destroyAllWindows()
            if pygame is not None:
                pygame.quit()
    if review_requested and recorded is not None:
        review_recording(recorded.video_path, samples_path)


if __name__ == '__main__':
    main()
