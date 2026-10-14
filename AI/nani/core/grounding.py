"""N.A.N.I. V2 — Sensory Machine Grounding
Inspects concrete host hardware, display server, and installed binaries.
Provides factual local context before model invocation so models never guess in the abstract.
"""

import os
import platform
import shutil
from pathlib import Path
from typing import Any


class MachineGrounding:
    """Collects ground-truth system facts in milliseconds without blocking execution."""

    KEY_BINARIES = (
        "brightnessctl",
        "pactl",
        "xterm",
        "gnome-terminal",
        "konsole",
        "xfce4-terminal",
        "ptyxis",
        "alacritty",
        "kitty",
        "foot",
        "x-terminal-emulator",
        "git",
        "gcc",
        "make",
        "python3",
        "curl",
        "ip",
    )

    @classmethod
    def get_installed_tools(cls) -> list[str]:
        """Detects which key CLI tools are currently installed on host $PATH."""
        installed = []
        for b in cls.KEY_BINARIES:
            if shutil.which(b):
                installed.append(b)
        return installed

    @classmethod
    def get_backlight_state(cls) -> dict[str, Any] | None:
        """Inspects Linux sysfs backlight interface."""
        backlight_dir = Path("/sys/class/backlight")
        if not backlight_dir.exists():
            return None
        try:
            for dev in backlight_dir.iterdir():
                cur_f = dev / "brightness"
                max_f = dev / "max_brightness"
                if cur_f.exists() and max_f.exists():
                    cur = int(cur_f.read_text().strip())
                    max_b = int(max_f.read_text().strip())
                    pct = int((cur / max_b) * 100) if max_b > 0 else 0
                    return {
                        "device": dev.name,
                        "current": cur,
                        "max": max_b,
                        "percent": pct,
                    }
        except Exception:
            pass
        return None

    @classmethod
    def get_battery_state(cls) -> dict[str, Any] | None:
        """Inspects battery status via Linux sysfs."""
        power_dir = Path("/sys/class/power_supply")
        if not power_dir.exists():
            return None
        try:
            for bat in power_dir.glob("BAT*"):
                cap_f = bat / "capacity"
                stat_f = bat / "status"
                if cap_f.exists():
                    pct = int(cap_f.read_text().strip())
                    status = stat_f.read_text().strip() if stat_f.exists() else "Unknown"
                    return {
                        "device": bat.name,
                        "percent": pct,
                        "status": status,
                    }
        except Exception:
            pass
        return None

    @classmethod
    def get_memory_state(cls) -> dict[str, int]:
        """Reads system RAM statistics from /proc/meminfo in megabytes."""
        mem_info = {"total_mb": 0, "available_mb": 0}
        meminfo_path = Path("/proc/meminfo")
        if not meminfo_path.exists():
            return mem_info
        try:
            for line in meminfo_path.read_text().splitlines():
                if line.startswith("MemTotal:"):
                    mem_info["total_mb"] = int(line.split()[1]) // 1024
                elif line.startswith("MemAvailable:"):
                    mem_info["available_mb"] = int(line.split()[1]) // 1024
        except Exception:
            pass
        return mem_info

    @classmethod
    def get_distro_info(cls) -> str:
        """Dynamically reads host distribution from /etc/os-release without hardcoding."""
        for p in (Path("/etc/os-release"), Path("/usr/lib/os-release")):
            if p.exists():
                try:
                    data: dict[str, str] = {}
                    for line in p.read_text().splitlines():
                        if "=" in line:
                            k, v = line.split("=", 1)
                            data[k.strip()] = v.strip("\"'")
                    return data.get("PRETTY_NAME") or data.get("NAME") or "Linux"
                except Exception:
                    pass
        return f"{platform.system()} ({platform.release()})"

    @classmethod
    def get_package_managers(cls) -> list[str]:
        """Dynamically inspects which package managers are installed on host $PATH."""
        candidates = ("apt", "snap", "flatpak", "pacman", "dnf", "zypper", "apk", "brew")
        return [mgr for mgr in candidates if shutil.which(mgr)]

    _sudo_override: bool | str | None = None

    @classmethod
    def override_sudo_status(cls, status: bool | str | None) -> None:
        """Overrides detected sudo status when session credentials are authorized."""
        cls._sudo_override = status

    @classmethod
    def check_sudo_privilege(cls) -> bool:
        """Returns True if the machine has active non-interactive passwordless sudo."""
        import subprocess

        try:
            res = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=1.0)
            return res.returncode == 0
        except Exception:
            return False

    @classmethod
    def get_sudo_status(cls) -> str:
        """Determines if the current user has non-interactive passwordless sudo or in-session credentials."""
        if cls._sudo_override is True:
            return "Autonomous sudo authorized (in-session credentials active)"
        if isinstance(cls._sudo_override, str):
            return cls._sudo_override
        if cls._sudo_override is False:
            return "Password required (non-interactive sudo unavailable)"
        if cls.check_sudo_privilege():
            return "Passwordless sudo available"
        return "Password required (non-interactive sudo unavailable)"

    @classmethod
    def get_snapshot(cls) -> dict[str, Any]:
        """Produces a comprehensive dictionary of the machine's concrete state."""
        load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
        return {
            "os": platform.system(),
            "distro": cls.get_distro_info(),
            "package_managers": cls.get_package_managers(),
            "sudo_status": cls.get_sudo_status(),
            "release": platform.release(),
            "machine": platform.machine(),
            "display": os.environ.get("DISPLAY"),
            "wayland_display": os.environ.get("WAYLAND_DISPLAY"),
            "desktop": os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION"),
            "session_type": os.environ.get("XDG_SESSION_TYPE", "unknown"),
            "user": os.environ.get("USER", "unknown"),
            "load_avg": [round(x, 2) for x in load],
            "memory": cls.get_memory_state(),
            "battery": cls.get_battery_state(),
            "backlight": cls.get_backlight_state(),
            "installed_tools": cls.get_installed_tools(),
        }

    @classmethod
    def format_grounding_prompt(cls) -> str:
        """Formats the machine snapshot into a concise, factual context block."""
        snap = cls.get_snapshot()
        lines = [
            "### Local Machine Ground Truth:",
            f"- OS: {snap['distro']} ({snap['machine']}, Kernel: {snap['release']})",
            f"- Package Managers: {', '.join(snap['package_managers']) if snap['package_managers'] else 'None detected'}",
            f"- Privilege: {snap['sudo_status']}",
            f"- Session: {snap['session_type'].upper()} (Desktop: {snap['desktop'] or 'None'}, Display: {snap['wayland_display'] or snap['display'] or 'Headless'})",
        ]

        if snap.get("backlight"):
            b = snap["backlight"]
            b_util = (
                "brightnessctl: INSTALLED"
                if "brightnessctl" in snap["installed_tools"]
                else "brightnessctl: NOT INSTALLED"
            )
            lines.append(f"- Backlight: {b['device']} ({b['percent']}% brightness, {b_util})")

        if snap.get("battery"):
            bat = snap["battery"]
            lines.append(f"- Battery: {bat['device']} ({bat['percent']}%, {bat['status']})")

        mem = snap.get("memory", {})
        if mem.get("total_mb"):
            lines.append(
                f"- Memory: {mem['available_mb']} MB available / {mem['total_mb']} MB total (Load: {snap['load_avg'][0]})"
            )

        terminals = [
            t
            for t in snap["installed_tools"]
            if "term" in t or t in ("konsole", "ptyxis", "alacritty", "kitty", "foot")
        ]
        if terminals:
            lines.append(f"- Available Terminals: {', '.join(terminals)}")

        return "\n".join(lines)
