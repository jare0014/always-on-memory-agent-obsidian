# Case Study: Building a Local-First Always-On Memory Layer for Obsidian

## Executive Summary
This case study examines the engineering challenges, architectural decisions, and troubleshooting steps in building a local-first **Always-On Memory Agent** inside **Obsidian**. The system integrates a Python agent server (built on the Google Agent Development Kit (ADK)) with a native TypeScript Obsidian plugin, offering seamless transitions between cloud-hosted Google Gemini models and completely local Ollama models.

---

## Architectural Evolution

### Phase 1: The Multi-Agent Orchestrator
Initially, the agent utilized a central Orchestrator model to route incoming text, files, and queries to specialized sub-agents (`ingest_agent`, `consolidate_agent`, `query_agent`) using the ADK's native agent delegation:

```
[User Request] ──> [Orchestrator Agent] ──(transfer_to_agent)──> [Specialist Agent] ──> [DB Output]
```

#### The Local Model Problem
While hosted models (like Gemini 1.5 Pro) handled this routing hierarchy with ease, local 7B models (like `qwen2.5:7b` and `gemma3:4b`) frequently failed:
1. **Tool-Calling Loops:** Local models would repeatedly call storage functions in a loop, failing to recognize tool results in the conversation history as completed actions.
2. **Delegation Failures:** The models hallucinated the names of the sub-agents, trying to call `ingest_agent()` directly as a tool instead of utilizing the registered `transfer_to_agent()` function.

---

### Phase 2: Specialist Direct Runners
To achieve stability on consumer-grade local hardware, we bypassed the Orchestrator layer entirely, refactoring the Python API to map requests directly to specialized runners:

```
[Ingest HTTP Request]       ──> [Ingest Runner]      ──> [store_memory]       ──> [DB Output]
[Consolidate HTTP Request]  ──> [Consolidate Runner] ──> [store_consolidation] ──> [DB Output]
```

#### Key Improvements:
* **Latency Reduction:** Eliminated two intermediate LLM reasoning steps, cutting ingestion time down from **70+ seconds** to **under 15 seconds** per note on Qwen.
* **Database Guardrails:** Added SQLite checks to intercept and discard duplicate note summaries/consolidation IDs, mitigating any remaining LLM loop tendencies.

---

## Core Engineering & Operating System Challenges

### 1. Windows Process Tree Orphanage
**Problem:** In the Obsidian plugin, spawning python subprocesses using `.venv/Scripts/python.exe` on Windows resulted in a wrapper shim process launching a child interpreter process. Standard Node `.kill()` commands only killed the shim, leaving the interpreter running in the background and locking the HTTP port (error `winerror 10048`).

**Solution:** Updated the cleanup script to run `taskkill /pid <PID> /f /t` synchronously (`spawnSync`) on Windows, guaranteeing the entire process tree is terminated and the socket port released before spawning a new instance.

### 2. Electron IPv6 loopback Routing
**Problem:** Chromium/Electron (underneath Obsidian) resolves `localhost` to an IPv6 address (`::1`) first. When the Python server bound to the IPv4 address (`127.0.0.1`), Electron requests timed out with a connection refused error.

**Solution:** Forced all HTTP calls in the TypeScript plugin to point explicitly to `127.0.0.1`, bypassing IPv6 resolution.

### 3. Windows Asyncio Signal Handling
**Problem:** Python's standard `asyncio` event loop throws a `NotImplementedError` when attempting to register signals (`loop.add_signal_handler`) under Windows.

**Solution:** Wrapped signal handlers in check blocks, and refactored the loop termination block to cleanly cancel and await all active background tasks on shutdown to avoid "destroyed but pending" warnings.
