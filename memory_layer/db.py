import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from memory_layer.config import DB_PATH, log
from memory_layer.embeddings import embed_text_memory


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


def safe_json_loads(val, default=None):
    """Safely parse JSON values with fallback."""
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


def store_memory(
    raw_text: str,
    summary: str,
    entities: list[str],
    topics: list[str],
    importance: float,
    source: str = "",
) -> dict:
    """Store a processed memory in the database and generate its vector embedding."""
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


def store_consolidation(
    source_ids: list[int],
    summary: str,
    insight: str,
    connections: list[dict],
) -> dict:
    """Store a consolidation result and mark source memories as consolidated."""
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


def delete_memory(memory_id: int) -> dict:
    """Delete a memory by ID."""
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


def get_memory_stats() -> dict:
    """Get current memory statistics."""
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
