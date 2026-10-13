"""N.A.N.I. V2 — Security Policy & Risk Evaluation
Combines tool-declared base risk, operation semantics, resource targets, and defense-in-depth command inspection.
"""

from typing import Any

from nani.core.task import RiskLevel


class SecurityPolicy:
    # Explicit high-risk actions and targets
    HIGH_RISK_OPERATIONS = {
        "payment_submit",
        "checkout",
        "enter_upi",
        "send_external_message",
        "delete_directory",
        "git_push",
        "modify_system_auth",
        "format_disk",
    }

    # High-risk targets and destructive shell patterns (Defense-in-Depth)
    HIGH_RISK_PATTERNS = [
        "rm -rf /",
        "rm -rf /*",
        "mkfs",
        "dd if=",
        ":(){ :|:& };:",
        "> /dev/sda",
        "drop database",
        "shutdown -h",
        "reboot",
        "payment",
        "checkout",
        "cvv",
        "credit_card",
        "upi_pin",
        "otp",
    ]

    # Explicit medium-risk actions
    MEDIUM_RISK_OPERATIONS = {
        "write_file",
        "patch_file",
        "git_commit",
        "kill_process",
        "restart_service",
    }

    @classmethod
    def evaluate_risk(
        cls,
        tool_name: str,
        parameters: dict[str, Any] | None = None,
        base_risk: RiskLevel | None = None,
    ) -> RiskLevel:
        """Determines effective risk level using tool base risk, action semantics, and resource inspection."""
        params = parameters or {}
        tool_lower = tool_name.lower()
        param_str = str(params).lower()

        # 1. Check for critical destructive / financial triggers (Escalates unconditionally to HIGH)
        for pattern in cls.HIGH_RISK_PATTERNS:
            if pattern in tool_lower or pattern in param_str:
                return RiskLevel.HIGH

        if tool_lower in cls.HIGH_RISK_OPERATIONS:
            return RiskLevel.HIGH

        # 2. Check tool-declared base risk if provided
        if base_risk == RiskLevel.HIGH:
            return RiskLevel.HIGH

        # 3. Target resource inspection (e.g. writing into system directories escalates to HIGH)
        target_path = str(params.get("path", "")).lower()
        if target_path and any(
            target_path.startswith(p) for p in ["/etc", "/boot", "/sys", "/usr", "/bin", "/sbin"]
        ):
            return RiskLevel.HIGH

        # 4. Check for medium-risk operations
        if tool_lower in cls.MEDIUM_RISK_OPERATIONS or base_risk == RiskLevel.MEDIUM:
            return RiskLevel.MEDIUM

        return base_risk or RiskLevel.LOW

    @classmethod
    def requires_human_approval(cls, risk_level: RiskLevel) -> bool:
        """Determines if execution must halt for explicit human creator confirmation."""
        return risk_level == RiskLevel.HIGH
