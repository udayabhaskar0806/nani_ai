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
| **Human-First Grounding & Multi-Model Debate Council** | Phase 3 (Next Target) | Mixture of Agents (MoA), Socratic Debate, Multiagent Debate | **BUILD Native Council & Grounding** | Inspect local machine reality first (Dell Latitude telemetry/tools) $\to$ query 5 models $\to$ cross-examine & debate discrepancies until convergence. |
| **Autonomous Document & Web Learning Engine** | Phase 3 (Next Target) | Mem0, RAG frameworks, LlamaIndex | **BUILD Federated SQLite FTS5 Learner** | Free bulk ingestion via Llama 3.3 (Groq/Ollama) $\to$ Precision verification via Gemini $\to$ Store learned skills in SQLite for 5ms instant recall. |
| **AST Repository Mapping** | Phase 4 (Planned) | Aider `repomap`, Tree-sitter | **BUILD Native Tree-sitter AST Graph** | Incremental AST parsing and PageRank dependency graphs to map 100k+ line codebases within tight token budgets. |
| **Desktop Screen Vision & Input** | Phase 5 (Planned) | Anthropic Computer Use, OS-World | **BUILD Closed-Loop Multimodal Vision** | Coordinate-scaled visual perception via Gemini/Claude Vision, `mss` screen grabber, and `pyautogui`/`xdotool`. |
| **Dual-Tier Browser Automation** | Phase 6 (Planned) | Playwright, Browser Use, Stagehand | **USE Playwright + ADAPT Browser-Use** | Playwright handles deterministic DOM extraction; visual browser agent handles dynamic canvas/SPA interaction. |
| **Autonomous Benchmark Harness** | Phase 7 (Planned) | SWE-bench, GAIA, OS-World | **BUILD Standardized Harness** | Continuous benchmark verification against real-world GitHub pull requests and desktop tasks. |

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

### Phase 3: Human-First Grounding, Multi-Model Debate Council & Autonomous Learning Engine
* **Status:** 🎯 **IMMEDIATE TARGET (NEXT IMPLEMENTATION)**
* **Objective:** Transform N.A.N.I. into a self-upgrading intelligence that senses local machine reality first, deliberates across 5 AI models with cross-examination debate, reads documents/web articles, and caches verified skills for 5ms instant zero-token recall.

#### 3.1 Human-First Cognitive Grounding
- **Sensory Reality Inspection:** Before asking any AI model, NANI instantly inspects its local machine facts:
  - OS & kernel (`uname -r`, distro, desktop environment).
  - Hardware controllers (`/sys/class/backlight`, `/sys/class/power_supply`, `/proc/meminfo`, audio sinks).
  - Installed binary tools on `$PATH` (`which brightnessctl pactl xterm git`).
- **Grounded Prompt Injection:** Injects this concrete machine snapshot into model prompts so models never hallucinate abstract or incompatible commands.

#### 3.2 Socratic Multi-Model Debate Council & Re-Questioning Loop
- **5-Model Parallel Fan-Out:** Queries Gemini 2.5, Groq (Llama 3.3 70B), DeepSeek R1, OpenRouter/OpenAI, and local Ollama concurrently via `asyncio.gather`.
- **Contradiction Detection:** Detects when candidate answers disagree on commands, flags, or logic.
- **Cross-Examination Debate (Re-Questioning):**
  - Sends Model B's critique to Model A: *"Model B argues that command X fails on Wayland. Why did you choose X over Y? Defend or revise."*
  - Maximum 2-turn deliberation until convergence or concession.
- **Agreement Tallying & Arbiter:** Tally verified consensus and select the winning action.

#### 3.3 Autonomous Ingestion & Research Learning
- **Search Engine Harvester:** Queries DuckDuckGo and GitHub for technical guides, documentation, and tutorials.
- **Article & Web Page Reader:** Strips HTML/ads and converts online documentation into clean technical text.
- **Local Document Reader:** Universal reader for local PDFs, Markdown files, codebase documentation, and system `man` pages (`man <cmd>`).

#### 3.4 Federated Learning (Cost & Speed Optimization)
- **High-Speed Free Bulk Reading:** Large articles and documentation (thousands of words) are processed by **Llama 3.3 70B (Groq / Ollama)** at 800+ tokens/sec for free.
- **Precision Hardware Verification:** Extracted commands and steps are passed to **Gemini** to cross-check against Dell Latitude hardware and safety boundaries.

#### 3.5 Persistent Skill Store & Knowledge Base (SQLite FTS5)
- **Learned Skill Assimilation:** Every verified solution is stored in SQLite `skills` with intent triggers, machine preconditions, and executable templates.
- **Instant Recall (Zero Tokens):** Subsequent requests matching learned skills execute in 5 milliseconds directly on the host without querying external AI models.
- **Full-Text Knowledge Index:** SQLite FTS5 table for instant keyword search over all ingested articles and docs.

* **Dependencies:** `httpx`, `pypdf` (or lightweight pdf parser), `beautifulsoup4` (clean text parsing), SQLite FTS5.
* **Acceptance Gate:**
  1. Ask NANI to increase brightness $\to$ verifies machine state first $\to$ executes $\to$ saves skill. Second request executes in <10ms with zero model tokens.
  2. Ask NANI to read a URL or local doc $\to$ digests content via Llama $\to$ verifies facts via Gemini $\to$ answers accurately from memory.
  3. Prompt where models disagree $\to$ logs Round 2 cross-examination debate $\to$ resolves to single verified winner.

---

### Phase 4: Deep AST Repository Dependency Mapping (Aider-Grade Architecture)
* **Status:** **PLANNED**
* **Objective:** Give N.A.N.I. human-expert code navigation across massive multi-thousand-file repositories without token blowup.
* **Key Components:**
  1. **Tree-Sitter Multi-Language AST Engine:** Incremental parser for Python, C/C++, TypeScript, JavaScript, Go, Rust.
  2. **PageRank Symbol Graph (`RepoMap`):** Directed dependency graph of definitions and references; injects a dense, token-budgeted map of the entire codebase into prompts.
  3. **Semantic Multi-File Diff Engine:** Unified diff applicator with rollback on syntax/compiler error.
* **Dependencies:** `tree-sitter`.
* **Acceptance Gate:** Point NANI to a multi-file 10,000+ line repository $\to$ refactors cross-module functions without reading the entire repository into context.

---

### Phase 5: Closed-Loop Multimodal GUI Vision (Computer Use & Pixel Grounding)
* **Status:** **PLANNED**
* **Objective:** Enable N.A.N.I. to visually perceive, understand, and interact with arbitrary non-scriptable desktop applications.
* **Key Components:**
  1. **High-Speed Frame Capture:** Multi-monitor screenshot pipeline via `mss` (X11) and `xdg-desktop-portal` (Wayland).
  2. **Multimodal Visual Coordinate Grounding:** Send desktop visual frames to vision models (Gemini 2.5 Flash / Claude 3.5 Sonnet) mapping UI elements to exact `(x, y)` screen pixels.
  3. **Closed-Loop Verification:** Execute input $\to$ capture next frame $\to$ verify visual change before progressing.
* **Dependencies:** `pillow`, `mss`, `pyautogui`, `xdotool`.

---

### Phase 6: Dual-Tier Web Browser Automation (Playwright DOM + Visual Agent)
* **Status:** **PLANNED**
* **Objective:** Reliable autonomous web research, form submission, and data extraction.
* **Key Components:**
  1. **Tier 1 (Fast Deterministic DOM):** Playwright Chromium engine for structured web scraping and element interaction.
  2. **Tier 2 (Open-Ended Visual Agent):** Wrapped `browser-use` adapter for dynamic single-page applications and complex canvases where DOM selectors fail.
  3. **Safety Intercept:** Autonomous payment / checkout gating halting for human confirmation.
* **Dependencies:** `playwright`.

---

### Phase 7: Continuous Public Benchmarking Harness (SWE-bench & OS-World)
* **Status:** **PLANNED**
* **Objective:** Benchmark N.A.N.I. against world-standard software engineering and agentic benchmarks.
* **Key Components:**
  1. **SWE-bench Lite Test Runner:** Standard test runner evaluating N.A.N.I.'s coding worker on 300 real GitHub issue PRs inside clean `bwrap` sandboxes.
  2. **OS-World Benchmark Adapter:** Standard benchmark assessing desktop operating system automation accuracy.

---

## 3. Rollback & Failsafe Guarantees

1. **Deterministic Verification Invariant:** No phase may weaken or bypass the independent [Verifier](file:///home/dell/Vibe%20Coding/AI/nani/core/verifier.py).
2. **Crash-Resilient State Machine:** Every action must continue to be journaled to SQLite before execution.
3. **Hardware Protection:** Low-level hardware drivers must retain clamping limits to prevent screen blackout or audio spikes.
