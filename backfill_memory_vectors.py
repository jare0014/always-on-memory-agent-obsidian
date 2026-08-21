#!/usr/bin/env python3
"""
Backfill Vector Embeddings for Existing Memories in memory.db
Computes 384-dimensional dense vectors using local fastembed ONNX runtime.
"""

import os
import sys
import time
import sqlite3
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

DB_PATH = os.getenv("MEMORY_DB", str(SCRIPT_DIR / "memory.db"))
if not os.path.isabs(DB_PATH):
    DB_PATH = str(SCRIPT_DIR / DB_PATH)

def init_embedding_table(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memory_embeddings (
            memory_id INTEGER PRIMARY KEY,
            vector BLOB NOT NULL,
            model TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(memory_id) REFERENCES memories(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_embeddings_model ON memory_embeddings(model);
    """)
    conn.commit()

def backfill_embeddings(batch_size: int = 64):
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    from fastembed import TextEmbedding
    print("🧠 Loading local fastembed ONNX model (BAAI/bge-small-en-v1.5)...")
    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_embedding_table(conn)

    # Find memories without embeddings
    cursor = conn.cursor()
    unembedded = cursor.execute("""
        SELECT m.id, m.summary, m.raw_text 
        FROM memories m 
        LEFT JOIN memory_embeddings e ON m.id = e.memory_id 
        WHERE e.memory_id IS NULL
        ORDER BY m.id ASC
    """).fetchall()

    total = len(unembedded)
    print(f"📊 Found {total} memories needing dense vector embeddings.")
    if total == 0:
        print("✅ All memories are already indexed with embeddings!")
        conn.close()
        return

    t0 = time.time()
    processed = 0

    for i in range(0, total, batch_size):
        batch = unembedded[i : i + batch_size]
        texts = [f"{r['summary']} {r['raw_text'][:400]}" for r in batch]
        ids = [r["id"] for r in batch]

        embeddings = list(model.embed(texts))
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        insert_data = []
        for mem_id, emb in zip(ids, embeddings):
            vec = np.array(emb, dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            insert_data.append((mem_id, vec.tobytes(), "bge-small-en-v1.5", now))

        cursor.executemany("""
            INSERT OR REPLACE INTO memory_embeddings (memory_id, vector, model, updated_at)
            VALUES (?, ?, ?, ?)
        """, insert_data)
        conn.commit()

        processed += len(batch)
        elapsed = time.time() - t0
        rate = processed / elapsed if elapsed > 0 else 0
        print(f"  ⚡ Processed {processed}/{total} memories ({processed/total*100:.1f}%) — {rate:.1f} memories/sec")

    conn.close()
    print(f"\n🎉 Successfully backfilled {total} memories in {time.time() - t0:.2f}s!")

if __name__ == "__main__":
    backfill_embeddings()
