"""N.A.N.I. Full-System Autonomous Agent
Gives N.A.N.I. full hands-on access to execute shell commands, control hardware,
inspect files, and operate the Linux laptop via natural language.
"""

import json
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

from nani.tools.laptop_control import LaptopController
from nani.tools.system_ops import SystemOps
from nani.tools.reminders import ReminderManager
from nani.tools.github_radar import GitHubRadar
from nani.tools.researcher import DeepResearcher
from nani.tools.screen_vision import ScreenVision
from nani.core.memory import MemoryStore

class SystemAgent:
    def __init__(self, memory: MemoryStore, engine):
        self.memory = memory
        self.engine = engine
        self.laptop = LaptopController()
        self.system_ops = SystemOps()
        self.reminders = ReminderManager(memory=self.memory)
        self.radar = GitHubRadar()
        self.researcher = DeepResearcher()
        self.vision = ScreenVision(engine=self.engine)

    def get_tool_definitions(self) -> str:
        """Returns the available system actions for the LLM."""
        return """
You have direct autonomous control over this Linux laptop.
When the user asks you to inspect, control, build, or fix something, you can execute actions by outputting an ACTION block in this exact format:

<<<ACTION
{
  "tool": "tool_name",
  "args": { ... }
}
>>>

Available Tools:
1. "run_shell": Run any bash command on the Linux laptop.
   args: {"cmd": "command string"}
2. "laptop_control": Control physical laptop hardware.
   args: {"action": "volume|mute|brightness|lock|screenshot|battery", "value": optional_number_or_str}
3. "file_read": Read content of a file on disk.
   args: {"path": "/path/to/file"}
4. "file_write": Write or create a file on disk.
   args: {"path": "/path/to/file", "content": "file content"}
5. "set_reminder": Schedule a future reminder.
   args: {"minutes": int, "task": "task description"}
6. "github_radar": Scan or inspect AI repositories.
   args: {"action": "scan|inspect", "target": "query or owner/repo"}
7. "deep_research": Run first-principles technical research.
   args: {"topic": "search topic"}
8. "see_screen": Visually analyze what is on the laptop screen right now using computer vision.
   args: {"question": "What is currently on my screen? (or inspect code/error/window)"}
9. "gui_action": Click or type anywhere on the screen.
   args: {"action": "click|type|key", "x": optional_int, "y": optional_int, "text": optional_str, "key": optional_str}

Rule: If a user asks you to do something (e.g., "what's on my screen?", "check my battery", "mute volume", "show git status", "click here"), EMIT THE ACTION BLOCK IMMEDIATELY. Then summarize the result clearly.
"""

    def execute_action(self, tool: str, args: Dict[str, Any]) -> str:
        """Executes the requested tool on the Linux laptop and returns the output."""
        try:
            if tool == "run_shell":
                cmd = args.get("cmd", "")
                if not cmd:
                    return "Error: Empty command."
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                stdout = res.stdout.strip()
                stderr = res.stderr.strip()
                output = stdout if stdout else (stderr if stderr else "[Command executed with 0 output]")
                return f"[Shell Execution (Exit {res.returncode})]:\n{output}"

            elif tool == "laptop_control":
                action = args.get("action")
                val = args.get("value")
                if action == "volume":
                    return self.laptop.set_volume(int(val) if val is not None else 50)
                elif action == "mute":
                    return self.laptop.toggle_mute()
                elif action == "brightness":
                    return self.laptop.set_brightness(int(val) if val is not None else 70)
                elif action == "lock":
                    return self.laptop.lock_screen()
                elif action == "screenshot":
                    shot = self.laptop.capture_screenshot()
                    return f"Screenshot saved at: {shot['path']}" if shot["success"] else f"Failed: {shot.get('error')}"
                elif action == "battery":
                    b = self.laptop.get_battery_info()
                    return f"Battery: {b['percentage']}% ({b['status']}), AC plugged in: {b['on_ac']}"
                return f"Unknown laptop action: {action}"

            elif tool == "file_read":
                path = Path(args.get("path", "")).expanduser()
                if not path.exists():
                    return f"Error: File '{path}' does not exist."
                return f"[File: {path}]:\n" + path.read_text(errors="replace")[:4000]

            elif tool == "file_write":
                path = Path(args.get("path", "")).expanduser()
                path.parent.mkdir(parents=True, exist_ok=True)
                content = args.get("content", "")
                path.write_text(content)
                return f"Successfully wrote {len(content)} bytes to '{path}'."

            elif tool == "set_reminder":
                mins = int(args.get("minutes", 10))
                task = args.get("task", "Reminder")
                job = self.reminders.schedule_in_minutes(task, mins)
                return f"Reminder set for {job['trigger_time']}: '{task}'"

            elif tool == "github_radar":
                act = args.get("action", "scan")
                target = args.get("target", "topic:ai")
                if act == "inspect":
                    return self.radar.analyze_repo(target, self.engine)
                else:
                    repos = self.radar.scan_trending_ai(target, limit=4)
                    return "\n".join([f"- {r.get('name')} ⭐ {r.get('stars')}: {r.get('description')}" for r in repos])

            elif tool == "deep_research":
                topic = args.get("topic", "")
                return self.researcher.research(topic, self.engine)

            elif tool == "see_screen":
                q = args.get("question", "What is currently happening on my screen?")
                return self.vision.see_and_analyze(q)

            elif tool == "gui_action":
                act = args.get("action", "")
                if act == "click":
                    return self.vision.click_at(int(args.get("x", 0)), int(args.get("y", 0)))
                elif act == "type":
                    return self.vision.type_text(args.get("text", ""))
                elif act == "key":
                    return self.vision.press_key(args.get("key", "enter"))
                return f"Unknown GUI action: '{act}'"

            else:
                return f"Unknown tool: '{tool}'"

        except Exception as e:
            return f"Action execution error: {str(e)}"

    def process_request(self, user_prompt: str) -> str:
        """Processes user input, executes any requested laptop tools, and synthesizes the response."""
        p_clean = user_prompt.strip().lower()

        # Immediate direct shortcut matching for common system triggers
        if p_clean in ("/see", "see screen", "look at my screen", "what is on my screen"):
            return self.vision.see_and_analyze("What is currently on my screen?")
        elif p_clean in ("/battery", "battery", "battery status", "check battery"):
            b = self.laptop.get_battery_info()
            ac_str = "Plugged into AC" if b['on_ac'] else "Running on Battery"
            return f"🔋 Battery: {b['percentage']}% ({b['status']}) | 🔌 {ac_str}"
        elif p_clean in ("/lock", "lock screen", "lock laptop"):
            return f"🔒 {self.laptop.lock_screen()}"
        elif p_clean in ("/screenshot", "take screenshot"):
            res = self.laptop.capture_screenshot()
            return f"📸 Screenshot saved: {res['path']}" if res["success"] else f"❌ {res.get('error')}"

        system_instruction = self.get_tool_definitions()
        
        # 1. Ask model for plan / action
        response = self.engine.generate(user_prompt, system_override=system_instruction)
        if isinstance(response, list):
            response = "".join(response)
        response = str(response)
        
        # 2. Check if an ACTION block was generated
        action_match = re.search(r"<<<ACTION\s*(\{.*?\})\s*>>>", response, re.DOTALL)
        if not action_match:
            return response

        # 3. Parse and execute the action
        action_json_str = action_match.group(1)
        try:
            action_data = json.loads(action_json_str)
            tool_name = action_data.get("tool")
            args = action_data.get("args", {})
            
            tool_result = self.execute_action(tool_name, args)
            
            # 4. Give the model the execution result to formulate its final reply
            final_prompt = f"""User request: "{user_prompt}"
Executed Tool: {tool_name} with arguments {json.dumps(args)}
Tool Execution Result:
{tool_result}

Provide your final, concise, first-principles status update to your creator. State clearly what was done."""
            
            final_response = self.engine.generate(final_prompt)
            return f"{response.split('<<<ACTION')[0].strip()}\n\n[⚡ N.A.N.I. System Action: {tool_name}]\n{tool_result}\n\n{final_response}".strip()

        except Exception as e:
            return f"{response}\n\n[Action Error]: Could not parse/execute action: {str(e)}"
