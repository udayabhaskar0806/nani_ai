# N.A.N.I. V2 — Personal AI Computer Operating Agent
**Neural Analytical Network Intelligence**
*Target OS: Ubuntu Linux (Dell Latitude i5-1155G7, 8GB RAM, X11 Display)*

---

## 1. What N.A.N.I. Is
N.A.N.I. is a persistent, general-purpose autonomous computer-operating agent designed to run natively on top of Ubuntu Linux. It accepts **high-level objectives** from its creator and autonomously derives intermediate steps, executes commands, inspects outcomes, and independently verifies task completion.

N.A.N.I. operates on a strict closed-loop control principle:
$$\text{GOAL} \longrightarrow \text{UNDERSTAND} \longrightarrow \text{OBSERVE} \longrightarrow \text{PLAN} \longrightarrow \text{ACT} \longrightarrow \text{OBSERVE RESULT} \longrightarrow \text{VERIFY} \longrightarrow \text{REPLAN} \longrightarrow \text{REPORT}$$

No action is assumed to have succeeded simply because a script was launched or a tool was called; every meaningful step must produce empirical, observable evidence.

## 2. What N.A.N.I. Is NOT
* **Not a Chatbot:** N.A.N.I. does not operate via chatty single-turn prompt-response conversations.
* **Not an API Wrapper:** N.A.N.I. is an active operating agent with hands on the machine.
* **Not a Brute-Force GUI Automator:** N.A.N.I. follows a strict tool hierarchy: direct APIs and filesystem commands are always preferred over slow, error-prone visual screen scrolling.
* **Not Tethered to a Single AI Provider:** N.A.N.I. routes work based on abstract **Capabilities** (`FAST`, `REASONING`, `CODING`, `VISION`, `RESEARCH`, `VERIFICATION`), with automated failover.

---

## 3. System Architecture Topology

```
                       USER
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
   TERMINAL CLI                  WEB DASHBOARD
 (Primary Dev / Debug)         (Visual Telemetry)
         │                             │
         └──────────────┬──────────────┘
                        │
                        ▼
                NANI ORCHESTRATOR
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
    TASK RUNTIME      MEMORY      WORLD STATE
  (State Machine &  (SQLite &     (System, Desktop,
   Action Journal)   Working)      Project State)
         │
         ▼
      PLANNER
         │
         ▼
  CAPABILITY ROUTER
         │
 ┌───────┼─────────────┬─────────────┬─────────────┐
 ▼       ▼             ▼             ▼             ▼
CODING  BROWSER   COMPUTER/DESKTOP  SYSTEM      RESEARCH
WORKER  WORKER        WORKER        WORKER       WORKER
 │       │             │             │             │
 ▼       ▼             ▼             ▼             ▼
[Adapters & Native Tools Operating against Ubuntu Linux OS]
```

---

## 4. Current Phase: Phase 1.1 — Runtime & Security Hardening
Following independent external audit of Phase 1, the core runtime has been hardened under **Phase 1.1**:

### Implemented Guarantees
* **Deterministic Core Runtime:** Deterministic task execution with zero external AI dependencies.
* **Trusted ExecutionContext:** Authoritative workspace boundary supplied by runtime; caller-controlled workspace overrides rejected.
* **Sandboxed Execution:** Linux user namespace isolation (`bwrap`) restricting writes strictly to authorized task workspace; fail-closed default.
* **Subprocess Supervision:** Bounded streaming stdout/stderr buffers preventing memory exhaustion, monotonic timeout enforcement, and clean process group reaping.
* **Read-Only Git Inspection:** Positive schema enforcement preventing branch mutation or configuration escapes.
* **Crash Resilience & Atomic Transitions:** Single-transaction state transitions with audit history; CAS protection against overwriting in-flight cancellations; uncertain non-idempotent crash recovery handling.
* **Secret Redaction:** Structured recursive dictionary and regex redaction at persistence and logging boundaries.
* **Task Final-Invariant Verification:** Re-verifies durable empirical file artifacts at task completion.
* **Task-Scoped Process Control:** Process termination strictly bounded to task-spawned processes.

### Explicitly Deferred (Phase 2+)
* Live model provider network integration (cloud LLMs).
* Browser automation (Playwright, Browser Use).
* Desktop GUI control (X11 capture, mouse, keyboard, window control).
* Autonomous coding agents (Aider, OpenHands integration).
* Vector databases and semantic memory.

---

## 5. Directory Structure

```
AI/
├── nani/
│   ├── core/                  # Orchestrator, TaskManager, Planner, Router, Verifier, Context
│   ├── models/                # Capability-based model router & provider abstractions
│   ├── agents/                # Decoupled worker adapters
│   ├── tools/                 # Native tools, path_utils, supervisor, registry
│   ├── computer/              # Native Linux screen capture, X11 windows, input
│   ├── memory/                # SQLite WAL database & ActionJournal
│   ├── security/              # Risk classification (LOW, MEDIUM, HIGH) & gates
│   ├── interfaces/            # Rich CLI console
│   ├── config.py              # Environment configuration
│   └── main.py                # Core entrypoint
├── tests/
│   ├── unit/                  # In-memory unit tests (contracts, tools, db, router)
│   ├── integration/           # Multi-worker pipeline and Phase 1.1 hardening tests
│   └── acceptance/            # Acceptance tests
├── data/                      # Local persistent SQLite databases (permissions 0600)
├── logs/                      # Structured JSONL event logs (secrets redacted)
├── pyproject.toml             # Modular dependency specification
└── README.md
```

---

## 6. Installation & Verification Commands

### Prerequisites
Ubuntu Linux 22.04+, Python 3.10+, Bubblewrap (`bwrap`).

```bash
cd "/home/dell/Vibe Coding/AI"

# 1. Create and activate clean virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install core development runtime
pip install -e ".[dev]"

# 3. Run complete test suite (81 tests)
pytest -v

# 4. Lint and Typecheck
ruff check .
ruff format --check .
mypy nani

# 5. Bootstrap CLI Runtime
python3 -m nani.main
```

---

## 7. Security Philosophy & Risk Tiers

* **LOW Risk (Fully Autonomous):** Reading files, listing directories, read-only Git inspection, verifying exit codes.
* **MEDIUM Risk (Autonomous within Sandbox):** Writing/patching project source files within workspace, supervised subprocess execution.
* **HIGH Risk (Blocked — Requires Creator Confirmation):** Financial checkout, entering card/UPI details, sending external communications, deleting directories, pushing to remote Git branches. Execution halts in `WAITING` state until explicit confirmation is provided.

---

## 8. Historical Reference
The working V1.2 prototype has been permanently preserved in Git:
- **Git Branch:** `archive/nani-v1.2`
- **Git Tag:** `nani-v1.2-final`
- **Commit:** `eaae6ee22d992cdbcdbfc3dcd46aac9bccff193b`
