"""COMET dashboard: calibrated tracking, simulated shot, 5 FPS raw recording.

One new executable source; reuses the installed uav_tracker vision package.
--preview writes a UI preview without connecting hardware. --self-test runs checks.
"""

import argparse
import ctypes
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import threading
import time

VISION_CAMERA = 1
VISION_DIR = Path("C:/comet/uav-tracker-test")
OFFSET_X = 101
OFFSET_Y = 134
ALIGN_TOLERANCE = 20
DWELL_SECONDS = 3.0
MAX_OBSERVATION_GAP = 0.5


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
        self.captured_at = 0.0
        self.last_delivered_time = 0.0
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
                    self.captured_at = time.monotonic()
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
            self.last_delivered_time = self.captured_at
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


def calibrated_error(point, width, height, offset_x=OFFSET_X, offset_y=OFFSET_Y):
    """Image errors are right/down positive; invert y only at serial conversion."""
    return point['cx'] - (width / 2 + offset_x), point['cy'] - (height / 2 + offset_y)


class AlignmentGate:
    """Advance only on distinct, fresh observations of the same tracked object."""
    def __init__(self, dwell=DWELL_SECONDS, tolerance=ALIGN_TOLERANCE,
                 max_gap=MAX_OBSERVATION_GAP):
        self.dwell, self.tolerance, self.max_gap = dwell, tolerance, max_gap
        self.reset()

    def reset(self):
        self.target_id = None
        self.sequence = -1
        self.since = None
        self.last_time = None
        self.elapsed = 0.0
        self.latched = False
        self.state = 'searching'

    def interrupt(self, state='searching'):
        self.since = None
        self.elapsed = 0.0
        self.state = state

    def update(self, sequence, observed_at, target_id, error, now):
        if observed_at <= 0 or now - observed_at > self.max_gap:
            self.interrupt('stale')
            return False
        if sequence == self.sequence:
            return False
        self.sequence = sequence
        if target_id is None or error is None:
            self.interrupt('searching')
            return False
        if target_id != self.target_id:
            self.target_id, self.latched = target_id, False
            self.interrupt()
            self.last_time = None
        if self.last_time is not None and (observed_at <= self.last_time or
                                           observed_at - self.last_time > self.max_gap):
            self.interrupt()
        self.last_time = observed_at
        if abs(error[0]) > self.tolerance or abs(error[1]) > self.tolerance:
            self.latched = False
            self.interrupt('aligning')
            return False
        if self.since is None:
            self.since = observed_at
            self.latched = False
        self.elapsed = min(self.dwell, observed_at - self.since)
        self.state = 'ready' if self.elapsed >= self.dwell else 'holding'
        return self.state == 'ready'

    def mark_sent(self):
        self.latched = True
        # Start a new full dwell on the next distinct, fresh observation.
        self.since = None
        self.elapsed = 0.0
        self.state = 'sent'


class TrackingWorker:
    """The recorder owns capture. This thread consumes copies for inference only."""
    def __init__(self, source, factory, pick_target, offset):
        self.source, self.factory, self.pick_target, self.offset = source, factory, pick_target, offset
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.enabled = threading.Event()
        self.generation = 0
        self.result = None
        self.status = 'preview'
        self.error = None
        self.thread = threading.Thread(target=self.run, daemon=True)

    def set_auto(self, enabled):
        with self.lock:
            self.generation += 1
            self.result = None
            self.error = None
            self.status = 'loading' if enabled else 'preview'
            if enabled:
                self.enabled.set()
            else:
                self.enabled.clear()

    def run(self):
        detector, locked_id, previous_generation, sequence = None, None, -1, 0
        while not self.stop.is_set():
            if not self.enabled.wait(0.05):
                continue
            with self.lock:
                generation = self.generation
            if generation != previous_generation:
                locked_id, previous_generation = None, generation
            try:
                if detector is None:
                    detector = self.factory()
                if self.stop.is_set():
                    break
                frame = self.source.read()
                observed_at = self.source.last_delivered_time
                started = time.monotonic()
                detections = detector.process(frame)
                target = self.pick_target(detections, locked_id)
                height, width = frame.shape[:2]
                error, target_id = None, None
                if target is not None:
                    target_id = target.track_id
                    locked_id = target_id
                    error = calibrated_error(target.coordinates(width, height), width, height, *self.offset)
                sequence += 1
                result = dict(sequence=sequence, observed_at=observed_at, target_id=target_id,
                              error=error, detections=detections, target=target,
                              fps=1 / max(time.monotonic() - started, 1e-6))
                with self.lock:
                    if generation == self.generation and self.enabled.is_set():
                        self.result, self.status = result, 'tracking'
            except Exception as exc:
                if self.stop.is_set():
                    break
                with self.lock:
                    if generation == self.generation:
                        self.result, self.error, self.status = None, str(exc), 'error'
                        print(f'Tracking error: {exc}', flush=True)
                self.enabled.clear()


class Dashboard:
    WIDTH, HEIGHT = 1600, 900
    BG, CARD, BORDER = '#0b111d', '#121d2d', '#243249'
    WHITE, MUTED, TEAL = '#edf3fb', '#879ab4', '#43dcc5'
    GOLD, RED = '#f4c86a', '#ff7181'

    def __init__(self, offset=(OFFSET_X, OFFSET_Y), tolerance=ALIGN_TOLERANCE):
        from PIL import ImageFont
        self.offset, self.tolerance = offset, tolerance
        self.fonts = {}
        for size in (12, 13, 14, 15, 16, 18, 20, 22, 24, 28, 32, 42, 48):
            for bold in (False, True):
                choices = [Path('C:/Windows/Fonts') / ('malgunbd.ttf' if bold else 'malgun.ttf'),
                           Path('C:/Windows/Fonts/segoeui.ttf')]
                path = next((p for p in choices if p.exists()), None)
                self.fonts[size, bold] = ImageFont.truetype(str(path), size) if path else ImageFont.load_default()

    def render(self, frame, mode, result, gate, connected, frames_written,
               elapsed, joystick=False, note='', vision_status='preview', camera_ok=True,
               requests=0, now=None, recording_ok=True):
        from PIL import Image, ImageDraw
        import cv2
        import numpy as np
        now = time.monotonic() if now is None else now
        image = Image.new('RGB', (self.WIDTH, self.HEIGHT), self.BG)
        d = ImageDraw.Draw(image)

        def text(x, y, value, size=16, color=None, bold=False):
            d.text((x, y), str(value), font=self.fonts[size, bold], fill=color or self.WHITE)

        def card(box):
            d.rounded_rectangle(box, radius=16, fill=self.CARD, outline=self.BORDER, width=1)

        def pill(x, y, label, color, width=110):
            d.rounded_rectangle((x, y, x + width, y + 30), radius=15, fill='#1a293a')
            d.ellipse((x + 12, y + 12, x + 18, y + 18), fill=color)
            text(x + 26, y + 5, label, 13, color)

        text(30, 18, 'COMET', 32, bold=True)
        text(174, 33, 'VISION CONTROL', 14, self.MUTED, True)
        for i, name in enumerate(('PC', 'MANUAL', 'AUTO')):
            x = 586 + i * 116
            active = mode == name
            d.rounded_rectangle((x, 30, x + 104, 70), radius=10,
                                fill='#183f43' if active else self.CARD,
                                outline=self.TEAL if active else self.BORDER)
            text(x + 16, 40, name, 15, self.TEAL if active else self.MUTED, True)
        pill(988, 36, 'CAMERA' if camera_ok else 'CAM OFF', self.TEAL if camera_ok else self.RED)
        pill(1110, 36, 'CONTROL' if connected else 'OFFLINE', self.TEAL if connected else self.RED, 120)
        pill(1242, 36, 'REC 5 FPS' if recording_ok else 'REC STOP', self.RED, 126)
        clock = datetime.now(timezone(timedelta(hours=9))).strftime('%H:%M:%S')
        text(1434, 40, clock, 18, self.MUTED)
        d.line((28, 101, 1572, 101), fill=self.BORDER)

        card((28, 120, 1156, 812))
        text(48, 133, 'LIVE VIEW', 13, self.MUTED, True)
        text(940, 133, f'{int(elapsed // 60):02d}:{int(elapsed % 60):02d}  /  {frames_written:05d} frames', 13, self.MUTED)
        vx, vy, vw, vh = 36, 166, 1112, 625
        d.rectangle((vx, vy, vx + vw, vy + vh), fill='#070c14')
        source_w, source_h, scale, px, py = 1280, 720, 1.0, vx, vy
        if frame is not None:
            source_h, source_w = frame.shape[:2]
            scale = min(vw / source_w, vh / source_h)
            dw, dh = round(source_w * scale), round(source_h * scale)
            px, py = vx + (vw - dw) // 2, vy + (vh - dh) // 2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image.paste(Image.fromarray(rgb).resize((dw, dh), Image.Resampling.BILINEAR), (px, py))
        else:
            text(420, 447, '카메라 연결을 기다리고 있습니다', 20, self.MUTED)

        def point(x, y):
            return px + x * scale, py + y * scale

        fresh = result is not None and now - result['observed_at'] <= MAX_OBSERVATION_GAP
        if fresh and mode == 'AUTO':
            for detection in result['detections']:
                selected = detection is result['target']
                color = self.TEAL if selected else '#90a0b5'
                x1, y1 = point(*detection.xyxy[:2])
                x2, y2 = point(*detection.xyxy[2:])
                if selected:
                    for x, y, sx, sy in ((x1, y1, 1, 1), (x2, y1, -1, 1),
                                         (x1, y2, 1, -1), (x2, y2, -1, -1)):
                        d.line((x, y + sy * 18, x, y, x + sx * 18, y), fill=color, width=3)
                    tx, ty = (x1 + x2) / 2, (y1 + y2) / 2
                    d.ellipse((tx - 3, ty - 3, tx + 3, ty + 3), fill=color)
                    label = f'TRACK {detection.track_id if detection.track_id is not None else "--"} · {detection.confidence:.0%}'
                    lx, ly = max(vx + 6, x1), max(vy + 4, y1 - 29)
                    d.rounded_rectangle((lx, ly, lx + 176, ly + 25), radius=5, fill='#123c3a')
                    text(lx + 8, ly + 3, label, 13, color, True)
                else:
                    d.rectangle((x1, y1, x2, y2), outline=color, width=1)

        rx, ry = point(source_w / 2 + self.offset[0], source_h / 2 + self.offset[1])
        color = self.GOLD if gate.state in ('holding', 'ready') else self.TEAL if gate.latched else self.WHITE
        box = self.tolerance * scale
        d.rectangle((rx - box, ry - box, rx + box, ry + box), outline=color, width=1)
        for a, b in ((-14, -5), (5, 14)):
            d.line((rx + a, ry, rx + b, ry), fill=self.WHITE, width=2)
            d.line((rx, ry + a, rx, ry + b), fill=self.WHITE, width=2)
        d.ellipse((rx - 1, ry - 1, rx + 1, ry + 1), fill=self.WHITE)
        d.arc((rx - 34, ry - 34, rx + 34, ry + 34), 0, 360, fill='#526478', width=3)
        progress = max(0, min(1, gate.elapsed / gate.dwell))
        if progress:
            d.arc((rx - 34, ry - 34, rx + 34, ry + 34), -90, -90 + progress * 360, fill=color, width=3)

        card((1180, 120, 1572, 252))
        text(1202, 140, 'TARGET STATUS', 12, self.MUTED, True)
        labels = dict(searching='대상 탐색 중', aligning='정렬 중', holding='정렬 유지 중',
                      ready='조건 충족', sent='모의 동작 요청 완료', stale='영상 갱신 대기')
        label = labels.get(gate.state, '대상 탐색 중') if mode == 'AUTO' else '수동 제어 준비'
        if not connected:
            label, color = '제어 연결 끊김', self.RED
        elif vision_status == 'error':
            label, color = '인식 오류', self.RED
        elif mode == 'AUTO' and vision_status == 'loading':
            label = '추적 모델 준비 중'
        text(1202, 170, label, 24, color, True)
        target_id = result['target_id'] if fresh else None
        text(1202, 216, f'TRACK {target_id if target_id is not None else "--"}', 13, self.MUTED)
        text(1414, 216, f'{result["fps"]:.1f} FPS' if fresh else 'LIVE PREVIEW', 12, self.MUTED)

        card((1180, 266, 1572, 457))
        text(1202, 286, 'CALIBRATED ERROR', 12, self.MUTED, True)
        error = result['error'] if fresh and mode == 'AUTO' else None
        for x, axis, value in ((1202, '수평 X', error[0] if error else None),
                               (1392, '수직 Y', error[1] if error else None)):
            text(x, 322, axis, 14, self.MUTED)
            text(x, 345, f'{value:+.0f}' if value is not None else '—', 42, bold=True)
            text(x + 125, 371, 'px', 13, self.MUTED)
        d.line((1375, 325, 1375, 400), fill=self.BORDER)
        text(1202, 420, '영상 좌표 · 오른쪽 +X / 아래쪽 +Y', 13, self.MUTED)

        card((1180, 471, 1572, 678))
        text(1202, 492, 'ALIGNMENT HOLD', 12, self.MUTED, True)
        text(1202, 523, f'{gate.elapsed:.1f}', 48, color, True)
        text(1304, 555, f'/ {gate.dwell:.1f} sec', 20, self.MUTED)
        d.rounded_rectangle((1202, 596, 1550, 604), radius=4, fill='#27364b')
        if progress:
            d.rounded_rectangle((1202, 596, 1202 + max(8, 348 * progress), 604), radius=4, fill=color)
        text(1202, 624, f'동일 타깃 · ±{self.tolerance}px 연속 유지', 14, self.MUTED)

        card((1180, 692, 1572, 812))
        text(1202, 737, 'SHOT', 22, bold=True)
        text(1438, 738, f'{requests:02d}회 요청', 18, self.TEAL, True)

        key_items = [('F1', 'PC'), ('F2', 'MANUAL'), ('F3', 'AUTO'),
                     ('WASD', '이동'), ('SPACE', '모의 동작'), ('Q', '녹화 종료·분석'), ('ESC', '종료')]
        x = 28
        for key, label in key_items:
            kw = max(38, 14 + len(key) * 9)
            d.rounded_rectangle((x, 840, x + kw, 870), radius=6, fill='#1b2a3e', outline=self.BORDER)
            text(x + 8, 846, key, 12, self.WHITE, True)
            text(x + kw + 9, 845, label, 14, self.MUTED)
            x += kw + 26 + (len(label) * 13)
        if note:
            # Short, user-facing status. Detailed exceptions go to the terminal.
            d.rounded_rectangle((64, 734, 1124, 778), radius=8, fill='#17283b')
            text(80, 744, note, 16, self.GOLD)
        return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def send_packet(port, command, shot=False):
    """One write keeps the control command and optional simulated request adjacent."""
    packet = (command + '\n' + ('X\n' if shot else '')).encode()
    if port.write(packet) != len(packet):
        raise OSError('Incomplete serial write')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera', type=int, default=VISION_CAMERA)
    parser.add_argument('--port', default='COM7')
    parser.add_argument('--vision-dir', type=Path, default=VISION_DIR)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parent / 'recordings')
    parser.add_argument('--offset-x', type=float, default=OFFSET_X)
    parser.add_argument('--offset-y', type=float, default=OFFSET_Y)
    parser.add_argument('--preview', type=Path, metavar='PNG', help='Render UI without hardware')
    parser.add_argument('--self-test', action='store_true', help='Run headless checks without hardware')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.preview:
        preview(args.preview, (args.offset_x, args.offset_y))
        return
    import cv2
    import serial
    sys.path.insert(0, str(args.vision_dir))
    from uav_tracker.camera import Camera
    from uav_tracker.geometry import pick_target
    try:
        import pygame
        pygame.display.init()
        pygame.joystick.init()
    except ImportError:
        pygame = None

    def load_detector():
        from uav_tracker.detector import Detector
        return Detector(str(args.vision_dir / 'models/best.pt'), 'track',
                        'bytetrack.yaml', 0.5, 640, 'cpu', None)

    source = worker = port = None
    review_requested = False
    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    # Avoid Windows DPI virtualization changing the preview's apparent aspect ratio.
    try:
        user32.SetProcessDPIAware()
    except AttributeError:
        pass
    window = 'COMET | Vision Control'
    session_time = datetime.now(timezone(timedelta(hours=9)))
    directory = args.output_dir / session_time.strftime('%Y%m%d_%H%M%S_%f')
    directory.mkdir(parents=True, exist_ok=False)
    save_json(directory / 'samples.json', [])
    offset = (args.offset_x, args.offset_y)
    dashboard, gate = Dashboard(offset), AlignmentGate()
    print(f'Recording directory: {directory}', flush=True)
    started = time.monotonic()
    try:
        source = RecordedCamera(Camera(args.camera, 'dshow', 1280, 720, 30), directory)
        worker = TrackingWorker(source, load_detector, pick_target, offset)
        worker.thread.start()
        connected, note = False, ''
        try:
            port = serial.Serial(args.port, 115200, timeout=0, write_timeout=0.2)
            time.sleep(3)
            connected = True
        except (serial.SerialException, OSError) as exc:
            print(f'Serial unavailable: {exc}', flush=True)
            note = '제어 장치 연결을 확인한 후 프로그램을 다시 실행하세요. 영상은 계속 표시됩니다.'
        cv2.namedWindow(window, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        screen_w, screen_h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        scale = min(1, (screen_w - 80) / 1600, (screen_h - 140) / 900)
        cv2.resizeWindow(window, int(1600 * scale), int(900 * scale))
        mode, next_send, requests, joystick = 'PC', 0.0, 0, None
        result, vision_status = None, 'preview'
        while True:
            now = time.monotonic()
            with source.condition:
                frame = None if source.latest is None else source.latest.copy()
                captured_at = source.captured_at
            with worker.lock:
                result, vision_status, vision_error = worker.result, worker.status, worker.error
            camera_ok = frame is not None and now - captured_at <= MAX_OBSERVATION_GAP and not source.error
            key = cv2.waitKeyEx(1)
            if key == 27:
                break
            if key in (ord('q'), ord('Q')):
                review_requested = True
                break
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                break
            hwnd = user32.FindWindowW(None, window)
            focused = bool(hwnd) and user32.GetForegroundWindow() == hwnd
            manual_shot = False
            if focused:
                new_mode = {0x700000: 'PC', ord('1'): 'PC', 0x710000: 'MANUAL',
                            ord('2'): 'MANUAL', 0x720000: 'AUTO', ord('3'): 'AUTO'}.get(key)
                if new_mode and new_mode != mode:
                    mode = new_mode
                    gate.reset()
                    result = None
                    worker.set_auto(mode == 'AUTO')
                manual_shot = key == 32 and mode in ('PC', 'AUTO')
            if pygame is not None:
                for event in pygame.event.get():
                    if event.type == pygame.JOYDEVICEADDED and joystick is None:
                        joystick = pygame.joystick.Joystick(event.device_index)
                        joystick.init()
                    elif event.type == pygame.JOYDEVICEREMOVED:
                        if joystick and event.instance_id == joystick.get_instance_id():
                            joystick = None
                    elif event.type == pygame.JOYBUTTONDOWN:
                        manual_shot |= focused and mode == 'MANUAL' and event.button == 4
            command, auto_shot = 'I', False
            fresh = result is not None and now - result['observed_at'] <= MAX_OBSERVATION_GAP
            calibrated_resolution = frame is not None and frame.shape[:2] == (720, 1280)
            if mode == 'AUTO' and connected and camera_ok and fresh and not vision_error and calibrated_resolution:
                error = result['error']
                if error is None:
                    command = 'A,0,0,0'
                else:
                    dx, dy = round(error[0]), round(-error[1])
                    if -32768 <= dx <= 32767 and -32768 <= dy <= 32767:
                        command = f'A,{dx},{dy},1'
                auto_shot = gate.update(result['sequence'], result['observed_at'],
                                        result['target_id'], error, now)
            elif mode == 'AUTO':
                gate.interrupt('stale')
            elif focused and mode == 'PC':
                direction = next((c for c in 'adws' if user32.GetAsyncKeyState(ord(c.upper())) & 0x8000), 'x')
                command = f'P,{direction}'
            elif focused and mode == 'MANUAL' and joystick:
                command = f'M,{round(joystick.get_axis(0) * 1200)},{round(joystick.get_axis(1) * 1200)}'
            shot = (manual_shot or auto_shot) and command != 'I'
            if connected:
                try:
                    if now >= next_send or shot:
                        send_packet(port, command, shot)
                        next_send = now + 0.05
                        if shot:
                            requests += 1
                            if mode == 'AUTO':
                                gate.mark_sent()
                            print(f'Simulated shot requested ({"auto" if auto_shot else "manual"}), count={requests}', flush=True)
                    if port.in_waiting:
                        print(port.read(port.in_waiting).decode('utf-8', errors='replace'), end='', flush=True)
                except (serial.SerialException, OSError) as exc:
                    print(f'Serial error: {exc}', flush=True)
                    connected = False
                    gate.interrupt('stale')
                    note = '제어 연결이 끊겼습니다. USB 연결 확인 후 다시 실행하세요.'
                    close_serial(port, send_stop=False)
            shown_note = note
            if source.error:
                shown_note = '카메라 또는 녹화 오류입니다. 터미널 메시지를 확인하세요.'
            elif mode == 'AUTO' and frame is not None and not calibrated_resolution:
                shown_note = '보정 기준은 1280×720입니다. 카메라 해상도가 달라 AUTO 제어를 대기합니다.'
            elif vision_error:
                shown_note = '추적 모델 오류입니다. F1으로 전환한 뒤 F3으로 다시 시도하세요.'
            elif mode == 'AUTO' and fresh and result['error'] is not None and result['target_id'] is None:
                shown_note = '대상 ID 확인 중 · ID가 확인되면 3초 조건 검사를 시작합니다.'
            ui = dashboard.render(frame, mode, result, gate, connected, source.frames_written,
                                  now - started, joystick is not None, shown_note,
                                  vision_status, camera_ok, requests, now, not source.error)
            cv2.imshow(window, ui)
            time.sleep(max(0, 1 / 30 - (time.monotonic() - now)))
    finally:
        if port is not None:
            close_serial(port)
        if worker is not None:
            worker.stop.set()
            worker.enabled.set()
        try:
            if source is not None:
                source.close()
                save_json(directory / 'session.json', dict(
                    started_at=session_time.isoformat(), camera=args.camera, video=source.video_path.name,
                    fps=5, frames=source.frames_written, repeated_frames=source.duplicates,
                    resolution=source.size, recording_error=source.error,
                    calibration_offset=list(offset), calibration_resolution=[1280, 720],
                    auto_shot=dict(tolerance=ALIGN_TOLERANCE, dwell_seconds=DWELL_SECONDS,
                                   max_observation_gap=MAX_OBSERVATION_GAP),
                    delta_convention='samples: selected-center, +x right, +y down; serial dy inverted'))
        finally:
            if worker is not None:
                worker.thread.join(timeout=2)
            cv2.destroyAllWindows()
            if pygame is not None:
                pygame.quit()
    if review_requested and source is not None and source.frames_written:
        review_recording(source.video_path, directory / 'samples.json')


def preview(path, offset=(OFFSET_X, OFFSET_Y)):
    """Code-rendered sample screen; no camera, serial port or model is opened."""
    import cv2
    import numpy as np
    from types import SimpleNamespace
    height, width = 720, 1280
    y, x = np.mgrid[:height, :width]
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, 0] = 32 + (y * 0.035).astype(np.uint8)
    frame[:, :, 1] = 38 + (x * 0.02).astype(np.uint8)
    frame[:, :, 2] = 28 + (y * 0.02).astype(np.uint8)
    for gx in range(0, width, 80):
        cv2.line(frame, (gx, 0), (gx, height), (58, 66, 61), 1)
    for gy in range(0, height, 80):
        cv2.line(frame, (0, gy), (width, gy), (58, 66, 61), 1)
    cx, cy = width / 2 + offset[0] + 12, height / 2 + offset[1] - 8
    cv2.circle(frame, (round(cx), round(cy)), 28, (110, 133, 133), -1, cv2.LINE_AA)
    target = SimpleNamespace(xyxy=(cx - 56, cy - 40, cx + 56, cy + 40), track_id=7, confidence=0.94)
    gate = AlignmentGate()
    for i in range(19):
        gate.update(i, 10 + i * 0.1, 7, (12, -8), 10 + i * 0.1)
    result = dict(observed_at=11.8, target_id=7, error=(12, -8), detections=[target], target=target, fps=24.6)
    ui = Dashboard(offset).render(frame, 'AUTO', result, gate, True, 642, 128.4,
                                  True, '', 'tracking', True, 2, 11.8)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), ui):
        raise RuntimeError(f'Cannot write preview: {path}')
    print(f'Preview: {path.resolve()}')


def self_test():
    import unittest

    class Checks(unittest.TestCase):
        def feed(self, gate, count=31, start=10, target=7, error=(20, -20)):
            answers = []
            for i in range(count):
                t = start + i * 0.1
                answers.append(gate.update(round(t * 100), t, target, error, t))
            return answers

        def test_offset_and_y_sign(self):
            self.assertEqual(calibrated_error(dict(cx=741, cy=494), 1280, 720), (0, 0))
            self.assertEqual(calibrated_error(dict(cx=751, cy=484), 1280, 720), (10, -10))

        def test_repeated_dwell_without_exiting(self):
            gate = AlignmentGate()
            answers = self.feed(gate)
            self.assertFalse(any(answers[:-1]))
            self.assertTrue(answers[-1])
            gate.mark_sent()
            self.assertEqual(gate.elapsed, 0)
            self.assertFalse(gate.update(1300, 13, 7, (0, 0), 13.01))
            answers = self.feed(gate, 31, 13.1)
            self.assertFalse(any(answers[:-1]))
            self.assertTrue(answers[-1])
            gate.mark_sent()
            self.assertFalse(any(self.feed(gate, 10, 16.2)))
            gate.update(1800, 18, 7, (21, 0), 18)
            self.assertTrue(self.feed(gate, 31, 18.1)[-1])

        def test_missing_stale_unknown_and_mode_reset(self):
            gate = AlignmentGate()
            self.feed(gate, 20)
            gate.update(1200, 12, None, None, 12)
            self.assertFalse(self.feed(gate, 10, 12.1)[-1])
            self.assertFalse(gate.update(1400, 14, 7, (0, 0), 15))
            self.assertEqual(gate.elapsed, 0)
            gate.reset()
            self.assertFalse(any(self.feed(gate, 40, target=None)))

        def test_same_frame_cannot_complete_dwell(self):
            gate = AlignmentGate()
            gate.update(1, 10, 7, (0, 0), 10)
            for now in (10.1, 10.2, 10.4, 14):
                self.assertFalse(gate.update(1, 10, 7, (0, 0), now))
            self.assertEqual(gate.elapsed, 0)

        def test_identity_gap_and_boundary(self):
            gate = AlignmentGate()
            self.feed(gate, 20)
            self.assertFalse(gate.update(2000, 12, 8, (0, 0), 12))
            self.assertEqual(gate.elapsed, 0)
            self.assertFalse(gate.update(2100, 13, 8, (0, 0), 13))
            self.assertEqual(gate.elapsed, 0)
            self.assertFalse(gate.update(2200, 13.1, 8, (20.01, 0), 13.1))
            self.assertEqual(gate.state, 'aligning')

        def test_packet_and_json_coordinate_convention(self):
            class Port:
                def write(self, data):
                    self.packet = data
                    return len(data)
            port = Port()
            send_packet(port, 'A,10,10,1', True)
            self.assertEqual(port.packet, b'A,10,10,1\nX\n')
            self.assertEqual(make_sample(0, 1280, 720, 650, 370)['delta_y'], 10)

        def test_worker_calibrates_target_and_rejects_old_mode(self):
            import numpy as np
            from types import SimpleNamespace
            class Source:
                last_delivered_time = 10
                def read(self):
                    return np.zeros((720, 1280, 3), dtype=np.uint8)
            class Detection:
                track_id = 7
                def coordinates(self, width, height):
                    return dict(cx=741, cy=494)
            for change_mode in (False, True):
                def process(frame):
                    if change_mode:
                        worker.set_auto(False)
                    worker.stop.set()
                    return [Detection()]
                worker = TrackingWorker(Source(), lambda: SimpleNamespace(process=process),
                                        lambda detections, locked: detections[0], (101, 134))
                worker.set_auto(True)
                worker.run()
                if change_mode:
                    self.assertIsNone(worker.result)
                else:
                    self.assertEqual(worker.result['error'], (0, 0))

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == '__main__':
    main()
