from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.config import get_settings
from backend.app.services.security import SecurityValidationError
from backend.app.services.video_analysis import analyze_pose_video, content_detection, probe_video


class VideoAnalysisServiceTests(unittest.TestCase):
    def test_missing_or_invalid_video_fails_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.mp4"
            path.write_bytes(b"not a real video")
            result = analyze_pose_video(path)
        self.assertIn(result["status"], {"insufficient_engine", "invalid_video", "insufficient_confidence"})
        self.assertIn("metrics", result)
        self.assertIn("content_detection", result)
        self.assertIn("detected_actions", result["content_detection"])

    def test_content_detection_reports_only_supported_sections(self) -> None:
        metrics = {
            "left_knee": [88, 104, 121, 92],
            "right_knee": [90, 109, 125, 96],
            "left_elbow": [108, 146, 164, 126],
            "right_elbow": [104, 140, 158, 122],
            "shoulder_tilt": [-4, 8, 15, 3],
            "hip_tilt": [-3, 4, 9, 1],
        }
        result = content_detection(metrics, processed=8, frame_count=240, fps=30.0, width=1920, height=1080)
        self.assertTrue(result["player_visible"])
        self.assertTrue(result["serve_sequences_present"])
        self.assertTrue(result["groundstroke_sequences_present"])
        self.assertTrue(result["movement_analysis_reliable"])
        self.assertIn("Ball speed, spin, racket angle", " ".join(result["limitations"]))

    def test_probe_rejects_invalid_media_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fake.mp4"
            path.write_bytes(b"not video content")
            with self.assertRaises(SecurityValidationError):
                probe_video(path, get_settings())

    def test_probe_accepts_small_valid_video(self) -> None:
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "valid.mp4"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
            for _ in range(10):
                writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
            writer.release()
            probe = probe_video(path, get_settings())
            self.assertEqual((probe.width, probe.height), (64, 48))


if __name__ == "__main__":
    unittest.main()
