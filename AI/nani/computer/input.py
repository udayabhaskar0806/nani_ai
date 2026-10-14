"""N.A.N.I. V2 — Desktop Mouse & Keyboard Input
Provides calibrated coordinate translation and bounded input dispatch using PyAutoGUI.
"""

from typing import Any

import pyautogui

# Set PyAutoGUI safety configuration
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


class DesktopInput:
    """Dispatches physical mouse and keyboard inputs with coordinate normalization."""

    @staticmethod
    def get_screen_size() -> tuple[int, int]:
        """Returns the physical screen width and height in pixels."""
        w, h = pyautogui.size()
        return int(w), int(h)

    @classmethod
    def click_at(
        cls,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
    ) -> dict[str, Any]:
        """Clicks at concrete physical pixel coordinates."""
        sw, sh = cls.get_screen_size()
        cx = max(0, min(x, sw - 1))
        cy = max(0, min(y, sh - 1))
        pyautogui.click(x=cx, y=cy, button=button, clicks=clicks)
        return {"action": "click", "x": cx, "y": cy, "button": button, "clicks": clicks}

    @classmethod
    def move_to(cls, x: int, y: int) -> dict[str, Any]:
        """Moves cursor to concrete physical coordinates."""
        sw, sh = cls.get_screen_size()
        cx = max(0, min(x, sw - 1))
        cy = max(0, min(y, sh - 1))
        pyautogui.moveTo(cx, cy)
        return {"action": "move", "x": cx, "y": cy}

    @classmethod
    def type_text(cls, text: str, interval: float = 0.02) -> dict[str, Any]:
        """Types string of characters into the currently focused window."""
        pyautogui.write(text, interval=interval)
        return {"action": "type_text", "chars": len(text)}

    @classmethod
    def press_key(cls, key: str) -> dict[str, Any]:
        """Presses an individual key or shortcut (e.g. 'enter', 'tab', 'ctrl', 'alt')."""
        pyautogui.press(key)
        return {"action": "press_key", "key": key}

    @classmethod
    def hotkey(cls, *keys: str) -> dict[str, Any]:
        """Executes a key combination shortcut (e.g. 'ctrl', 'c')."""
        pyautogui.hotkey(*keys)
        return {"action": "hotkey", "keys": list(keys)}
