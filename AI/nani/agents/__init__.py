"""N.A.N.I. V2 — Specialized Autonomous Agent Workers
Exports BaseWorker, WorkerResult, CodingWorker, ComputerWorker, and ResearchWorker.
"""

from nani.agents.base import BaseWorker, WorkerResult
from nani.agents.coding.native import CodingWorker
from nani.agents.computer.native_linux import ComputerWorker
from nani.agents.research.native import ResearchWorker

__all__ = [
    "BaseWorker",
    "WorkerResult",
    "CodingWorker",
    "ComputerWorker",
    "ResearchWorker",
]
