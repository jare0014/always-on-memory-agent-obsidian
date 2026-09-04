"""
Agent Memory Layer — Always-On ADK Agent

A lightweight, cost-effective background agent that continuously processes, consolidates, and serves memory. Runs 24/7 on Gemini 3.1 Flash-Lite.

Usage:
    python agent.py                          # watch ./inbox, serve on :8888
    python agent.py --watch ./docs --port 9000
    python agent.py --consolidate-every 15   # consolidate every 15 min

Query:
    curl "http://localhost:8888/query?q=what+do+you+know"
    curl -X POST http://localhost:8888/ingest -d '{"text": "some info"}'
"""

import argparse
import asyncio
import json
import logging
import mimetypes
import os
import shutil
import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from aiohttp import web
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# ─── Config ────────────────────────────────────────────────────

AGENT_DIR = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(AGENT_DIR / ".env")
except ImportError:
    pass

# ─── Model & Compute Routing Configuration ─────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "http://127.0.0.1:11434").strip()
if OLLAMA_API_BASE:
    os.environ["OLLAMA_API_BASE"] = OLLAMA_API_BASE

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "hybrid").lower()
LOCAL_DEFAULT = "litellm:ollama/qwen2.5:7b"
CLOUD_DEFAULT = "gemini-2.5-flash-lite"

LOCAL_MODEL = os.getenv("LOCAL_MODEL") or os.getenv("OLLAMA_MODEL") or LOCAL_DEFAULT
CLOUD_MODEL = os.getenv("CLOUD_MODEL") or os.getenv("GEMINI_MODEL") or CLOUD_DEFAULT

if LLM_PROVIDER == "hybrid":
    INGEST_MODEL = os.getenv("INGEST_MODEL", LOCAL_MODEL)
    CONSOLIDATE_MODEL = os.getenv("CONSOLIDATE_MODEL", LOCAL_MODEL)
    QUERY_MODEL = os.getenv("QUERY_MODEL", CLOUD_MODEL if GEMINI_API_KEY else LOCAL_MODEL)
elif LLM_PROVIDER == "gemini":
    INGEST_MODEL = os.getenv("INGEST_MODEL", CLOUD_MODEL)
    CONSOLIDATE_MODEL = os.getenv("CONSOLIDATE_MODEL", CLOUD_MODEL)
    QUERY_MODEL = os.getenv("QUERY_MODEL", CLOUD_MODEL)
else:  # ollama
    INGEST_MODEL = os.getenv("INGEST_MODEL", LOCAL_MODEL)
    CONSOLIDATE_MODEL = os.getenv("CONSOLIDATE_MODEL", LOCAL_MODEL)
    QUERY_MODEL = os.getenv("QUERY_MODEL", LOCAL_MODEL)

MODEL = QUERY_MODEL
DB_PATH = os.getenv("MEMORY_DB", str(AGENT_DIR / "memory.db"))
if not os.path.isabs(DB_PATH):
    DB_PATH = str(AGENT_DIR / DB_PATH)

_fastembed_model = None

def get_fastembed_model():
    global _fastembed_model
    if _fastembed_model is None:
        try:
            os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
            from fastembed import TextEmbedding
            _fastembed_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        except Exception as e:
            log.warning(f"⚠️ fastembed initialization warning: {e}")
            _fastembed_model = False
    return _fastembed_model

def embed_text_memory(text: str) -> np.ndarray | None:
    """Embed text using local fastembed (384-dim) or return None on failure."""
    model = get_fastembed_model()
    if model:
        try:
            embeddings = list(model.embed([text]))
            vec = np.array(embeddings[0], dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            return vec
        except Exception as e:
            log.warning(f"Embedding error: {e}")
    return None

# Supported file types for multimodal ingestion
TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".log", ".xml", ".yaml", ".yml"}
MEDIA_EXTENSIONS = {
    # Images
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    # Audio
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    # Video
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    # Documents
    ".pdf": "application/pdf",
}
ALL_SUPPORTED = TEXT_EXTENSIONS | set(MEDIA_EXTENSIONS.keys())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="[%H:%M]",
    stream=sys.stdout,
)
log = logging.getLogger("memory-agent")

# ─── Database ──────────────────────────────────────────────────


def init_db():
    """Initialize database schema, WAL mode, FTS5 virtual table, and indexes once on startup."""
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL;")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL DEFAULT '',
            raw_text TEXT NOT NULL,
            summary TEXT NOT NULL,
            entities TEXT NOT NULL DEFAULT '[]',
            topics TEXT NOT NULL DEFAULT '[]',
            connections TEXT NOT NULL DEFAULT '[]',
            importance REAL NOT NULL DEFAULT 0.5,
            created_at TEXT NOT NULL,
            consolidated INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS memory_embeddings (
            memory_id INTEGER PRIMARY KEY,
            vector BLOB NOT NULL,
            model TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(memory_id) REFERENCES memories(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS consolidations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_ids TEXT NOT NULL,
            summary TEXT NOT NULL,
            insight TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS processed_files (
            path TEXT PRIMARY KEY,
            processed_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_memories_topics ON memories(topics);
        CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_embeddings_model ON memory_embeddings(model);
    """)

    # Attempt to setup FTS5 table and triggers for full-text search
    try:
        db.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                summary,
                raw_text,
                content='memories',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, summary, raw_text) VALUES (new.id, new.summary, new.raw_text);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, summary, raw_text) VALUES('delete', old.id, old.summary, old.raw_text);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, summary, raw_text) VALUES('delete', old.id, old.summary, old.raw_text);
                INSERT INTO memories_fts(rowid, summary, raw_text) VALUES (new.id, new.summary, new.raw_text);
            END;
        """)
    except sqlite3.OperationalError as e:
        log.warning(f"⚠️ FTS5 indexing setup warning (falling back to LIKE queries): {e}")

    db.close()


def get_db() -> sqlite3.Connection:
    """Return a lightweight connection to the SQLite database without re-running DDL migrations."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db



# ─── ADK Tools ─────────────────────────────────────────────────


def store_memory(
    raw_text: str,
    summary: str,
    entities: list[str],
    topics: list[str],
    importance: float,
    source: str = "",
) -> dict:
    """Store a processed memory in the database and generate its vector embedding.

    Args:
        raw_text: The original input text.
        summary: A concise 1-2 sentence summary.
        entities: Key people, companies, products, or concepts.
        topics: 2-4 topic tags.
        importance: Float 0.0 to 1.0 indicating importance.
        source: Where this memory came from (filename, URL, etc).

    Returns:
        dict with memory_id and confirmation.
    """
    db = get_db()
    existing = db.execute("SELECT id FROM memories WHERE summary = ? OR raw_text = ?", (summary, raw_text)).fetchone()
    if existing:
        mid = existing["id"]
        db.close()
        log.info(f"📥 Memory #{mid} already stored (duplicate skipped): {summary[:60]}...")
        return {"memory_id": mid, "status": "already_stored", "summary": summary}

    now = datetime.now(timezone.utc).isoformat()
    cursor = db.execute(
        """INSERT INTO memories (source, raw_text, summary, entities, topics, importance, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (source, raw_text, summary, json.dumps(entities), json.dumps(topics), importance, now),
    )
    mid = cursor.lastrowid

    # Compute and store vector embedding
    vec = embed_text_memory(f"{summary} {raw_text[:500]}")
    if vec is not None:
        try:
            db.execute(
                "INSERT OR REPLACE INTO memory_embeddings (memory_id, vector, model, updated_at) VALUES (?, ?, ?, ?)",
                (mid, vec.tobytes(), "bge-small-en-v1.5", now),
            )
        except Exception as e:
            log.warning(f"Embedding storage failed for #{mid}: {e}")

    db.commit()
    db.close()
    log.info(f"📥 Stored memory #{mid} (with vector): {summary[:60]}...")
    return {"memory_id": mid, "status": "stored", "summary": summary}


def safe_json_loads(val, default=None):
    if default is None:
        default = []
    if val is None or val == "":
        return default
    if isinstance(val, (list, dict)):
        return val
    try:
        return json.loads(val)
    except Exception:
        if isinstance(val, str) and "," in val:
            return [x.strip() for x in val.split(",") if x.strip()]
        return default


def read_all_memories() -> dict:
    """Read all stored memories from the database, most recent first.

    Returns:
        dict with list of memories and count.
    """
    db = get_db()
    rows = db.execute("SELECT * FROM memories ORDER BY created_at DESC LIMIT 50").fetchall()
    memories = []
    for r in rows:
        memories.append({
            "id": r["id"], "source": r["source"], "summary": r["summary"],
            "entities": safe_json_loads(r["entities"]), "topics": safe_json_loads(r["topics"]),
            "importance": r["importance"], "connections": safe_json_loads(r["connections"]),
            "created_at": r["created_at"], "consolidated": bool(r["consolidated"]),
        })
    db.close()
    return {"memories": memories, "count": len(memories)}


def search_memories(query: str, limit: int = 20) -> dict:
    """Search stored memories using Hybrid Semantic Vector + FTS5 Full-Text Search.

    Args:
        query: The search keywords or phrases to look for.
        limit: Maximum number of relevant memories to return.

    Returns:
        dict with list of matching memories, similarity scores, and count.
    """
    db = get_db()
    query_clean = query.strip()
    if not query_clean:
        db.close()
        return read_all_memories()

    # 1. Vector Search
    vector_ranks = {}
    query_vec = embed_text_memory(query_clean)
    if query_vec is not None:
        try:
            rows = db.execute("SELECT memory_id, vector FROM memory_embeddings").fetchall()
            if rows:
                m_ids = [r["memory_id"] for r in rows]
                vec_list = [np.frombuffer(r["vector"], dtype=np.float32) for r in rows]
                matrix = np.array(vec_list, dtype=np.float32)
                scores = np.dot(matrix, query_vec)
                ranked_pairs = sorted(zip(m_ids, scores), key=lambda x: x[1], reverse=True)
                for rank, (m_id, sim) in enumerate(ranked_pairs[:100], 1):
                    vector_ranks[m_id] = (rank, float(sim))
        except Exception as e:
            log.warning(f"Vector search warning: {e}")

    # 2. FTS5 / Keyword Search
    fts_ranks = {}
    try:
        sql = """
            SELECT m.id, bm25(memories_fts) as rank_score FROM memories m
            JOIN memories_fts fts ON m.id = fts.rowid
            WHERE memories_fts MATCH ?
            ORDER BY rank_score ASC LIMIT 50
        """
        rows = db.execute(sql, (query_clean,)).fetchall()
        for rank, r in enumerate(rows, 1):
            fts_ranks[r["id"]] = rank
    except sqlite3.OperationalError:
        like_pattern = f"%{query_clean}%"
        sql = """
            SELECT id FROM memories
            WHERE summary LIKE ? OR topics LIKE ? OR raw_text LIKE ? OR source LIKE ?
            ORDER BY importance DESC, created_at DESC LIMIT 50
        """
        rows = db.execute(sql, (like_pattern, like_pattern, like_pattern, like_pattern)).fetchall()
        for rank, r in enumerate(rows, 1):
            fts_ranks[r["id"]] = rank

    # 3. Reciprocal Rank Fusion (RRF)
    all_candidate_ids = set(vector_ranks.keys()) | set(fts_ranks.keys())
    if not all_candidate_ids:
        db.close()
        return read_all_memories()

    rrf_scores = []
    for m_id in all_candidate_ids:
        rrf = 0.0
        sim_val = 0.0
        if m_id in vector_ranks:
            v_rank, sim_val = vector_ranks[m_id]
            rrf += 1.0 / (60.0 + v_rank)
        if m_id in fts_ranks:
            f_rank = fts_ranks[m_id]
            rrf += 1.0 / (60.0 + f_rank)
        rrf_scores.append((m_id, rrf, sim_val))

    rrf_scores.sort(key=lambda x: x[1], reverse=True)
    top_candidates = rrf_scores[:limit]
    top_ids = [c[0] for c in top_candidates]

    placeholders = ",".join("?" * len(top_ids))
    rows = db.execute(f"SELECT * FROM memories WHERE id IN ({placeholders})", top_ids).fetchall()
    row_map = {r["id"]: r for r in rows}

    memories = []
    for m_id, rrf, sim in top_candidates:
        if m_id in row_map:
            r = row_map[m_id]
            memories.append({
                "id": r["id"],
                "source": r["source"],
                "summary": r["summary"],
                "entities": safe_json_loads(r["entities"]),
                "topics": safe_json_loads(r["topics"]),
                "importance": r["importance"],
                "connections": safe_json_loads(r["connections"]),
                "created_at": r["created_at"],
                "consolidated": bool(r["consolidated"]),
                "similarity_score": round(sim, 4) if sim > 0 else None,
                "rrf_score": round(rrf, 5)
            })

    db.close()
    return {"query": query, "memories": memories, "count": len(memories)}



def read_unconsolidated_memories() -> dict:
    """Read memories that haven't been consolidated yet using Hybrid Thematic Vector Clustering
    with Chronological fallback.

    Returns:
        dict with list of unconsolidated memories, cluster type, and count.
    """
    db = get_db()
    # Pull candidate pool of unconsolidated memories (up to 50)
    rows = db.execute(
        "SELECT id, summary, raw_text, entities, topics, importance, created_at "
        "FROM memories WHERE consolidated = 0 ORDER BY created_at DESC LIMIT 50"
    ).fetchall()

    if not rows:
        db.close()
        return {"memories": [], "count": 0, "cluster_type": "none"}

    if len(rows) < 3:
        # If very few memories, return them directly
        memories = [{
            "id": r["id"], "summary": r["summary"],
            "entities": safe_json_loads(r["entities"]), "topics": safe_json_loads(r["topics"]),
            "importance": r["importance"], "created_at": r["created_at"],
        } for r in rows]
        db.close()
        return {"memories": memories, "count": len(memories), "cluster_type": "chronological"}

    # Attempt Thematic Vector Clustering
    m_ids = [r["id"] for r in rows]
    row_map = {r["id"]: r for r in rows}

    placeholders = ",".join("?" * len(m_ids))
    emb_rows = db.execute(
        f"SELECT memory_id, vector FROM memory_embeddings WHERE memory_id IN ({placeholders})",
        m_ids,
    ).fetchall()
    emb_dict = {r["memory_id"]: np.frombuffer(r["vector"], dtype=np.float32) for r in emb_rows}

    # If any unconsolidated memory lacks an embedding, compute it now
    missing_ids = [mid for mid in m_ids if mid not in emb_dict]
    if missing_ids:
        now = datetime.now(timezone.utc).isoformat()
        for mid in missing_ids:
            r = row_map[mid]
            vec = embed_text_memory(f"{r['summary']} {r['raw_text'][:500]}")
            if vec is not None:
                emb_dict[mid] = vec
                try:
                    db.execute(
                        "INSERT OR REPLACE INTO memory_embeddings (memory_id, vector, model, updated_at) VALUES (?, ?, ?, ?)",
                        (mid, vec.tobytes(), "bge-small-en-v1.5", now),
                    )
                except Exception:
                    pass
        db.commit()

    # Find the most cohesive thematic cluster
    best_cluster = []
    best_cluster_score = 0.0

    # Test each memory with an embedding as a potential cluster centroid
    available_ids = [mid for mid in m_ids if mid in emb_dict]
    if len(available_ids) >= 3:
        for seed_id in available_ids[:15]:  # check top 15 most recent candidates
            seed_vec = emb_dict[seed_id]
            scores = []
            for other_id in available_ids:
                if other_id == seed_id:
                    continue
                other_vec = emb_dict[other_id]
                sim = float(np.dot(seed_vec, other_vec))
                if sim >= 0.60:  # High semantic similarity threshold
                    scores.append((other_id, sim))

            # If we found at least 2 strong neighbors (forming cluster of >= 3)
            if len(scores) >= 2:
                scores.sort(key=lambda x: x[1], reverse=True)
                cluster_members = [seed_id] + [s[0] for s in scores[:7]]
                avg_sim = sum(s[1] for s in scores[:len(cluster_members) - 1]) / (len(cluster_members) - 1)
                cluster_score = avg_sim * (1.0 + 0.1 * len(cluster_members))
                if cluster_score > best_cluster_score:
                    best_cluster = cluster_members
                    best_cluster_score = cluster_score

    db.close()

    if best_cluster and len(best_cluster) >= 3:
        log.info(f"🧩 Thematic cluster identified ({len(best_cluster)} memories, score {best_cluster_score:.3f}): IDs {best_cluster}")
        cluster_rows = [row_map[mid] for mid in best_cluster if mid in row_map]
        memories = [{
            "id": r["id"], "summary": r["summary"],
            "entities": safe_json_loads(r["entities"]), "topics": safe_json_loads(r["topics"]),
            "importance": r["importance"], "created_at": r["created_at"],
        } for r in cluster_rows]
        return {
            "memories": memories,
            "count": len(memories),
            "cluster_type": "thematic",
            "cluster_score": round(best_cluster_score, 4)
        }

    # Fallback to chronological batching (top 10)
    chrono_rows = rows[:10]
    memories = [{
        "id": r["id"], "summary": r["summary"],
        "entities": safe_json_loads(r["entities"]), "topics": safe_json_loads(r["topics"]),
        "importance": r["importance"], "created_at": r["created_at"],
    } for r in chrono_rows]
    return {
        "memories": memories,
        "count": len(memories),
        "cluster_type": "chronological"
    }


def store_consolidation(
    source_ids: list[int],
    summary: str,
    insight: str,
    connections: list[dict],
) -> dict:
    """Store a consolidation result and mark source memories as consolidated.

    Args:
        source_ids: List of memory IDs that were consolidated.
        summary: A synthesized summary across all source memories.
        insight: One key pattern or insight discovered.
        connections: List of dicts with 'from_id', 'to_id', 'relationship'.

    Returns:
        dict with confirmation.
    """
    db = get_db()
    existing = db.execute("SELECT id FROM consolidations WHERE source_ids = ?", (json.dumps(source_ids),)).fetchone()
    if existing:
        db.close()
        log.info(f"🔄 Consolidation already exists for source_ids {source_ids}, skipping duplicate.")
        return {"status": "already_consolidated", "memories_processed": len(source_ids), "insight": insight}

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO consolidations (source_ids, summary, insight, created_at) VALUES (?, ?, ?, ?)",
        (json.dumps(source_ids), summary, insight, now),
    )
    for conn in connections:
        from_id, to_id = conn.get("from_id"), conn.get("to_id")
        rel = conn.get("relationship", "")
        if from_id and to_id:
            for mid in [from_id, to_id]:
                row = db.execute("SELECT connections FROM memories WHERE id = ?", (mid,)).fetchone()
                if row:
                    existing = safe_json_loads(row["connections"])
                    existing.append({"linked_to": to_id if mid == from_id else from_id, "relationship": rel})
                    db.execute("UPDATE memories SET connections = ? WHERE id = ?", (json.dumps(existing), mid))
    placeholders = ",".join("?" * len(source_ids))
    db.execute(f"UPDATE memories SET consolidated = 1 WHERE id IN ({placeholders})", source_ids)
    db.commit()
    db.close()
    log.info(f"🔄 Consolidated {len(source_ids)} memories. Insight: {insight[:80]}...")
    return {"status": "consolidated", "memories_processed": len(source_ids), "insight": insight}


def read_consolidation_history() -> dict:
    """Read past consolidation insights.

    Returns:
        dict with list of consolidation records.
    """
    db = get_db()
    rows = db.execute("SELECT * FROM consolidations ORDER BY created_at DESC LIMIT 10").fetchall()
    result = [{"summary": r["summary"], "insight": r["insight"], "source_ids": r["source_ids"]} for r in rows]
    db.close()
    return {"consolidations": result, "count": len(result)}


def get_memory_stats() -> dict:
    """Get current memory statistics.

    Returns:
        dict with counts of memories, consolidations, etc.
    """
    db = get_db()
    total = db.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
    unconsolidated = db.execute("SELECT COUNT(*) as c FROM memories WHERE consolidated = 0").fetchone()["c"]
    consolidations = db.execute("SELECT COUNT(*) as c FROM consolidations").fetchone()["c"]
    db.close()
    return {
        "total_memories": total,
        "unconsolidated": unconsolidated,
        "consolidations": consolidations,
    }


def read_all_memories(limit: int = 50) -> dict:
    """Reads stored memories from SQLite database for UI display."""
    db = get_db()
    rows = db.execute("SELECT id, raw_text, source, summary, topics, created_at FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    memories = []
    for r in rows:
        topics_val = r["topics"]
        if isinstance(topics_val, str):
            try:
                topics_list = json.loads(topics_val)
            except Exception:
                topics_list = [t.strip() for t in topics_val.split(",") if t.strip()]
        elif isinstance(topics_val, list):
            topics_list = topics_val
        else:
            topics_list = []
        
        memories.append({
            "id": r["id"],
            "raw_text": r["raw_text"],
            "source": r["source"],
            "summary": r["summary"],
            "topics": topics_list,
            "created_at": r["created_at"]
        })
    db.close()
    return {"memories": memories, "count": len(memories)}


def delete_memory(memory_id: int) -> dict:
    """Delete a memory by ID.

    Args:
        memory_id: The ID of the memory to delete.

    Returns:
        dict with status.
    """
    db = get_db()
    row = db.execute("SELECT 1 FROM memories WHERE id = ?", (memory_id,)).fetchone()
    if not row:
        db.close()
        return {"status": "not_found", "memory_id": memory_id}
    db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    db.commit()
    db.close()
    log.info(f"🗑️  Deleted memory #{memory_id}")
    return {"status": "deleted", "memory_id": memory_id}


def clear_all_memories(inbox_path: str | None = None) -> dict:
    """Delete all memories, consolidations, and inbox files. Full reset."""
    db = get_db()
    mem_count = db.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
    db.execute("DELETE FROM memories")
    db.execute("DELETE FROM consolidations")
    db.execute("DELETE FROM processed_files")
    db.commit()
    db.close()

    # Also clear the inbox folder so files aren't re-ingested
    files_deleted = 0
    if inbox_path:
        folder = Path(inbox_path)
        if folder.is_dir():
            for f in folder.iterdir():
                if f.name.startswith("."):
                    continue  # keep hidden files like .gitkeep
                try:
                    if f.is_file():
                        f.unlink()
                        files_deleted += 1
                    elif f.is_dir():
                        shutil.rmtree(f)
                        files_deleted += 1
                except OSError as e:
                    log.error(f"Failed to delete {f.name}: {e}")

    log.info(f"🗑️  Cleared all {mem_count} memories, deleted {files_deleted} inbox files")
    return {"status": "cleared", "memories_deleted": mem_count, "files_deleted": files_deleted}


# ─── ADK Agents ────────────────────────────────────────────────


def build_agents():
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


# ─── Agent Runner ──────────────────────────────────────────────


class MemoryAgent:
    def __init__(self):
        ingest_agent, consolidate_agent, query_agent, orchestrator = build_agents()
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
                    await self.session_service.delete_session(app_name=runner.app_name, user_id="agent", session_id=session.id)
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
            # Fallback to mimetypes module
            mime_type, _ = mimetypes.guess_type(str(file_path))
            mime_type = mime_type or "application/octet-stream"

        file_bytes = file_path.read_bytes()
        size_mb = len(file_bytes) / (1024 * 1024)

        # Gemini has a ~20MB inline limit; skip very large files
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
            raise e

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
        return f"Memory Stats:\nTotal Memories: {stats.get('total_memories')}\nPending Consolidation: {stats.get('unconsolidated')}\nConsolidations: {stats.get('consolidations')}"


# ─── File Watcher ──────────────────────────────────────────────


async def watch_folder(agent: MemoryAgent, folder: Path, poll_interval: int = 5):
    """Watch a folder for new files and ingest them (text, images, audio, video, PDFs)."""
    folder.mkdir(parents=True, exist_ok=True)
    log.info(f"👁️  Watching: {folder}/  (supports: text, images, audio, video, PDFs)")

    while True:
        try:
            db = get_db()
            try:
                for f in sorted(folder.iterdir()):
                    if f.name.startswith("."):
                        continue  # skip hidden files
                    suffix = f.suffix.lower()
                    if suffix not in ALL_SUPPORTED:
                        continue
                    row = db.execute("SELECT 1 FROM processed_files WHERE path = ?", (str(f),)).fetchone()
                    if row:
                        continue

                    try:
                        if suffix in TEXT_EXTENSIONS:
                            # Text-based files — read as string
                            log.info(f"📄 New text file: {f.name}")
                            text = f.read_text(encoding="utf-8", errors="replace")[:10000]
                            if text.strip():
                                await agent.ingest(text, source=f.name)
                        else:
                            # Media files — send as multimodal bytes
                            log.info(f"🖼️  New media file: {f.name}")
                            await agent.ingest_file(f)
                    except Exception as file_err:
                        log.error(f"Error ingesting {f.name}: {file_err}")

                    db.execute(
                        "INSERT INTO processed_files (path, processed_at) VALUES (?, ?)",
                        (str(f), datetime.now(timezone.utc).isoformat()),
                    )
                    db.commit()
            finally:
                db.close()
        except Exception as e:
            log.error(f"Watch error: {e}")

        await asyncio.sleep(poll_interval)



# ─── Consolidation Timer ──────────────────────────────────────


async def consolidation_loop(agent: MemoryAgent, interval_minutes: int = 30):
    """Run consolidation periodically, like sleep cycles."""
    log.info(f"🔄 Consolidation: every {interval_minutes} minutes")
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            db = get_db()
            count = db.execute("SELECT COUNT(*) as c FROM memories WHERE consolidated = 0").fetchone()["c"]
            db.close()
            if count >= 2:
                log.info(f"🔄 Running consolidation ({count} unconsolidated memories)...")
                result = await agent.consolidate()
                log.info(f"🔄 {result[:100]}")
            else:
                log.info(f"🔄 Skipping consolidation ({count} unconsolidated memories)")
        except Exception as e:
            log.error(f"Consolidation error: {e}")


# ─── HTTP API ──────────────────────────────────────────────────


def build_http(agent: MemoryAgent, watch_path: str = "./inbox"):
    @web.middleware
    async def cors_middleware(request, handler):
        if request.method == "OPTIONS":
            response = web.Response(status=204)
        else:
            response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, DELETE"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    app = web.Application(middlewares=[cors_middleware])

    async def handle_query(request: web.Request):
        q = request.query.get("q", "").strip()
        if not q:
            return web.json_response({"error": "missing ?q= parameter"}, status=400)
        try:
            answer = await agent.query(q)
            return web.json_response({"question": q, "answer": answer})
        except Exception as e:
            err_msg = str(e)
            log.error(f"Error handling query: {err_msg}")
            if "401" in err_msg or "UNAUTHENTICATED" in err_msg or "No API key" in err_msg:
                return web.json_response({
                    "error": "Gemini API key invalid or unauthenticated (401). Please enter your valid Gemini API key in Always-On Memory Agent settings in Obsidian."
                }, status=401)
            # Graceful search fallback instead of unhandled 500
            try:
                search_res = search_memories(q, limit=5)
                mems = search_res.get("memories", [])
                if mems:
                    fallback_text = f"**Search Excerpts for:** *{q}*\n\n"
                    for m in mems:
                        fallback_text += f"- **[Memory #{m['id']}]** (*{m.get('source', 'Vault')}*): {m.get('summary') or m.get('raw_text', '')[:200]}\n"
                    return web.json_response({"question": q, "answer": fallback_text, "fallback": True})
            except Exception:
                pass
            return web.json_response({"error": err_msg}, status=500)

    async def handle_ingest(request: web.Request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        text = data.get("text", "").strip()
        if not text:
            return web.json_response({"error": "missing 'text' field"}, status=400)
        source = data.get("source", "api")
        try:
            result = await agent.ingest(text, source=source)
            return web.json_response({"status": "ingested", "response": result})
        except Exception as e:
            log.error(f"Error handling ingest: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_consolidate(request: web.Request):
        try:
            result = await agent.consolidate()
            return web.json_response({"status": "done", "response": result})
        except Exception as e:
            log.error(f"Error handling consolidate: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_status(request: web.Request):
        stats = get_memory_stats()
        return web.json_response(stats)

    async def handle_memories(request: web.Request):
        data = read_all_memories()
        return web.json_response(data)

    async def handle_delete(request: web.Request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        memory_id = data.get("memory_id")
        if not memory_id:
            return web.json_response({"error": "missing 'memory_id' field"}, status=400)
        result = delete_memory(int(memory_id))
        return web.json_response(result)

    async def handle_semantic_query(request: web.Request):
        q = request.query.get("q", "").strip()
        top_k = int(request.query.get("top_k", 8))
        if not q:
            return web.json_response({"error": "missing ?q= parameter"}, status=400)
        try:
            results = search_memories(q, limit=top_k)
            return web.json_response(results)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_ping(request: web.Request):
        return web.json_response({"ok": True, "status": "healthy", "service": "always-on-memory-agent"})

    async def handle_clear(request: web.Request):
        result = clear_all_memories(inbox_path=watch_path)
        return web.json_response(result)

    app.router.add_get("/ping", handle_ping)
    app.router.add_get("/query", handle_query)
    app.router.add_get("/semantic-query", handle_semantic_query)
    app.router.add_post("/ingest", handle_ingest)
    app.router.add_post("/consolidate", handle_consolidate)
    app.router.add_get("/status", handle_status)
    app.router.add_get("/memories", handle_memories)
    app.router.add_post("/delete", handle_delete)
    app.router.add_post("/clear", handle_clear)

    return app


# ─── Main ──────────────────────────────────────────────────────


async def main_async(args):
    init_db()
    agent = MemoryAgent()

    log.info("🧠 Agent Memory Layer starting")
    log.info(f"   Model: {MODEL}")
    log.info(f"   Database: {DB_PATH}")
    log.info(f"   Watch: {args.watch}")
    log.info(f"   Consolidate: every {args.consolidate_every}m")
    log.info(f"   API: http://localhost:{args.port}")
    log.info("")


    # Start background tasks
    tasks = [
        asyncio.create_task(watch_folder(agent, Path(args.watch))),
        asyncio.create_task(consolidation_loop(agent, args.consolidate_every)),
    ]

    # Start HTTP server
    app = build_http(agent, watch_path=args.watch)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", args.port)
    await site.start()

    log.info(f"✅ Agent running. Drop files in {args.watch}/ or POST to http://localhost:{args.port}/ingest")
    log.info(f"   Supported: text, images, audio, video, PDFs")
    log.info("")

    # Wait forever
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()


def main():
    parser = argparse.ArgumentParser(description="Agent Memory Layer - Always-On ADK Agent")
    parser.add_argument("--watch", default="./inbox", help="Folder to watch for new files (default: ./inbox)")
    parser.add_argument("--port", type=int, default=8888, help="HTTP API port (default: 8888)")
    parser.add_argument("--consolidate-every", type=int, default=30, help="Consolidation interval in minutes (default: 30)")
    args = parser.parse_args()

    # Handle graceful shutdown
    loop = asyncio.new_event_loop()

    def shutdown(sig):
        log.info(f"\n👋 Shutting down (signal {sig})...")
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown, sig)
        except NotImplementedError:
            pass

    try:
        loop.run_until_complete(main_async(args))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
        log.info("🧠 Agent stopped.")


if __name__ == "__main__":
    main()
