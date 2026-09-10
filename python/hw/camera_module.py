"""
USB webcam management (Logitech Brio 105) via OpenCV/V4L2.

Handles two capture modes:
- Full-resolution photos (1080p), verifying that the camera actually accepted
  the requested resolution.
- LCD Live View: generates an RGB565 thumbnail downscaled from the 1080p
  frame and sends it in chunks (see send_view_frame_chunked) to stay within
  RPC message size limits.
"""

import base64
import math
import time

import cv2  # type: ignore[import]
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
        """Initializes the manager with no open capture device; the camera is opened lazily on first use via ensure_open()."""
        self._cap = None
        self.last_photo_path = (
            None  # path of the last captured photo (for vision_module)
        )

    def ensure_open(self):
        """Returns an active cv2.VideoCapture instance, opening and configuring the device if it isn't already open, or None if opening fails."""
        if self._cap is None or not self._cap.isOpened():
            self._cap = self._open()
        return self._cap

    def close(self):
        """Releases the camera device and clears the internal capture handle."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _open(self):
        cap = cv2.VideoCapture(CAMERA_DEVICE_INDEX, cv2.CAP_V4L2)
        if not cap.isOpened():
            print(f"[ERROR] Could not open camera at index {CAMERA_DEVICE_INDEX}")
            return None

        # fourcc must precede resolution configuration for MJPG mode
        fourcc = cv2.VideoWriter_fourcc(*CAMERA_FOURCC)
        cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_PHOTO_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_PHOTO_HEIGHT)

        self._verify_resolution(cap)
        return cap

    @staticmethod
    def _verify_resolution(cap) -> bool:
        """Checks whether an open capture device actually accepted the configured target resolution, logging a warning with a v4l2-ctl diagnostic hint if not. Returns True if the resolution matches, False otherwise."""
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if (actual_w, actual_h) == (CAMERA_PHOTO_WIDTH, CAMERA_PHOTO_HEIGHT):
            print(
                f"[OK] Camera opened at index {CAMERA_DEVICE_INDEX} ({actual_w}x{actual_h})"
            )
            return True

        print(
            f"[WARN] Camera accepted {actual_w}x{actual_h} instead of "
            f"{CAMERA_PHOTO_WIDTH}x{CAMERA_PHOTO_HEIGHT}. Photos will not be 1080p. "
            f"Check supported resolutions with 'v4l2-ctl -d /dev/video{CAMERA_DEVICE_INDEX} --list-formats-ext'."
        )
        return False

    def _grab_frame(self, flush: int = 5):
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

    def take_photo(self):
        """Captures a single frame and writes it as a timestamped, resolution-tagged JPEG to PHOTOS_DIR, updating last_photo_path on success. Returns the written file's path, or None if frame acquisition fails."""
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
        self.last_photo_path = filename
        return filename

    def send_view_frame_chunked(
        self,
        bridge,
        thumb_w: int,
        thumb_h: int,
        chunk_pixels: int,
        chunk_delay_s: float,
    ) -> bool:
        """Captures a frame, downscales it to thumb_w by thumb_h in RGB565 format, and streams it to the sketch over the Bridge RPC connection as a sequence of Base64-encoded chunks of chunk_pixels each, pausing chunk_delay_s seconds between chunks to avoid overloading the link. Returns True once all chunks are sent, or False if frame capture fails."""
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
        """Resizes a BGR OpenCV frame to the given dimensions and packs it into a
        little-endian 16-bit BGR565 byte buffer matching the ST7735 (INITR_GREENTAB)
        hardware channel order. The display expects Blue in bits[15:11], Green in
        bits[10:5], Red in bits[4:0]. OpenCV frames are already BGR so we map each
        channel directly — no conversion needed.
        """
        resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        # OpenCV channel 0=B, 1=G, 2=R — maps directly to ST7735 BGR565 layout
        b = (resized[:, :, 0].astype(np.uint16) >> 3) << 11
        g = (resized[:, :, 1].astype(np.uint16) >> 2) << 5
        r = resized[:, :, 2].astype(np.uint16) >> 3
        bgr565 = (b | g | r).astype("<u2")
        return bgr565.tobytes()
