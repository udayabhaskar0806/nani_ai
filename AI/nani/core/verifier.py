"""N.A.N.I. V2 — Minimal Evidence-Based Verifier
Validates execution results against strict empirical criteria (exit code, file existence, content match).
No LLM calls, strictly deterministic evidence evaluation and task final-invariant checking.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from nani.core.task import PlanStep, StepStatus, Task
from nani.tools.path_utils import resolve_safe_path
from nani.tools.result import ToolResult


class VerificationResult(BaseModel):
    verified: bool
    criteria_checked: list[dict[str, Any]] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class Verifier:
    """Strictly deterministic verifier inspecting concrete files, exit codes, and output buffers."""

    def verify_step(
        self,
        step: PlanStep,
        result: ToolResult | None = None,
        workspace_path: Path | str | None = None,
    ) -> VerificationResult:
        """Evaluates empirical evidence against the step's verification criteria."""
        ws = Path(workspace_path or Path.cwd()).resolve()
        criteria = step.verification or {}
        checked: list[dict[str, Any]] = []
        failures: list[str] = []
        evidence: dict[str, Any] = {}

        # 1. Base ToolResult Success Check
        if result is not None:
            evidence["result_success"] = result.success
            evidence["exit_code"] = result.exit_code
            evidence["duration_ms"] = result.duration_ms
            if not result.success and criteria.get("type") != "allow_failure":
                failures.append(f"Tool execution failed: {result.error or result.stderr}")

        if not criteria:
            is_ok = len(failures) == 0 and (result is not None and result.success)
            if not is_ok and result is None:
                failures.append("No execution result or empirical verification criteria provided.")
            return VerificationResult(
                verified=is_ok,
                criteria_checked=[{"type": "default_success", "passed": is_ok}],
                failure_reasons=failures,
                evidence=evidence,
            )

        # Normalize criteria into a list of check dicts
        criteria_list: list[dict[str, Any]]
        if "checks" in criteria and isinstance(criteria["checks"], list):
            criteria_list = criteria["checks"]
        else:
            criteria_list = [criteria]

        for crit in criteria_list:
            crit_type = crit.get("type")
            passed = False

            if crit_type == "tool_success":
                passed = result is not None and result.success is True
                if not passed:
                    failures.append("Expected tool execution to succeed.")

            elif crit_type == "exit_code":
                expected_code = crit.get("expected", 0)
                actual_code = result.exit_code if result else None
                passed = actual_code == expected_code
                if not passed:
                    failures.append(
                        f"Exit code mismatch: expected {expected_code}, got {actual_code}."
                    )

            elif crit_type == "file_exists":
                rel_path = crit.get("path", "")
                try:
                    target = resolve_safe_path(rel_path, ws)
                    passed = target.exists()
                    evidence[f"file_exists:{rel_path}"] = passed
                    if not passed:
                        failures.append(f"Expected file does not exist: {rel_path}")
                except Exception as e:
                    failures.append(f"Path resolution error for '{rel_path}': {e}")

            elif crit_type == "file_content":
                rel_path = crit.get("path", "")
                expected_content = crit.get("expected_content")
                substring = crit.get("substring")
                try:
                    target = resolve_safe_path(rel_path, ws)
                    if not target.is_file():
                        failures.append(
                            f"Expected file for content verification not found: {rel_path}"
                        )
                    else:
                        content = target.read_text(encoding="utf-8", errors="replace")
                        evidence[f"file_length:{rel_path}"] = len(content)
                        if expected_content is not None:
                            passed = content == expected_content
                            if not passed:
                                failures.append(
                                    f"File content mismatch in {rel_path}: content did not match expected."
                                )
                        elif substring is not None:
                            passed = substring in content
                            if not passed:
                                failures.append(
                                    f"File {rel_path} does not contain expected substring: {substring}"
                                )
                        else:
                            passed = True
                except Exception as e:
                    failures.append(f"File content verification error for '{rel_path}': {e}")

            elif crit_type == "stdout_contains":
                expected_text = crit.get("expected", "")
                actual_stdout = result.stdout if result else ""
                passed = expected_text in actual_stdout
                evidence["stdout_matched"] = passed
                if not passed:
                    failures.append(
                        f"Expected stdout to contain '{expected_text}', got: {actual_stdout[:200]}"
                    )

            elif crit_type == "stderr_empty":
                actual_stderr = result.stderr.strip() if result else ""
                passed = actual_stderr == ""
                if not passed:
                    failures.append(f"Expected empty stderr, got: {actual_stderr[:200]}")

            else:
                failures.append(f"Unknown verification criteria type: '{crit_type}'")

            checked.append({"criteria": crit, "passed": passed})

        all_passed = len(failures) == 0
        return VerificationResult(
            verified=all_passed,
            criteria_checked=checked,
            failure_reasons=failures,
            evidence=evidence,
        )

    def verify_task(
        self, task: Task, workspace_path: Path | str | None = None
    ) -> VerificationResult:
        """Verifies that all plan steps are COMPLETED and that task-level final invariants hold."""
        failures: list[str] = []
        checked: list[dict[str, Any]] = []

        if not task.plan:
            return VerificationResult(
                verified=False,
                failure_reasons=["Task plan is empty."],
            )

        ws = Path(workspace_path or task.workspace_path).resolve()

        # 1. Step completion check
        for step in task.plan:
            step_ok = step.status == StepStatus.COMPLETED
            if not step_ok:
                failures.append(
                    f"Step {step.order} ('{step.description}') status is {step.status.value}"
                )
            checked.append({"step_id": step.step_id, "order": step.order, "passed": step_ok})

        # 2. Re-verify durable file invariants: if a later action invalidated an artifact, fail!
        for step in task.plan:
            crit = step.verification or {}
            crit_type = crit.get("type")
            if crit_type in ("file_content", "file_exists"):
                invariant_res = self.verify_step(step, workspace_path=ws)
                if not invariant_res.verified:
                    failures.append(
                        f"Final artifact invariant invalidated for step {step.order}: {'; '.join(invariant_res.failure_reasons)}"
                    )
                    checked.append({"step_id": step.step_id, "final_invariant_passed": False})

        return VerificationResult(
            verified=len(failures) == 0,
            criteria_checked=checked,
            failure_reasons=failures,
            evidence={
                "completed_steps": len([s for s in task.plan if s.status == StepStatus.COMPLETED]),
                "workspace": str(ws),
            },
        )
