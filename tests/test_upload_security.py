from __future__ import annotations

import unittest

from backend.app.config import get_settings
from backend.app.services.security import SecurityValidationError, validate_video_upload_metadata


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


if __name__ == "__main__":
    unittest.main()
