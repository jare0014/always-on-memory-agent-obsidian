from google.adk.agents import Agent
from memory_layer.config import INGEST_MODEL, CONSOLIDATE_MODEL, QUERY_MODEL
from memory_layer.db import store_memory, store_consolidation, get_memory_stats
from memory_layer.search import (
    read_all_memories,
    search_memories,
    read_unconsolidated_memories,
    read_consolidation_history
)


def build_agents():
    """Build the 4 Google ADK agents: ingest, consolidate, query, and orchestrator."""
    ingest_agent = Agent(
        name="ingest_agent",
        model=INGEST_MODEL,
        description="Processes raw text or media into structured memory. Call this when new information arrives.",
        instruction=(
            "You are a Memory Ingest Agent. You handle ALL types of input — text, images,\n"
            "audio, video, and PDFs. For any input you receive:\n"
            "1. Thoroughly describe what the content contains\n"
            "2. Create a concise 1-2 sentence summary\n"
            "3. Extract key entities (people, companies, products, concepts, objects, locations)\n"
            "4. Assign 2-4 topic tags\n"
            "5. Rate importance from 0.0 to 1.0\n"
            "6. Call store_memory with all extracted information\n\n"
            "For images: describe the scene, objects, text, people, and any visual details.\n"
            "For audio/video: describe the spoken content, sounds, scenes, and key moments.\n"
            "For PDFs: extract and summarize the document content.\n\n"
            "Use the full description as raw_text in store_memory so the context is preserved.\n"
            "Always call store_memory. Be concise and accurate.\n"
            "CRITICAL: Call the store_memory tool EXACTLY ONCE. Do not call it repeatedly. Once you receive the tool response showing the memory has been stored, output a single confirmation sentence and finish."
        ),
        tools=[store_memory],
    )

    consolidate_agent = Agent(
        name="consolidate_agent",
        model=CONSOLIDATE_MODEL,
        description="Merges related memories and finds patterns. Call this periodically.",
        instruction=(
            "You are a Memory Consolidation Agent. You:\n"
            "1. Call read_unconsolidated_memories to see what needs processing (which automatically returns thematically clustered or chronological memories)\n"
            "2. If fewer than 2 memories, say nothing to consolidate\n"
            "3. Find connections and patterns across the memories\n"
            "4. Create a synthesized summary and one key insight\n"
            "5. Call store_consolidation with source_ids, summary, insight, and connections\n\n"
            "Connections: list of dicts with 'from_id', 'to_id', 'relationship' keys.\n"
            "Think deeply about cross-cutting patterns.\n"
            "CRITICAL: Call the store_consolidation tool EXACTLY ONCE. Do not call it repeatedly. Once you receive the tool response showing consolidation was stored, stop and finish."
        ),
        tools=[read_unconsolidated_memories, store_consolidation],
    )

    query_agent = Agent(
        name="query_agent",
        model=QUERY_MODEL,
        description="Answers questions using stored memories.",
        instruction=(
            "You are a Memory Query Agent. When asked a question:\n"
            "1. Call search_memories with relevant keywords to locate target memories\n"
            "2. If search_memories returns empty or for broad queries, call read_all_memories\n"
            "3. Call read_consolidation_history for higher-level insights\n"
            "4. Synthesize a clean, human-readable answer in Markdown based ONLY on stored memories\n"
            "5. Reference memory IDs: [Memory #1101], [Memory #1102], etc.\n"
            "6. If no relevant memories exist, say so honestly\n\n"
            "CRITICAL FORMATTING RULE: Synthesize an articulated Markdown answer with bullet points and bold titles. NEVER output raw JSON objects, stringified JSON dicts, or unformatted data structures."
        ),
        tools=[search_memories, read_all_memories, read_consolidation_history],
    )

    orchestrator = Agent(
        name="memory_orchestrator",
        model=QUERY_MODEL,
        description="Routes memory operations to specialist agents.",
        instruction=(
            "You are the Memory Orchestrator for an always-on memory system.\n"
            "Route requests to the right sub-agent:\n"
            "- New information -> ingest_agent\n"
            "- Consolidation request -> consolidate_agent\n"
            "- Questions -> query_agent\n"
            "- Status check -> call get_memory_stats and report\n\n"
            "After the sub-agent completes, summarize their findings in clean human-readable Markdown. Never pass raw JSON tool dumps to the final user."
        ),
        sub_agents=[ingest_agent, consolidate_agent, query_agent],
        tools=[get_memory_stats],
    )

    return ingest_agent, consolidate_agent, query_agent, orchestrator
