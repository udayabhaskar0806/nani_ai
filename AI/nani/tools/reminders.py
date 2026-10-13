"""N.A.N.I. Reminders & Scheduler Engine
Schedules personal reminders, triggers desktop notifications on Linux, and tracks pending tasks.
"""

import shutil
import subprocess
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from nani.core.memory import MemoryStore

class ReminderManager:
    def __init__(self, memory: MemoryStore):
        self.memory = memory
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self.has_notify_send = shutil.which("notify-send") is not None

    def trigger_alert(self, reminder_id: int, task: str):
        """Dispatches an alert when a reminder fires."""
        # 1. Update database
        self.memory.mark_reminder_done(reminder_id)

        # 2. Linux Desktop Notification via notify-send
        if self.has_notify_send:
            try:
                subprocess.run(
                    ["notify-send", "-u", "critical", "-a", "N.A.N.I.", "⚡ N.A.N.I. Reminder", task],
                    check=False
                )
            except Exception:
                pass

        # 3. Print bell/alert to terminal
        print(f"\n\a🔔 [N.A.N.I. ALERT]: {task} (Triggered at {datetime.now().strftime('%H:%M:%S')})\n> ", end="")

    def schedule_in_minutes(self, task: str, minutes: int) -> Dict[str, Any]:
        """Schedules a task X minutes from now."""
        trigger_time = datetime.now() + timedelta(minutes=minutes)
        trigger_iso = trigger_time.isoformat()
        
        rem_id = self.memory.add_reminder(task, trigger_iso)
        self.scheduler.add_job(
            self.trigger_alert,
            'date',
            run_date=trigger_time,
            args=[rem_id, task],
            id=f"rem_{rem_id}"
        )

        return {
            "id": rem_id,
            "task": task,
            "trigger_time": trigger_time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "scheduled"
        }

    def list_reminders(self) -> List[Dict[str, Any]]:
        return self.memory.get_pending_reminders()

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
