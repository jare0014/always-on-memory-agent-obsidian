# Development Log: Always-On Memory Agent

A chronological log of milestones, issues, and resolutions during the development and stabilization of the Always-On Memory Agent.

---

## 2026-07-21: Project Initialization & API Key Integration
- **Milestone:** Sparse checked out and extracted the `always-on-memory-agent` codebase.
- **Milestone:** Initialized Python virtualenv and installed ADK/dependencies.
- **Milestone:** Connected to the Windows Credential Manager (`keyring`) to securely pull the developer's Gemini API Key (`gemini:antigravity`), writing it to `.env` to prevent manual configuration.
- **Issue (Windows Asyncio):** Python's `asyncio` threw a `NotImplementedError` when attempting to register Unix-like signal handlers (`add_signal_handler`) on Windows.
- **Resolution:** Wrapped signal registration in a `try...except NotImplementedError` block to allow cross-platform execution on Windows.

## 2026-07-21: Local Model Support & Loop Troubleshooting
- **Milestone:** Integrated `litellm` and pointed the backend to a local Ollama server running `qwen2.5:7b` / `gemma3:4b`.
- **Issue (Infinite Tool-Calling Loop):** The local Qwen model would repeatedly call `store_memory` in a loop, ignoring the tool response history and creating duplicate rows in the SQLite database.
- **Resolution:**
  1. Updated system instructions to explicitly command the agent to call the storage tool exactly once.
  2. Implemented database-level checks in `store_memory` and `store_consolidation` to skip duplicate summaries, making the storage layer completely resilient to LLM loop behavior.

## 2026-07-21: Specialist Direct Runner Refactoring
- **Issue (Multi-Agent Delegation Overhead):** The ADK multi-agent orchestrator was too complex for smaller local models (Qwen 2.5 7B), causing tool hallucinations (e.g. attempting to run `ingest_agent` directly instead of using the `transfer_to_agent` mechanism).
- **Resolution:** Refactored `MemoryAgent` in `agent.py` to route HTTP endpoints directly to specialized Runners (Ingestion, Query, Consolidation). This bypassed orchestrator delegation completely, reducing LLM calls from 3 to 1 and speeding up ingestion from 70 seconds to under 15 seconds.
- **Issue (Session Namespace Mismatch):** Spawning separate runners caused a `SessionNotFoundError` because the session was created with the default `"memory_layer"` app name instead of matching the specific runner's app name.
- **Resolution:** Modified the session spawner to dynamically use `runner.app_name` when initializing sessions.

## 2026-07-21: Obsidian Plugin Packaging & OS Compatibility
- **Milestone:** Packaged the system as a native Obsidian Desktop plugin in `main.ts` with custom settings and a sidebar dashboard view.
- **Issue (Orphaned Python Subprocesses):** Windows virtual environment python shims (`.venv/Scripts/python.exe`) spawn a child interpreter. Standard Node `.kill()` commands only killed the parent shim, leaving the interpreter orphaned and locking port 8888.
- **Resolution:** Updated `stopBackend()` to run `taskkill /pid <PID> /f /t` on Windows, cleanly terminating the entire subprocess tree.
- **Issue (Port Binding Race Condition):** Re-launching the backend immediately after shutdown threw a `winerror 10048` socket error because process cleanup was running asynchronously.
- **Resolution:** Changed process termination from `spawn` to `spawnSync` to block and guarantee the port is released before a new backend starts.
- **Issue (Electron localhost Resolving):** Chromium/Electron attempts to connect to `localhost` over IPv6 loopback (`::1`) first. Because Python listens on IPv4 (`127.0.0.1`), requests failed.
- **Resolution:** Updated all HTTP requests in the plugin to point directly to `127.0.0.1`.
- **Issue (Query Method Mismatch):** The `/query` endpoint expected a GET request with query params, but the plugin was sending a POST.
- **Resolution:** Fixed the endpoint call in `main.ts` to use GET with query parameters and read the correct response key.
