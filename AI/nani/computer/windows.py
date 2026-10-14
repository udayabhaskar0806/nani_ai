"""N.A.N.I. V2 — X11 Window Management & Focus Control
Lists visible desktop windows and focuses active applications via wmctrl/xdotool.
"""

import asyncio
from typing import Any


class WindowManager:
    """Controls X11 desktop windows (list, find, activate)."""

    async def list_windows(self) -> list[dict[str, Any]]:
        """Lists active windows with window ID, desktop ID, machine, and title."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "wmctrl",
                "-l",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return []

            windows = []
            for line in stdout.decode("utf-8", errors="replace").splitlines():
                parts = line.strip().split(None, 3)
                if len(parts) >= 4:
                    windows.append(
                        {
                            "window_id": parts[0],
                            "desktop_id": parts[1],
                            "client_machine": parts[2],
                            "title": parts[3],
                        }
                    )
            return windows
        except FileNotFoundError:
            return []
        except Exception:
            return []

    async def focus_window(self, title_substring: str) -> bool:
        """Focuses/activates a window by substring matching its title."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "wmctrl",
                "-a",
                title_substring,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode == 0
        except FileNotFoundError:
            return False
        except Exception:
            return False

    async def get_active_window_title(self) -> str:
        """Returns the title of the currently focused X11 window."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "xdotool",
                "getactivewindow",
                "getwindowname",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                return stdout.decode("utf-8", errors="replace").strip()
            return ""
        except FileNotFoundError:
            return ""
        except Exception:
            return ""
