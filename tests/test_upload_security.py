from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.config import get_settings
from backend.app.services.security import (
    SecurityValidationError,
    validate_video_signature,
    validate_video_upload_metadata,
)


class UploadSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = get_settings()

    def test_rejects_path_traversal_extension(self) -> None:
        with self.assertRaises(SecurityValidationError):
            validate_video_upload_metadata(
                original_filename="../../evil.exe",
                content_type="video/mp4",
                size_bytes=1024,
                settings=self.settings,
            )

    def test_generates_safe_server_filename(self) -> None:
        upload = validate_video_upload_metadata(
            original_filename="../clip.MP4",
            content_type="video/mp4",
            size_bytes=1024,
            settings=self.settings,
        )
        self.assertTrue(upload.safe_filename.endswith(".mp4"))
        self.assertNotIn("clip", upload.safe_filename)
        self.assertNotIn("..", upload.safe_filename)

    def test_rejects_oversized_upload(self) -> None:
        with self.assertRaises(SecurityValidationError):
            validate_video_upload_metadata(
                original_filename="clip.mp4",
                content_type="video/mp4",
                size_bytes=self.settings.upload_limit_bytes + 1,
                settings=self.settings,
            )

    def test_rejects_double_extension_and_mime_mismatch(self) -> None:
        for filename, content_type in (("video.mp4.exe", "video/mp4"), ("video.mp4", "application/octet-stream")):
            with self.subTest(filename=filename, content_type=content_type), self.assertRaises(SecurityValidationError):
                validate_video_upload_metadata(
                    original_filename=filename, content_type=content_type, size_bytes=1024, settings=self.settings
                )

    def test_rejects_random_bytes_before_native_decoder(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "random.mp4"
            path.write_bytes(b"random bytes renamed as mp4")
            with self.assertRaises(SecurityValidationError):
                validate_video_signature(path, ".mp4")

    def test_accepts_supported_container_signatures(self) -> None:
        with TemporaryDirectory() as tmp:
            mp4 = Path(tmp) / "clip.mp4"
            mp4.write_bytes(b"\x00\x00\x00\x18ftypisom0000")
            validate_video_signature(mp4, ".mp4")
            webm = Path(tmp) / "clip.webm"
            webm.write_bytes(b"\x1aE\xdf\xa3webm")
            validate_video_signature(webm, ".webm")


if __name__ == "__main__":
    unittest.main()
