"""Headless checks: run with the vision environment's Python and unittest."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from control_overlay_v2 import RecordedCamera, make_sample, review_recording, save_json


class OverlayV2Tests(unittest.TestCase):
    def test_pixel_coordinates_and_json_list(self):
        sample = make_sample(10, 1280, 720, 650, 340)
        self.assertEqual((sample['delta_x'], sample['delta_y']), (10, -20))
        self.assertEqual(sample['time_seconds'], 2)
        self.assertEqual(make_sample(0, 641, 481, 320, 240)['delta_y'], 0)
        with self.assertRaises(ValueError):
            make_sample(0, 640, 480, 640, 10)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'samples.json'
            save_json(path, [sample])
            self.assertEqual(json.loads(path.read_text()), [sample])

    def test_raw_recording_is_5fps_and_not_modified_by_preview(self):
        class Camera:
            closed = False

            def read(self):
                time.sleep(1 / 30)
                return np.full((240, 320, 3), 100, np.uint8)

            def close(self):
                self.closed = True

        with tempfile.TemporaryDirectory() as temp:
            camera = Camera()
            recorded = RecordedCamera(camera, Path(temp))
            try:
                preview = recorded.read()
                preview[:] = 255  # UI/inference can mutate its own copy.
                time.sleep(1.05)
            finally:
                recorded.close()
            self.assertIsNone(recorded.error)
            self.assertTrue(camera.closed)
            cap = cv2.VideoCapture(str(recorded.video_path))
            try:
                self.assertEqual(cap.get(cv2.CAP_PROP_FPS), 5.0)
                self.assertGreaterEqual(recorded.frames_written, 5)
                self.assertLessEqual(recorded.frames_written, 8)
                self.assertEqual(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), recorded.frames_written)
                ok, frame = cap.read()
                self.assertTrue(ok)
                self.assertLess(abs(float(frame.mean()) - 100), 3)
            finally:
                cap.release()

    def test_review_collects_multiple_frames_until_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            video = directory / 'raw.avi'
            output = directory / 'samples.json'
            writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'),
                                     5, (320, 240))
            self.assertTrue(writer.isOpened())
            for _ in range(3):
                writer.write(np.full((240, 320, 3), 100, np.uint8))
            writer.release()
            ui = dict(frame=0, mouse=None, step=0)

            def wait_key(delay):
                step = ui['step']
                ui['step'] += 1
                if step == 0:
                    ui['mouse'](cv2.EVENT_LBUTTONDOWN, 170, 260, 0, None)
                    return ord('l')  # Refine the original x by exactly one pixel.
                if step == 1:
                    return 13
                if step == 2:
                    return ord('d')
                if step == 3:
                    ui['mouse'](cv2.EVENT_LBUTTONDOWN, 150, 280, 0, None)
                    return 13
                return 27

            with patch.multiple(cv2,
                                namedWindow=lambda *a: None,
                                createTrackbar=lambda *a: None,
                                setMouseCallback=lambda name, cb: ui.update(mouse=cb),
                                getTrackbarPos=lambda *a: ui['frame'],
                                setTrackbarPos=lambda name, win, pos: ui.update(frame=pos),
                                imshow=lambda *a: None,
                                waitKeyEx=wait_key,
                                getWindowProperty=lambda *a: 1,
                                destroyAllWindows=lambda: None):
                review_recording(video, output)
            samples = json.loads(output.read_text())
            self.assertEqual(len(samples), 2)
            self.assertEqual([s['frame_index'] for s in samples], [0, 1])
            self.assertEqual((samples[0]['delta_x'], samples[0]['delta_y']), (11, -10))
            self.assertEqual((samples[1]['delta_x'], samples[1]['delta_y']), (-10, 10))


if __name__ == '__main__':
    unittest.main()
