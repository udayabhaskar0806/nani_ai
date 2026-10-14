"""N.A.N.I. V2 — Native Linux Desktop Computer Worker
Performs closed-loop physical desktop actions: screen capture, window focus, mouse, and keyboard interaction.
"""

from typing import Any

from nani.agents.base import BaseWorker, WorkerResult
from nani.computer.input import DesktopInput
from nani.computer.screen import ScreenCapture
from nani.computer.windows import WindowManager
from nani.core.state import WorldState
from nani.core.task import Observation, PlanStep, WorkerCapability


class ComputerWorker(BaseWorker):
    """Native Linux computer-use worker interacting with the desktop GUI via X11."""

    def __init__(
        self,
        screen: ScreenCapture | None = None,
        windows: WindowManager | None = None,
        desktop_input: DesktopInput | None = None,
    ) -> None:
        self.screen = screen or ScreenCapture()
        self.windows = windows or WindowManager()
        self.desktop_input = desktop_input or DesktopInput()

    @property
    def capability_name(self) -> WorkerCapability:
        return WorkerCapability.COMPUTER

    async def can_handle(self, step: PlanStep, world_state: WorldState) -> bool:
        if step.capability_required == WorkerCapability.COMPUTER:
            return True
        desc = step.description.lower()
        return any(
            k in desc
            for k in [
                "desktop",
                "screen",
                "window",
                "click",
                "type on keyboard",
                "focus",
                "mouse",
                "screenshot",
            ]
        )

    async def execute(self, step: PlanStep, world_state: WorldState) -> WorkerResult:
        desc = step.description.lower()
        params: dict[str, Any] = {}
        if step.actions:
            params = step.actions[0].parameters

        observations: list[Observation] = []

        # 1. Window focus / search
        if "focus" in desc or "window" in desc and "focus" in params.get("operation", ""):
            target_title = str(params.get("title") or params.get("target") or step.description)
            success = await self.windows.focus_window(target_title)
            active_win = await self.windows.get_active_window_title()
            obs = Observation(
                source="window_manager",
                content=f"Focus window '{target_title}': {'success' if success else 'not found'}. Current active window: '{active_win}'.",
                metadata={"active_window": active_win, "focus_success": success},
            )
            observations.append(obs)
            return WorkerResult.ok(
                summary=f"Focused window matching '{target_title}' (Current: {active_win})",
                observations=observations,
            )

        # 2. Typing
        if "type" in desc or "write text" in desc or params.get("operation") == "type":
            text = str(params.get("text") or params.get("content") or "")
            res = self.desktop_input.type_text(text)
            obs = Observation(
                source="keyboard",
                content=f"Typed {res.get('chars')} characters into active window.",
                metadata=res,
            )
            observations.append(obs)
            return WorkerResult.ok(
                summary=f"Typed text ({len(text)} characters) into active window.",
                observations=observations,
            )

        # 3. Mouse Click
        if "click" in desc or params.get("operation") == "click":
            x = int(params.get("x", 500))
            y = int(params.get("y", 500))
            button = str(params.get("button", "left"))
            res = self.desktop_input.click_at(x, y, button=button)
            obs = Observation(
                source="mouse",
                content=f"Clicked at ({x}, {y}) with {button} button.",
                metadata=res,
            )
            observations.append(obs)
            return WorkerResult.ok(
                summary=f"Clicked at coordinates ({x}, {y})",
                observations=observations,
            )

        # 4. Default / Fallback: Capture frame observation
        frame_data = self.screen.capture_frame()
        active_win = await self.windows.get_active_window_title()
        obs = Observation(
            source="screen_vision",
            content=f"Captured desktop screenshot ({frame_data['width']}x{frame_data['height']}). Active window: '{active_win}'.",
            metadata={
                "width": frame_data["width"],
                "height": frame_data["height"],
                "active_window": active_win,
            },
        )
        observations.append(obs)
        return WorkerResult.ok(
            summary=f"Captured desktop state: resolution {frame_data['width']}x{frame_data['height']}, active window '{active_win}'.",
            observations=observations,
        )
