import json
import sqlite3
from datetime import datetime, timezone
import numpy as np

from memory_layer.config import log
from memory_layer.embeddings import embed_text_memory
from memory_layer.db import get_db, safe_json_loads


def read_all_memories(limit: int = 50) -> dict:
    """Reads stored memories from SQLite database for UI display."""
    db = get_db()
    rows = db.execute(
        "SELECT id, raw_text, source, summary, topics, created_at, entities, connections, importance, consolidated "
        "FROM memories ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
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
            "created_at": r["created_at"],
            "entities": safe_json_loads(r["entities"]),
            "connections": safe_json_loads(r["connections"]),
            "importance": r["importance"],
            "consolidated": bool(r["consolidated"])
        })
    db.close()
    return {"memories": memories, "count": len(memories)}


def search_memories(query: str, limit: int = 20) -> dict:
    """Search stored memories using Hybrid Semantic Vector + FTS5 Full-Text Search with RRF."""
    db = get_db()
    query_clean = query.strip()
    if not query_clean:
        db.close()
        return read_all_memories(limit=limit)

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
        return read_all_memories(limit=limit)

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
    with Chronological fallback."""
    db = get_db()
    rows = db.execute(
        "SELECT id, summary, raw_text, entities, topics, importance, created_at "
        "FROM memories WHERE consolidated = 0 ORDER BY created_at DESC LIMIT 50"
    ).fetchall()

    if not rows:
        db.close()
        return {"memories": [], "count": 0, "cluster_type": "none"}

    if len(rows) < 3:
        memories = [{
            "id": r["id"], "summary": r["summary"],
            "entities": safe_json_loads(r["entities"]), "topics": safe_json_loads(r["topics"]),
            "importance": r["importance"], "created_at": r["created_at"],
        } for r in rows]
        db.close()
        return {"memories": memories, "count": len(memories), "cluster_type": "chronological"}

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

    best_cluster = []
    best_cluster_score = 0.0

    available_ids = [mid for mid in m_ids if mid in emb_dict]
    if len(available_ids) >= 3:
        for seed_id in available_ids[:15]:
            seed_vec = emb_dict[seed_id]
            scores = []
            for other_id in available_ids:
                if other_id == seed_id:
                    continue
                other_vec = emb_dict[other_id]
                sim = float(np.dot(seed_vec, other_vec))
                if sim >= 0.60:
                    scores.append((other_id, sim))

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


def read_consolidation_history() -> dict:
    """Read past consolidation insights."""
    db = get_db()
    rows = db.execute("SELECT * FROM consolidations ORDER BY created_at DESC LIMIT 10").fetchall()
    result = [{"summary": r["summary"], "insight": r["insight"], "source_ids": r["source_ids"]} for r in rows]
    db.close()
    return {"consolidations": result, "count": len(result)}
