"""N.A.N.I. V2 — Sudo Privilege and Autonomous Execution Manager
Handles in-session volatile credential storage, validation via sudo -S,
and optional permanent passwordless configuration (/etc/sudoers.d/nani-sudo).
"""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

from nani.core.grounding import MachineGrounding


class SudoManager:
    """Manages sudo credentials and privilege elevation safely and autonomously."""

    _session_password: str | None = None

    @classmethod
    def set_session_password(cls, password: str | None) -> None:
        """Stores sudo password in process memory only and updates grounding."""
        cls._session_password = password
        if password:
            MachineGrounding.override_sudo_status(True)
        else:
            MachineGrounding.override_sudo_status(None)

    @classmethod
    def get_session_password(cls) -> str | None:
        """Returns the in-session password if available."""
        return cls._session_password

    @classmethod
    def is_authorized(cls) -> bool:
        """Returns True if autonomous sudo is currently usable (passwordless or in-session)."""
        if cls._session_password:
            return True
        return MachineGrounding.check_sudo_privilege()

    @classmethod
    def clear(cls) -> None:
        """Purges session password from memory and resets grounding override."""
        cls._session_password = None
        MachineGrounding.override_sudo_status(None)

    @classmethod
    async def verify_password(cls, password: str) -> bool:
        """Validates sudo password by running sudo -S -k true non-interactively."""
        if not password:
            return False

        def _run_verify() -> bool:
            try:
                res = subprocess.run(
                    ["sudo", "-S", "-k", "true"],
                    input=(password + "\n").encode(),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=5,
                )
                return res.returncode == 0
            except Exception:
                return False

        return await asyncio.to_thread(_run_verify)

    @classmethod
    async def authorize(cls, password: str) -> bool:
        """Verifies and registers in-session sudo credentials."""
        ok = await cls.verify_password(password)
        if ok:
            cls.set_session_password(password)
            return True
        return False

    @classmethod
    async def configure_permanent_sudo(cls, password: str | None = None) -> tuple[bool, str]:
        """Configures /etc/sudoers.d/nani-sudo for permanent autonomous execution.
        Uses visudo -cf to validate syntax strictly before committing.
        """
        pwd = password or cls.get_session_password()
        current_user = os.environ.get("USER", "dell")
        sudoers_line = f"{current_user} ALL=(ALL) NOPASSWD: ALL\n"
        sudoers_target = "/etc/sudoers.d/nani-sudo"

        def _do_config() -> tuple[bool, str]:
            visudo_bin = shutil.which("visudo") or "/usr/sbin/visudo"
            if not Path(visudo_bin).exists():
                return False, "visudo binary not found on host machine"

            # Prepare command to write and test sudoers entry
            script = (
                f"echo '{sudoers_line.strip()}' > {sudoers_target} && "
                f"chmod 0440 {sudoers_target} && "
                f"{visudo_bin} -cf {sudoers_target}"
            )

            try:
                if pwd:
                    res = subprocess.run(
                        ["sudo", "-S", "sh", "-c", script],
                        input=(pwd + "\n").encode(),
                        capture_output=True,
                        timeout=10,
                    )
                else:
                    res = subprocess.run(
                        ["sudo", "-n", "sh", "-c", script],
                        capture_output=True,
                        timeout=10,
                    )

                if res.returncode == 0:
                    MachineGrounding.override_sudo_status(True)
                    return True, f"Permanent autonomous sudo configured for user '{current_user}'."
                else:
                    err = res.stderr.decode().strip()
                    # Cleanup corrupt file if needed
                    cleanup_cmd = f"rm -f {sudoers_target}"
                    if pwd:
                        subprocess.run(
                            ["sudo", "-S", "sh", "-c", cleanup_cmd],
                            input=(pwd + "\n").encode(),
                            capture_output=True,
                        )
                    return False, f"Failed to configure sudoers: {err}"
            except Exception as exc:
                return False, f"Error configuring permanent sudo: {exc}"

        return await asyncio.to_thread(_do_config)

    @classmethod
    async def remove_permanent_sudo(cls, password: str | None = None) -> tuple[bool, str]:
        """Removes /etc/sudoers.d/nani-sudo."""
        pwd = password or cls.get_session_password()
        sudoers_target = "/etc/sudoers.d/nani-sudo"

        def _do_remove() -> tuple[bool, str]:
            try:
                cmd = (
                    ["sudo", "-S", "rm", "-f", sudoers_target]
                    if pwd
                    else ["sudo", "-n", "rm", "-f", sudoers_target]
                )
                inp = (pwd + "\n").encode() if pwd else None
                res = subprocess.run(cmd, input=inp, capture_output=True, timeout=5)
                if res.returncode == 0:
                    cls.clear()
                    return True, "Permanent sudoers configuration removed."
                return False, res.stderr.decode().strip()
            except Exception as exc:
                return False, str(exc)

        return await asyncio.to_thread(_do_remove)
