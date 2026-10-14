"""N.A.N.I. V2 — System Hardware Telemetry & Control Native Tool
Provides structured inspection and control for audio volume, screen brightness, battery, and system resources.
Strict value clamping prevents hardware damage or unsafe states.
"""

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from nani.core.task import RiskLevel, WorkerCapability
from nani.tools.registry import BaseTool, ToolRegistry
from nani.tools.result import ToolResult


class SystemHardwareTool(BaseTool):
    """Inspects and controls Linux hardware parameters (audio, battery, brightness, resources)."""

    @property
    def name(self) -> str:
        return "system_hardware"

    @property
    def description(self) -> str:
        return "Inspects and controls hardware state: volume, battery, brightness, and system load."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    @property
    def capability(self) -> WorkerCapability:
        return WorkerCapability.SYSTEM

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "get_battery",
                        "get_system_resources",
                        "get_volume",
                        "set_volume",
                        "get_brightness",
                        "set_brightness",
                    ],
                },
                "value": {
                    "type": "integer",
                    "description": "Target percentage value (0-100) for set operations",
                },
            },
            "required": ["operation"],
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        operation = kwargs.get("operation")
        if not operation:
            return ToolResult.fail("Missing required parameter: 'operation'")

        op = str(operation).strip().lower()

        if op == "get_battery":
            return await self._get_battery()
        elif op == "get_system_resources":
            return await self._get_system_resources()
        elif op == "get_volume":
            return await self._get_volume()
        elif op == "set_volume":
            val = kwargs.get("value")
            if val is None:
                return ToolResult.fail("Missing required parameter 'value' for set_volume")
            return await self._set_volume(int(val))
        elif op == "get_brightness":
            return await self._get_brightness()
        elif op == "set_brightness":
            val = kwargs.get("value")
            if val is None:
                return ToolResult.fail("Missing required parameter 'value' for set_brightness")
            return await self._set_brightness(int(val))
        else:
            return ToolResult.fail(f"Unknown hardware operation: '{operation}'")

    async def _get_battery(self) -> ToolResult:
        try:
            power_supply = Path("/sys/class/power_supply")
            if not power_supply.exists():
                return ToolResult.ok(data={"battery_present": False, "status": "no_sysfs"})

            for bat in power_supply.glob("BAT*"):
                cap_file = bat / "capacity"
                stat_file = bat / "status"
                if cap_file.exists():
                    capacity = int(cap_file.read_text().strip())
                    status = stat_file.read_text().strip() if stat_file.exists() else "Unknown"
                    return ToolResult.ok(
                        data={
                            "battery_present": True,
                            "battery_name": bat.name,
                            "percent": capacity,
                            "status": status,
                            "on_ac": status.lower() == "charging" or status.lower() == "full",
                        }
                    )
            return ToolResult.ok(data={"battery_present": False, "on_ac": True})
        except Exception as e:
            return ToolResult.fail(f"Failed to read battery status: {e}")

    async def _get_system_resources(self) -> ToolResult:
        try:
            # CPU Load
            load1, load5, load15 = os.getloadavg()

            # RAM info from /proc/meminfo
            mem_total = 0
            mem_avail = 0
            if Path("/proc/meminfo").exists():
                for line in Path("/proc/meminfo").read_text().splitlines():
                    if line.startswith("MemTotal:"):
                        mem_total = int(line.split()[1]) // 1024
                    elif line.startswith("MemAvailable:"):
                        mem_avail = int(line.split()[1]) // 1024

            return ToolResult.ok(
                data={
                    "load_avg": [load1, load5, load15],
                    "ram_total_mb": mem_total,
                    "ram_available_mb": mem_avail,
                    "ram_used_mb": max(mem_total - mem_avail, 0),
                    "cpu_count": os.cpu_count() or 1,
                }
            )
        except Exception as e:
            return ToolResult.fail(f"Failed to read system resources: {e}")

    async def _get_volume(self) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "pactl",
                "get-sink-volume",
                "@DEFAULT_SINK@",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                match = re.search(r"(\d+)%", stdout.decode("utf-8", errors="replace"))
                if match:
                    return ToolResult.ok(data={"volume_percent": int(match.group(1))})
            return ToolResult.ok(data={"volume_percent": 50, "note": "Default/fallback level"})
        except Exception as e:
            return ToolResult.fail(f"Failed to query volume: {e}")

    async def _set_volume(self, value: int) -> ToolResult:
        # Clamped safety bounds: 0% to 100%
        clamped = max(0, min(value, 100))
        try:
            proc = await asyncio.create_subprocess_exec(
                "pactl",
                "set-sink-volume",
                "@DEFAULT_SINK@",
                f"{clamped}%",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                return ToolResult.fail(
                    f"pactl command failed: {stderr.decode('utf-8', errors='replace')}"
                )
            return ToolResult.ok(data={"volume_percent": clamped, "success": True})
        except Exception as e:
            return ToolResult.fail(f"Failed to set volume: {e}")

    async def _get_brightness(self) -> ToolResult:
        try:
            backlight_dir = Path("/sys/class/backlight")
            if backlight_dir.exists():
                for dev in backlight_dir.iterdir():
                    b_file = dev / "brightness"
                    m_file = dev / "max_brightness"
                    if b_file.exists() and m_file.exists():
                        cur = int(b_file.read_text().strip())
                        max_b = int(m_file.read_text().strip())
                        pct = int((cur / max_b) * 100) if max_b > 0 else 50
                        return ToolResult.ok(data={"brightness_percent": pct, "device": dev.name})
            return ToolResult.ok(
                data={"brightness_percent": 100, "note": "Hardware backlight not present"}
            )
        except Exception as e:
            return ToolResult.fail(f"Failed to query brightness: {e}")

    async def _set_brightness(self, value: int) -> ToolResult:
        # Clamped safety bounds: minimum 10% to prevent unreadable pitch-black screen, max 100%
        clamped = max(10, min(value, 100))
        try:
            # Try brightnessctl if available
            proc = await asyncio.create_subprocess_exec(
                "brightnessctl",
                "set",
                f"{clamped}%",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                return ToolResult.ok(data={"brightness_percent": clamped, "status": "applied"})
            return ToolResult.fail(
                f"brightnessctl command failed: {stderr.decode('utf-8', errors='replace')}"
            )
        except FileNotFoundError:
            return ToolResult.fail("brightnessctl utility not installed on this system.")
        except Exception as e:
            return ToolResult.fail(f"Failed to set brightness: {e}")


def register_hardware_tools(registry: ToolRegistry) -> None:
    """Registers system hardware inspection and control tool."""
    tool = SystemHardwareTool()
    if registry.exists(tool.name):
        registry.replace(tool)
    else:
        registry.register(tool)
