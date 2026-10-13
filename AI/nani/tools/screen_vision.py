"""N.A.N.I. Screen Vision & GUI Interaction Engine
Allows N.A.N.I. to "see" your display via multimodal vision models,
and interact with GUI elements via keyboard and mouse automation.
"""

import base64
import io
import os
from pathlib import Path
from typing import Dict, Any, Optional
import mss
from PIL import Image
import pyautogui

from nani.config import Config

class ScreenVision:
    def __init__(self, engine=None):
        self.engine = engine
        self.temp_dir = Path("/tmp/nani")
        self.temp_dir.mkdir(exist_ok=True)
        pyautogui.FAILSAFE = True  # Move mouse to corner to abort

    def capture_screen_image(self, max_dimension: int = 1600, quality: int = 80) -> Image.Image:
        """Captures screen and optimizes resolution for vision LLM inference."""
        with mss.MSS() as sct:
            mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

            # Scale down if larger than max_dimension to keep tokens and latency low
            if max(img.size) > max_dimension:
                scale = max_dimension / max(img.size)
                new_size = (int(img.width * scale), int(img.height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            return img

    def get_screen_base64(self) -> str:
        """Captures display and converts to base64 JPEG string."""
        img = self.capture_screen_image()
        buffered = io.BytesIO()
        
        img.save(buffered, format="JPEG", quality=80)
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    def see_and_analyze(self, question: str = "What is currently happening on my screen?") -> str:
        """Sends the screen image to a multimodal AI model and returns a deep visual breakdown."""
        from nani.core.gemini_client import GeminiDirectClient
        gemini = GeminiDirectClient()
        if gemini.is_configured:
            b64_img = self.get_screen_base64()
            return gemini.analyze_image_base64(b64_img, question)

        # Fallback if no cloud multimodal key is configured
        img = self.capture_screen_image()
        return (
            f"📸 [N.A.N.I. Vision Local Capture]:\n"
            f"Screen successfully grabbed at resolution: {img.width}x{img.height} pixels.\n"
            f"Notice: To enable full AI visual analysis of your screen, add a free Gemini API key to .env (GEMINI_API_KEY=...).\n"
            f"Gemini 2.0 Flash includes 1,500 free multimodal image analysis requests per day!"
        )

    # GUI Actions (Keyboard & Mouse)
    def click_at(self, x: int, y: int) -> str:
        """Clicks at specific screen coordinates."""
        pyautogui.click(x, y)
        return f"Clicked at coordinates ({x}, {y})."

    def type_text(self, text: str) -> str:
        """Types text using virtual keyboard."""
        pyautogui.write(text, interval=0.02)
        return f"Typed: '{text}'"

    def press_key(self, key: str) -> str:
        """Presses a specific key (e.g. 'enter', 'esc', 'tab', 'ctrl', 'c')."""
        pyautogui.press(key)
        return f"Pressed key: '{key}'"
