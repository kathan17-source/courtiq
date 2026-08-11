from __future__ import annotations

from dataclasses import dataclass
from math import acos, degrees, sqrt
from pathlib import Path
from statistics import mean
from math import isfinite

from backend.app.config import Settings
from backend.app.services.security import SecurityValidationError


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True)
class VideoProbe:
    width: int
    height: int
    fps: float
    frame_count: int
    duration_seconds: float


def probe_video(path: Path, settings: Settings) -> VideoProbe:
    try:
        import cv2  # type: ignore
    except ModuleNotFoundError as exc:
        raise SecurityValidationError("media_probe_unavailable", "Video probing is unavailable in this runtime.") from exc
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise SecurityValidationError("invalid_video", "Uploaded content is not a readable video.")
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = frame_count / fps if fps > 0 else float("inf")
        if width <= 0 or height <= 0 or fps <= 0 or frame_count <= 0 or not isfinite(duration):
            raise SecurityValidationError("invalid_video_metadata", "Video metadata is invalid or incomplete.")
        if fps > settings.video_max_fps:
            raise SecurityValidationError("video_fps_too_high", "Video frame rate exceeds the supported limit.")
        if width * height > settings.video_max_pixels:
            raise SecurityValidationError("video_resolution_too_large", "Video resolution exceeds the supported limit.")
        if frame_count > settings.video_max_frames or duration > settings.video_max_duration_seconds:
            raise SecurityValidationError("video_duration_too_long", "Video duration exceeds the supported limit.")
        return VideoProbe(width, height, fps, frame_count, duration)
    finally:
        capture.release()


def joint_angle(a: Point2D, b: Point2D, c: Point2D) -> float:
    bax = a.x - b.x
    bay = a.y - b.y
    bcx = c.x - b.x
    bcy = c.y - b.y
    denom = sqrt(bax * bax + bay * bay) * sqrt(bcx * bcx + bcy * bcy)
    if denom == 0:
        return 0.0
    cos_theta = max(-1.0, min(1.0, (bax * bcx + bay * bcy) / denom))
    return degrees(acos(cos_theta))


def analyze_pose_video(path: Path, max_frames: int = 90, min_visibility: float = 0.55) -> dict[str, object]:
    """Analyze sampled video frames with MediaPipe Pose when available.

    This intentionally reports only body landmarks that were actually detected.
    It does not infer racket path, ball speed, spin, winners, or unforced errors.
    """
    try:
        import cv2  # type: ignore
        import mediapipe as mp  # type: ignore
    except ModuleNotFoundError:
        return {
            "status": "insufficient_engine",
            "reason": "OpenCV and MediaPipe are not installed in this runtime.",
            "metrics": {},
            "frames_processed": 0,
            "content_detection": content_detection({}, 0, 0, 30.0, 0, 0),
        }

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return {
            "status": "invalid_video",
            "reason": "Video could not be opened.",
            "metrics": {},
            "frames_processed": 0,
            "content_detection": content_detection({}, 0, 0, 30.0, 0, 0),
        }

    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    step = max(1, frame_count // max_frames) if frame_count else 1
    pose = mp.solutions.pose.Pose(static_image_mode=False, model_complexity=1, enable_segmentation=False)
    metrics: dict[str, list[float]] = {"left_knee": [], "right_knee": [], "left_elbow": [], "right_elbow": [], "shoulder_tilt": [], "hip_tilt": []}
    timestamps: list[dict[str, float]] = []

    index = 0
    processed = 0
    try:
        while processed < max_frames:
            ok, frame = capture.read()
            if not ok:
                break
            if index % step:
                index += 1
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = pose.process(rgb)
            if result.pose_landmarks:
                landmarks = result.pose_landmarks.landmark
                frame_metrics = frame_pose_metrics(landmarks, min_visibility)
                if frame_metrics:
                    for key, value in frame_metrics.items():
                        metrics[key].append(value)
                    timestamps.append({"time": round(index / fps, 3), **{key: round(value, 2) for key, value in frame_metrics.items()}})
            processed += 1
            index += 1
    finally:
        pose.close()
        capture.release()

    detected = sum(len(values) for values in metrics.values())
    if detected == 0:
        return {
            "status": "insufficient_confidence",
            "reason": "No reliable body landmarks were detected.",
            "metrics": {},
            "frames_processed": processed,
            "content_detection": content_detection({}, processed, frame_count, fps, width, height),
        }

    summarized = {
        key: {
            "mean": round(mean(values), 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "confidence": round(min(1.0, len(values) / max(processed, 1)), 3),
        }
        for key, values in metrics.items()
        if values
    }
    return {
        "status": "ok",
        "frames_processed": processed,
        "metrics": summarized,
        "timestamps": timestamps[:40],
        "content_detection": content_detection(metrics, processed, frame_count, fps, width, height),
    }


def content_detection(
    metrics: dict[str, list[float]],
    processed: int,
    frame_count: int,
    fps: float,
    width: int,
    height: int,
) -> dict[str, object]:
    """Describe only what the pose pass can defensibly support."""
    usable_frames = max((len(values) for values in metrics.values()), default=0)
    usable_ratio = round(usable_frames / max(processed, 1), 3)
    upper_frames = max(len(metrics.get("left_elbow", [])), len(metrics.get("right_elbow", [])), len(metrics.get("shoulder_tilt", [])))
    lower_frames = max(len(metrics.get("left_knee", [])), len(metrics.get("right_knee", [])), len(metrics.get("hip_tilt", [])))
    upper_ratio = upper_frames / max(processed, 1)
    lower_ratio = lower_frames / max(processed, 1)
    shoulder_values = metrics.get("shoulder_tilt", [])
    hip_values = metrics.get("hip_tilt", [])
    elbow_values = metrics.get("left_elbow", []) + metrics.get("right_elbow", [])

    def value_range(values: list[float]) -> float:
        return max(values) - min(values) if values else 0.0

    player_visible = usable_ratio >= 0.12
    if upper_ratio >= 0.35 and lower_ratio >= 0.35:
        body_visibility = "full body visible often enough"
    elif upper_ratio >= 0.25 or lower_ratio >= 0.25:
        body_visibility = "partial body visible"
    else:
        body_visibility = "body visibility too limited"

    if width and height:
        aspect = width / max(height, 1)
        view_orientation = "landscape court view" if aspect >= 1.25 else "portrait or cropped view"
    else:
        view_orientation = "unknown view"

    serve_present = upper_ratio >= 0.35 and value_range(elbow_values) >= 28 and value_range(shoulder_values) >= 8
    groundstroke_present = upper_ratio >= 0.30 and value_range(shoulder_values) >= 6
    movement_reliable = lower_ratio >= 0.32 and (value_range(metrics.get("left_knee", [])) >= 12 or value_range(metrics.get("right_knee", [])) >= 12)
    rally_context = processed >= 35 and (groundstroke_present or movement_reliable)

    detected_actions: list[str] = []
    supported_sections: list[str] = ["Data quality"]
    if player_visible:
        detected_actions.append("player visible")
    if serve_present:
        detected_actions.append("serve-like upper-body loading")
        supported_sections.append("Serve/body loading")
    if groundstroke_present:
        detected_actions.append("groundstroke-style torso rotation")
        supported_sections.append("Stroke mechanics")
    if movement_reliable:
        detected_actions.append("lower-body movement")
        supported_sections.extend(["Footwork", "Recovery"])
    if rally_context:
        detected_actions.append("multi-moment rally/movement sample")
        supported_sections.append("Consistency")
    if not detected_actions:
        detected_actions.append("no reliable tennis action confirmed")

    limitations: list[str] = []
    if usable_ratio < 0.35:
        limitations.append("Limited usable landmark frames; confidence is reduced.")
    if lower_ratio < 0.25:
        limitations.append("Lower body was not visible often enough for reliable footwork claims.")
    if upper_ratio < 0.25:
        limitations.append("Upper body was not visible often enough for reliable stroke mechanics.")
    limitations.append("Ball speed, spin, racket angle and shot outcome are not measured by this pose-only analyzer.")

    duration_seconds = round(frame_count / fps, 2) if frame_count and fps else None
    return {
        "player_visible": player_visible,
        "usable_frames": usable_frames,
        "usable_frame_ratio": usable_ratio,
        "body_visibility": body_visibility,
        "view_orientation": view_orientation,
        "serve_sequences_present": serve_present,
        "groundstroke_sequences_present": groundstroke_present,
        "rally_context_identified": rally_context,
        "movement_analysis_reliable": movement_reliable,
        "detected_actions": detected_actions,
        "supported_sections": sorted(set(supported_sections)),
        "limitations": limitations,
        "duration_seconds": duration_seconds,
        "frame_size": {"width": width, "height": height},
    }


def frame_pose_metrics(landmarks: object, min_visibility: float) -> dict[str, float]:
    def point(index: int) -> Point2D | None:
        landmark = landmarks[index]
        if getattr(landmark, "visibility", 1.0) < min_visibility:
            return None
        return Point2D(float(landmark.x), float(landmark.y))

    # MediaPipe Pose indices.
    pairs = {
        "left_knee": (23, 25, 27),
        "right_knee": (24, 26, 28),
        "left_elbow": (11, 13, 15),
        "right_elbow": (12, 14, 16),
    }
    output: dict[str, float] = {}
    for name, (a_i, b_i, c_i) in pairs.items():
        a, b, c = point(a_i), point(b_i), point(c_i)
        if a and b and c:
            output[name] = joint_angle(a, b, c)

    left_shoulder, right_shoulder = point(11), point(12)
    left_hip, right_hip = point(23), point(24)
    if left_shoulder and right_shoulder:
        output["shoulder_tilt"] = degrees_from_horizontal(left_shoulder, right_shoulder)
    if left_hip and right_hip:
        output["hip_tilt"] = degrees_from_horizontal(left_hip, right_hip)
    return output


def degrees_from_horizontal(a: Point2D, b: Point2D) -> float:
    dx = b.x - a.x
    dy = b.y - a.y
    if dx == 0:
        return 90.0
    from math import atan2

    return degrees(atan2(dy, dx))
