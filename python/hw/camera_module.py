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
from pathlib import Path
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
        self._current_index = CAMERA_DEVICE_INDEX
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
        candidates = []
        if self._current_index is not None and self._current_index not in candidates:
            candidates.append(self._current_index)
        if CAMERA_DEVICE_INDEX not in candidates:
            candidates.append(CAMERA_DEVICE_INDEX)
        try:
            from hw.device_discovery import discover_camera_index
            discovered = discover_camera_index()
            if discovered is not None and discovered not in candidates:
                candidates.append(discovered)
        except Exception:
            pass
        for fallback in (2, 0, 1, 3):
            if fallback not in candidates:
                candidates.append(fallback)

        for idx in candidates:
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if cap.isOpened():
                # fourcc must precede resolution configuration for MJPG mode
                fourcc = cv2.VideoWriter_fourcc(*CAMERA_FOURCC)
                cap.set(cv2.CAP_PROP_FOURCC, fourcc)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_PHOTO_WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_PHOTO_HEIGHT)

                self._current_index = idx
                self._verify_resolution(cap, idx)
                return cap
            cap.release()

        print(f"[ERROR] Could not open camera at any index in candidates {candidates}")
        return None

    @staticmethod
    def _verify_resolution(cap, index: int) -> bool:
        """Checks whether an open capture device actually accepted the configured target resolution, logging a warning with a v4l2-ctl diagnostic hint if not. Returns True if the resolution matches, False otherwise."""
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if (actual_w, actual_h) == (CAMERA_PHOTO_WIDTH, CAMERA_PHOTO_HEIGHT):
            print(
                f"[OK] Camera opened at index {index} ({actual_w}x{actual_h})"
            )
            return True

        print(
            f"[WARN] Camera at index {index} accepted {actual_w}x{actual_h} instead of "
            f"{CAMERA_PHOTO_WIDTH}x{CAMERA_PHOTO_HEIGHT}. Photos will not be 1080p. "
            f"Check supported resolutions with 'v4l2-ctl -d /dev/video{index} --list-formats-ext'."
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

    def send_photo_preview(
        self,
        bridge,
        photo_path: Path | str,
        preview_w: int = 160,
        preview_h: int = 86,
        chunk_pixels: int = 80,
    ) -> bool:
        """Loads the captured JPEG photo from disk, crops and resizes it to preview_w x preview_h
        with subtle sharpening, converts it to BGR565 format for the ST7735 LCD, and streams it
        in chunks via the 'receive_photo_chunk' Bridge RPC method."""
        path = Path(photo_path)
        if not path.exists():
            print(f"[WARN] send_photo_preview: photo not found: {path}")
            return False

        frame = cv2.imread(str(path))
        if frame is None:
            print(f"[WARN] send_photo_preview: failed to read image: {path}")
            return False

        # Fit aspect ratio to preview_w x preview_h (160x86 is ~1.86, 16:9 is 1.78)
        h_orig, w_orig = frame.shape[:2]
        scale = preview_w / w_orig
        new_h = int(h_orig * scale)
        resized = cv2.resize(frame, (preview_w, new_h), interpolation=cv2.INTER_AREA)

        # Center crop vertically to preview_h
        if new_h > preview_h:
            y_start = (new_h - preview_h) // 2
            cropped = resized[y_start : y_start + preview_h, :]
        elif new_h < preview_h:
            cropped = cv2.resize(frame, (preview_w, preview_h), interpolation=cv2.INTER_AREA)
        else:
            cropped = resized

        # Subtle unsharp masking filter for crisp edges on the small TFT display
        blurred = cv2.GaussianBlur(cropped, (0, 0), 1.0)
        sharpened = cv2.addWeighted(cropped, 1.3, blurred, -0.3, 0)

        # Format to BGR565 for ST7735
        b = (sharpened[:, :, 0].astype(np.uint16) >> 3) << 11
        g = (sharpened[:, :, 1].astype(np.uint16) >> 2) << 5
        r = sharpened[:, :, 2].astype(np.uint16) >> 3
        bgr565 = (b | g | r).astype("<u2")
        raw_bytes = bgr565.tobytes()

        total_pixels = preview_w * preview_h
        total_chunks = math.ceil(total_pixels / chunk_pixels)

        for chunk_index in range(total_chunks):
            start = chunk_index * chunk_pixels * 2
            end = min(start + chunk_pixels * 2, len(raw_bytes))
            chunk_b64 = base64.b64encode(raw_bytes[start:end]).decode("ascii")
            bridge.call("receive_photo_chunk", chunk_index, total_chunks, chunk_b64)

        print(f"[OK] High-res photo preview streamed ({preview_w}x{preview_h} in {total_chunks} chunks).")
        return True
