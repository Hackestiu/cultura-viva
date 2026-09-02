"""
USB webcam management (Logitech Brio 105) via OpenCV/V4L2:
- Full resolution photos (1080p), verifying that the camera accepted the requested resolution.
- LCD Live View: generates an RGB565 thumbnail reduced from the 1080p frame and sends it
  IN CHUNKS (see send_view_frame_chunked) to stay within RPC message size limits.
"""

import base64
import math
import time

import cv2
import numpy as np

from config import (
    CAMERA_DEVICE_INDEX,
    CAMERA_FOURCC,
    CAMERA_PHOTO_HEIGHT,
    CAMERA_PHOTO_WIDTH,
    PHOTOS_DIR,
)


class CameraManager:
    def __init__(self):
        self._cap = None
        self.last_photo_path = None  # path of the last captured photo (for vision_module)

    # ---------- Lifecycle ----------
    def ensure_open(self):
        if self._cap is None or not self._cap.isOpened():
            self._cap = self._open()
        return self._cap

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _open(self):
        # V4L2 is the native Linux backend
        cap = cv2.VideoCapture(CAMERA_DEVICE_INDEX, cv2.CAP_V4L2)
        if not cap.isOpened():
            print(f"[ERROR] Could not open camera at index {CAMERA_DEVICE_INDEX}")
            return None

        # fourcc must be set before width/height; required for 1080p on this webcam
        fourcc = cv2.VideoWriter_fourcc(*CAMERA_FOURCC)
        cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_PHOTO_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_PHOTO_HEIGHT)

        self._verify_resolution(cap)
        return cap

    @staticmethod
    def _verify_resolution(cap) -> bool:
        """Checks if the camera actually accepted the requested resolution."""
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if (actual_w, actual_h) == (CAMERA_PHOTO_WIDTH, CAMERA_PHOTO_HEIGHT):
            print(f"[OK] Camera opened at index {CAMERA_DEVICE_INDEX} ({actual_w}x{actual_h})")
            return True

        print(
            f"[WARN] Camera accepted {actual_w}x{actual_h} instead of "
            f"{CAMERA_PHOTO_WIDTH}x{CAMERA_PHOTO_HEIGHT}. Photos will not be 1080p. "
            f"Check supported resolutions with 'v4l2-ctl -d /dev/video{CAMERA_DEVICE_INDEX} --list-formats-ext'."
        )
        return False

    def _grab_frame(self, flush=5):
        cap = self.ensure_open()
        if cap is None:
            return None
        for _ in range(flush):
            cap.grab()
        ret, frame = cap.retrieve()
        if not ret:
            print("[ERROR] Could not capture frame from camera")
            return None
        return frame

    # ---------- Photos (Button D7) ----------
    def take_photo(self):
        """Captures a frame from the camera and saves it as a JPEG to PHOTOS_DIR.
        The filename encodes the timestamp and actual frame dimensions.
        Returns the saved file path, or None if the camera is unavailable or capture fails."""
        frame = self._grab_frame(flush=5)
        if frame is None:
            return None

        height, width = frame.shape[:2]
        is_full_res = (width, height) == (CAMERA_PHOTO_WIDTH, CAMERA_PHOTO_HEIGHT)
        if not is_full_res:
            print(
                f"[WARN] Frame captured at {width}x{height} instead of expected "
                f"{CAMERA_PHOTO_WIDTH}x{CAMERA_PHOTO_HEIGHT}."
            )

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = PHOTOS_DIR / f"capture_{timestamp}_{width}x{height}.jpg"
        cv2.imwrite(str(filename), frame)
        print(f"[OK] Photo saved to: {filename} ({width}x{height})")
        self.last_photo_path = filename  # save path for vision_module
        return filename

    # ---------- Live View (switch D6 ON), sent in chunks ----------
    def send_view_frame_chunked(self, bridge, thumb_w, thumb_h, chunk_pixels, chunk_delay_s):
        """Captures a frame, resizes to thumb_w x thumb_h in RGB565, and sends
        it to sketch in consecutive chunks via 'receive_camera_chunk'.
        Returns True if successful, False otherwise."""
        frame = self._grab_frame(flush=2)
        if frame is None:
            return False

        raw_bytes = self._frame_to_rgb565_bytes(frame, thumb_w, thumb_h)
        total_pixels = thumb_w * thumb_h
        total_chunks = math.ceil(total_pixels / chunk_pixels)

        for chunk_index in range(total_chunks):
            start = chunk_index * chunk_pixels * 2
            end = min(start + chunk_pixels * 2, len(raw_bytes))
            chunk_b64 = base64.b64encode(raw_bytes[start:end]).decode("ascii")
            bridge.call("receive_camera_chunk", chunk_index, total_chunks, chunk_b64)
            if chunk_delay_s > 0 and chunk_index < total_chunks - 1:
                time.sleep(chunk_delay_s)

        return True

    @staticmethod
    def _frame_to_rgb565_bytes(frame: np.ndarray, width: int, height: int) -> bytes:
        """Converts BGR OpenCV frame to RGB565 bytes (2 bytes/pixel, little-endian)."""
        resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        r = (rgb[:, :, 0].astype(np.uint16) >> 3) << 11
        g = (rgb[:, :, 1].astype(np.uint16) >> 2) << 5
        b = rgb[:, :, 2].astype(np.uint16) >> 3
        rgb565 = (r | g | b).astype("<u2")
        return rgb565.tobytes()
