# Portfolio Nugget: Always-On Memory Agent for Obsidian

A high-impact project showcase summarizing the engineering value, impact, and technology stack of the Always-On Memory Agent.

---

## The Pitch
An always-on personal knowledge graph and semantic memory layer that runs continuously in the background, observing Obsidian notes, extracting structural metadata, and consolidating knowledge into an SQLite database. It bridges the gap between high-performance cloud APIs (Google Gemini) and completely private local execution (Ollama Qwen/Gemma) within a native desktop interface.

---

## Key Stats & Impact
* **3x Performance Gain:** Refactored from a multi-agent orchestration architecture to direct specialist runners, reducing LLM API overhead and lowering ingestion time from 70s to 12s on local Qwen 7B.
* **100% Data Integrity:** Implemented database-level duplicate filtering and state tracking, preventing database bloating from LLM tool-calling loops.
* **Zero Terminal Overhead:** Integrated child process trees and port conflict resolution directly inside a TypeScript Obsidian plugin, spawning and cleaning up the Python backend server invisibly.
* **Cost-Efficient Ingestion:** Ingesting and consolidating a massive vault of 4,600+ markdown files costs **less than $4.00** using Gemini 2.5 Flash.

---

## Technical Stack & Skills
* **Backend:** Python, Google ADK (Agent Development Kit), LiteLLM, aiohttp, SQLite, asyncio, python-dotenv
* **Frontend:** TypeScript, Obsidian API, ESBuild, CSS, Node.js (`child_process`, `fs`)
* **AI Integration:** Google Gemini API, Ollama (Qwen 2.5, Gemma 3)
* **DevOps & Tooling:** Windows Subprocess Trees, process lifecycle, Git version control
