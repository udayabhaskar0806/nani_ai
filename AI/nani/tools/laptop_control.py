"""N.A.N.I. Linux Laptop Hardware & System Controller
Direct control over laptop hardware: Audio volume, brightness, battery, lock screen, and screenshots.
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

class LaptopController:
    def __init__(self):
        self.temp_dir = Path("/tmp/nani")
        self.temp_dir.mkdir(exist_ok=True)

    def get_battery_info(self) -> Dict[str, Any]:
        """Reads hardware battery state directly from Linux sysfs."""
        info = {"present": False, "percentage": 0, "status": "Unknown", "on_ac": False}
        bat_dir = Path("/sys/class/power_supply/BAT0")
        ac_dir = Path("/sys/class/power_supply/AC")

        if bat_dir.exists():
            info["present"] = True
            try:
                cap_file = bat_dir / "capacity"
                if cap_file.exists():
                    info["percentage"] = int(cap_file.read_text().strip())
                status_file = bat_dir / "status"
                if status_file.exists():
                    info["status"] = status_file.read_text().strip()
            except Exception:
                pass

        if ac_dir.exists():
            try:
                online_file = ac_dir / "online"
                if online_file.exists():
                    info["on_ac"] = online_file.read_text().strip() == "1"
            except Exception:
                pass

        return info

    def set_volume(self, percent: int) -> str:
        """Sets laptop speaker volume (0 to 100%)."""
        val = max(0, min(100, percent))
        cmd = f"pactl set-sink-volume @DEFAULT_SINK@ {val}%"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            return f"Speaker volume set to {val}%."
        return f"Failed to adjust volume: {res.stderr.strip()}"

    def toggle_mute(self) -> str:
        """Mutes or unmutes the default audio sink."""
        cmd = "pactl set-sink-mute @DEFAULT_SINK@ toggle"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            return "Audio mute toggled."
        return f"Failed to toggle mute: {res.stderr.strip()}"

    def set_brightness(self, percent: int) -> str:
        """Sets display brightness using xrandr (10% to 100%)."""
        clamped = max(10, min(100, percent))
        factor = round(clamped / 100.0, 2)
        # Try finding primary connected display
        detect = subprocess.run("xrandr --query | grep ' connected'", shell=True, capture_output=True, text=True)
        display = "eDP-1"
        if detect.stdout:
            display = detect.stdout.split()[0]
        
        cmd = f"xrandr --output {display} --brightness {factor}"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            return f"Display brightness set to {clamped}% on {display}."
        return f"Failed to adjust brightness: {res.stderr.strip()}"

    def lock_screen(self) -> str:
        """Immediately locks the Linux desktop session."""
        cmd = "loginctl lock-session"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            return "Desktop session locked."
        return f"Lock command failed: {res.stderr.strip()}"

    def capture_screenshot(self, filename: str = "screenshot.png") -> Dict[str, Any]:
        """Takes a full-resolution screenshot of the laptop screen."""
        out_path = self.temp_dir / filename
        
        # Method 1: Python mss (Fastest, zero-dependency)
        try:
            import mss
            with mss.mss() as sct:
                sct.shot(output=str(out_path))
            if out_path.exists():
                return {"success": True, "path": str(out_path), "bytes": out_path.stat().st_size}
        except Exception:
            pass

        # Method 2: ImageMagick import fallback
        try:
            res = subprocess.run(f"import -window root {out_path}", shell=True, capture_output=True, timeout=5)
            if res.returncode == 0 and out_path.exists():
                return {"success": True, "path": str(out_path), "bytes": out_path.stat().st_size}
        except Exception:
            pass

        return {"success": False, "error": "Could not capture screenshot (display server may be detached)."}

    def launch_app(self, app_command: str) -> str:
        """Launches a desktop GUI application in the background."""
        try:
            subprocess.Popen(app_command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Launched application: '{app_command}'."
        except Exception as e:
            return f"Failed to launch '{app_command}': {str(e)}"

    def kill_app(self, proc_name: str) -> str:
        """Safely terminates a named process."""
        cmd = f"pkill -f {proc_name}"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            return f"Terminated processes matching '{proc_name}'."
        return f"No running processes found matching '{proc_name}'."
