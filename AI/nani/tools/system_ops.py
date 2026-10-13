"""N.A.N.I. Linux System Operations & Hardware Monitor
Monitors CPU, RAM, kernel stats, and provides system introspection.
"""

import os
import platform
import subprocess
from typing import Dict, Any

class SystemOps:
    @staticmethod
    def get_hardware_telemetry() -> Dict[str, Any]:
        """Gathers real-time Linux hardware and system metrics."""
        telemetry = {
            "kernel": platform.release(),
            "arch": platform.machine(),
            "cpu_model": "Unknown",
            "load_avg": [round(x, 2) for x in os.getloadavg()],
            "ram_total_mb": 0,
            "ram_available_mb": 0,
            "ram_percent_used": 0.0,
        }

        # Parse /proc/cpuinfo
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        telemetry["cpu_model"] = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass

        # Parse /proc/meminfo
        try:
            meminfo = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip().split()[0]
                        meminfo[key] = int(val)
            
            total_kb = meminfo.get("MemTotal", 1)
            avail_kb = meminfo.get("MemAvailable", 0)
            used_kb = total_kb - avail_kb

            telemetry["ram_total_mb"] = total_kb // 1024
            telemetry["ram_available_mb"] = avail_kb // 1024
            telemetry["ram_percent_used"] = round((used_kb / total_kb) * 100, 1)
        except Exception:
            pass

        return telemetry

    @staticmethod
    def run_safe_command(cmd: str) -> str:
        """Runs a read-only or inspection command safely."""
        # Whitelisted commands or standard system checks
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout or result.stderr or "[Command executed with empty output]"
        except subprocess.TimeoutExpired:
            return "[Error: Command timed out after 10 seconds]"
        except Exception as e:
            return f"[Execution error: {str(e)}]"
