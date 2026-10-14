"""N.A.N.I. V2 — Screen Perception & Frame Capture
Captures desktop frames via mss and provides coordinate normalization and base64 encoding.
"""

import base64
import io
from pathlib import Path
from typing import Any

import mss
from PIL import Image


class ScreenCapture:
    """Provides high-performance screen capture and coordinate transformation."""

    def __init__(self, target_max_dimension: int = 1280) -> None:
        self.target_max_dimension = target_max_dimension

    def capture_frame(self, monitor_index: int = 1) -> dict[str, Any]:
        """Captures the screen and returns image data with physical and normalized dimensions."""
        with mss.mss() as sct:
            monitors = sct.monitors
            idx = monitor_index if monitor_index < len(monitors) else 1
            monitor = monitors[idx]

            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            width, height = img.size

            # Downscale proportionally if larger than target max dimension to conserve memory/tokens
            scale = 1.0
            if max(width, height) > self.target_max_dimension:
                scale = self.target_max_dimension / float(max(width, height))
                new_size = (int(width * scale), int(height * scale))
                img_scaled = img.resize(new_size, Image.Resampling.LANCZOS)
            else:
                img_scaled = img

            buf = io.BytesIO()
            img_scaled.save(buf, format="JPEG", quality=85)
            jpeg_bytes = buf.getvalue()
            b64_str = base64.b64encode(jpeg_bytes).decode("ascii")

            return {
                "width": width,
                "height": height,
                "scaled_width": img_scaled.width,
                "scaled_height": img_scaled.height,
                "scale": scale,
                "base64_jpeg": b64_str,
                "bytes_len": len(jpeg_bytes),
            }

    def save_screenshot(self, target_path: Path | str, monitor_index: int = 1) -> Path:
        """Saves current screen directly to disk."""
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with mss.mss() as sct:
            monitors = sct.monitors
            idx = monitor_index if monitor_index < len(monitors) else 1
            sct.shot(mon=idx, output=str(target))
        return target
