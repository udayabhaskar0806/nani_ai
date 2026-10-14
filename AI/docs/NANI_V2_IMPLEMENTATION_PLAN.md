# N.A.N.I. V2 — STEP-BY-STEP IMPLEMENTATION PLAN
**Engineering Execution Roadmap with Acceptance Gates, State-of-the-Art Milestones, and Rollback Strategies**

---

## 1. Master Build-vs-Reuse Decision Table

| Capability / Subsystem | Existing N.A.N.I. State | Evaluated External Candidates | Architectural Decision | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Task State Machine & Lifecycle** | Complete (Phase 1/1.1) | LangGraph, AutoGen, CrewAI, PydanticAI | **BUILT (In-House)** | Lightweight `TaskManager` with SQLite WAL persistence is faster, zero-bloat, and 100% transparent. |
| **Model Routing & Failover** | Complete (Phase 2) | LiteLLM, OpenRouter SDK | **BUILT (In-House)** | Capability-based router (`FAST`, `REASONING`, `CODING`, `VISION`, `RESEARCH`) with Gemini, Groq, and local Ollama failover. |
| **Linux Hardware & Telemetry** | Complete (Phase 2) | Linux MCP, UFO | **BUILT (In-House)** | Native `/sys/class`, `pactl`, `brightnessctl`, and `/proc/meminfo` telemetry directly integrated into tool registry. |
| **Shell & Execution Sandboxing** | Complete (Phase 1.1/2) | Docker, Podman, bubblewrap | **BUILT (bwrap Kernel Namespaces)** | Zero-container-overhead Linux namespace sandboxing with streaming byte limits, process reaping, and display pass-through. |
| **Dynamic Multi-Turn Reasoning CLI** | Complete (Phase 2) | Open Interpreter, ShellGPT | **BUILT (In-House Rich CLI)** | Dynamic ReAct tool loop with multi-turn memory, autonomous command execution, and display-agnostic terminal dispatch. |
| **AST Repository Mapping** | Phase 3 (Planned) | Aider `repomap`, Tree-sitter | **BUILD Native Tree-sitter AST Graph** | Incremental AST parsing and PageRank dependency graphs to map 100k+ line codebases within tight token budgets. |
| **Desktop Screen Vision & Input** | Phase 4 (Planned) | Anthropic Computer Use, OS-World | **BUILD Closed-Loop Multimodal Vision** | Coordinate-scaled visual perception via Gemini/Claude Vision, `mss` screen grabber, and `pyautogui`/`xdotool`. |
| **Dual-Tier Browser Automation** | Phase 5 (Planned) | Playwright, Browser Use, Stagehand | **USE Playwright + ADAPT Browser-Use** | Playwright handles deterministic DOM extraction; visual browser agent handles dynamic canvas/SPA interaction. |
| **Autonomous Benchmark Harness** | Phase 6 (Planned) | SWE-bench, GAIA, OS-World | **BUILD Standardized Harness** | Continuous benchmark verification against real-world GitHub pull requests and desktop tasks. |

---

## 2. Phased Development Roadmap

### Phase 0: Architecture Research & Open-Source Audit
* **Status:** **COMPLETE**
* **Delivered:** Dependency audit, risk matrix, system architecture specification.

---

### Phase 1 & 1.1: Core Runtime, State Machine & Hardened Sandbox
* **Status:** **COMPLETE (Commit `cdfc676`, 81 Tests Passing)**
* **Delivered:**
  - ACID SQLite transactional database (WAL mode, schema v3, CAS versioning).
  - Durable `ActionJournal` recording action start, observations, results, and approval gates.
  - Deterministic `Verifier` checking concrete exit codes, file content hashes, and state invariants.
  - Linux kernel namespace isolation (`bwrap`) with read-only root and bounded stream limits.
  - Process-group reaping (`_kill_pgid`) and monotonic execution timeouts.

---

### Phase 2: Live Model Providers, Autonomous ReAct CLI & Hardware Telemetry
* **Status:** **COMPLETE (Commit `c740f50`, 111 Tests Passing)**
* **Delivered:**
  - Multi-provider `ModelRouter` (Gemini `gemini-flash-lite-latest`, Groq, and local Ollama fallback).
  - Rich interactive terminal CLI with persistent multi-turn conversational history.
  - Dynamic AI ReAct loop executing native shell, web search, and file tools autonomously.
  - Desktop display pass-through (X11 & Wayland, D-Bus session bus, XDG session vars).
  - Dynamic AI `Planner` using `ModelCapability.REASONING` with deterministic offline fallback.
  - Native hardware telemetry tools (battery capacity, CPU/RAM load, audio volume, brightness).

---

### Phase 3: Deep AST Repository Dependency Mapping (Aider-Grade Code Intelligence)
* **Status:** **UPCOMING TARGET**
* **Objective:** Give N.A.N.I. human-expert code navigation across massive multi-thousand-file repositories without token blowup.
* **Key Components:**
  1. **Tree-Sitter Multi-Language AST Engine:**
     - Incremental parser for Python, C/C++, TypeScript, JavaScript, Go, Rust.
     - Extract definition nodes (classes, functions, methods, structs) and reference nodes (function calls, imports, type annotations).
  2. **PageRank Symbol Graph (`RepoMap`):**
     - Build a directed dependency graph where nodes are source files/symbols and edges are references.
     - Compute PageRank to identify central architectural components.
     - Dynamically generate a condensed, token-budgeted `<repo-map>` injected into model prompts.
  3. **Semantic Multi-File Diff Engine:**
     - Unified diff applicator with fuzzy line matching and rollback on syntax error.
* **Dependencies:** `tree-sitter`, language grammars (`tree-sitter-python`, `tree-sitter-c`).
* **Acceptance Gate:**
  - Point NANI to a multi-file 10,000+ line repository.
  - Prompt: *"Refactor logging across all worker modules to use structured JSON"*.
  - Verify NANI selects the exact relevant files and produces correct diffs without reading the entire codebase into context.

---

### Phase 4: Closed-Loop Multimodal GUI Vision (Computer Use & Pixel Grounding)
* **Status:** **UPCOMING TARGET**
* **Objective:** Enable N.A.N.I. to visually perceive, understand, and interact with arbitrary non-scriptable desktop applications.
* **Key Components:**
  1. **High-Speed Frame Capture:**
     - Multi-monitor screenshot pipeline via `mss` (X11) and `xdg-desktop-portal` (Wayland).
     - Intelligent downscaling maintaining readable typography and UI borders.
  2. **Multimodal Visual Coordinate Grounding:**
     - Send desktop visual frames to multimodal vision models (Gemini 2.5 Flash / Claude 3.5 Sonnet).
     - Ground natural language UI references (*"Click the green Run button"*, *"Select the third tab"*) to exact `(x, y)` screen pixels.
  3. **Closed-Loop Verification:**
     - Execute input $\to$ Capture subsequent frame $\to$ Verify visual change (e.g., menu opened, button toggled).
* **Dependencies:** `pillow`, `mss`, `pyautogui`, `xdotool`.
* **Acceptance Gate:**
  - Command: *"Open LibreOffice Writer, type 'NANI Automated Document', and click Save"*.
  - Verify the closed loop successfully completes via vision and mouse clicks.

---

### Phase 5: Dual-Tier Web Browser Automation (Playwright DOM + Visual Agent)
* **Status:** **PLANNED**
* **Objective:** Reliable autonomous web research, form submission, and data extraction.
* **Key Components:**
  1. **Tier 1 (Fast Deterministic DOM):** Playwright Chromium engine for structured web scraping and element interaction.
  2. **Tier 2 (Open-Ended Visual Agent):** Wrapped `browser-use` adapter for dynamic single-page applications and complex canvases where DOM selectors fail.
  3. **Safety Intercept:** Autonomous payment / checkout gating halting for human confirmation.
* **Dependencies:** `playwright`.

---

### Phase 6: Continuous Public Benchmarking Harness (SWE-bench & OS-World)
* **Status:** **PLANNED**
* **Objective:** Benchmark N.A.N.I. against world-standard software engineering and agentic benchmarks.
* **Key Components:**
  1. **SWE-bench Lite Test Runner:**
     - Standard test runner evaluating N.A.N.I.'s coding worker on 300 real GitHub issue PRs.
     - Automated patch verification running unit tests inside clean `bwrap` sandboxes.
  2. **OS-World Benchmark Adapter:**
     - Standard benchmark assessing desktop operating system automation accuracy.
* **Acceptance Gate:**
  - Automated benchmark report generating resolve rate %, token cost, and execution duration.

---

## 3. Rollback & Failsafe Guarantees

1. **Deterministic Verification Invariant:** No phase may weaken or bypass the independent [Verifier](file:///home/dell/Vibe%20Coding/AI/nani/core/verifier.py).
2. **Crash-Resilient State Machine:** Every action must continue to be journaled to SQLite before execution.
3. **Hardware Protection:** Low-level hardware drivers must retain clamping limits to prevent screen blackout or audio spikes.
