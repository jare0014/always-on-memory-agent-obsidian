# Always-On Memory Agent (Obsidian Edition)

An always-on personal memory and intelligence layer that runs continuously in the background, observing your Obsidian notes, extracting semantic insights, and building a structured SQLite database of knowledge.

Built using the **Google ADK (Agent Development Kit)** and packaged as a native Obsidian Desktop plugin.

---

## Features

* **Continuous Auto-Watch:** Monitors an inbox folder for new text, PDFs, images, or media files and immediately ingests them.
* **Specialist Agent Routing:** Directly schedules processing task workloads across specialist sub-agents (Ingestion, Query, and Consolidation) for maximum speed and execution reliability.
* **Obsidian Sidebar Dashboard:** A native Obsidian sidebar view showing statistics, recent memories, query boxes to ask questions of your database, and manual control over ingestion and consolidation.
* **Obsidian Settings UI:** Toggle between **Google Gemini (API-hosted)** or **Ollama (completely local)** backends directly from Obsidian's community plugin settings panel.
* **Forcible Subprocess Cleanup:** Built-in Windows-safe process tree termination that cleans up all Python processes (and virtualenv shims) upon disabling or reloading.
* **Vault Crawling:** Recursively index your entire vault safely with rate-limits and database state-tracking.

---

## Installation & Setup

### Prerequisites
- Python 3.10+
- Node.js (for compilation, if editing the plugin)

### Installation
1. **Initialize Backend Environment:**
   In your shell, navigate to this project folder and run:
   ```powershell
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **Enable the Obsidian Plugin:**
   - Move or copy the `always-on-memory-agent` folder inside your vault's `.obsidian/plugins/` directory.
   - Go to **Obsidian Settings** -> **Community Plugins** -> click **Reload**.
   - Toggle **Always-On Memory Agent** ON.
   - Configure the paths (Python executable and Agent directory) in the plugin settings.

---

## Architecture

The system consists of two primary components:
1. **Python Agent Server (`agent.py`):**
   - Uses `aiohttp` to expose endpoints (`/ingest`, `/query`, `/consolidate`, `/memories`, `/status`).
   - Uses **Google ADK** runners to execute specialist LLM prompts.
   - Stores structured text, summaries, importance scores, connections, and metadata in a local SQLite database (`memory.db`).
2. **Obsidian Desktop Plugin:**
   - A TypeScript plugin compiling to `main.js` and `styles.css`.
   - Uses Node's `child_process` to manage the lifecycle of the Python server.
   - Exposes a native user interface for settings and a sidebar pane.
