"""N.A.N.I. V2 — Security Policy & Risk Evaluation
Enforces scoped autonomy, classifying operations into LOW, MEDIUM, and HIGH risk tiers.
"""

from typing import Any

from nani.core.task import RiskLevel


class SecurityPolicy:
    HIGH_RISK_KEYWORDS = [
        "payment",
        "checkout",
        "cvv",
        "credit card",
        "upi",
        "otp",
        "buy now",
        "rm -rf",
        "mkfs",
        "dd if=",
        ":(){ :|:& };:",
        "drop database",
        "shutdown",
        "send email",
        "post tweet",
        "send message",
        "linkedin msg",
        "git push",
    ]

    MEDIUM_RISK_KEYWORDS = [
        "write_file",
        "patch_file",
        "git commit",
        "kill",
        "systemctl restart",
        "pip install",
    ]

    @classmethod
    def evaluate_risk(cls, action_name: str, parameters: dict[str, Any]) -> RiskLevel:
        """Determines the risk tier of a planned action."""
        action_lower = action_name.lower()
        param_str = str(parameters).lower()

        # Check for High Risk triggers
        for kw in cls.HIGH_RISK_KEYWORDS:
            if kw in action_lower or kw in param_str:
                return RiskLevel.HIGH

        # Check for Medium Risk triggers
        for kw in cls.MEDIUM_RISK_KEYWORDS:
            if kw in action_lower or kw in param_str:
                return RiskLevel.MEDIUM

        return RiskLevel.LOW

    @classmethod
    def requires_human_approval(cls, risk_level: RiskLevel) -> bool:
        """Returns True if the operation must pause for human confirmation."""
        return risk_level == RiskLevel.HIGH
