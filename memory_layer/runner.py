import mimetypes
from pathlib import Path

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from memory_layer.config import (
    QUERY_MODEL,
    LOCAL_MODEL,
    MEDIA_EXTENSIONS,
    log
)
from memory_layer.db import get_memory_stats
from memory_layer.search import search_memories
from memory_layer.adk_agents import build_agents


class MemoryAgent:
    def __init__(self):
        ingest_agent, consolidate_agent, query_agent, _ = build_agents()
        self.session_service = InMemorySessionService()

        self.ingest_runner = Runner(
            agent=ingest_agent,
            app_name="ingest_layer",
            session_service=self.session_service,
        )
        self.consolidate_runner = Runner(
            agent=consolidate_agent,
            app_name="consolidate_layer",
            session_service=self.session_service,
        )
        self.query_runner = Runner(
            agent=query_agent,
            app_name="query_layer",
            session_service=self.session_service,
        )

    async def run(self, message: str, runner: Runner) -> str:
        session = await self.session_service.create_session(
            app_name=runner.app_name, user_id="agent",
        )
        content = types.Content(role="user", parts=[types.Part.from_text(text=message)])
        return await self._execute(session, content, runner)

    async def run_multimodal(self, text: str, file_bytes: bytes, mime_type: str, runner: Runner) -> str:
        """Send a multimodal message with both text and a media file."""
        session = await self.session_service.create_session(
            app_name=runner.app_name, user_id="agent",
        )
        parts = [
            types.Part.from_text(text=text),
            types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
        ]
        content = types.Content(role="user", parts=parts)
        return await self._execute(session, content, runner)

    async def _execute(self, session, content: types.Content, runner: Runner) -> str:
        """Run the agent with the given content and return the text response."""
        response = ""
        try:
            async for event in runner.run_async(
                user_id="agent", session_id=session.id, new_message=content,
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            response += part.text
        finally:
            # Cleanup session to prevent unbounded memory growth in 24/7 operation
            try:
                if hasattr(self.session_service, "delete_session"):
                    await self.session_service.delete_session(
                        app_name=runner.app_name, user_id="agent", session_id=session.id
                    )
                elif hasattr(self.session_service, "_sessions") and isinstance(self.session_service._sessions, dict):
                    self.session_service._sessions.pop(session.id, None)
            except Exception:
                pass
        return response

    async def ingest(self, text: str, source: str = "") -> str:
        MAX_INGEST_CHARS = 40000
        if len(text) > MAX_INGEST_CHARS:
            log.info(f"✂️ Truncating note text for '{source}' from {len(text)} to {MAX_INGEST_CHARS} characters for indexing.")
            text = text[:MAX_INGEST_CHARS] + "\n\n[Content truncated for indexing size limits...]"
        msg = f"Remember this information (source: {source}):\n\n{text}" if source else f"Remember this information:\n\n{text}"
        return await self.run(msg, self.ingest_runner)

    async def ingest_file(self, file_path: Path) -> str:
        """Ingest a media file (image, audio, video, PDF) via multimodal."""
        suffix = file_path.suffix.lower()
        mime_type = MEDIA_EXTENSIONS.get(suffix)
        if not mime_type:
            mime_type, _ = mimetypes.guess_type(str(file_path))
            mime_type = mime_type or "application/octet-stream"

        file_bytes = file_path.read_bytes()
        size_mb = len(file_bytes) / (1024 * 1024)

        if size_mb > 20:
            log.warning(f"⚠️  Skipping {file_path.name} ({size_mb:.1f}MB) — exceeds 20MB limit")
            return f"Skipped: file too large ({size_mb:.1f}MB)"

        prompt = (
            f"Remember this file (source: {file_path.name}, type: {mime_type}).\n\n"
            f"Thoroughly analyze the content of this {mime_type.split('/')[0]} file and "
            f"extract all meaningful information for memory storage."
        )
        log.info(f"🔮 Ingesting {mime_type.split('/')[0]}: {file_path.name} ({size_mb:.1f}MB)")
        return await self.run_multimodal(prompt, file_bytes, mime_type, self.ingest_runner)

    async def consolidate(self) -> str:
        return await self.run("Consolidate unconsolidated memories. Find connections and patterns.", self.consolidate_runner)

    async def query(self, question: str) -> str:
        msg = f"Based on my memories, answer: {question}"
        try:
            res = await self.run(msg, self.query_runner)
            if res and res.strip() and res.strip() != "{}":
                return res
        except Exception as e:
            log.warning(f"⚠️ Primary query runner ({QUERY_MODEL}) failed: {e}")
            if QUERY_MODEL != LOCAL_MODEL:
                log.info(f"🔄 Falling back to local model: {LOCAL_MODEL}")
                try:
                    fallback_agent = Agent(
                        name="fallback_query_agent",
                        model=LOCAL_MODEL,
                        instruction=self.query_runner.agent.instruction,
                        tools=self.query_runner.agent.tools,
                    )
                    fallback_runner = Runner(
                        agent=fallback_agent,
                        app_name="fallback_query_layer",
                        session_service=self.session_service,
                    )
                    fallback_res = await self.run(msg, fallback_runner)
                    if fallback_res and fallback_res.strip() and fallback_res.strip() != "{}":
                        return fallback_res
                except Exception as fallback_err:
                    log.error(f"Fallback query runner failed: {fallback_err}")

        # If LLM returned empty or "{}" without text
        search_res = search_memories(question, limit=5)
        mems = search_res.get("memories", [])
        if mems:
            lines = [f"### 🧠 Memory Search Results: *{question}*\n"]
            for m in mems:
                lines.append(f"- **[Memory #{m['id']}]** (*{m.get('source', 'Vault')}*): {m.get('summary') or m.get('raw_text', '')[:200]}")
            return "\n".join(lines)
        return "I checked your memories, but found no relevant records for this question."

    async def status(self) -> str:
        stats = get_memory_stats()
        return (
            f"Memory Stats:\n"
            f"Total Memories: {stats.get('total_memories')}\n"
            f"Pending Consolidation: {stats.get('unconsolidated')}\n"
            f"Consolidations: {stats.get('consolidations')}"
        )
