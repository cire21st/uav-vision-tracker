"""Read the vision program's JSON output without opening the Arduino port."""

import json
import os
from pathlib import Path
import subprocess
import threading
import time


VISION_DIR = Path("C:/comet/uav-tracker-test")
VISION_CAMERA = 1


class VisionInput:
    def __init__(
        self, project_dir=VISION_DIR, python_path=None, timeout=1.0,
        camera=VISION_CAMERA,
    ):
        self.project_dir = Path(project_dir)
        self.python_path = Path(python_path) if python_path else (
            self.project_dir / ".venv/Scripts/python.exe"
        )
        self.timeout = timeout
        self.camera = camera
        self.process = None
        self.latest = None
        self.updated_at = 0.0
        self.lock = threading.Lock()
        self.reader = None

    def start(self):
        if self.process is not None and self.process.poll() is None:
            return

        with self.lock:
            self.latest = None
            self.updated_at = 0.0

        # No --serial: control.py is the sole owner of the Arduino COM port.
        process = subprocess.Popen(
            [
                str(self.python_path), "-u", "main.py",
                "--camera", str(self.camera),
                "--print-every", "1",
                "--width", "1280", "--height", "720",
            ],
            cwd=str(self.project_dir),
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        )
        self.process = process
        self.reader = threading.Thread(
            target=self._receive, args=(process,), daemon=True
        )
        self.reader.start()

    def _receive(self, process):
        locked_id = None

        with process.stdout:
            for line in process.stdout:
                try:
                    frame = json.loads(line)
                    if not isinstance(frame, dict) or "objects" not in frame:
                        continue

                    objects = frame["objects"]
                    if not objects:
                        values = (0, 0, 0)
                    else:
                        target = next(
                            (obj for obj in objects
                             if locked_id is not None
                             and obj.get("track_id") == locked_id),
                            None,
                        )
                        if target is None:
                            target = max(objects, key=lambda obj: obj["confidence"])

                        dx = round(target["error_x"])
                        dy = round(-target["error_y"])
                        if not (-32768 <= dx <= 32767 and -32768 <= dy <= 32767):
                            continue
                        locked_id = target.get("track_id")
                        values = (dx, dy, 1)

                    with self.lock:
                        # A previous process may finish reading after a restart.
                        if self.process is process:
                            self.latest = values
                            self.updated_at = time.monotonic()
                except (ValueError, KeyError, TypeError, OverflowError):
                    # Ignore ordinary YOLO output and malformed JSON frames.
                    continue

    def read(self):
        if self.process is None or self.process.poll() is not None:
            return None

        with self.lock:
            if time.monotonic() - self.updated_at > self.timeout:
                return None
            return self.latest

    def close(self):
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        if self.reader is not None:
            self.reader.join(timeout=1)
        self.process = None
        with self.lock:
            self.latest = None
            self.updated_at = 0.0
